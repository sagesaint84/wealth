"""Synthetic document content and isolated users only; no external OCR or real documents."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.services import national_pension as np, national_pension_import as imp, portfolio, savings
from tests.test_national_pension_history import users

HISTORY='''국민연금 가입내역조회
성명 합성검증인 발급번호 SYNTHETIC-PRIVATE
조회일 2026.10.14
납부한 보험료 총액 9,000,000원
실제 납부 월수 120개월
미납 보험료 30,000원
미납 월수 2개월
납입예정 금액 20,000원
납입예정 월수 1개월
납부할 수 없는 보험료 10,000원
납부할 수 없는 월수 1개월
예상 월 연금액 200,000원
예상 연금 개시월 2045.01
현재가치
향후 총 예상 납부액 300,000원
2013.01~2014.12 사업장 기준소득월액 1,000,000 실제납부 240,000 납부월수 24 미납금액 0 미납월수 0
2015.01~2015.12 지역 기준소득월액 2,000,000 실제납부 150,000 납부월수 6 미납금액 30,000 미납월수 2
2025년 실제 납부액 100,000원
'''
CERT='''연금보험료 소득공제용 납부확인서
귀속연도 2025
발행일 2026.01.20
1월 사업장 고지금액 100,000원
2월 지역 납부금액 50,000원
연간 합계 150,000원
추가 보험료 0원
'''


def request_payload(item,**fields):
    return dict(fingerprint='a'*64,expected=imp.snapshot(item),annual=[],
                metadata=dict(document_type='history',fields=fields,periods=[],monthly=[]))


def item():
    return portfolio.read_portfolio('alice')['insurance_accounts'][0]


def test_history_has_no_personal_identity_no_annual_apportionment_and_no_unpaid_addition():
    result=imp.parse_text(HISTORY)
    fields={row['key']:row['value'] for row in result['fields']}
    assert fields['total_paid_amount']==9000000 and fields['unpaid_amount']==30000
    assert fields['paid_months']==120 and fields['scheduled_months']==1
    assert fields['monthly_payout']==200000 and fields['pension_start']=='2045-01-01'
    assert len(result['periods'])==2 and result['periods'][0]['paid']==240000
    assert result['periods'][1]['income_base']==2000000
    assert all(row['personal_paid'] is None and row['workplace_role']=='unknown' for row in result['periods'])
    assert result['annual']==[dict(year='2025',deposit=100000,status='정확히 추출됨')]
    serialized=json.dumps(result,ensure_ascii=False)
    assert '합성검증인' not in serialized and 'SYNTHETIC-PRIVATE' not in serialized
    assert '2013' not in [row['year'] for row in result['annual']]
    assert any('기간별 실제 납부 합계' in msg for msg in result['warnings'])


def test_certificate_keeps_billed_paid_separate_and_detects_bad_sum_ocr_and_duplicates():
    result=imp.parse_text(CERT,ocr=True)
    assert result['document_type']=='certificate' and result['annual']==[]
    assert [row['kind'] for row in result['monthly']]==['billed','paid']
    assert result['monthly'][0]['status']=='실제 납부 여부 미확인'
    assert result['monthly'][1]['status']=='OCR 확인 필요'
    assert not result['warnings']
    assert any('합계 불일치' in msg for msg in imp.parse_text(CERT.replace('150,000','160,000'))['warnings'])
    bad=imp.parse_text(CERT.replace('50,000','5O,000'))
    assert len(bad['monthly'])==1 and any('숫자' in msg for msg in bad['warnings'])
    duplicated=imp.parse_text(CERT+'1월 사업장 고지금액 100,000원\n')
    assert any('중복' in msg for msg in duplicated['warnings'])
    assert imp.parse_text('분류가 없는 합성 문서')['document_type']=='unknown'
    assert imp.parse_text('가입내역조회 소득공제용 납부확인서')['document_type']=='unknown'


def test_explicit_table_headers_are_parsed_without_guessing_or_splitting_years():
    result=imp.parse_text('가입내역조회\n기간  가입종별  기준소득월액  실제 납부액  납부 월수  미납액\n2013.01~2014.12  사업장  1,000,000  240,000  24  30,000\n')
    assert result['periods'][0]['paid']==240000 and result['periods'][0]['unpaid']==30000
    assert result['periods'][0]['personal_paid'] is None and result['annual']==[]
    cert=imp.parse_text('소득공제용 납부확인서\n귀속연도 2025\n월  사업장 고지금액  지역 납부금액\n1  100,000  -\n2  -  50,000\n연간 합계 150,000\n')
    assert [row['kind'] for row in cert['monthly']]==['billed','paid']
    assert not cert['warnings'] and cert['annual']==[]


def test_concurrent_import_snapshots_cannot_silently_lose_updates(users):
    from concurrent.futures import ThreadPoolExecutor
    original=item()
    requests=[request_payload(original,unpaid_amount=value) for value in (100,200)]
    def write(payload):
        try:return imp.apply('alice-np','alice',payload)['item']
        except np.PensionConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,requests))
    assert sum(result=='conflict' for result in results)==1
    assert item()['national_pension_import']['fields']['unpaid_amount'] in {100,200}
    assert item()['total_paid_amount']==original['total_paid_amount']


def test_partial_approved_save_reimport_roundtrip_and_existing_product_edits_preserve_metadata(users):
    original=deepcopy(item());bob=(users/'bob/portfolio.json').read_bytes()
    payload=request_payload(original,unpaid_amount=30000)
    payload['annual']=[dict(year='2025',deposit=123456)]
    first=imp.apply('alice-np','alice',payload)['item']
    for key,value in original.items():
        if key not in {'yearly_contributions','national_pension_import'}: assert first[key]==value
    assert first['yearly_contributions']==[dict(year='2025',deposit=123456)]
    payload['expected']=imp.snapshot(first)
    second=imp.apply('alice-np','alice',payload)['item']
    assert second['yearly_contributions']==first['yearly_contributions']
    # Explicit approval alone permits changing the financial source field, without revaluing assets.
    approved=request_payload(second,total_paid_amount=9100000,monthly_payout=220000)
    third=imp.apply('alice-np','alice',approved)['item']
    assert third['total_paid_amount']==9100000 and third['monthly_payout']==220000
    assert third['expected_amount']==original['expected_amount'] and third['converted_total_asset']==original['converted_total_asset']
    # Existing stored approved amount must not later overwrite an unselected financial field.
    stored=deepcopy(third);stored['total_paid_amount']=9200000
    data=portfolio.read_portfolio('alice');data['insurance_accounts'][0]=stored;portfolio.write_portfolio(data,'alice')
    fourth=imp.apply('alice-np','alice',request_payload(stored,paid_months=120))['item']
    assert fourth['total_paid_amount']==9200000
    assert fourth['national_pension_import']['fields']['unpaid_amount']==30000
    assert (users/'bob/portfolio.json').read_bytes()==bob
    updated=savings.save_insurance_account({**fourth,'product_name':'합성 수정'},'alice')
    assert updated['national_pension_import']==fourth['national_pension_import']


@pytest.mark.parametrize('change',[
    dict(fields={'unpaid_amount':float('nan')}),dict(fields={'total_paid_amount':-1}),
    dict(fields={'personal_paid':100}),dict(fields={'paid_months':1.5}),
    dict(periods=[dict(start='2025-12',end='2025-01')]),
    dict(periods=[dict(start='2024-01',end='2025-01'),dict(start='2025-01',end='2026-01')]),
    dict(monthly=[dict(year=2025,month=1,kind='billed',amount=10)]*2),
    dict(fields={'annual_total':20},monthly=[dict(year=2025,month=1,kind='billed',amount=10)]),
])
def test_invalid_input_never_partially_writes(users,change):
    path=users/'alice/portfolio.json';before=path.read_bytes();payload=request_payload(item())
    payload['metadata'].update(change)
    with pytest.raises(ValueError): imp.apply('alice-np','alice',payload)
    assert path.read_bytes()==before


def test_conflict_other_user_and_wrong_product_never_write(users):
    payload=request_payload(item(),unpaid_amount=10)
    payload['expected']['total_paid_amount']=1
    before=(users/'alice/portfolio.json').read_bytes()
    with pytest.raises(np.PensionConflict): imp.apply('alice-np','alice',payload)
    with pytest.raises(LookupError): imp.apply('bob-np','alice',payload)
    with pytest.raises(ValueError): imp.apply('alice-yu','alice',payload)
    assert (users/'alice/portfolio.json').read_bytes()==before


def test_preview_private_temp_cleanup_mime_comparison_and_no_writes(users,monkeypatch):
    seen=[]
    class Worker:
        returncode=0
        def __init__(self,args,**kwargs):
            path=Path(args[-3]);seen.append(path);assert path.is_file()
            assert kwargs['stderr'] is imp.subprocess.DEVNULL
            if os.name=='posix': assert path.stat().st_mode&0o777==0o600 and path.parent.stat().st_mode&0o777==0o700
        def communicate(self,timeout):return json.dumps(imp.parse_text(HISTORY)).encode(),None
    monkeypatch.setattr(imp.subprocess,'Popen',Worker)
    before=(users/'alice/portfolio.json').read_bytes()
    result=imp.preview('alice-np','alice',b'%PDF-synthetic','application/pdf')
    assert result['fingerprint']==hashlib.sha256(b'%PDF-synthetic').hexdigest()
    assert result['fields'][0]['comparison']=='기존 값과 불일치'
    dates={row['key']:row['value'] for row in json.loads(json.dumps(result))['fields']
           if row['key'] in {'query_date','issued_date','pension_start'}}
    assert dates=={'query_date':'2026-10-14','pension_start':'2045-01-01'}
    assert all(not path.exists() for path in seen)
    assert (users/'alice/portfolio.json').read_bytes()==before
    for data,mime in [(b'bad','image/png'),(b'%PDF-x','image/jpeg'),(b'x'*(imp.MAX_BYTES+1),'application/pdf')]:
        with pytest.raises(ValueError): imp.preview('alice-np','alice',data,mime)
    with pytest.raises(LookupError): imp.preview('bob-np','alice',b'%PDF-x','application/pdf')


def test_all_date_fields_worker_preview_review_and_storage_json_round_trip(users,monkeypatch):
    from app.services import national_pension_document as worker
    source=HISTORY+'\n발행일 2026.10.13\n'
    expected_dates={'query_date':'2026-10-14','issued_date':'2026-10-13','pension_start':'2045-01-01'}
    parsed=imp.parse_text(source)
    encoded=worker.encode_result(parsed)
    decoded=json.loads(encoded)
    assert decoded==parsed
    assert {row['key']:row['value'] for row in decoded['fields'] if row['key'] in expected_dates}==expected_dates
    process=Mock(returncode=0,communicate=Mock(return_value=(encoded.encode('utf-8'),None)))
    monkeypatch.setattr(imp.subprocess,'Popen',lambda *args,**kwargs:process)
    path=users/'alice/portfolio.json';before=path.read_bytes();original=deepcopy(item())
    bob_before=(users/'bob/portfolio.json').read_bytes()
    preview=imp.preview('alice-np','alice',b'%PDF-date-fixture','application/pdf')
    assert path.read_bytes()==before
    # JSON round trip models the API response and browser-selected request body.
    reviewed=json.loads(json.dumps(preview,allow_nan=False))
    payload=dict(fingerprint=reviewed['fingerprint'],expected=reviewed['expected'],annual=[],
                 metadata=dict(document_type=reviewed['document_type'],fields={
                     row['key']:row['value'] for row in reviewed['fields'] if row['key'] in expected_dates},periods=[],monthly=[]))
    response=imp.apply('alice-np','alice',json.loads(json.dumps(payload)))
    assert json.loads(json.dumps(response))['item']['national_pension_import']['fields']==expected_dates
    persisted=json.loads(path.read_text(encoding='utf-8'))['insurance_accounts'][0]
    assert persisted['national_pension_import']['fields']==expected_dates
    assert all(isinstance(value,str) for value in persisted['national_pension_import']['fields'].values())
    for key,value in original.items():assert persisted[key]==value
    assert (users/'bob/portfolio.json').read_bytes()==bob_before


@pytest.mark.parametrize('key,label', [('query_date','조회일'),('issued_date','발행일'),('pension_start','예상 연금 개시월')])
def test_missing_or_invalid_import_dates_are_not_fabricated_or_saved(users,key,label):
    assert not any(row['key']==key for row in imp.parse_text('가입내역조회')['fields'])
    result=imp.parse_text(f'가입내역조회\n{label} 2026.02.30\n')
    assert not any(row['key']==key for row in result['fields'])
    assert any(label in message for message in result['warnings'])
    before=(users/'alice/portfolio.json').read_bytes()
    for invalid in ('2026-02-30','2026-2-01',None,np.date(2026,2,1)):
        payload=request_payload(item(),**{key:invalid})
        with pytest.raises(ValueError):imp.apply('alice-np','alice',payload)
        assert (users/'alice/portfolio.json').read_bytes()==before


def test_worker_json_failure_never_changes_financial_data(users):
    from app.services import national_pension_document as worker
    before=(users/'alice/portfolio.json').read_bytes()
    with pytest.raises(TypeError):worker.encode_result({'fields':[{'key':'query_date','value':np.date(2026,10,14)}]})
    assert (users/'alice/portfolio.json').read_bytes()==before


def test_worker_error_has_no_raw_error_output_and_temp_is_removed(users,monkeypatch):
    seen=[]
    def worker(args,**kwargs):
        seen.append(Path(args[-3]));return Mock(returncode=1,communicate=Mock(return_value=(b'PRIVATE_SYNTHETIC',None)))
    monkeypatch.setattr(imp.subprocess,'Popen',worker)
    with pytest.raises(ValueError) as error: imp.preview('alice-np','alice',b'%PDF-x','application/pdf')
    assert 'PRIVATE_SYNTHETIC' not in str(error.value)
    assert all(not path.exists() for path in seen)


def test_decoder_timeout_cleans_private_files_and_does_not_write(users,monkeypatch):
    seen=[];signals=[]
    process=Mock(pid=12345,returncode=1)
    process.communicate.side_effect=[imp.subprocess.TimeoutExpired('private-command',75),(b'',None)]
    def worker(args,**kwargs):seen.append(Path(args[-3]));return process
    monkeypatch.setattr(imp.subprocess,'Popen',worker)
    monkeypatch.setattr(imp.os,'killpg',lambda pid,sig:signals.append(pid),raising=False)
    before=(users/'alice/portfolio.json').read_bytes()
    with pytest.raises(ValueError) as error:imp.preview('alice-np','alice',b'%PDF-x','application/pdf')
    assert 'private-command' not in str(error.value)
    if os.name=='posix':assert signals==[12345]
    else:process.kill.assert_called_once()
    assert all(not path.exists() for path in seen)
    assert (users/'alice/portfolio.json').read_bytes()==before


def test_docker_offline_native_dependencies_and_existing_auth_smoke_preserved():
    root=Path(__file__).resolve().parents[1];docker=(root/'Dockerfile').read_text(encoding='utf-8')
    for name in ('poppler-utils','tesseract-ocr-kor','tesseract-ocr-eng','tesseract-ocr-osd','python:3.11-slim-bookworm'):
        assert name in docker
    # PR #171 wraps the offline smoke to clean QEMU cores without masking failure.
    offline_run = docker.split('RUN --network=none ', 1)[1].split('\n\n', 1)[0]
    assert 'set -eu;' in offline_run
    assert 'smoke_status=0;' in offline_run
    assert '/opt/toss-auth/venv/bin/python /opt/toss-auth/browser_smoke.py || smoke_status=$?;' in offline_run
    assert 'exit "$smoke_status"' in offline_run
    assert 'Pillow==12.3.0' in (root/'requirements.txt').read_text(encoding='utf-8')
