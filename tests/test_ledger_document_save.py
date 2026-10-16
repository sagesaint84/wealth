"""User-confirmed ledger drafts. Synthetic temp users only; no OCR/server APIs."""
import asyncio
import copy
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from app.services import ledger, portfolio, user_manager
from app.services.financial_json import FinancialStorageError


@pytest.fixture
def users(tmp_path, monkeypatch):
    root=tmp_path/'users'
    monkeypatch.setattr(user_manager,'USERS_DIR',root)
    # Preview resolves USERS_DIR directly, while canonical writers/RMW locks use
    # service getters. Bind both to this fixture, independent of older tests'
    # leaked get_user_data_dir mocks. No lookup creates a directory.
    monkeypatch.setattr(ledger, 'get_ledger_path',
        lambda username=None: root/(username or 'sagesaint')/'ledger.json')
    monkeypatch.setattr(portfolio, '_get_portfolio_file',
        lambda username=None: root/(username or 'sagesaint')/'portfolio.json')
    return root


def row(**changes):
    return {'date':'2026-10-14','amount':'12345','type':'expense','owner':'아빠',
        'category':'식비/외식','direction':'outflow','source_kind':'normal',
        'merchant':'합성상점','transaction_time':'','memo':'',
        'special_confirmed':False,'duplicate_confirmed':False,**changes}


def request_for(rows, username='alice', **changes):
    review=ledger.review_document_transactions(rows,username)
    return {'rows':copy.deepcopy(rows),'revision':review['revision'],'review_token':review['review_token'],
        'confirmed':True,**changes}


def saved(users,username='alice'):
    return json.loads((users/username/'ledger.json').read_text(encoding='utf-8'))


def seed(users,username='alice',data=None):
    parent=users/username;parent.mkdir(parents=True,exist_ok=True)
    path=parent/'ledger.json';path.write_text(json.dumps(data or ledger.default_ledger_data()),encoding='utf-8')
    return path


def test_review_and_options_never_create_user_or_financial_paths(users):
    assert ledger.document_import_options('alice')['owners']==['아빠','엄마','자녀','모두']
    review=ledger.review_document_transactions([row()],'alice')
    assert review['count']==1 and review['duplicates']==[False] and review['total']=='12345'
    assert not users.exists()


def test_commit_single_atomic_record_only_and_stale_resubmission_rejected(users):
    parent=users/'alice';parent.mkdir(parents=True)
    protected={'portfolio.json':{'settings':{},'bank_accounts':[{'id':'synthetic','balance':777}]},
        'dividend_records.json':{'records':[]},'realized_pnl_records.json':{'records':[]}}
    before={}
    for name,value in protected.items():
        path=parent/name;path.write_text(json.dumps(value),encoding='utf-8');before[name]=path.read_bytes()
    body=request_for([row(),row(type='transfer',category='계좌이체/저축',source_kind='bank_transfer')])
    result=ledger.commit_document_transactions(body,'alice')
    assert result['count']==2 and len(result['transaction_ids'])==2
    assert 'document_import_requests' not in saved(users)
    content=(parent/'ledger.json').read_bytes()
    with pytest.raises(ledger.DocumentImportConflict):
        ledger.commit_document_transactions(body,'alice')
    assert (parent/'ledger.json').read_bytes()==content
    assert all((parent/name).read_bytes()==value for name,value in before.items())
    for tx in saved(users)['transactions']:
        assert tx['applied_delta']==0 and not tx['account_id'] and not tx['card_id']
        assert tx['source']=='document_review' and 'balance_after' not in tx
    assert saved(users)['transactions'][1]['type']=='transfer'


@pytest.mark.parametrize('changes',[
    {'date':''},{'date':'10-14'},{'date':'2026-02-30'},{'amount':None},{'amount':''},
    {'amount':0},{'amount':-1},{'amount':'NaN'},{'amount':'Infinity'},{'amount':float('nan')},
    {'amount':float('inf')},{'amount':True},{'amount':'9007199254740992'},
    {'type':''},{'type':[]},{'owner':''},{'owner':'다른소유자'},{'category':''},
    {'category':'급여/상여'},{'direction':'inflow'},{'transaction_time':'25:00'},
    {'source_kind':'bank_transfer'},{'source_kind':'refund'},
    {'source_kind':'card_cancellation'},{'special_confirmed':'true'},
    {'account_id':'forbidden'},{'apply_to_account':True},{'balance_after':'1234'},
])
def test_invalid_selected_rows_fail_without_financial_write(users,changes):
    path=seed(users);before=path.read_bytes()
    with pytest.raises(ValueError):ledger.review_document_transactions([row(),row(**changes)],'alice')
    assert path.read_bytes()==before
    body=request_for([row()]);body['rows'].append(row(**changes))
    with pytest.raises(ValueError):ledger.commit_document_transactions(body,'alice')
    assert path.read_bytes()==before and not saved(users).get('document_import_requests')


@pytest.mark.parametrize('kind',['card_cancellation','refund'])
def test_special_requires_explicit_type_and_confirmation(users,kind):
    chosen=row(source_kind=kind,special_confirmed=True,type='income',direction='inflow',category='부수입/기타수입')
    ledger.commit_document_transactions(request_for([chosen]),'alice')
    tx=saved(users)['transactions'][0]
    assert tx['type']=='income' and tx['document_kind']==kind and tx['amount']==12345
    assert len(saved(users)['transactions'])==1


def test_duplicate_requires_reconfirmation_but_distinct_identical_transaction_is_allowed(users):
    first=request_for([row()]);ledger.commit_document_transactions(first,'alice')
    second=request_for([row()])
    assert ledger.review_document_transactions([row()],'alice')['duplicates']==[True]
    before=(users/'alice'/'ledger.json').read_bytes()
    with pytest.raises(ledger.DocumentImportConflict):ledger.commit_document_transactions(second,'alice')
    assert (users/'alice'/'ledger.json').read_bytes()==before
    acknowledged=row(duplicate_confirmed=True)
    ledger.commit_document_transactions(request_for([acknowledged]),'alice')
    assert len(saved(users)['transactions'])==2
    assert ledger.review_document_transactions([row(),row()],'bob')['duplicates']==[False,True]


def test_state_change_and_changed_content_require_new_review(users):
    old=request_for([row()]);other=request_for([row(merchant='합성다른상점')])
    ledger.commit_document_transactions(other,'alice')
    with pytest.raises(ledger.DocumentImportConflict):ledger.commit_document_transactions(old,'alice')
    changed=copy.deepcopy(other);changed['rows'][0]['amount']='999'
    with pytest.raises(ledger.DocumentImportConflict):ledger.commit_document_transactions(changed,'alice')
    assert len(saved(users)['transactions'])==1


def test_atomic_failure_preserves_original_bytes_and_no_retry_receipt(users,monkeypatch):
    path=seed(users);before=path.read_bytes()
    body=request_for([row(),row(merchant='synthetic-second',duplicate_confirmed=True)])
    calls=[]
    def fail(data,**kwargs):
        calls.append(len(data['transactions']))
        raise OSError('synthetic atomic failure')
    monkeypatch.setattr(ledger,'write_ledger',fail)
    with pytest.raises(OSError):ledger.commit_document_transactions(body,'alice')
    assert path.read_bytes()==before and calls==[2]


@pytest.mark.parametrize('same_request',[True,False])
def test_concurrent_commit_is_serialized_and_requires_fresh_review(users,same_request):
    first=request_for([row()]);second=copy.deepcopy(first) if same_request else request_for([row(merchant='합성다른상점')])
    def commit(body):
        try:return ledger.commit_document_transactions(body,'alice')
        except ledger.DocumentImportConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(commit,[first,second]))
    assert len(saved(users)['transactions'])==1
    assert results.count('conflict')==1
    assert sum(isinstance(result,dict) for result in results)==1
    assert 'document_import_requests' not in saved(users)


def test_user_owner_isolation_and_foreign_review_rejected(users):
    body=request_for([row()],'alice')
    with pytest.raises(ledger.DocumentImportConflict):ledger.commit_document_transactions(body,'bob')
    ledger.commit_document_transactions(body,'alice')
    assert not (users/'bob'/'ledger.json').exists()
    parent=users/'carol';parent.mkdir()
    (parent/'portfolio.json').write_text(json.dumps({'settings':{'family_members':['합성소유자']}}),encoding='utf-8')
    assert ledger.document_import_options('carol')['owners']==['합성소유자','모두']
    with pytest.raises(ValueError):ledger.review_document_transactions([row()],'carol')
    ledger.commit_document_transactions(request_for([row(owner='합성소유자')],'carol'),'carol')
    assert saved(users,'carol')['transactions'][0]['owner']=='합성소유자'


@pytest.mark.parametrize('content',['{broken','{"transactions":{}}','{"transactions":[null]}','{"transactions":[],"categories":{}}'])
def test_corruption_is_fail_closed_without_repair(users,content):
    path=seed(users);path.write_text(content,encoding='utf-8');before=path.read_bytes()
    with pytest.raises(FinancialStorageError):ledger.document_import_options('alice')
    with pytest.raises(FinancialStorageError):ledger.review_document_transactions([row()],'alice')
    assert path.read_bytes()==before


def api_request(path,body=None,origin='http://testserver'):
    data=json.dumps(body).encode() if body is not None else b''
    async def receive():return {'type':'http.request','body':data,'more_body':False}
    return Request({'type':'http','method':'POST' if body else 'GET','scheme':'http','server':('testserver',80),
        'path':path,'headers':[(b'host',b'testserver'),(b'origin',origin.encode())],'query_string':b''},receive)


def test_api_review_commit_auth_origin_and_no_original_upload(users,monkeypatch):
    from app import main
    called=[]
    monkeypatch.setattr(main,'get_current_username',lambda request:called.append(True) or 'alice')
    options=asyncio.run(main.ledger_document_options(api_request('/api/ledger/document-import/options')))
    assert options.headers['cache-control']=='no-store' and not users.exists()
    review=asyncio.run(main.ledger_document_review_or_commit(api_request('/api/ledger/document-import/review',{'rows':[row()]})))
    result=json.loads(review.body);assert not users.exists()
    body={'rows':[row()],'revision':result['revision'],'review_token':result['review_token'],
        'confirmed':True}
    saved_response=asyncio.run(main.ledger_document_review_or_commit(api_request('/api/ledger/document-import/commit',body)))
    assert json.loads(saved_response.body)['count']==1 and len(called)==3
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.ledger_document_options(api_request('/api/ledger/document-import/options',origin='https://foreign.invalid')))
    assert error.value.status_code==403
    body['rows'][0]['amount']='777'
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.ledger_document_review_or_commit(api_request('/api/ledger/document-import/commit',body)))
    assert error.value.status_code==409

@pytest.mark.parametrize('username',['../alice','..','alice/child','alice\\child','D:other','alice ','alice.',''])
def test_invalid_identity_is_rejected_before_lock_or_directory_creation(users,username):
    with pytest.raises(ValueError):ledger.commit_document_transactions({},username)
    assert not users.exists()


def test_legacy_receipt_metadata_is_not_used_as_storage_or_retry_permission(users):
    data=ledger.default_ledger_data();data['document_import_requests']={'synthetic':{'digest':'bad','count':1}}
    path=seed(users,data=data);before=path.read_bytes()
    assert ledger.document_import_options('alice')['owners']
    assert path.read_bytes()==before
    ledger.commit_document_transactions(request_for([row()]),'alice')
    assert saved(users)['document_import_requests']==data['document_import_requests']
    assert len(saved(users)['transactions'])==1


def test_unconfirmed_and_changed_review_payload_cannot_write(users):
    path=seed(users);before=path.read_bytes()
    body=request_for([row()]);body['confirmed']=False
    with pytest.raises(ValueError):ledger.commit_document_transactions(body,'alice')
    body['confirmed']=True;body['rows'][0]['merchant']='검토후변경합성상점'
    with pytest.raises(ledger.DocumentImportConflict):ledger.commit_document_transactions(body,'alice')
    assert path.read_bytes()==before

@pytest.mark.parametrize('amount',['NaN',{},None])
def test_invalid_existing_financial_amount_blocks_review_without_repair(users,amount):
    data=ledger.default_ledger_data();data['transactions']=[{'amount':amount}]
    path=seed(users,data=data);before=path.read_bytes()
    with pytest.raises(FinancialStorageError):ledger.review_document_transactions([row()],'alice')
    assert path.read_bytes()==before


def test_corrected_merchant_or_time_does_not_hide_duplicate_candidate(users):
    ledger.commit_document_transactions(request_for([row()]),'alice')
    changed=row(merchant='수정된합성거래처',transaction_time='12:34')
    assert ledger.review_document_transactions([changed],'alice')['duplicates']==[True]
    with pytest.raises(ledger.DocumentImportConflict):ledger.commit_document_transactions(request_for([changed]),'alice')
    changed['duplicate_confirmed']=True
    ledger.commit_document_transactions(request_for([changed]),'alice')
    assert len(saved(users)['transactions'])==2


@pytest.mark.parametrize('changed_setting', ['owner', 'category'])
def test_current_membership_changes_require_user_correction_before_reconfirmation(users, changed_setting):
    body = request_for([row()])
    ledger.commit_document_transactions(body, 'alice')
    path = users/'alice'/'ledger.json'
    if changed_setting == 'owner':
        (users/'alice'/'portfolio.json').write_text(
            json.dumps({'settings': {'family_members': ['엄마']}}), encoding='utf-8')
    else:
        data = saved(users)
        data['categories'] = copy.deepcopy(data['categories'])
        data['categories']['expense'].remove('식비/외식')
        path.write_text(json.dumps(data), encoding='utf-8')
    before = path.read_bytes()
    with pytest.raises(ValueError):
        ledger.commit_document_transactions(copy.deepcopy(body), 'alice')
    assert path.read_bytes() == before
    altered = copy.deepcopy(body)
    altered['rows'][0]['memo'] = '합성 변경 내용'
    with pytest.raises(ValueError):
        ledger.commit_document_transactions(altered, 'alice')
    with pytest.raises(ValueError):
        ledger.review_document_transactions(body['rows'], 'alice')
    with pytest.raises(ledger.DocumentImportConflict):
        ledger.commit_document_transactions(body, 'bob')
    assert not (users/'bob'/'ledger.json').exists()
    assert path.read_bytes() == before


def test_legacy_receipt_count_does_not_block_new_confirmed_imports(users):
    body = request_for([row()])
    ledger.commit_document_transactions(body, 'alice')
    data = saved(users)
    legacy_receipts = {str(uuid.uuid4()): {'legacy': True} for _ in range(10000)}
    data['document_import_requests'] = legacy_receipts
    path = users/'alice'/'ledger.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    before = path.read_bytes()
    new_request = request_for([row(amount='54321')])
    assert ledger.commit_document_transactions(new_request, 'alice')['count']==1
    assert path.read_bytes() != before
    assert saved(users)['document_import_requests']==legacy_receipts
    assert len(saved(users)['document_import_requests']) == 10000
    assert len(saved(users)['transactions']) == 2
    after = path.read_bytes()
    with pytest.raises(ledger.DocumentImportConflict):
        ledger.commit_document_transactions(new_request, 'alice')
    assert path.read_bytes() == after


def test_cached_client_request_key_does_not_allow_automatic_resubmission(users):
    body = request_for([row()], request_id=str(uuid.uuid4()))
    ledger.commit_document_transactions(body, 'alice')
    path = users/'alice'/'ledger.json'
    before = path.read_bytes()
    with pytest.raises(ledger.DocumentImportConflict):
        ledger.commit_document_transactions(body, 'alice')
    assert path.read_bytes() == before
    assert 'document_import_requests' not in saved(users)
