"""O1.2 smoke contracts only. No native OCR, user fonts or financial documents."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location('ocr_smoke_' + name, ROOT / 'ops/pension-ocr' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def smoke():
    return load_script('smoke')


def expected_result(kind):
    rows = []
    expected = ([('가상입금처','1234567','inflow','11234567','09:10'),
                 ('가상출금처','234567','outflow','11000000','10:20')]
                if kind == 'bank_transactions' else
                [('가상카페','12345','unknown',None,None),('가상서점','23456','unknown',None,None)])
    for index, (party, amount, direction, balance, clock) in enumerate(expected):
        rows.append({'row_id':f'preview-{index+1}', 'counterparty':party if kind=='bank_transactions' else None,
                     'merchant':party if kind=='card_transactions' else None, 'amount':amount,
                     'direction':direction, 'balance_after':balance, 'transaction_time':clock,
                     'transaction_date':None, 'transaction_date_parts':{'year':None,'month':10,'day':14-index},
                     'review_status':'review_required', 'review_reasons':['year_missing'],
                     'owner':None, 'account_id':None,
                     'source_location':{'method':'ocr_tsv','page':1,'line':index+1,'bbox':[100,200,600,64]},
                     'transaction_type_candidate':'card_approval_candidate' if kind=='card_transactions' else 'unknown',
                     'payment_method_candidate':'card' if kind=='card_transactions' else None, 'warnings':[]})
    return {'document_type':kind,'status':'review_required','rows':rows,'warnings':[]}


@pytest.mark.parametrize('kind', ['bank_transactions','card_transactions'])
def test_validator_accepts_only_exact_synthetic_contract(smoke,kind):
    smoke.validate_ledger_result(expected_result(kind),kind)


@pytest.mark.parametrize('field,value', [
    ('amount','91234567'), ('amount',1234567), ('amount',None), ('direction','unknown'),
    ('balance_after','11000000'), ('transaction_date','2026-10-14'),
    ('transaction_date_parts',{'year':2026,'month':10,'day':14}),
    ('transaction_time','15:35'), ('review_status','confirmed'), ('review_reasons',[]),
    ('owner','private-owner'), ('account_id','private-account'), ('counterparty','private-party'),
    ('source_location',{'method':'text','page':1,'bbox':[100,200,600,64]}),
    ('source_location',{'method':'ocr_tsv','page':1,'bbox':None}), ('raw_text','private-raw-text'),
])
def test_validator_rejects_bad_ocr_or_invented_financial_state_without_raw_errors(smoke,field,value,capsys):
    result=expected_result('bank_transactions');result['rows'][0][field]=value
    with pytest.raises(RuntimeError) as error: smoke.validate_ledger_result(result,'bank_transactions')
    assert 'private' not in str(error.value) and '91234567' not in str(error.value)
    assert capsys.readouterr()==('', '')


@pytest.mark.parametrize('change', ['extra-total','duplicate-id','wrong-type','wrong-status','raw-root'])
def test_validator_rejects_extra_totals_and_changed_response_contract(smoke,change):
    result=expected_result('bank_transactions')
    if change=='extra-total':result['rows'].append(copy.deepcopy(result['rows'][0]))
    elif change=='duplicate-id':result['rows'][1]['row_id']=result['rows'][0]['row_id']
    elif change=='wrong-type':result['document_type']='card_transactions'
    elif change=='wrong-status':result['status']='confirmed'
    else:result['raw_text']='private-raw-text'
    with pytest.raises(RuntimeError):smoke.validate_ledger_result(result,'bank_transactions')


@pytest.mark.parametrize('field,value', [('amount','35801'),('direction','inflow'),
    ('transaction_type_candidate','refund'),('payment_method_candidate','bank'),('balance_after','35801')])
def test_card_validator_rejects_total_refund_or_balance_confusion(smoke,field,value):
    result=expected_result('card_transactions');result['rows'][0][field]=value
    with pytest.raises(RuntimeError):smoke.validate_ledger_result(result,'card_transactions')


def test_generator_preserves_pension_and_creates_only_transient_synthetic_images(tmp_path,monkeypatch,capsys):
    from PIL import Image, ImageFont
    generator=load_script('generate_fixtures')
    # Pillow's bundled font exercises encoding/layout, not Korean recognition.
    # Native CI alone uses the public Nanum font and actual Tesseract.
    font=ImageFont.load_default(size=64)
    monkeypatch.setattr(generator.ImageFont,'truetype',lambda *args,**kwargs:font)
    font_marker=tmp_path/'public-font-marker';font_marker.write_bytes(b'synthetic-marker')
    (tmp_path/'public-font-markerBold').write_bytes(b'synthetic-bold-marker')
    output=tmp_path/'fixtures'
    monkeypatch.setattr(sys,'argv',['generate_fixtures','--font',str(font_marker),'--output',str(output)])
    generator.main()
    assert {p.name for p in output.iterdir()}=={'synthetic.png','synthetic.pdf','bank.png','bank.pdf','card.jpg','card.pdf'}
    with Image.open(output/'synthetic.png') as image:assert image.size==(1800,1000)
    with Image.open(output/'bank.png') as image:
        assert image.size[0]==1800 and image.getpixel((0,0))==(17,24,39)
    with Image.open(output/'card.jpg') as image:
        assert image.size[0]==1800 and image.getpixel((0,0))==(255,255,255)
    for name in ('synthetic.pdf','bank.pdf','card.pdf'):
        data=(output/name).read_bytes()
        assert data.startswith(b'%PDF-') and b'/Subtype /Image' in data
    assert '+1,234,567 원' in generator.BANK_LINES and '-234,567 원' in generator.BANK_LINES
    assert '총 사용금액 35,801원' in generator.CARD_LINES
    if os.name=='posix':
        assert all((output/name).stat().st_mode & 0o777 == 0o644 for name in ('bank.png','bank.pdf','card.jpg','card.pdf'))
    assert '1234567' not in capsys.readouterr().out


def test_generator_rejects_oversized_text_instead_of_clipping_it(tmp_path,monkeypatch):
    generator=load_script('generate_fixtures')
    class Draw:
        def textbbox(self,*args,**kwargs):return (0,0,1700,64)
    monkeypatch.setattr(generator.ImageDraw,'Draw',lambda *args:Draw())
    with pytest.raises(SystemExit,match='does not fit'):generator.generate_ledger_fixtures(tmp_path,None)
    assert list(tmp_path.iterdir())==[]


@pytest.mark.parametrize('name,kind,document_type', [
    ('bank.png','png','bank_transactions'),('bank.pdf','pdf','bank_transactions'),
    ('card.jpg','jpeg','card_transactions'),('card.pdf','pdf','card_transactions')])
def test_case_uses_real_coordinator_contract_and_cleans_private_copies(smoke,tmp_path,monkeypatch,name,kind,document_type,capsys):
    from app.services import ledger_document_import as importer
    fixtures=tmp_path/'fixtures';fixtures.mkdir();(fixtures/name).write_bytes(b'synthetic-input')
    monkeypatch.setattr(smoke,'command',lambda args,timeout=30:'Pages: 1\n' if args[0]=='pdfinfo' else '\f')
    before={key:os.environ.get(key) for key in ('WEALTH_ENV','WEALTH_DISABLE_ENV_FILE','WEALTH_DATA_DIR','DATA_DIR','TMPDIR')}
    original_temp=tempfile.tempdir
    locations=[]
    def preview(data,mime,selected):
        assert data==b'synthetic-input' and selected==document_type
        assert mime=={'png':'image/png','jpeg':'image/jpeg','pdf':'application/pdf'}[kind]
        assert os.environ['WEALTH_ENV']=='test' and os.environ['WEALTH_DISABLE_ENV_FILE']=='1'
        inputs=Path(tempfile.gettempdir());locations.append(inputs.parent)
        assert inputs.is_dir() and os.environ['TMPDIR']==str(inputs)
        assert Path(os.environ['DATA_DIR']).parent==inputs.parent
        if os.name=='posix':assert inputs.stat().st_mode & 0o777 == 0o700
        return expected_result(selected)
    monkeypatch.setattr(importer,'preview',preview)
    smoke.run_ledger_case(fixtures,name,kind,document_type)
    assert locations and all(not p.exists() for p in locations)
    assert tempfile.tempdir==original_temp and all(os.environ.get(key)==value for key,value in before.items())
    assert {p.name for p in fixtures.iterdir()}=={name}
    out=capsys.readouterr();assert 'PASS:' in out.out and not out.err
    assert '가상입금처' not in out.out and 'synthetic-input' not in out.out


@pytest.mark.parametrize('failure', ['wrong-amount','worker-failure','financial-write','user-dir','leaked-input'])
def test_case_fails_closed_and_restores_scope_on_all_failures(smoke,tmp_path,monkeypatch,failure,capsys):
    from app.services import ledger_document_import as importer
    (tmp_path/'bank.png').write_bytes(b'synthetic-input')
    original_temp=tempfile.tempdir;original_data=os.environ.get('WEALTH_DATA_DIR');locations=[]
    def preview(*args):
        locations.append(Path(tempfile.gettempdir()).parent)
        if failure=='worker-failure':raise ValueError('fixed-safe-worker-error')
        result=expected_result('bank_transactions')
        if failure=='wrong-amount':result['rows'][0]['amount']='112000000'
        elif failure=='financial-write':(Path(os.environ['WEALTH_DATA_DIR'])/'ledger.json').write_bytes(b'changed')
        elif failure=='user-dir':(Path(os.environ['WEALTH_DATA_DIR'])/'users').mkdir()
        elif failure=='leaked-input':(Path(tempfile.gettempdir())/'orphan.png').write_bytes(b'synthetic')
        return result
    monkeypatch.setattr(importer,'preview',preview)
    with pytest.raises((RuntimeError,ValueError)):smoke.run_ledger_case(tmp_path,'bank.png','png','bank_transactions')
    assert all(not p.exists() for p in locations) and tempfile.tempdir==original_temp
    assert os.environ.get('WEALTH_DATA_DIR')==original_data and capsys.readouterr()==('', '')


def test_scanned_pdf_with_text_layer_is_rejected_before_worker(smoke,tmp_path,monkeypatch):
    from app.services import ledger_document_import as importer
    (tmp_path/'bank.pdf').write_bytes(b'%PDF-synthetic')
    monkeypatch.setattr(smoke,'command',lambda args,timeout=30:'Pages: 1\n' if args[0]=='pdfinfo' else 'unexpected text')
    monkeypatch.setattr(importer,'preview',lambda *args:pytest.fail('Scanned fixture must really exercise OCR'))
    with pytest.raises(RuntimeError,match='no text layer'):smoke.run_ledger_case(tmp_path,'bank.pdf','pdf','bank_transactions')


def test_existing_native_workflow_and_production_pension_checks_are_preserved(smoke,monkeypatch,tmp_path):
    # Simulate main's routing only: this is NOT a native tool/architecture test.
    from app.services import national_pension_import
    from tests.test_national_pension_import import HISTORY
    pension=national_pension_import.parse_text(HISTORY,ocr=True)
    # Existing native source fixture has these independent exact values.
    for row in pension['fields']:
        if row['key']=='total_paid_amount':row['value']=1200000
        elif row['key']=='paid_months':row['value']=12
    for suffix in ('png','pdf'):(tmp_path/('synthetic.'+suffix)).write_bytes(b'synthetic')
    calls=[];ledger=[]
    def command(args,timeout=30):
        calls.append(args)
        if args[0]=='tesseract':
            if '--version' in args:return 'tesseract 5'
            if '--list-langs' in args:return 'kor\neng\nosd\n'
            return '국민연금 납부내역 확인'
        if args[0]=='pdfinfo' and '-v' not in args:return 'Pages: 1\n'
        if '-m' in args:return json.dumps(pension)
        return ''
    monkeypatch.setattr(smoke,'command',command)
    monkeypatch.setattr(smoke.sys,'platform','linux')
    monkeypatch.setattr(smoke.platform,'machine',lambda:'aarch64')
    monkeypatch.setattr(smoke.shutil,'which',lambda tool:'/synthetic/'+tool)
    monkeypatch.setattr(smoke,'run_ledger_case',lambda *args:ledger.append(args[1:]))
    monkeypatch.setattr(sys,'argv',['smoke','--fixtures',str(tmp_path),'--expected-machine','aarch64'])
    smoke.main()
    assert len([call for call in calls if '-m' in call and 'app.services.national_pension_document' in call])==2
    assert len([call for call in calls if call[0]=='tesseract' and '--psm' in call])==2
    assert ledger==[('bank.png','png','bank_transactions'),('bank.pdf','pdf','bank_transactions'),
                    ('card.jpg','jpeg','card_transactions'),('card.pdf','pdf','card_transactions')]
    workflow=(ROOT/'.github/workflows/toss-auth-pr-validation.yml').read_text(encoding='utf-8')
    assert "'ops/pension-ocr/**'" in workflow
    for flag in ('--network none --read-only','--cap-drop ALL --security-opt no-new-privileges',
                 '--user 65534:65534','readonly','ubuntu-24.04-arm','ubuntu-24.04'):
        assert flag in workflow


def test_wrong_native_architecture_fails_before_tool_execution(smoke,monkeypatch):
    monkeypatch.setattr(sys,'argv',['smoke','--expected-machine','aarch64'])
    monkeypatch.setattr(smoke.sys,'platform','linux')
    monkeypatch.setattr(smoke.platform,'machine',lambda:'x86_64')
    monkeypatch.setattr(smoke,'command',lambda *args:pytest.fail('Wrong architecture must fail first'))
    with pytest.raises(RuntimeError,match='architecture'):smoke.main()


def test_type_and_status_failures_are_independent_fixed_diagnostics(smoke):
    result = expected_result('bank_transactions')
    result['document_type'] = 'unknown'
    with pytest.raises(RuntimeError, match=r'Ledger document type failed \(unknown=True\)'):
        smoke.validate_ledger_result(result, 'bank_transactions')
    result['document_type'] = 'bank_transactions'
    result['status'] = 'confirmed'
    with pytest.raises(RuntimeError, match='Ledger review status failed'):
        smoke.validate_ledger_result(result, 'bank_transactions')


def test_failure_probe_logs_only_allowlisted_booleans(smoke,monkeypatch,tmp_path,capsys):
    evidence = {'date': False, 'money': True, 'bank_header': True,
                'card_header': False, 'tsv_lines': True}
    calls = []
    def command(args, timeout=30):
        calls.append((args, timeout))
        return json.dumps(evidence)
    monkeypatch.setattr(smoke, 'command', command)
    smoke.diagnose_ledger_evidence(tmp_path/'synthetic.png', 'png')
    assert calls[0][0][:2] == [sys.executable, '-c'] and calls[0][1] == 75
    assert 'set_worker_limits()' in calls[0][0][2]
    assert 'tsv=True' in calls[0][0][2]
    assert calls[0][0][-2:] == [str(tmp_path/'synthetic.png'), 'png']
    assert capsys.readouterr() == ('DIAG: ledger date=False money=True bank_header=True card_header=False tsv_lines=True\n', '')


@pytest.mark.parametrize('extra', [{'raw_text':'private-document'}, {'date':'private-value'}])
def test_failure_probe_rejects_raw_or_nonboolean_diagnostics(smoke,monkeypatch,tmp_path,capsys,extra):
    evidence = {'date': False, 'money': True, 'bank_header': True, 'card_header': False, 'tsv_lines': True}
    evidence.update(extra)
    monkeypatch.setattr(smoke, 'command', lambda *args, **kwargs: json.dumps(evidence))
    with pytest.raises(RuntimeError, match='Ledger diagnostic contract failed'):
        smoke.diagnose_ledger_evidence(tmp_path/'synthetic.png', 'png')
    assert capsys.readouterr() == ('', '')


def test_command_failure_never_logs_raw_decoder_output(smoke,monkeypatch,capsys):
    def run(*args,**kwargs):
        return subprocess.CompletedProcess(args[0],1,b'private-document-text',b'private-file-name')
    monkeypatch.setattr(smoke.subprocess,'run',run)
    with pytest.raises(RuntimeError) as error:smoke.command(['tesseract','private-file-name'])
    assert 'private' not in str(error.value) and capsys.readouterr()==('', '')


def trace_bank_parties(smoke,tmp_path,*,bad_row=None,low_source=False,low_reread=False,conflict=False,low_amount=False):
    """Actual production branches with MOCK tool outputs; NOT real native OCR."""
    from PIL import Image
    from app.services import ledger_document as ledger
    from tests.test_ledger_document_import import positioned_tsv,crop_tsv,page
    image=tmp_path/'prepared.png';Image.new('L',(1800,2000),'white').save(image)
    source=positioned_tsv(['은행 입출금 거래내역','10월 14일','가 상 입 금 처','09:10',
        '+1,234,567 원','거래 후 잔액 11,234,567 원','10월 13일','가 상 출 금 처','10:20',
        '-234,567 원','거래 후 잔액 11,000,000 원'])
    if low_source or low_amount:
        records=source.splitlines()
        for index,record in enumerate(records):
            fields=record.split('\t')
            if fields[0]=='5' and fields[4]==('5' if low_amount else '3'):
                fields[10]='20';records[index]='\t'.join(fields)
        source='\n'.join(records)
    outputs=[('가상입금처','가 상 입 금 처'),('+1,234,567 원','+1,234,567 원'),
        ('거래 후 잔액 11,234,567 원','거래 후 잔액 11,234,567 원'),
        ('가상출금처','가 상 출 금 처'),('-234,567 원','-234,567 원'),
        ('거래 후 잔액 11,000,000 원','거래 후 잔액 11,000,000 원')]
    if low_source:outputs.pop(0)
    if low_amount:outputs.pop(1)
    if bad_row is not None:
        at=0 if bad_row==1 else 3
        outputs[at]=('다른합성거래처',outputs[at][1]) if conflict else ('가 상 입 금 처',outputs[at][1])
    outputs=iter(outputs);calls=[]
    def run(args,timeout):
        txt,tsv=next(outputs);calls.append(args)
        return crop_tsv(args,tsv,txt=txt,confidence=45 if low_reread and len(calls)==1 else 95)
    observer=smoke.PartyObserver(ledger)
    def execute():
        refined=ledger.LineRecognizer().refine(source,image,run)
        return ledger.parse_pages([{**page(source,method='ocr_tsv'),'ocr_lines':refined}])
    result=observer.observe(execute)
    return result,smoke.party_report(result,observer),observer


def trace_focused_numeric(smoke,tmp_path,*,card=False,low=False,clipped=False,conflict=False,unknown_type=False):
    """Real traced guards, synthetic mocked TXT/TSV, no native OCR claim."""
    from PIL import Image
    from app.services import ledger_document as ledger
    from tests.test_ledger_document_import import positioned_tsv,crop_tsv,page
    image=tmp_path/'prepared.png';Image.new('L',(1800,2000),'white').save(image)
    source=positioned_tsv(['카드 이용내역' if card else '은행 입출금 거래내역','10월 14일',
        '가 상 카 페' if card else '가 상 입 금 처',
        '승인금액 12,345 원' if card else '+1,234,567 원',
        '거래 후 잔액 11,234,567 원'] if not card else
        ['카드 이용내역','10월 14일','가 상 카 페','승인금액 12,345 원'])
    if unknown_type:
        source=source.replace('\t카드\n','\t합성\n').replace('\t이용내역\n','\t자료\n')
    outputs=iter([('가상카페' if card else '가상입금처','가 상 카 페' if card else '가 상 입 금 처'),
        ('승인금액 12,345 원' if card else '+1,234,568 원' if conflict else '+1,234,567 원',
         '승인금액 12,345 원' if card else '+1,234,568 원' if conflict else '+1,234,567 원'),
        ('거래 후 잔액 11,234,567 원','거래 후 잔액 11,234,567 원')])
    calls=[]
    def run(args,timeout):
        txt,tsv=next(outputs);calls.append(args)
        crop_tsv(args,tsv,txt=txt,confidence=89 if low and len(calls)==2 else 95)
        if clipped and len(calls)==3:
            path=Path(args[2]+'.tsv');records=path.read_text(encoding='utf-8').splitlines()
            fields=records[2].split('\t');fields[6]='1';records[2]='\t'.join(fields)
            path.write_text('\n'.join(records),encoding='utf-8')
        return b''
    observer=smoke.FocusObserver(ledger)
    def execute():
        lines=ledger.LineRecognizer().refine(source,image,run)
        return ledger.parse_pages([{**page(source,method='ocr_tsv'),'ocr_lines':lines}])
    result=observer.observe(execute)
    return result,smoke.focus_report(observer,'card_transactions' if card else 'bank_transactions',result),observer


def test_focused_trace_separates_amount_confidence_and_balance_clipping(smoke,tmp_path,capsys):
    result,rows,observer=trace_focused_numeric(smoke,tmp_path,low=True,clipped=True)
    assert observer.supported
    amount=next(r for r in rows if r['kind']=='bank_amount')
    balance=next(r for r in rows if r['kind']=='bank_balance')
    assert amount['reread_confidence_bucket']=='80to89' and amount['reread_confidence_ok'] is False
    assert amount['reject_code']=='reread_initial_guard' and amount['expanded_crop_used'] is False
    assert balance['reread_row_clipped'] is True and balance['reject_code']=='reread_initial_guard'
    smoke.emit_focus_report(rows,'bank.png')
    output=capsys.readouterr().out
    assert 'kind=bank_amount' in output and 'kind=bank_balance' in output
    for private in ('가상','1234567','11,234,567','[100'):
        assert private not in output


def test_focused_trace_records_executed_numeric_mismatch(smoke,tmp_path):
    _,rows,_=trace_focused_numeric(smoke,tmp_path,conflict=True)
    amount=next(r for r in rows if r['kind']=='bank_amount')
    assert amount['old_numeric_valid'] and amount['new_numeric_valid']
    assert amount['numeric_values_equal'] is False and amount['numeric_sign_equal'] is True
    assert amount['reject_code']=='numeric_guard' and amount['accepted'] is False


def test_focused_trace_identifies_card_row_without_weakening_exact_validator(smoke,tmp_path):
    result,rows,_=trace_focused_numeric(smoke,tmp_path,card=True)
    assert rows and rows[0]['kind']=='card_row' and rows[0]['accepted'] is True
    with pytest.raises(RuntimeError):smoke.validate_ledger_result(result,'card_transactions')


def test_focused_trace_reports_source_candidates_when_card_classification_fails(smoke,tmp_path,capsys):
    result,rows,observer=trace_focused_numeric(smoke,tmp_path,card=True,unknown_type=True)
    assert result['document_type']=='unknown' and not observer.amount_rows
    assert rows and rows[0]['kind']=='card_row'
    assert rows[0]['parser_row_seen'] is False and rows[0]['document_type_matches'] is False
    assert rows[0]['refine_called'] is True
    smoke.emit_focus_report(rows,'card.jpg')
    assert 'document_type_matches=false' in capsys.readouterr().out


@pytest.mark.parametrize('bad', ['raw_text','source_line','refine_calls','reread_confidence_bucket','accepted'])
def test_focused_emitter_rejects_bad_schema_without_partial_log(smoke,tmp_path,capsys,bad):
    _,rows,_=trace_focused_numeric(smoke,tmp_path)
    if bad=='raw_text':rows[-1]['raw_text']='private-payload'
    elif bad=='source_line':rows[-1][bad]='private-payload'
    elif bad=='refine_calls':rows[-1][bad]=9
    elif bad=='reread_confidence_bucket':rows[-1][bad]='private-payload'
    else:rows[-1][bad]='private-payload'
    with pytest.raises(RuntimeError):smoke.emit_focus_report(rows,'bank.png')
    assert capsys.readouterr()==('', '')


def test_focused_probe_rejects_nonfixture_before_any_file_read(smoke,tmp_path,monkeypatch):
    monkeypatch.setattr(smoke,'subprocess',None)
    with pytest.raises(RuntimeError,match='input denied'):
        smoke.diagnose_ledger_rejections(tmp_path/'private.png')


def test_focused_failure_runs_before_original_exact_assertion_is_reraised(smoke,tmp_path,monkeypatch,capsys):
    from app.services import ledger_document_import as importer
    (tmp_path/'card.jpg').write_bytes(b'synthetic-only')
    result=expected_result('card_transactions');result['rows'][0]['amount']=None
    monkeypatch.setattr(importer,'preview',lambda *args:result)
    calls=[];monkeypatch.setattr(smoke,'diagnose_ledger_rejections',lambda path:calls.append(path.name))
    monkeypatch.setattr(smoke,'is_public_ledger_fixture',lambda path:True)
    with pytest.raises(RuntimeError):smoke.run_ledger_case(tmp_path,'card.jpg','jpeg','card_transactions')
    assert calls==['card.jpg'] and 'PASS:' not in capsys.readouterr().out


@pytest.mark.parametrize('fault',['none','timeout','bad-schema'])
def test_focused_subprocess_is_bounded_private_and_cleaned(smoke,tmp_path,monkeypatch,capsys,fault):
    _,rows,_=trace_focused_numeric(smoke,tmp_path,card=True)
    fixtures=tmp_path/'public';fixtures.mkdir();source=fixtures/'card.jpg';source.write_bytes(b'public-synthetic')
    real_path=Path
    monkeypatch.setattr(smoke,'Path',lambda value:fixtures if str(value)=='/fixtures' else real_path(value))
    monkeypatch.setattr(smoke.sys,'platform','linux')
    locations=[];kills=[]
    class Process:
        pid=987654;returncode=0
        def __init__(self,args,**kwargs):
            assert args[-2]=='--focus-probe' and kwargs['start_new_session'] is True
            assert kwargs['stderr'] is subprocess.DEVNULL
            self.target=real_path(args[-1]);locations.append(self.target.parent);self.calls=0
            assert self.target.read_bytes()==b'public-synthetic'
        def communicate(self,timeout=None):
            self.calls+=1
            if self.calls==1:
                assert timeout==75
                if fault=='timeout':raise subprocess.TimeoutExpired('synthetic-probe',75)
            payload=copy.deepcopy(rows)
            if fault=='bad-schema':payload[0]['raw_text']='private-value'
            return json.dumps(payload).encode(),None
    monkeypatch.setattr(smoke.subprocess,'Popen',Process)
    monkeypatch.setattr(smoke.signal,'SIGKILL',9,raising=False)
    monkeypatch.setattr(smoke.os,'killpg',lambda pid,sig:kills.append((pid,sig)),raising=False)
    if fault=='none':
        smoke.diagnose_ledger_rejections(source)
        output=capsys.readouterr().out
        assert 'DIAG card.jpg' in output and 'private-value' not in output
    else:
        with pytest.raises(RuntimeError):smoke.diagnose_ledger_rejections(source)
        assert capsys.readouterr()==('', '')
    assert locations and all(not path.exists() for path in locations)
    assert kills==([(987654,9)] if fault=='timeout' else [])


def test_smoke_collects_all_four_failures_and_still_fails(smoke,tmp_path,monkeypatch,capsys):
    for name in ('synthetic.png','synthetic.pdf'):(tmp_path/name).write_bytes(b'public-only')
    pension={'document_type':'history','detected_type':'history','fields':[
        {'key':key,'value':value,'status':'OCR 확인 필요'} for key,value in
        [('total_paid_amount',1200000),('paid_months',12),('query_date','2026-10-14')]]}
    def command(args,timeout=30):
        if args[0]=='tesseract':return 'tesseract 5' if '--version' in args else 'kor\neng\nosd\n' if '--list-langs' in args else '국민연금납부내역확인'
        if args[0]=='pdfinfo':return 'Pages: 1\n'
        if args[0]=='pdftotext':return '\f'
        if '-m' in args:return json.dumps(pension)
        return ''
    monkeypatch.setattr(smoke,'command',command)
    monkeypatch.setattr(smoke.sys,'platform','linux')
    monkeypatch.setattr(smoke.platform,'machine',lambda:'aarch64')
    monkeypatch.setattr(smoke.shutil,'which',lambda tool:'/synthetic/'+tool)
    calls=[]
    def failed(fixtures,name,kind,document_type):
        calls.append(name);raise smoke.LedgerOCRError('private exception must not be logged')
    monkeypatch.setattr(smoke,'run_ledger_case',failed)
    monkeypatch.setattr(sys,'argv',['smoke','--fixtures',str(tmp_path),'--expected-machine','aarch64'])
    with pytest.raises(RuntimeError,match='exact-value checks failed'):smoke.main()
    assert calls==['bank.png','bank.pdf','card.jpg','card.pdf']
    output=capsys.readouterr().out
    assert output.count('FAIL: synthetic ledger exact-value check')==4 and 'private exception' not in output


@pytest.mark.parametrize('bad_row',[1,2])
def test_party_diagnostic_distinguishes_first_and_second_failure(smoke,tmp_path,capsys,bad_row):
    result,rows,observer=trace_bank_parties(smoke,tmp_path,bad_row=bad_row,conflict=True)
    assert observer.supported and len(observer.rows)==2
    for index,row in enumerate(rows,1):
        assert row['original_candidate_exists'] is True and row['original_split'] is True
        assert row['refine_called'] is True and row['refine_calls']==1
        assert row['txt_created'] is True and row['tsv_created'] is True
        assert row['output_checks_ok'] is True and row['bbox_valid'] is True and row['overlap'] is False
        assert row['txt_tsv_equal'] is (index!=bad_row)
        if index!=bad_row:
            assert row['txt_split'] is False and row['reread_tsv_split'] is True
            assert row['txt_tsv_spacing_differs'] is True
        assert row['accepted'] is (index!=bad_row)
        assert row['final_party_null'] is (index==bad_row) and row['final_party_exact'] is (index!=bad_row)
        assert row['reject_code']==('txt_tsv_guard' if index==bad_row else 'accepted')
        assert row['review_reasons_allowed'] is True
    smoke.emit_party_report(rows,result)
    output=capsys.readouterr()
    assert 'row=1' in output.out and 'row=2' in output.out and not output.err
    for forbidden in ('가상입금처','가상출금처','다른합성거래처','1234567','11234567','bbox=['):
        assert forbidden not in output.out


def test_party_diagnostic_records_actual_source_quality_rejection(smoke,tmp_path):
    _,rows,_=trace_bank_parties(smoke,tmp_path,low_source=True)
    first,second=rows
    assert first['original_confidence_bucket']=='under30'
    assert first['source_quality_ok'] is False and first['reject_code']=='source_quality_guard'
    assert first['refine_called'] is False and first['refine_calls']==0
    assert first['txt_created'] is None and first['tsv_created'] is None
    assert first['bbox_valid'] is None and first['overlap'] is None
    assert first['final_party_null'] is True and second['accepted'] is True


def test_party_diagnostic_records_actual_low_reread_confidence(smoke,tmp_path):
    _,rows,_=trace_bank_parties(smoke,tmp_path,low_reread=True)
    first=rows[0]
    assert first['refine_called'] is True and first['reread_confidence_bucket']=='30to79'
    assert first['reject_code']=='reread_initial_guard' and first['accepted'] is False
    assert first['txt_tsv_equal'] is None and first['party_format_ok'] is None


def test_party_diagnostic_distinguishes_character_guard_from_evidence_conflict(smoke,tmp_path):
    _,rows,_=trace_bank_parties(smoke,tmp_path,bad_row=1)
    first=rows[0]
    assert first['txt_tsv_equal'] is True and first['party_format_ok'] is False
    assert first['txt_split'] is True and first['reject_code']=='party_format_guard'


def test_party_diagnostic_preserves_accepted_candidate_and_trace_state(smoke,tmp_path):
    previous=sys.gettrace()
    result,rows,_=trace_bank_parties(smoke,tmp_path)
    assert sys.gettrace() is previous
    assert all(row['accepted'] is True and row['final_party_exact'] is True for row in rows)
    assert all(row['party_format_ok'] is True and row['reread_confidence_bucket']=='90plus' for row in rows)
    smoke.validate_ledger_result(result,'bank_transactions')


def test_unsupported_party_trace_is_unknown_not_invented(smoke,tmp_path):
    result,_,observer=trace_bank_parties(smoke,tmp_path)
    observer.supported=False
    rows=smoke.party_report(result,observer)
    assert all(row['observer_supported'] is False and row['refine_called'] is None and
               row['refine_calls'] is None and row['reject_code']=='unknown' for row in rows)
    assert all(row['final_party_exact'] is True for row in rows)


@pytest.mark.parametrize('bad_row',[1,2])
def test_party_failure_triggers_both_row_diagnostics_without_weakening_assertion(smoke,tmp_path,monkeypatch,bad_row):
    from app.services import ledger_document_import as importer
    (tmp_path/'bank.png').write_bytes(b'synthetic-input')
    result=expected_result('bank_transactions');result['rows'][bad_row-1]['counterparty']=None
    calls=[]
    monkeypatch.setattr(importer,'preview',lambda *args:result)
    monkeypatch.setattr(smoke,'diagnose_bank_parties',lambda source,preview:calls.append((source,preview)))
    with pytest.raises(RuntimeError,match='Synthetic Korean ledger party extraction failed'):
        smoke.run_ledger_case(tmp_path,'bank.png','png','bank_transactions')
    assert len(calls)==1 and calls[0][0]==tmp_path/'bank.png' and calls[0][1] is result


@pytest.mark.parametrize('field,value',[('raw_text','private-document'),('reject_code','private-data'),
    ('original_confidence_bucket','private-data'),('refine_called',1),('refine_calls',1000)])
def test_party_diagnostic_rejects_unallowlisted_output_before_logging(smoke,capsys,field,value):
    rows=[smoke.empty_party_evidence(),smoke.empty_party_evidence()];rows[1][field]=value
    with pytest.raises(RuntimeError):smoke.emit_party_report(rows,expected_result('bank_transactions'))
    assert capsys.readouterr()==('', '')


def test_party_diagnostic_rejects_nonfixture_input_without_reading_it(smoke,tmp_path,monkeypatch):
    monkeypatch.setattr(smoke.sys,'platform','linux')
    monkeypatch.setattr(smoke.subprocess,'Popen',lambda *args,**kwargs:pytest.fail('Non-CI documents may not be probed'))
    with pytest.raises(RuntimeError,match='input denied'):
        smoke.diagnose_bank_parties(tmp_path/'bank.png',expected_result('bank_transactions'))


def test_adopted_party_can_be_nullified_by_actual_downstream_parser(smoke,tmp_path):
    _,rows,_=trace_bank_parties(smoke,tmp_path,low_amount=True)
    assert rows[0]['accepted'] is True and rows[0]['reject_code']=='accepted'
    assert rows[0]['final_party_null'] is True and rows[0]['final_party_exact'] is False
    assert rows[1]['accepted'] is True and rows[1]['final_party_exact'] is True


def test_observer_reports_executed_overlap_guard_without_coordinates(smoke,tmp_path):
    from PIL import Image
    from app.services import ledger_document as ledger
    from tests.test_ledger_document_import import positioned_tsv
    image=tmp_path/'prepared.png';Image.new('L',(1800,2000),'white').save(image)
    records=positioned_tsv(['가 상 입 금 처','+1000 원']).splitlines()
    for index,record in enumerate(records):
        fields=record.split('\t')
        if fields[0]=='5' and fields[4]=='2':fields[7]='200';records[index]='\t'.join(fields)
    observer=smoke.PartyObserver(ledger)
    lines=observer.observe(lambda:ledger.LineRecognizer().refine('\n'.join(records),image,
        lambda *args:pytest.fail('Overlapping regions may not invoke OCR')))
    row=observer.records[id(lines[0])]
    assert observer.supported and row['bbox_valid'] is True and row['overlap'] is True
    assert row['refine_called'] is False and row['reject_code']=='overlap_guard'


@pytest.mark.parametrize('failure',['none','timeout','bad-schema','bad-return'])
def test_party_probe_subprocess_scope_is_private_bounded_and_cleaned(smoke,tmp_path,monkeypatch,capsys,failure):
    source=tmp_path/'bank.png';source.write_bytes(b'public-synthetic-only')
    monkeypatch.setattr(smoke.sys,'platform','linux')
    monkeypatch.setattr(smoke,'CI_BANK_FIXTURE',source.resolve())
    locations=[];kills=[]
    class Process:
        pid=987654;returncode=0
        def __init__(self,args,**kwargs):
            assert args[-2]=='--party-probe' and kwargs['start_new_session'] is True
            assert kwargs['stderr'] is subprocess.DEVNULL
            self.input=Path(args[-1]);locations.append(self.input.parent)
            assert self.input.read_bytes()==b'public-synthetic-only'
            self.waits=0
            if failure=='bad-return':self.returncode=1
        def communicate(self,timeout=None):
            self.waits+=1
            if self.waits==1:
                assert timeout==75
                if failure=='timeout':raise subprocess.TimeoutExpired('synthetic-probe',75)
            rows=[smoke.empty_party_evidence(),smoke.empty_party_evidence()]
            if failure=='bad-schema':rows[1]['raw_text']='private-data'
            return json.dumps(rows).encode(),None
    monkeypatch.setattr(smoke.subprocess,'Popen',Process)
    monkeypatch.setattr(smoke.signal,'SIGKILL',9,raising=False)
    monkeypatch.setattr(smoke.os,'killpg',lambda pid,sig:kills.append((pid,sig)),raising=False)
    if failure=='none':
        smoke.diagnose_bank_parties(source,expected_result('bank_transactions'))
        assert 'row=1' in capsys.readouterr().out
    else:
        with pytest.raises(RuntimeError):smoke.diagnose_bank_parties(source,expected_result('bank_transactions'))
        assert capsys.readouterr()==('', '')
    assert locations and all(not path.exists() for path in locations)
    assert kills==([(987654,9)] if failure=='timeout' else [])
    assert source.read_bytes()==b'public-synthetic-only'

@pytest.mark.parametrize('ocr', ['pass','wrong','timeout','unexpected'])
@pytest.mark.parametrize('damage', ['none','changed','deleted','extra','input'])
def test_safety_always_inspected_before_ocr_failure(smoke,tmp_path,monkeypatch,capsys,ocr,damage):
    from app.services import ledger_document_import as importer
    (tmp_path/'card.jpg').write_bytes(b'synthetic-only')
    locations=[]
    def preview(*args):
        data=Path(os.environ['DATA_DIR']);locations.append(data.parent)
        if damage=='changed':(data/'ledger.json').write_bytes(b'changed')
        if damage=='deleted':(data/'ledger.json').unlink()
        if damage=='extra':(data/'extra.json').write_bytes(b'extra')
        if damage=='input':(Path(tempfile.gettempdir())/'orphan').write_bytes(b'orphan')
        if ocr=='timeout':raise subprocess.TimeoutExpired('private-command',75)
        if ocr=='unexpected':raise LookupError('private-payload')
        result=expected_result('card_transactions')
        if ocr=='wrong':result['rows'][0]['amount']=None
        return result
    monkeypatch.setattr(importer,'preview',preview)
    error=smoke.SmokeSafetyError if damage!='none' else LookupError if ocr=='unexpected' else smoke.LedgerOCRError
    if damage=='none' and ocr=='pass':smoke.run_ledger_case(tmp_path,'card.jpg','jpeg','card_transactions')
    else:
        with pytest.raises(error):smoke.run_ledger_case(tmp_path,'card.jpg','jpeg','card_transactions')
    assert locations and all(not path.exists() for path in locations)
    output=capsys.readouterr()
    assert all(value not in output.out+output.err for value in ('private-payload','private-command',str(tmp_path),'changed'))


def test_integrity_check_exceptions_and_symlinks_fail_closed(smoke,tmp_path,monkeypatch):
    data=tmp_path/'data';inputs=tmp_path/'inputs';data.mkdir();inputs.mkdir()
    sentinel=data/'ledger.json';sentinel.write_bytes(b'original')
    original=Path.is_symlink
    monkeypatch.setattr(Path,'is_symlink',lambda path:True if path==sentinel else original(path))
    with pytest.raises(smoke.SmokeSafetyError):smoke.check_ledger_integrity(data,inputs,{sentinel:b'original'})
    monkeypatch.setattr(Path,'is_symlink',original)
    monkeypatch.setattr(Path,'read_bytes',lambda path:(_ for _ in ()).throw(OSError('private-path')))
    with pytest.raises(smoke.SmokeSafetyError):smoke.check_ledger_integrity(data,inputs,{sentinel:b'original'})


def test_workspace_cleanup_failure_overrides_ocr_error(smoke,tmp_path,monkeypatch):
    class BrokenDirectory:
        def __init__(self,**kwargs):pass
        def __enter__(self):return str(tmp_path)
        def __exit__(self,*args):raise OSError('private-path')
    monkeypatch.setattr(smoke.tempfile,'TemporaryDirectory',BrokenDirectory)
    with pytest.raises(smoke.SmokeSafetyError,match='workspace cleanup'):
        with smoke.ledger_workspace():raise smoke.LedgerOCRError('ocr')


@pytest.mark.parametrize('fatal', ['safety','unexpected'])
def test_main_stops_after_first_fatal_failure(smoke,tmp_path,monkeypatch,fatal):
    for name in ('synthetic.png','synthetic.pdf'):(tmp_path/name).write_bytes(b'synthetic')
    pension={'document_type':'history','detected_type':'history','fields':[
        {'key':key,'value':value,'status':'OCR 확인 필요'} for key,value in
        [('total_paid_amount',1200000),('paid_months',12),('query_date','2026-10-14')]]}
    def command(args,timeout=30):
        if args[0]=='tesseract':return 'tesseract 5' if '--version' in args else 'kor\neng\nosd\n' if '--list-langs' in args else '국민연금납부내역확인'
        if args[0]=='pdfinfo':return 'Pages: 1\n'
        if '-m' in args:return json.dumps(pension)
        return ''
    monkeypatch.setattr(smoke,'command',command)
    monkeypatch.setattr(smoke.sys,'platform','linux')
    monkeypatch.setattr(smoke.platform,'machine',lambda:'aarch64')
    monkeypatch.setattr(smoke.shutil,'which',lambda tool:'/synthetic/'+tool)
    calls=[];error=smoke.SmokeSafetyError if fatal=='safety' else LookupError
    def failed(*args):calls.append(args[1]);raise error('fixed-code')
    monkeypatch.setattr(smoke,'run_ledger_case',failed)
    monkeypatch.setattr(sys,'argv',['smoke','--fixtures',str(tmp_path),'--expected-machine','aarch64'])
    with pytest.raises(error):smoke.main()
    assert calls==['bank.png']


def test_diagnostic_safety_error_is_never_swallowed(smoke,tmp_path,monkeypatch):
    from app.services import ledger_document_import as importer
    (tmp_path/'card.jpg').write_bytes(b'synthetic')
    result=expected_result('card_transactions');result['rows'][0]['amount']=None
    monkeypatch.setattr(importer,'preview',lambda *args:result)
    monkeypatch.setattr(smoke,'is_public_ledger_fixture',lambda path:True)
    def fail(path):raise smoke.SmokeSafetyError('fixed-safety-code')
    monkeypatch.setattr(smoke,'diagnose_ledger_rejections',fail)
    with pytest.raises(smoke.SmokeSafetyError):smoke.run_ledger_case(tmp_path,'card.jpg','jpeg','card_transactions')

@pytest.mark.parametrize('ocr_failure',[False,True])
def test_real_case_cleanup_failure_has_safety_priority(smoke,tmp_path,monkeypatch,ocr_failure):
    from app.services import ledger_document_import as importer
    (tmp_path/'card.jpg').write_bytes(b'synthetic')
    original=tempfile.TemporaryDirectory;managers=[]
    class Directory:
        def __init__(self,**kwargs):self.inner=original(**kwargs);managers.append(self.inner)
        def __enter__(self):return self.inner.__enter__()
        def __exit__(self,*args):
            self.inner.__exit__(*args)
            raise OSError('private-cleanup-path')
    monkeypatch.setattr(smoke.tempfile,'TemporaryDirectory',Directory)
    def preview(*args):
        if ocr_failure:raise subprocess.TimeoutExpired('private-command',75)
        return expected_result('card_transactions')
    monkeypatch.setattr(importer,'preview',preview)
    with pytest.raises(smoke.SmokeSafetyError):smoke.run_ledger_case(tmp_path,'card.jpg','jpeg','card_transactions')
    assert managers and all(not Path(m.name).exists() for m in managers)


def test_unknown_validation_exception_is_not_general_ocr_failure(smoke,tmp_path,monkeypatch):
    from app.services import ledger_document_import as importer
    (tmp_path/'card.jpg').write_bytes(b'synthetic')
    monkeypatch.setattr(importer,'preview',lambda *args:expected_result('card_transactions'))
    def invalid(*args):raise RuntimeError('unknown-private-error')
    monkeypatch.setattr(smoke,'validate_ledger_result',invalid)
    with pytest.raises(RuntimeError) as error:smoke.run_ledger_case(tmp_path,'card.jpg','jpeg','card_transactions')
    assert type(error.value) is RuntimeError and not isinstance(error.value,smoke.LedgerOCRError)

@pytest.mark.parametrize('code',[2,3])
@pytest.mark.parametrize('probe',['party','focus'])
def test_probe_fatal_exit_codes_propagate_safety(smoke,tmp_path,monkeypatch,capsys,code,probe):
    source=tmp_path/'bank.png';source.write_bytes(b'public-synthetic')
    monkeypatch.setattr(smoke.sys,'platform','linux')
    monkeypatch.setattr(smoke,'CI_BANK_FIXTURE',source.resolve())
    monkeypatch.setattr(smoke,'is_public_ledger_fixture',lambda path:True)
    locations=[]
    class Process:
        returncode=code
        def __init__(self,args,**kwargs):locations.append(Path(args[-1]).parent)
        def communicate(self,timeout=None):return b'private-output-must-not-log',None
    monkeypatch.setattr(smoke.subprocess,'Popen',Process)
    with pytest.raises(smoke.SmokeSafetyError):
        if probe=='party':smoke.diagnose_bank_parties(source,expected_result('bank_transactions'))
        else:smoke.diagnose_ledger_rejections(source)
    assert locations and all(not path.exists() for path in locations)
    assert capsys.readouterr()==('', '')

@pytest.mark.parametrize('fault',['none','neighbor','page-edge','source-clipped','reread-clipped','low-confidence'])
def test_isolation_observes_actual_party_expansion_branch(smoke,tmp_path,fault,capsys):
    from PIL import Image
    from app.services import ledger_document as ledger
    from tests.test_ledger_document_import import positioned_tsv,crop_tsv
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    records=positioned_tsv([]).splitlines()[:2]
    left=10 if fault=='page-edge' else 1 if fault=='source-clipped' else 100
    records.append(f'5\t1\t1\t1\t1\t1\t{left}\t200\t300\t40\t95\t가 상 입 금 처')
    if fault=='neighbor':records.append('5\t1\t1\t1\t2\t1\t100\t250\t300\t40\t95\t10:20')
    calls=[]
    def run(args,timeout):
        calls.append(args)
        crop_tsv(args,'가 상 입 금 처',txt='가상입금처',confidence=89 if fault=='low-confidence' else 95)
        if fault=='reread-clipped':
            path=Path(args[2]+'.tsv');lines=path.read_text(encoding='utf-8').splitlines()
            fields=lines[2].split('\t');fields[6]='1';lines[2]='\t'.join(fields)
            path.write_text('\n'.join(lines),encoding='utf-8')
        return b''
    observer=smoke.FocusObserver(ledger)
    observer.observe(lambda:ledger.LineRecognizer().refine('\n'.join(records),image,run))
    rows=smoke.focus_report(observer,'bank_transactions')
    row=next(row for row in rows if row['kind']=='bank_party')
    assert observer.supported
    if fault=='source-clipped':
        assert not calls and row['expanded_inside_page'] is None and row['expanded_crop_used'] is None
        assert row['reread_confidence_ok'] is None and row['party_format_ok'] is None
    else:
        assert calls and row['expanded_inside_page']==(fault!='page-edge')
        assert row['expanded_neighbor_overlap']==(fault=='neighbor')
        assert row['expanded_crop_used']==(fault not in ('neighbor','page-edge'))
        assert row['reread_row_clipped']==(fault=='reread-clipped')
        assert row['reread_confidence_ok']==(fault!='low-confidence')
        assert row['accepted']==(fault not in ('reread-clipped','low-confidence'))
        if fault in ('reread-clipped','low-confidence'):
            assert row['txt_tsv_equal'] is None and row['party_format_ok'] is None
    smoke.emit_focus_report(rows,'bank.png')
    output=capsys.readouterr().out
    assert all(private not in output for private in ('가상입금처',str(tmp_path),'300','200'))
    assert not list(tmp_path.glob('line-*'))


@pytest.mark.parametrize('old,new,space,units,tokens,action,party',[
    ('승인 금액','승인금액',True,False,False,False,None),
    ('승인 원','승인 KRW',False,True,False,False,None),
    ('승인:','승인/',False,True,False,False,None),
    ('승인금액','이용금액',False,False,True,True,None),
    ('승인','취소',False,False,True,True,None),
    ('취소','환불',False,False,True,True,None),
    ('가맹점:가상카페','가맹점:가상서점',False,False,True,False,True),
    ('거래처:가상카페','거래처:가상카페',False,False,False,False,False),
    (None,'승인',None,None,None,None,None),
])
def test_isolation_context_differences_are_diagnostic_only(smoke,old,new,space,units,tokens,action,party):
    report=smoke.context_difference_checks(old,new)
    assert tuple(report.values())==(space,units,tokens,action,party)


def test_isolation_context_observed_from_real_numeric_guard(smoke,tmp_path):
    from PIL import Image
    from app.services import ledger_document as ledger
    from tests.test_ledger_document_import import positioned_tsv,crop_tsv
    image=tmp_path/'page.png';Image.new('L',(1800,2000),'white').save(image)
    original=positioned_tsv(['승인금액 12,345 원'])
    observer=smoke.FocusObserver(ledger)
    lines=observer.observe(lambda:ledger.LineRecognizer().refine(original,image,
        lambda args,timeout:crop_tsv(args,'승인 12,345 원')))
    report=smoke.focus_report(observer,'card_transactions')[0]
    assert report['context_nonnumeric_tokens_differ'] is True
    assert report['context_action_differ'] is False and report['context_whitespace_only'] is False
    assert report['context_party_related_tokens_differ'] is None
    assert report['numeric_values_equal'] is True and report['numeric_sign_equal'] is True
    assert report['numeric_context_equal'] is False and report['accepted'] is False
    assert report['reject_code']=='numeric_guard' and lines[0]['text']=='승인금액 12,345 원'


@pytest.mark.parametrize('kind',['bank_transactions','card_transactions'])
def test_isolation_exact_fields_independent_of_first_strict_failure(smoke,kind):
    result=expected_result(kind)
    assert all(all(value is True for value in row.values()) for row in smoke.exact_ledger_report(result,kind))
    key='counterparty' if kind=='bank_transactions' else 'merchant'
    result['rows'][0][key]=None
    result['rows'][1]['amount']=None
    report=smoke.exact_ledger_report(result,kind)
    assert report[0]['party'] is False and report[0]['amount'] is True
    assert report[1]['party'] is True and report[1]['amount'] is False
    assert report[0]['summary_excluded'] is None
    assert all(row['year_null'] and row['owner_null'] and row['review_required'] for row in report)
    with pytest.raises(smoke.SmokeCheckError):smoke.validate_ledger_result(result,kind)


@pytest.mark.parametrize('field,key,value',[
    ('direction','direction','outflow'),('balance','balance_after',None),
    ('time','transaction_time',None),('owner_null','owner','synthetic-owner'),
    ('review_required','review_status','confirmed'),
])
def test_isolation_exact_field_failure_does_not_mask_other_fields(smoke,field,key,value):
    result=expected_result('bank_transactions');result['rows'][0][key]=value
    report=smoke.exact_ledger_report(result,'bank_transactions')
    assert report[0][field] is False and all(v is True for v in report[1].values())


def test_isolation_exact_unknown_missing_dates_and_summary(smoke):
    assert all(all(value is None for value in row.values()) for row in smoke.exact_ledger_report(None,'bank_transactions'))
    result=expected_result('bank_transactions')
    result['rows'][0]['transaction_date_parts']={'year':2026,'month':11,'day':14}
    result['rows'][0]['counterparty']='총 잔액'
    result['rows'].append(dict(result['rows'][0]))
    report=smoke.exact_ledger_report(result,'bank_transactions')
    assert report[0]['month_day'] is False and report[0]['year_null'] is False
    assert report[0]['row_count'] is False and report[0]['summary_excluded'] is False
    result['rows']=[]
    report=smoke.exact_ledger_report(result,'bank_transactions')
    assert all(row['row_count'] is False and row['party'] is False and row['owner_null'] is False for row in report)


def test_isolation_exact_log_denies_private_inputs_and_never_prints_values(smoke,tmp_path,monkeypatch,capsys):
    source=tmp_path/'bank.png'
    with pytest.raises(smoke.SmokeCheckError):smoke.emit_exact_report(expected_result('bank_transactions'),source,'bank_transactions')
    assert capsys.readouterr()==('', '')
    monkeypatch.setattr(smoke,'is_public_ledger_fixture',lambda path:True)
    result=expected_result('bank_transactions');result['raw_text']='private-payload'
    smoke.emit_exact_report(result,source,'bank_transactions')
    output=capsys.readouterr().out
    assert output.count('EXACT bank.png row=')==2
    assert all(value not in output for value in ('가상','1234567',str(tmp_path),'private-payload','[100'))

@pytest.mark.parametrize('name,kind',[
    ('bank.png','bank_transactions'),('bank.pdf','bank_transactions'),
    ('card.jpg','card_transactions'),('card.pdf','card_transactions')])
def test_isolation_exact_reports_each_public_format(smoke,tmp_path,monkeypatch,capsys,name,kind):
    monkeypatch.setattr(smoke,'is_public_ledger_fixture',lambda path:True)
    smoke.emit_exact_report(expected_result(kind),tmp_path/name,kind)
    output=capsys.readouterr().out
    assert output.count('EXACT '+name+' row=')==2
    assert '=false' not in output and '=unknown' not in output
    assert all(field+'=true' in output for field in smoke.EXACT_FIELDS)


def test_isolation_unsupported_observation_does_not_invent_checks(smoke,tmp_path):
    _,_,observer=trace_focused_numeric(smoke,tmp_path,card=True)
    observer.supported=False
    rows=smoke.focus_report(observer,'bank_transactions')
    party=next(row for row in rows if row['kind']=='bank_party')
    assert all(party[key] is None for key in ('expanded_crop_used','expanded_inside_page',
        'expanded_neighbor_overlap','reread_row_clipped','reread_text_too_small',
        'reread_other_risks','txt_printable','output_geometry_ok','reread_confidence_ok',
        'txt_tsv_equal','party_format_ok','accepted'))

@pytest.mark.parametrize('old,new',[
    ('가맹점:강원상점','가맹점:가상학원'),
    ('가맹점:승인카페','가맹점:취소서점')])
def test_isolation_merchant_syllables_are_not_currency_or_action_labels(smoke,old,new):
    report=smoke.context_difference_checks(old,new)
    assert report['context_units_symbols_differ'] is False
    assert report['context_action_differ'] is False
    assert report['context_nonnumeric_tokens_differ'] is True
    assert report['context_party_related_tokens_differ'] is True
