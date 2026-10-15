"""Synthetic preview only; all decoder/tool calls mocked, no external OCR/network."""
import asyncio
import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from starlette.datastructures import URL

from app.services import document_extraction as engine, ledger_document as parser
from app.services import ledger_document_import as importer

# Public fictional digit patterns; never copied from a user screenshot.
BANK = '''은행 입출금 거래내역
현재 잔액 11,000,000원
2026.10.14
합성거래처
09:10
+1,234,567원
거래 후 잔액 11,234,567원
합성마트
10:20
-234,567원
잔액 11,000,000원
'''
CARD = '''카드 이용내역
총 사용금액 35,801원
2026-10-14
합성카페
승인금액 12,345원
합성마트 취소
승인금액 23,456원
'''


def page(text, number=1, method='text'):
    return {'page': number, 'text': text, 'method': method}


def tsv(text, confidence=95):
    header = 'level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n'
    rows = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for word_number, word in enumerate(line.split(), 1):
            rows.append(f'5\t1\t1\t1\t{line_number}\t{word_number}\t10\t{line_number*30}\t80\t25\t{confidence}\t{word}')
    return header + '\n'.join(rows)


def test_bank_headers_signs_balance_and_no_owner_inference():
    result = parser.parse_pages([page(BANK)])
    assert len(result['rows']) == 2
    first, second = result['rows']
    assert (first['amount'], first['direction'], first['balance_after']) == ('1234567', 'inflow', '11234567')
    assert (second['amount'], second['direction']) == ('234567', 'outflow')
    assert first['transaction_date'] == '2026-10-14' and first['transaction_time'] == '09:10'
    assert first['counterparty'] == '합성거래처'
    assert all(row['owner'] is None and row['account_id'] is None and row['review_status'] == 'review_required' for row in result['rows'])
    assert '현재 잔액' not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize('marker', ['10 월 14 일', '10월 14 일', '10 월 14일'])
def test_native_ocr_unit_spacing_keeps_year_unknown(marker):
    text = f'은행 입출금 거래내역\n현재 잔액 11,000,000 원\n{marker}\n합성거래처\n+1,234,567 원\n거래 후 잔액 11,234,567 원'
    result = parser.parse_pages([page(tsv(text), method='ocr_tsv')])
    assert result['document_type'] == 'bank_transactions'
    assert result['status'] == 'review_required' and len(result['rows']) == 1
    row = result['rows'][0]
    assert row['transaction_date'] is None
    assert row['transaction_date_parts'] == {'year': None, 'month': 10, 'day': 14}
    assert (row['amount'], row['direction'], row['balance_after']) == ('1234567', 'inflow', '11234567')
    assert row['owner'] is None and row['account_id'] is None
    assert 'year_missing' in row['review_reasons']
    assert not parser.needs_ocr(text)


def test_native_ocr_split_hangul_party_is_not_reconstructed():
    text = '은행 입출금 거래내역\n10월 14일\n가 상 입 금 처\n+1,234,567 원'
    row = parser.parse_pages([page(tsv(text), method='ocr_tsv')])['rows'][0]
    assert row['counterparty'] is None
    assert 'party_unverified' in row['review_reasons']
    assert row['review_status'] == 'review_required'
    assert row['owner'] is None and row['account_id'] is None


@pytest.mark.parametrize('marker', ['10 월 32 일', '13 월 14 일', '2 월 30 일',
    '합계 10 월 14 일', '10 월 14 일 기준금액', '110 월 14 일'])
def test_spaced_date_does_not_authorize_unrelated_or_impossible_document(marker):
    result = parser.parse_pages([page(f'은행 입출금 거래내역\n{marker}\n합성거래처\n+1,234,567 원')])
    if result['rows']:
        row = result['rows'][0]
        assert row['transaction_date'] is None
        assert row['transaction_date_parts'] == {'year': None, 'month': None, 'day': None}
        assert 'date_invalid' in row['review_reasons']
    else:
        assert result['document_type'] == 'unknown'


@pytest.mark.parametrize('token', ['-234, 5672원', '-234, 5672', '++1,234,567 원',
    '+-1,234,567 원', '−234,567 원', '1,234,567 원'])
def test_native_damaged_digits_and_unverified_sign_never_become_signed_cashflow(token):
    result = parser.parse_pages([page(f'은행 입출금 거래내역\n10월 14일\n합성거래처\n{token}')])
    assert all(row['direction'] == 'unknown' for row in result['rows'])
    if token != '1,234,567 원':
        assert all(row['amount'] is None for row in result['rows'])


@pytest.mark.parametrize('kind', ['auto', 'bank_transactions', 'card_transactions'])
def test_native_spaced_date_alone_cannot_promote_unrelated_document(kind):
    result = parser.parse_pages([page('자료 요약\n10 월 14 일\n+1,234,567 원')], kind)
    assert result['document_type'] == 'unknown' and result['rows'] == []


def test_native_structural_evidence_explains_date_gate_without_raw_text():
    pages = [page(tsv('은행 입출금 거래내역\n10 월 14 일\n합성거래처\n+1,234,567 원'), method='ocr_tsv')]
    evidence = parser.classification_evidence(pages)
    assert evidence == {'date': True, 'money': True, 'bank_header': True,
                        'card_header': False, 'tsv_lines': True}
    assert all(type(value) is bool for value in evidence.values())


def test_card_total_excluded_and_cancellation_remains_candidate():
    result = parser.parse_pages([page(CARD)])
    assert len(result['rows']) == 2
    assert result['rows'][0]['merchant'] == '합성카페'
    assert result['rows'][0]['transaction_type_candidate'] == 'card_approval_candidate'
    assert result['rows'][1]['transaction_type_candidate'] == 'card_cancellation'
    assert all(row['direction'] == 'unknown' and row['review_status'] == 'review_required' for row in result['rows'])


@pytest.mark.parametrize('token', ['1,00', '1,234,5?', '1.000', 'O000'])
def test_unclear_digits_are_not_corrected(token):
    row = parser.parse_pages([page(f'은행 입출금\n2026-10-14\n합성거래처\n+{token}원')])['rows'][0]
    assert row['amount'] is None and row['direction'] == 'unknown'
    assert row['warnings']


def test_unsigned_clipped_page_boundary_and_duplicates_require_review():
    result = parser.parse_pages([page('은행 입출금\n2026-10-14\n합성가게\n1000원'),
                                 page('합성가게\n+1000원\n합성가게\n+1000원', 2)])
    assert result['rows'][0]['direction'] == 'unknown'
    assert result['rows'][1]['transaction_date'] is None
    assert result['rows'][2]['warnings']
    assert len(result['rows']) == 3  # Never silently discard duplicate-looking rows.


def test_ocr_confidence_and_coordinates_not_accuracy_claim():
    high = parser.parse_pages([page(tsv(BANK), method='ocr_tsv')])['rows'][0]
    low = parser.parse_pages([page(tsv(BANK, 35), method='ocr_tsv')])['rows'][0]
    assert high['source_location']['bbox'] and high['review_status'] == 'review_required'
    assert low['amount'] is None and low['transaction_date'] is None


def test_unknown_document_and_privacy_labels():
    assert parser.parse_pages([page('종류 미확인\n2026-10-14\n+1000원')])['rows'] == []
    result = parser.parse_pages([page(BANK + '\n계좌번호 123-456-789012\n고객명 합성개인정보')])
    encoded = json.dumps(result, ensure_ascii=False)
    assert '123-456-789012' not in encoded and '합성개인정보' not in encoded


@pytest.mark.parametrize('kind,format,bg', [('png','PNG','black'), ('jpeg','JPEG','white')])
def test_mock_image_decoder_dark_bank_white_card(tmp_path, kind, format, bg):
    from PIL import Image
    path = tmp_path / ('synthetic.' + kind)
    Image.new('RGB', (800,600), bg).save(path, format=format)
    calls = []
    def run(args, timeout=12):
        calls.append(args)
        if args[-1] == '0':
            raise subprocess.CalledProcessError(1, args)
        return tsv(BANK if bg == 'black' else CARD).encode()
    pages = engine.extract_pages(path, kind, run=run, needs_ocr=parser.needs_ocr, tsv=True)
    assert len(parser.parse_pages(pages)['rows']) == 2
    assert any(args[-1] == 'tsv' and 'kor+eng' in args for args in calls)


@pytest.mark.parametrize('scanned_pages', [set(), {1,2}, {2}])
def test_text_scanned_and_mixed_pdf(tmp_path, scanned_pages):
    from PIL import Image
    path = tmp_path / 'synthetic.pdf'; path.write_bytes(b'%PDF-synthetic')
    calls = []
    def run(args, timeout=12):
        calls.append(args)
        if args[0] == 'pdfinfo': return b'Pages: 2\nEncrypted: no\n'
        if args[0] == 'pdftotext':
            number = int(args[args.index('-f')+1])
            Path(args[-1]).write_text('' if number in scanned_pages else BANK, encoding='utf-8'); return b''
        if args[0] == 'pdftoppm': Image.new('RGB',(800,600),'white').save(args[-1]+'.png'); return b''
        if args[-1] == '0': raise subprocess.CalledProcessError(1,args)
        return tsv(BANK).encode()
    pages = engine.extract_pages(path,'pdf',run=run,needs_ocr=parser.needs_ocr,tsv=True)
    assert [p['method'] for p in pages] == ['ocr_tsv' if n in scanned_pages else 'text' for n in (1,2)]
    assert len(parser.parse_pages(pages)['rows']) == 4


def test_latin_numeric_pdf_policy_is_not_hangul_count():
    assert not parser.needs_ocr('2026-10-14\nSYNTHETIC SHOP\n+1,000원')
    assert parser.needs_ocr('broken \ufffd')


@pytest.mark.parametrize('info', [b'Pages: 9\nEncrypted: no', b'Pages: 1\nEncrypted: yes', b'broken'])
def test_pdf_limits(tmp_path, info):
    with pytest.raises(ValueError):
        engine.extract_pages(tmp_path/'x.pdf','pdf',run=lambda *args: info,needs_ocr=parser.needs_ocr)


def test_corrupt_image_and_multiframe_rejected(tmp_path):
    from PIL import Image
    bad = tmp_path/'bad.png'; bad.write_bytes(b'\x89PNG\r\n\x1a\ninvalid')
    with pytest.raises(OSError): engine.extract_pages(bad,'png',needs_ocr=parser.needs_ocr)
    frames = tmp_path/'animated.png'
    Image.new('RGB',(10,10),'white').save(frames,save_all=True,append_images=[Image.new('RGB',(10,10),'black')])
    with pytest.raises(ValueError): engine.extract_pages(frames,'png',needs_ocr=parser.needs_ocr)


def test_oversized_pixels_rejected(tmp_path):
    from PIL import Image
    path=tmp_path/'large.png';Image.new('1',(4100,4100)).save(path)
    with pytest.warns(Image.DecompressionBombWarning), pytest.raises(ValueError):
        engine.extract_pages(path,'png',needs_ocr=parser.needs_ocr)


@pytest.mark.parametrize('data,mime', [(b'', 'image/png'), (b'x','image/png'),
    (b'%PDF-x','image/jpeg'), (b'x'*(engine.MAX_BYTES+1),'application/pdf')],
    ids=['empty','bad-magic','mime-mismatch','oversized'])
def test_upload_limits(data,mime):
    with pytest.raises(ValueError): importer.preview(data,mime)


def fake_worker(monkeypatch, output=None):
    paths=[]
    class Worker:
        returncode=0; pid=987654
        def __init__(self,args,**kwargs):
            path=Path(args[-3]);paths.append(path)
            assert path.is_file() and kwargs['stderr'] is subprocess.DEVNULL
            if os.name=='posix':
                assert path.stat().st_mode & 0o777 == 0o600
                assert path.parent.stat().st_mode & 0o777 == 0o700
        def communicate(self,timeout=None):
            return json.dumps(output or parser.parse_pages([page(BANK)])).encode(),None
        def kill(self): pass
    monkeypatch.setattr(importer.subprocess,'Popen',Worker)
    return paths


def test_preview_cleanup_no_financial_write_no_user_directory(tmp_path,monkeypatch,capsys):
    from app.services import ledger, portfolio, user_manager, national_pension_import
    monkeypatch.setattr(user_manager,'USERS_DIR',tmp_path/'absent-users')
    def forbidden(*args,**kwargs): pytest.fail('Preview must not touch financial storage')
    for name in ('add_transaction','import_ledger_from_file_bytes','write_ledger','get_ledger_path'):
        monkeypatch.setattr(ledger,name,forbidden)
    monkeypatch.setattr(portfolio,'write_portfolio',forbidden)
    paths=fake_worker(monkeypatch)
    assert importer.preview(b'%PDF-synthetic','application/pdf')['rows']
    assert not (tmp_path/'absent-users').exists()
    assert not paths[0].parent.exists()
    assert capsys.readouterr()==('', '')
    assert national_pension_import._slots is engine.DECODE_SLOTS


def test_worker_spawn_failure_is_safe_and_releases_budget(monkeypatch):
    monkeypatch.setattr(importer.subprocess,'Popen',Mock(side_effect=OSError('PRIVATE INPUT MUST NOT ESCAPE')))
    with pytest.raises(ValueError) as error: importer.preview(b'%PDF-x','application/pdf')
    assert 'PRIVATE' not in str(error.value)
    assert engine.DECODE_SLOTS.acquire(False);engine.DECODE_SLOTS.release()


def test_timeout_reaps_worker_and_removes_temp(monkeypatch):
    paths=[]
    class Worker:
        returncode=0;pid=987654
        def __init__(self,args,**kwargs): paths.append(Path(args[-3]));self.calls=0
        def communicate(self,timeout=None):
            self.calls+=1
            if self.calls==1:raise subprocess.TimeoutExpired('worker',75)
            return b'',None
        def kill(self): self.killed=True
    monkeypatch.setattr(importer.subprocess,'Popen',Worker)
    kill=Mock();monkeypatch.setattr(importer.os,'killpg',kill,raising=False)
    with pytest.raises(ValueError,match='초과'): importer.preview(b'%PDF-x','application/pdf')
    assert paths and not paths[-1].parent.exists()
    if os.name=='posix':kill.assert_called_once()


def test_concurrency_budget_denies_excess_request(monkeypatch):
    monkeypatch.setattr(importer,'DECODE_SLOTS',threading.BoundedSemaphore(0))
    spawn=Mock();monkeypatch.setattr(importer.subprocess,'Popen',spawn)
    with pytest.raises(ValueError,match='진행 중'):importer.preview(b'%PDF-x','application/pdf')
    spawn.assert_not_called()


class Request:
    def __init__(self,data=b'%PDF-synthetic',username='synthetic-alice',origin='http://testserver'):
        self.state=SimpleNamespace(username=username);self.url=URL('http://testserver/api/ledger/document-import/preview')
        self.headers={'content-type':'application/pdf','origin':origin};self.data=data;self.consumed=False
    async def stream(self): self.consumed=True;yield self.data


def test_api_auth_origin_limits_and_no_store(monkeypatch,tmp_path):
    from regression_support import import_main_without_loading_real_env
    main=import_main_without_loading_real_env()
    fake_worker(monkeypatch)
    result=asyncio.run(main.preview_ledger_document(Request(), 'auto'))
    assert result.headers['cache-control']=='no-store'
    assert json.loads(result.body)['rows']
    for request,code in ((Request(username=None),401),(Request(origin='https://foreign.invalid'),403),
                         (Request(data=b'x'*(engine.MAX_BYTES+1)),413)):
        with pytest.raises(HTTPException) as error: asyncio.run(main.preview_ledger_document(request,'auto'))
        assert error.value.status_code==code
        if code!=413: assert not request.consumed


def test_api_user_requests_have_no_shared_preview_state(monkeypatch):
    from regression_support import import_main_without_loading_real_env
    main=import_main_without_loading_real_env()
    decode=Mock(side_effect=[{'document_type':'bank_transactions','status':'review_required','rows':[], 'warnings':['synthetic-A']},
                            {'document_type':'card_transactions','status':'review_required','rows':[], 'warnings':['synthetic-B']}])
    monkeypatch.setattr(importer,'preview',decode)
    a=asyncio.run(main.preview_ledger_document(Request(username='alice'),'auto'))
    b=asyncio.run(main.preview_ledger_document(Request(username='bob'),'auto'))
    assert json.loads(a.body)['warnings']==['synthetic-A']
    assert json.loads(b.body)['warnings']==['synthetic-B']
    assert 'alice' not in a.body.decode() and 'bob' not in b.body.decode()


def partial_bank(header=''):
    return ('은행 입출금 거래내역\n' + header + '\n현재 잔액 11,000,000원\n'
            '10월 14일\n합성송금처 이체\n09:10\n+1,234,567원\n잔액 11,234,567원\n'
            '10월 13일\n합성매장\n10:20\n-234,567원\n거래 후 잔액 11,000,000원')


def geometry_tsv(text, *, width=800, height=1800, glyph_height=25, clipped_line=None):
    """Synthetic geometry only; no screenshots, real fonts or account identities."""
    records = tsv(text).splitlines()
    records.insert(1, f'1\t1\t0\t0\t0\t0\t0\t0\t{width}\t{height}\t-1\t')
    for index in range(2, len(records)):
        fields = records[index].split('\t')
        fields[7] = str(int(fields[4])*30)
        fields[9] = str(glyph_height)
        if int(fields[4]) == clipped_line:
            fields[6] = str(width-80)  # A word touches the right edge.
        records[index] = '\t'.join(fields)
    return '\n'.join(records)


def positioned_tsv(lines, confidence=95):
    """Public synthetic TSV with disjoint, page-local line and word bounds."""
    records = ['level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext',
               '1\t1\t0\t0\t0\t0\t0\t0\t1800\t2000\t-1\t']
    for number, text in enumerate(lines, 1):
        x = 100
        for word_number, word in enumerate(text.split(), 1):
            width = max(25, len(word)*25)
            records.append(f'5\t1\t1\t1\t{number}\t{word_number}\t{x}\t{100+number*100}\t{width}\t40\t{confidence}\t{word}')
            x += width + 12
    return '\n'.join(records)


def crop_tsv(args, text, confidence=95, txt=None):
    from PIL import Image
    with Image.open(args[1]) as image:
        width, height = image.size
    header = positioned_tsv([]).splitlines()[0]
    rows = [header, f'1\t1\t0\t0\t0\t0\t0\t0\t{width}\t{height}\t-1\t']
    lines = text.splitlines() or ['']
    line_height = (height-16)//len(lines)
    for index,line in enumerate(lines,1):
        # Actual word-level TSV: split Korean syllables stay separate records.
        words=line.split() or ['']; step=(width-16)//len(words)
        for number,word in enumerate(words,1):
            rows.append(f'5\t1\t1\t1\t{index}\t{number}\t{8+(number-1)*step}\t{8+(index-1)*line_height}\t{step-2}\t{line_height-2}\t{confidence}\t{word}')
    data='\n'.join(rows).encode()
    assert args[-4:]==['--psm','7','txt','tsv'] and args[2]!='stdout'
    base=Path(args[2])
    assert base.parent==Path(args[1]).parent and base.name.startswith('line-')
    Path(str(base)+'.txt').write_text((text if txt is None else txt)+'\n',encoding='utf-8')
    Path(str(base)+'.tsv').write_bytes(data)
    return b''


@pytest.mark.parametrize('party', ['가상입금처','가상출금처'])
def test_same_ocr_txt_preserves_party_while_tsv_has_syllable_words(tmp_path,party):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    fragmented=' '.join(party)
    source=positioned_tsv([fragmented])
    assert parser.lines_for_page(page(source,method='ocr_tsv'))[0]['text']==fragmented
    def run(args,timeout):
        return crop_tsv(args,fragmented,txt=party)
    lines=parser.LineRecognizer().refine(source,image,run)
    assert lines[0]['text']==party and not parser.unsafe_line(lines[0])
    assert not list(tmp_path.glob('line-*'))


@pytest.mark.parametrize('txt,tsv_text', [
    ('합성 마트 본점','합 성 마 트 본 점'),
    ('가상 카페','가 상 카 페'),
])
def test_txt_spaces_are_engine_evidence_not_tsv_joining(tmp_path,txt,tsv_text):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    lines=parser.LineRecognizer().refine(positioned_tsv([tsv_text]),image,
        lambda args,timeout:crop_tsv(args,tsv_text,txt=txt))
    assert lines[0]['text']==txt and not parser.unsafe_line(lines[0])


@pytest.mark.parametrize('txt,tsv_text', [
    ('','가 상 입 금 처'), ('가상입금처\n가상출금처','가 상 입 금 처'),
    ('가상출금처','가 상 입 금 처'), ('가상123카페','가상123카페'),
    ('+1000 원','+1000 원'), ('가상?카페','가상?카페'), ('가상□카페','가상□카페'),
    ('가상�카페','가상�카페'), ('가상\x00카페','가상\x00카페'),
    ('가상\t카페','가상 카페'), ('가 상 입 금 처','가 상 입 금 처'),
    ('총 사용금액','총 사용금액'),
])
def test_unclear_or_contradictory_txt_is_not_a_party(tmp_path,capsys,txt,tsv_text):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    original='가 상 입 금 처'
    lines=parser.LineRecognizer().refine(positioned_tsv([original]),image,
        lambda args,timeout:crop_tsv(args,tsv_text,txt=txt))
    assert lines[0]['text']==original and 'ocr_line_conflict' in lines[0]['reasons']
    assert parser.unsafe_line(lines[0]) and not list(tmp_path.glob('line-*'))
    assert capsys.readouterr()==('', '')


@pytest.mark.parametrize('txt,tsv_text', [('+1001 원','+1000 원'),
    ('-1000 원','+1000 원'), ('+1,000 원','+1, 000 원'), ('+1000 원','+1,000 원')])
def test_txt_tsv_numeric_conflict_stays_unknown(tmp_path,txt,tsv_text):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    original='+1000 원'
    lines=parser.LineRecognizer().refine(positioned_tsv([original]),image,
        lambda args,timeout:crop_tsv(args,tsv_text,txt=txt))
    assert lines[0]['text']==original and 'ocr_line_conflict' in lines[0]['reasons']
    assert parser.unsafe_line(lines[0])


@pytest.mark.parametrize('fault', ['missing-txt','missing-tsv','invalid-txt','invalid-tsv',
    'invalid-header','large-txt','large-tsv','partial-timeout','partial-tool-error'])
def test_paired_ocr_file_failures_are_bounded_private_and_cleaned(tmp_path,capsys,fault):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    def run(args,timeout):
        crop_tsv(args,'가 상 입 금 처',txt='가상입금처')
        txt=Path(args[2]+'.txt');tsv=Path(args[2]+'.tsv')
        if fault=='missing-txt':txt.unlink()
        elif fault=='missing-tsv':tsv.unlink()
        elif fault=='invalid-txt':txt.write_bytes(b'\xff')
        elif fault=='invalid-tsv':tsv.write_bytes(b'\xff')
        elif fault=='invalid-header':tsv.write_text('wrong\tcolumns\n',encoding='utf-8')
        elif fault=='large-txt':txt.write_bytes(b'x'*20_001)
        elif fault=='large-tsv':tsv.write_bytes(b'x'*20_001)
        elif fault=='partial-timeout':raise subprocess.TimeoutExpired(args,timeout)
        else:raise subprocess.CalledProcessError(1,args)
        return b''
    with pytest.raises((ValueError,subprocess.SubprocessError)):
        parser.LineRecognizer().refine(positioned_tsv(['가 상 입 금 처']),image,run)
    assert not list(tmp_path.glob('line-*')) and capsys.readouterr()==('', '')


def test_line_output_reader_private_permissions_and_no_symlink_following(tmp_path):
    output=tmp_path/'synthetic.txt';output.write_bytes('가상 카페'.encode())
    assert parser.read_line_output(output)=='가상 카페'
    if os.name=='posix':assert output.stat().st_mode & 0o777==0o600
    link=Mock();link.is_symlink.return_value=True
    with pytest.raises(ValueError,match='missing or invalid'):parser.read_line_output(link)
    link.is_file.assert_not_called();link.open.assert_not_called()


def test_bounded_line_ocr_reproduces_split_syllables_and_uses_image_regions(tmp_path):
    from PIL import Image
    image = tmp_path/'prepared.png'; Image.new('L', (1800,2000), 'white').save(image)
    text = positioned_tsv(['은행 입출금 거래내역', '현재 잔액 11,000,000 원', '10 월 14 일',
                           '가 상 입 금 처', '+1,234,567 원', '거래 후 잔액 11,234,567 원'])
    original = parser.parse_pages([page(text, method='ocr_tsv')])['rows'][0]
    assert original['counterparty'] is None and 'party_unverified' in original['review_reasons']
    outputs = iter(['가상입금처', '+1,234,567 원', '거래 후 잔액 11,234,567 원'])
    calls = []
    def run(args, timeout):
        assert args[-4:] == ['--psm', '7', 'txt', 'tsv'] and 0 < timeout <= 3
        assert args[2] != 'stdout'
        crop = Path(args[1]); calls.append(crop)
        with Image.open(crop) as frame:
            assert 40 < frame.width < 1800 and 40 < frame.height < 100
        return crop_tsv(args,next(outputs))
    refined = parser.LineRecognizer().refine(text, image, run)
    result = parser.parse_pages([{**page(text,method='ocr_tsv'), 'ocr_lines':refined}])
    row = result['rows'][0]
    assert (row['counterparty'],row['amount'],row['direction'],row['balance_after']) == ('가상입금처','1234567','inflow','11234567')
    assert row['transaction_date_parts'] == {'year':None,'month':10,'day':14}
    assert row['review_status']=='review_required' and row['owner'] is None and row['account_id'] is None
    assert len(calls)==3 and all(not crop.exists() for crop in calls)


@pytest.mark.parametrize('old,new', [('+1,234,567 원','+1,234,568 원'),
    ('-234,567 원','+234,567 원'), ('234,567 원','-234,567 원'),
    ('거래 후 잔액 11,000,000 원','거래 후 잔액 11,000,001 원')])
def test_line_numeric_disagreement_never_selects_convenient_reading(tmp_path,old,new):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    text=positioned_tsv([old])
    lines=parser.LineRecognizer().refine(text,image,lambda args,timeout:crop_tsv(args,new))
    assert 'ocr_line_conflict' in lines[0]['reasons']
    assert parser.unsafe_line(lines[0])
    assert lines[0]['text']==old  # No changed digit/sign replaces the original evidence.


def test_line_recognition_preserves_normal_word_spaces(tmp_path):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    text=positioned_tsv(['은행 입출금', '10월 14일', '합성 마트 본점', '+1000 원'])
    calls=[]
    outputs=iter(['합성 마트 본점','+1000 원'])
    def run(args,timeout):
        calls.append(args);return crop_tsv(args,next(outputs))
    lines=parser.LineRecognizer().refine(text,image,run)
    assert lines[2]['text']=='합성 마트 본점' and len(calls)==2


@pytest.mark.parametrize('new', ['-234, 5672 원', '−234,567 원', '++234,567 원'])
def test_line_rereading_never_repairs_damaged_numeric_output(tmp_path,new):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    lines=parser.LineRecognizer().refine(positioned_tsv(['-234,567 원']),image,
        lambda args,timeout:crop_tsv(args,new))
    assert parser.unsafe_line(lines[0]) and lines[0]['text']=='-234,567 원'


def test_line_rereading_accepts_new_valid_pixels_only_when_old_number_is_invalid(tmp_path):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    lines=parser.LineRecognizer().refine(positioned_tsv(['-234, 5672']),image,
        lambda args,timeout:crop_tsv(args,'-234,567 원'))
    assert lines[0]['text']=='-234,567 원' and not parser.unsafe_line(lines[0])


def test_low_confidence_single_line_output_remains_unknown(tmp_path):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    lines=parser.LineRecognizer().refine(positioned_tsv(['가 상 입 금 처']),image,
        lambda args,timeout:crop_tsv(args,'가상입금처',confidence=35))
    assert lines[0]['text']=='가 상 입 금 처' and parser.unsafe_line(lines[0])


def test_line_budget_is_document_wide_across_pages(tmp_path):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    recognizer=parser.LineRecognizer(); calls=[]
    def run(args,timeout):
        calls.append(args);return crop_tsv(args,'+1000 원')
    for _ in range(8):recognizer.refine(positioned_tsv(['+1000 원']),image,run)
    with pytest.raises(ValueError,match='budget'):recognizer.refine(positioned_tsv(['+1000 원']),image,run)
    assert len(calls)==8 and not list(tmp_path.glob('line-*.png'))


@pytest.mark.parametrize('fault', ['missing-size','wrong-size','clipped','negative','overlap','tiny','low-confidence'])
def test_unreliable_source_regions_never_trigger_ocr(tmp_path,fault):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    text=positioned_tsv(['가 상 입 금 처'])
    records=text.splitlines()
    if fault=='missing-size':records.pop(1)
    elif fault=='wrong-size':records[1]=records[1].replace('1800','900')
    elif fault=='overlap':
        fields=records[2].split('\t');fields[4]='2';records.append('\t'.join(fields))
    else:
        fields=records[2].split('\t')
        if fault=='clipped':fields[6]='1'
        elif fault=='negative':fields[6]='-1'
        elif fault=='tiny':fields[9]='6'
        else:fields[10]='20'
        records[2]='\t'.join(fields)
    lines=parser.LineRecognizer().refine('\n'.join(records),image,
        lambda *args:pytest.fail('Unreliable geometry must not be cropped'))
    assert all(parser.unsafe_line(line) for line in lines)


@pytest.mark.parametrize('failure', ['timeout','too-large','elapsed','multiline'])
def test_line_ocr_limits_and_failures_clean_crops(tmp_path,monkeypatch,failure):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    recognizer=parser.LineRecognizer()
    def run(args,timeout):
        if failure=='timeout':raise subprocess.TimeoutExpired(args,timeout)
        if failure=='too-large':
            crop_tsv(args,'+1000 원')
            Path(args[2]+'.tsv').write_bytes(b'x'*20_001)
            return b''
        return crop_tsv(args,'unexpected\ntwo lines')
    if failure=='elapsed':recognizer.elapsed=12
    if failure=='multiline':
        lines=recognizer.refine(positioned_tsv(['+1000 원']),image,run)
        assert parser.unsafe_line(lines[0])
    else:
        with pytest.raises((subprocess.TimeoutExpired,ValueError)):
            recognizer.refine(positioned_tsv(['+1000 원']),image,run)
    assert not list(tmp_path.glob('line-*'))


def test_shared_decoder_refines_each_pdf_page_before_pixels_are_replaced(tmp_path):
    from PIL import Image
    path=tmp_path/'synthetic.pdf';path.write_bytes(b'%PDF-synthetic')
    seen=[]
    def run(args,timeout=12):
        if args[0]=='pdfinfo':return b'Pages: 2\nEncrypted: no\n'
        if args[0]=='pdftotext':Path(args[-1]).write_text('');return b''
        if args[0]=='pdftoppm':
            number=int(args[args.index('-f')+1]);Image.new('L',(800,600),0 if number==1 else 255).save(args[-1]+'.png');return b''
        if args[-1]=='0':raise subprocess.CalledProcessError(1,args)
        return positioned_tsv(['synthetic']).encode()
    def refine(text,prepared,runner):
        with Image.open(prepared) as image:seen.append(image.getpixel((0,0)))
        return [{'text':'page-'+str(len(seen)), 'confidence':95,'bbox':[10,10,40,20],'reasons':[]}]
    pages=engine.extract_pages(path,'pdf',run=run,needs_ocr=parser.needs_ocr,tsv=True,refine_tsv=refine)
    assert seen==[0,255] and [p['ocr_lines'][0]['text'] for p in pages]==['page-1','page-2']
    assert [p['page'] for p in pages]==[1,2]
    plain=engine.extract_pages(path,'pdf',run=run,needs_ocr=parser.needs_ocr)
    assert all(set(p)=={'page','text','method'} and p['method']=='ocr' for p in plain)


def test_document_deadline_does_not_extend_outer_timeout(monkeypatch,tmp_path):
    clock=iter([0,56])
    monkeypatch.setattr(parser.time,'monotonic',lambda:next(clock))
    monkeypatch.setattr(parser,'command',lambda *args:pytest.fail('Expired document must not run another tool'))
    def extract(*args,**kwargs):kwargs['run'](['tesseract'],20)
    monkeypatch.setattr(parser,'extract_pages',extract)
    with pytest.raises(ValueError,match='Document OCR budget'):parser.extract(tmp_path/'x.png','png','auto')


def test_separate_parties_amounts_and_balances_stay_in_their_own_regions(tmp_path):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    content=['은행 입출금 거래내역', '현재 잔액 11,000,000 원', '10월 14일',
             '가 상 입 금 처', '+1,234,567 원', '거래 후 잔액 11,234,567 원',
             '10월 13일', '가 상 출 금 처', '-234,567 원', '거래 후 잔액 11,000,000 원']
    text=positioned_tsv(content)
    outputs=iter(['가상입금처','+1,234,567 원','거래 후 잔액 11,234,567 원',
                  '가상출금처','-234,567 원','거래 후 잔액 11,000,000 원'])
    positions=[]
    def run(args,timeout):
        positions.append(args[1]);return crop_tsv(args,next(outputs))
    refined=parser.LineRecognizer().refine(text,image,run)
    rows=parser.parse_pages([{**page(text,method='ocr_tsv'),'ocr_lines':refined}])['rows']
    assert len(rows)==2 and len(positions)==6
    assert [(r['counterparty'],r['amount'],r['direction'],r['balance_after']) for r in rows]==[
        ('가상입금처','1234567','inflow','11234567'),('가상출금처','234567','outflow','11000000')]
    assert all(r['review_status']=='review_required' and r['owner'] is None and r['account_id'] is None for r in rows)


def test_balance_conflict_is_null_in_final_preview_not_a_second_transaction(tmp_path):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    text=positioned_tsv(['은행 입출금 거래내역','10월 14일','합성 상점','+1000 원','거래 후 잔액 9000 원'])
    outputs=iter(['합성 상점','+1000 원','거래 후 잔액 9001 원'])
    refined=parser.LineRecognizer().refine(text,image,lambda args,timeout:crop_tsv(args,next(outputs)))
    rows=parser.parse_pages([{**page(text,method='ocr_tsv'),'ocr_lines':refined}])['rows']
    assert len(rows)==1 and rows[0]['amount']=='1000' and rows[0]['balance_after'] is None
    assert 'balance_ambiguous' in rows[0]['review_reasons']


@pytest.mark.parametrize('text',['+1000 원 -2000 원','++234,567 원','+-234,567 원','−234,567 원'])
def test_multiple_amounts_or_damaged_source_signs_are_never_resolved_by_rereading(tmp_path,text):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    lines=parser.LineRecognizer().refine(positioned_tsv([text]),image,
        lambda *args:pytest.fail('Ambiguous source numbers/signs must stay unknown'))
    assert 'ocr_line_conflict' in lines[0]['reasons']


def test_ledger_extract_uses_opt_in_hook_and_remaining_deadline(monkeypatch,tmp_path):
    times=iter([10,20])
    monkeypatch.setattr(parser.time,'monotonic',lambda:next(times))
    calls=[]
    monkeypatch.setattr(parser,'command',lambda args,timeout:calls.append(timeout) or b'bounded')
    def extract(path,kind,**kwargs):
        assert kwargs['tsv'] is True and callable(kwargs['refine_tsv'])
        assert kwargs['run'](['tesseract'],60)==b'bounded'
        return [page(BANK)]
    monkeypatch.setattr(parser,'extract_pages',extract)
    result=parser.extract(tmp_path/'synthetic.png','png','auto')
    assert calls==[45] and len(result['rows'])==2


def test_existing_inline_date_amount_is_preserved_without_line_rereading(tmp_path):
    from PIL import Image
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    text=positioned_tsv(['은행 입출금 거래내역','2026-10-14 +1000 원'])
    before=parser.parse_pages([page(text,method='ocr_tsv')])
    refined=parser.LineRecognizer().refine(text,image,
        lambda *args:pytest.fail('Date punctuation is not a damaged amount sign'))
    after=parser.parse_pages([{**page(text,method='ocr_tsv'),'ocr_lines':refined}])
    assert after==before and after['rows'][0]['transaction_date']=='2026-10-14'
    assert after['rows'][0]['amount']=='1000'


def test_o11_month_day_separators_do_not_become_merchants_or_invent_year():
    rows = parser.parse_pages([page(partial_bank())])['rows']
    assert len(rows) == 2
    assert [r['transaction_date_parts'] for r in rows] == [
        {'year':None,'month':10,'day':14}, {'year':None,'month':10,'day':13}]
    assert all(r['transaction_date'] is None and 'year_missing' in r['review_reasons'] for r in rows)
    assert [r['counterparty'] for r in rows] == ['합성송금처 이체', '합성매장']
    assert [(r['amount'],r['direction'],r['balance_after']) for r in rows] == [
        ('1234567','inflow','11234567'), ('234567','outflow','11000000')]
    assert rows[0]['transaction_type_candidate']=='bank_transfer'
    assert 'transfer_not_income_expense' in rows[0]['review_reasons']
    assert all(r['review_status']=='review_required' and r['owner'] is None and r['account_id'] is None for r in rows)


@pytest.mark.parametrize('header', ['거래 연도: 2026', '조회 기간: 2026.10.01 ~ 2026.10.31'])
def test_o11_explicit_year_or_bounded_period_matches_partial_rows(header):
    rows = parser.parse_pages([page(partial_bank(header))])['rows']
    assert [r['transaction_date'] for r in rows]==['2026-10-14','2026-10-13']
    assert all(r['transaction_date_parts']['year']==2026 and 'year_missing' not in r['review_reasons'] for r in rows)
    assert not parser.needs_ocr(partial_bank())  # Text PDF need not OCR just because year is absent.


@pytest.mark.parametrize('header', ['발급일 2026.10.15', '촬영 연도 2026',
    '거래 연도: 2025\n거래 연도: 2026', '조회 기간: 2025.01.01 ~ 2026.12.31',
    '조회 기간: 2026.01.01 ~ 2026.02.28'])
def test_o11_unrelated_conflicting_or_ambiguous_year_does_not_fill_date(header):
    rows = parser.parse_pages([page(partial_bank(header))])['rows']
    assert len(rows)==2 and all(r['transaction_date'] is None for r in rows)
    assert all('year_missing' in r['review_reasons'] for r in rows)


def test_o11_year_boundary_and_page_boundaries_are_explicit():
    text = ('은행 입출금\n조회 기간: 2025.12.30 ~ 2026.01.02\n'
            '1월 2일\n합성상점\n-1000원\n12월 31일\n합성상점\n-1000원')
    rows = parser.parse_pages([page(text), page('은행 입출금\n1월 1일\n합성상점\n-1000원',2)])['rows']
    assert [r['transaction_date'] for r in rows]==['2026-01-02','2025-12-31',None]
    assert rows[-1]['transaction_date_parts']=={'year':None,'month':1,'day':1}
    assert all(r['review_status']=='review_required' for r in rows)


@pytest.mark.parametrize('marker', ['13월 1일', '2월 30일', '2026년 2월 29일'])
def test_o11_invalid_dates_reset_context_instead_of_becoming_labels(marker):
    rows = parser.parse_pages([page('은행 입출금\n'+marker+'\n합성상점\n+1000원')])['rows']
    assert len(rows)==1 and rows[0]['transaction_date'] is None
    assert 'date_invalid' in rows[0]['review_reasons'] and rows[0]['counterparty']=='합성상점'


def test_o11_full_korean_date_and_leap_day_without_year():
    rows=parser.parse_pages([page('은행 입출금\n2024년 2월 29일\n합성상점\n+1000원\n'
                                 '2월 29일\n합성상점\n+1000원')])['rows']
    assert rows[0]['transaction_date']=='2024-02-29'
    assert rows[1]['transaction_date'] is None and rows[1]['transaction_date_parts']['day']==29
    assert 'year_missing' in rows[1]['review_reasons']


def test_o11_unlabeled_small_balance_never_becomes_second_transaction():
    rows=parser.parse_pages([page('은행 입출금\n10월 14일\n합성상점\n+1234567원\n11234567원')])['rows']
    assert len(rows)==1 and rows[0]['amount']=='1234567' and rows[0]['balance_after'] is None
    assert 'unlabeled_amount_ambiguous' in rows[0]['review_reasons']


def test_o11_balance_before_amount_or_new_merchant_is_not_attached_to_prior_row():
    rows=parser.parse_pages([page('은행 입출금\n10월 14일\n합성상점\n+1000원\n'
                                 '합성두번째상점\n잔액 8000원\n-2000원')])['rows']
    assert len(rows)==2 and all(r['balance_after'] is None for r in rows)
    assert [(r['amount'],r['counterparty']) for r in rows]==[('1000','합성상점'),('2000','합성두번째상점')]


@pytest.mark.parametrize('token', ['+12X000', '+12 000', '+1,00,000', '+12…', '+12□', '−1000', '+NaN', '+Infinity',
                                 "+12'000", '+12:000', '+12/000'])
def test_o11_malformed_token_is_not_replaced_by_valid_numeric_suffix(token):
    rows=parser.parse_pages([page('은행 입출금\n10월 14일\n합성상점\n'+token+'원')])['rows']
    assert len(rows)==1 and rows[0]['amount'] is None and rows[0]['direction']=='unknown'
    assert 'amount_invalid' in rows[0]['review_reasons']


@pytest.mark.parametrize('token,expected', [('1234567','1234567'),('234,567','234567')])
def test_o11_unsigned_amount_has_unknown_direction_and_never_inferred_from_label(token,expected):
    row=parser.parse_pages([page('은행 입출금\n10월 14일\n합성입금처\n'+token+'원')])['rows'][0]
    assert row['amount']==expected and row['direction']=='unknown'
    assert 'direction_unknown' in row['review_reasons'] and row['transaction_date'] is None


def test_o11_legitimate_same_merchant_same_date_same_amount_rows_are_all_retained():
    text='은행 입출금\n10월 14일\n합성상점\n-1000원\n합성상점\n-1000원'
    rows=parser.parse_pages([page(text)])['rows']
    assert len(rows)==2 and all(r['amount']=='1000' and r['counterparty']=='합성상점' for r in rows)
    assert rows[-1]['warnings'] and rows[0]['row_id']!=rows[1]['row_id']


@pytest.mark.parametrize('state,candidate', [('취소','card_cancellation'),('환불','refund'),
    ('카드대금 납부','card_bill'),('취소 환불','unknown')])
def test_o11_card_partial_date_total_and_state_remain_review_candidates(state,candidate):
    row=parser.parse_pages([page('카드 이용내역\n총 사용금액 80000원\n10월 14일\n'
                                '합성가맹점 '+state+'\n승인금액 1000원')])['rows'][0]
    assert row['transaction_date'] is None and row['transaction_date_parts']['day']==14
    assert row['amount']=='1000' and row['transaction_type_candidate']==candidate
    assert row['direction']=='unknown' and row['review_status']=='review_required'
    assert 'card_classification_unconfirmed' in row['review_reasons']


@pytest.mark.parametrize('layout,reason', [({'width':180},'image_low_resolution'),
    ({'glyph_height':8},'text_too_small'), ({'clipped_line':4},'row_clipped')])
def test_o11_low_resolution_or_clipped_ocr_never_guesses_amount_or_merchant(layout,reason):
    text='카드 이용내역\n10월 14일\n합성가맹점\n승인금액 1000원'
    row=parser.parse_pages([page(geometry_tsv(text,**layout),method='ocr_tsv')])['rows'][0]
    assert row['amount'] is None and row['merchant'] is None and row['direction']=='unknown'
    assert reason in row['review_reasons'] and row['review_status']=='review_required'


def test_o11_clipped_merchant_invalidates_associated_amount_even_when_digits_look_clear():
    text='카드 이용내역\n10월 14일\n합성가맹점\n승인금액 1000원'
    row=parser.parse_pages([page(geometry_tsv(text,clipped_line=3),method='ocr_tsv')])['rows'][0]
    assert row['merchant'] is None and row['amount'] is None
    assert 'row_clipped' in row['review_reasons'] and 'party_unverified' in row['review_reasons']


def test_o11_clear_ocr_geometry_keeps_candidates_but_not_accuracy_claim():
    row=parser.parse_pages([page(geometry_tsv(partial_bank()),method='ocr_tsv')])['rows'][0]
    assert row['amount']=='1234567' and row['balance_after']=='11234567'
    assert row['transaction_date'] is None and row['transaction_date_parts']=={'year':None,'month':10,'day':14}
    assert row['review_status']=='review_required' and 'year_missing' in row['review_reasons']


@pytest.mark.parametrize('kind', ['auto','bank_transactions','card_transactions'])
def test_o11_unrelated_or_conflicting_document_is_unknown_even_with_user_type(kind):
    for text in ('사용 설명\n10월 14일\n합성상점\n1000원',
                 '은행 입출금\n카드 이용내역\n10월 14일\n합성상점\n1000원'):
        result=parser.parse_pages([page(text)],kind)
        assert result['document_type']=='unknown' and result['rows']==[]


def test_o11_preview_preserves_synthetic_financial_files_and_creates_no_user_paths(tmp_path,monkeypatch,capsys):
    from app.services import user_manager, ledger, portfolio
    users=tmp_path/'users'; users.mkdir()
    ledger_file=tmp_path/'ledger.json';ledger_file.write_text('{"transactions":[]}',encoding='utf-8')
    portfolio_file=tmp_path/'portfolio.json';portfolio_file.write_text('{"cash":12345}',encoding='utf-8')
    before=[file.read_bytes() for file in (ledger_file,portfolio_file)]
    monkeypatch.setattr(user_manager,'USERS_DIR',users)
    def forbidden(*args,**kwargs): pytest.fail('OCR may not resolve/create a financial path or call any writer')
    for module,names in ((user_manager,('get_user_data_dir',)),
            (ledger,('add_transaction','import_ledger_from_file_bytes','write_ledger','get_ledger_path')),
            (portfolio,('write_portfolio','_get_portfolio_file'))):
        for name in names: monkeypatch.setattr(module,name,forbidden)
    paths=fake_worker(monkeypatch,parser.parse_pages([page(partial_bank())]))
    result=importer.preview(b'%PDF-synthetic','application/pdf')
    assert result['rows'][0]['transaction_date'] is None
    assert [file.read_bytes() for file in (ledger_file,portfolio_file)]==before
    assert list(users.iterdir())==[] and not paths[0].parent.exists()
    assert capsys.readouterr()==('', '')


@pytest.mark.parametrize('label', ['조회일', '발급일', '촬영 날짜'])
def test_o11_metadata_dates_never_become_transaction_context(label):
    text='은행 입출금\n10월 14일\n합성상점\n+1000원\n'+label+' 2026.10.15\n합성다른상점\n-2000원'
    rows=parser.parse_pages([page(text)])['rows']
    assert len(rows)==2 and all(r['transaction_date'] is None for r in rows)
    assert all(r['transaction_date_parts']=={'year':None,'month':10,'day':14} for r in rows)


@pytest.mark.parametrize('text', ['+5000원 잔액 8000원', '잔액 8000원 거래금액 +5000원'])
def test_o11_two_amounts_on_a_balance_line_cannot_be_reinterpreted_as_transactions(text):
    result=parser.parse_pages([page('은행 입출금\n10월 14일\n합성상점\n'+text)])
    assert result['rows']==[] and result['status']=='review_required' and result['warnings']
