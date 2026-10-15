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
    assert '+1,234,567원' in generator.BANK_LINES and '-234,567원' in generator.BANK_LINES
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


def test_command_failure_never_logs_raw_decoder_output(smoke,monkeypatch,capsys):
    def run(*args,**kwargs):
        return subprocess.CompletedProcess(args[0],1,b'private-document-text',b'private-file-name')
    monkeypatch.setattr(smoke.subprocess,'run',run)
    with pytest.raises(RuntimeError) as error:smoke.command(['tesseract','private-file-name'])
    assert 'private' not in str(error.value) and capsys.readouterr()==('', '')
