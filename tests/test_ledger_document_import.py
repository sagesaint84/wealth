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
