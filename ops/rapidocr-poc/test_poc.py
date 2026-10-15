"""Synthetic harness regression, not evidence of actual Linux OCR accuracy."""
import ast
from contextlib import contextmanager
import importlib.util
import io
from pathlib import Path
import re
import os
import subprocess
import sys

import pytest
import yaml

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))


def module(name):
    spec=importlib.util.spec_from_file_location('poc_'+name,HERE/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


worker=module('worker'); runner=module('run'); prepare=module('prepare')


def test_geometry_preserves_engine_word_spaces_and_never_repairs_syllables():
    lines=worker.merge_boxes([('가 상 입 금 처',95,[0,0,100,20]),('가상 두 단어',96,[0,40,100,20])])
    assert [line['text'] for line in lines]==['가 상 입 금 처','가상 두 단어']


def test_geometry_orders_fragments_without_using_expected_values():
    lines=worker.merge_boxes([('원',99,[200,10,20,20]),('+1,234,567',99,[10,9,170,20])])
    assert lines[0]['text']=='+1,234,567 원'


@pytest.mark.parametrize('width,reason',[(221,'image_low_resolution'),(135,'image_low_resolution')])
def test_small_images_retain_existing_risk(width,reason):
    lines=worker.apply_geometry([{'text':'가상','bbox':[10,20,50,15],'confidence':99,'reasons':[]}],width,100)
    assert reason in lines[0]['reasons']


@pytest.mark.parametrize('text',['승인금액 12.345 원','승인금액 12345 원','승인금액 123,450 원'])
def test_numeric_comparison_does_not_repair_bad_separators_or_digits(text):
    assert not worker.ocr_metrics([{'text':text}],['승인금액 12,345 원'])['numeric_exact']


def test_sign_loss_cannot_pass_raw_numeric_comparison():
    assert not worker.ocr_metrics([{'text':'234,567 원'}],['-234,567 원'])['numeric_exact']


def test_one_duplicate_numeric_token_is_not_two():
    assert not worker.ocr_metrics([{'text':'12,345 원'}],['12,345 원','12,345 원'])['numeric_exact']


@pytest.mark.parametrize('kind',['history','certificate'])
def test_actual_pension_parser_contract_and_json_without_financial_write(kind,tmp_path):
    # Guarded aliases live only in this disposable subprocess, never leak into
    # any existing tests sharing pytest's interpreter.
    code='''import importlib.util,sys,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('pocworker',Path(sys.argv[1])/'worker.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
calls=w.guard_finance()
from app.services.national_pension_import import parse_text
kind=sys.argv[2]
heading='국민연금 가입내역조회' if kind=='history' else '국민연금 소득공제 납부확인'
text=heading+'\\n납부한 보험료 총액 1200000원\\n실제 납부 월수 12개월\\n조회일 2026.10.14'
result=parse_text(text,ocr=True)
checks,ok=w.pension_checks(result,kind,[text],False)
assert ok and all(checks.values()) and not calls
assert json.loads(json.dumps(result,allow_nan=False))==result
print('PASS')
'''
    result=subprocess.run([sys.executable,'-c',code,str(HERE),kind],capture_output=True,
                          env={**os.environ,'WEALTH_ENV':'test','WEALTH_DISABLE_ENV_FILE':'1',
                               'WEALTH_DATA_DIR':str(tmp_path/'finance'),'PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode==0,result.stderr.decode(errors='replace')
    assert result.stdout.strip()==b'PASS'
    assert not (tmp_path/'finance').exists()


def test_pension_wrong_date_and_missing_field_do_not_pass():
    result={'document_type':'history','detected_type':'history','fields':[]}
    _,ok=worker.pension_checks(result,'history',[''],False)
    assert not ok


def test_page_order_is_checked_independently():
    result={'document_type':'history','detected_type':'history','fields':[]}
    checks,_=worker.pension_checks(result,'history',['2026.10.15','2026.10.14'],True)
    assert not checks['page_order']


@pytest.mark.parametrize('status',['FAIL','BLOCKED','PENDING'])
def test_any_nonpass_keeps_gate_failed(status):
    assert not runner.final_pass([{'status':'PASS'},{'status':status}])
    assert not runner.final_pass([])


def test_checksum_failure_halts_before_fixture_creation(tmp_path,monkeypatch):
    @contextmanager
    def response(*args,**kwargs):yield io.BytesIO(b'not-the-model')
    monkeypatch.setattr(prepare.urllib.request,'urlopen',response)
    with pytest.raises(ValueError,match='MODEL_CHECKSUM_FAIL'):
        prepare.prepare(tmp_path/'bundle',tmp_path/'font.ttf')
    assert not (tmp_path/'bundle/fixtures').exists()


@pytest.mark.parametrize('arch',['amd64','arm64'])
def test_locks_are_complete_pinned_and_hash_required(arch):
    rows=[line for line in (HERE/f'requirements-{arch}.lock').read_text().splitlines() if not line.startswith('#')]
    assert len(rows)==26
    assert all(re.fullmatch(r'[\w.-]+==[\w.+-]+ --hash=sha256:[0-9a-f]{64}',line) for line in rows)
    assert any(line.startswith('rapidocr==3.9.2 ') for line in rows)
    assert any(line.startswith('onnxruntime==1.24.3 ') for line in rows)


def test_workflow_is_native_readonly_and_separate_from_main():
    data=yaml.load((ROOT/'.github/workflows/rapidocr-native-poc.yml').read_text(),Loader=yaml.BaseLoader)
    assert data['on']['pull_request']['branches']==['codex/v202-ledger-ipo-ocr-import']
    assert 'pull_request_target' not in data['on']
    assert data['permissions']=={'contents':'read'}
    job=data['jobs']['native-poc']
    assert job['strategy']['fail-fast']=='false' and job['timeout-minutes']=='45'
    assert {row['runner'] for row in job['strategy']['matrix']['include']}=={'ubuntu-24.04','ubuntu-24.04-arm'}
    assert data['jobs']['native-poc']['steps'][0]['with']['persist-credentials']=='false'


def test_limits_precede_heavy_imports_and_no_ocr_text_print():
    tree=ast.parse((HERE/'worker.py').read_text(encoding='utf-8'))
    top_imports=[node for node in tree.body if isinstance(node,(ast.Import,ast.ImportFrom))]
    assert not any('rapidocr' in ast.unparse(node) or 'onnxruntime' in ast.unparse(node) for node in top_imports)
    source=(HERE/'worker.py').read_text(encoding='utf-8')
    assert source.index('resource.setrlimit(resource.RLIMIT_AS')<source.index('result=execute(args.bundle')
    assert 'print(json.dumps(result,allow_nan=False)' in source
    runner_source=(HERE/'run.py').read_text()
    for option in ["'--network','none'","'--read-only'","'--cap-drop','ALL'","'no-new-privileges'","'65534:65534'"]:
        assert option in runner_source
