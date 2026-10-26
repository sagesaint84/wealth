"""Real persisted synthetic DB + actual app middleware. Never production data."""
import threading
import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import system_update
from app.services import user_manager as users
from app.services.update_permissions import can_system_update
from tests.test_request_state_user_id import _import_main_without_loading_real_env

A='11111111-1111-4111-8111-111111111111'
U='22222222-2222-4222-8222-222222222222'
O='33333333-3333-4333-8333-333333333333'
IMAGE='sha256:'+'e'*64


@pytest.fixture
def persisted(tmp_path,monkeypatch):
    global A,U,O
    A,U,O=(str(uuid.uuid4()) for _ in range(3))
    monkeypatch.setattr(users,'DATA_DIR',tmp_path)
    monkeypatch.setattr(users,'USERS_FILE',tmp_path/'users.json')
    monkeypatch.setattr(users,'USERS_DIR',tmp_path/'users')
    records=[]
    for name,uid,role in [('admin',A,'admin'),('sagesaint',U,'user'),('other',O,'user')]:
        salt,hashed=users.hash_password('SYNTHETIC-'+name)
        records.append({'id':uid,'username':name,'role':role,'salt':salt,'password_hash':hashed,'must_change_password':False,'future_user_field':'preserved'})
    users.save_users_db({'users':records,'future_top_field':{'keep':True}})
    main=_import_main_without_loading_real_env()
    host=Mock()
    def call(method,args=None,actor=None):
        if method=='cleanup_preview':return {'images':[IMAGE],'preserved':['sha256:'+'a'*64,'sha256:'+'b'*64]}
        return {'jobs':[],'busy':False,'current':{'sha':'a'*40,'digest':'sha256:'+'a'*64},'id':'a'*32}
    host.call.side_effect=call
    monkeypatch.setattr(system_update,'client',host)
    monkeypatch.setattr(main,'_validate_same_origin_request',lambda r:r.headers.get('origin')=='https://synthetic.invalid')
    # register holds the original callback, whose trusted stored origin is stubbed.
    monkeypatch.setattr('app.services.system_settings.get_effective_system_settings',lambda:{'public_base_url':'https://synthetic.invalid'})
    def client(name='admin'):
        c=TestClient(main.app)
        c.cookies.set(main.COOKIE_NAME,main._new_session_token(users.get_user_by_name(name)))
        return c
    return main,host,client


def grant(enabled=True):
    actor=users.get_user_by_name('admin')
    return users.set_system_update_permission(A,U,enabled,credentials=(actor['salt'],actor['password_hash']))


def csrf(client):
    return {'Origin':'https://synthetic.invalid','X-Wealth-Update-CSRF':client.get('/api/system-update/status').json()['csrf_token']}


@pytest.mark.parametrize('path',['status','check','cleanup-preview','install','confirm','cleanup'])
def test_default_denied_and_immediate_revoke_for_all_six_endpoints(persisted,path):
    _,host,client=persisted;c=client('sagesaint')
    send=lambda:c.post('/api/system-update/'+path,json={}) if path in {'install','confirm','cleanup'} else c.get('/api/system-update/'+path)
    assert send().status_code==403
    grant();assert c.get('/api/system-update/status').status_code==200
    grant(False);host.reset_mock()
    assert send().status_code==403
    host.call.assert_not_called()
    assert users.get_user_by_name('sagesaint')['role']=='user'


@pytest.mark.parametrize('action,args',[('install',{'sha':'b'*40,'digest':'sha256:'+'b'*64}),('confirm',{'job_id':'b'*32}),('cleanup',{'images':[IMAGE]})])
def test_delegated_all_dangerous_actions_use_own_password_and_same_ipc(persisted,action,args):
    _,host,client=persisted;grant();c=client('sagesaint');h=csrf(c)
    if action=='cleanup':args={**args,'preview_token':c.get('/api/system-update/cleanup-preview').json()['preview_token']}
    host.reset_mock()
    assert c.post('/api/system-update/'+action,json={**args,'password':'SYNTHETIC-sagesaint','confirm':True},headers=h).status_code in (200,202)
    expected={k:v for k,v in args.items() if k!='preview_token'}
    host.call.assert_called_once_with(action,expected,U)
    assert c.get('/api/system-update/check').status_code==200
    assert c.get('/api/admin/users').status_code==403
    assert c.post('/api/admin/users',json={'username':'forged','role':'admin'}).status_code==403
    assert c.get('/api/admin/system-update-permissions/challenge?target_id='+O+'&enabled=true').status_code==403


@pytest.mark.parametrize('fault',['admin_password','no_confirmation','bad_origin','bad_csrf','missing_preview','invalid_preview_type','changed_images','replayed_preview','other_session_preview','same_user_other_session_preview'])
def test_delegated_cleanup_requires_preview_own_reauth_origin_csrf_and_confirmation(persisted,fault):
    _,host,client=persisted;grant();c=client('sagesaint');h=csrf(c)
    preview=c.get('/api/system-update/cleanup-preview').json()
    body={'images':[IMAGE],'preview_token':preview['preview_token'],'password':'SYNTHETIC-sagesaint','confirm':True}
    if fault=='admin_password':body['password']='SYNTHETIC-admin'
    if fault=='no_confirmation':body['confirm']=False
    if fault=='bad_origin':h['Origin']='https://evil.invalid'
    if fault=='bad_csrf':h['X-Wealth-Update-CSRF']='forged'
    if fault=='missing_preview':body.pop('preview_token')
    if fault=='invalid_preview_type':body['preview_token']=123
    if fault=='changed_images':body['images']=['sha256:'+'f'*64]
    if fault=='replayed_preview':assert c.post('/api/system-update/cleanup',json=body,headers=h).status_code==202
    if fault=='same_user_other_session_preview':
        other=client('sagesaint');body['preview_token']=other.get('/api/system-update/cleanup-preview').json()['preview_token']
    if fault=='other_session_preview':
        other=client('admin');body['preview_token']=other.get('/api/system-update/cleanup-preview').json()['preview_token']
    host.reset_mock()
    assert c.post('/api/system-update/cleanup',json=body,headers=h).status_code in (400,403)
    host.call.assert_not_called()


def challenge(c,target=None,enabled=True):
    target=target or U
    r=c.get('/api/admin/system-update-permissions/challenge',params={'target_id':target,'enabled':str(enabled).lower()})
    assert r.status_code==200
    value=r.json()
    return {'Origin':'https://synthetic.invalid','X-Wealth-Update-CSRF':value['csrf_token']}, {'enabled':enabled,'intent_token':value['intent_token'],'password':'SYNTHETIC-admin','confirm':True}


@pytest.mark.parametrize('fault',[None,'own_password','csrf','origin','target_changed','admin_target','bad_id','wrong_type','no_confirmation','replay','forged_role'])
def test_grant_endpoint_is_current_admin_only_scoped_and_single_use(persisted,fault):
    main,host,client=persisted;c=client();h,body=challenge(c)
    target=U
    if fault=='own_password':body['password']='SYNTHETIC-sagesaint'
    if fault=='csrf':h['X-Wealth-Update-CSRF']='bad'
    if fault=='origin':h['Origin']='https://evil.invalid'
    if fault=='target_changed':target=O
    if fault=='admin_target':target=A;h,body=challenge(c,A)
    if fault=='bad_id':target='../user'
    if fault=='wrong_type':body['enabled']='true'
    if fault=='no_confirmation':body['confirm']=False
    if fault=='forged_role':
        c=client('sagesaint');c.cookies.set(main.COOKIE_NAME,main._serializer.dumps({'user':'sagesaint','role':'admin'}))
    if fault=='replay':assert c.post('/api/admin/users/'+target+'/system-update',json=body,headers=h).status_code==200
    response=c.post('/api/admin/users/'+target+'/system-update',json=body,headers=h)
    if fault is None:
        assert response.status_code==200,response.text
        value=users.load_users_db()
        assert value['future_top_field']=={'keep':True}
        assert all(u['future_user_field']=='preserved' for u in value['users'])
        assert users.get_user_by_name('sagesaint')['permissions']=={'system_update':True}
    else:assert response.status_code in (400,403,404)
    assert users.get_user_by_name('sagesaint')['role']=='user'
    host.call.assert_not_called()


@pytest.mark.parametrize('state',[{'must_change_password':True},{'disabled':True},{'active':False},{'is_active':False}])
def test_inactive_targets_cannot_be_granted_or_use_capability(persisted,state):
    _,_,client=persisted
    db=users.load_users_db();db['users'][1].update(state);users.save_users_db(db)
    assert not can_system_update(users.get_user_by_name('sagesaint'))
    c=client();h,body=challenge(c)
    assert c.post('/api/admin/users/'+U+'/system-update',json=body,headers=h).status_code==400


def test_profile_flag_is_safe_and_old_records_new_users_default_deny(persisted):
    _,_,client=persisted;c=client('sagesaint')
    assert c.get('/api/auth/me').json()=={'username':'sagesaint','role':'user','must_change_password':False,'can_system_update':False}
    grant();assert c.get('/api/auth/me').json()['can_system_update'] is True
    # Avoid financial template creation while testing just new identity defaults.
    from unittest.mock import patch
    with patch.object(users,'init_empty_portfolio'):
        users.create_new_user('newuser','1234')
    new=users.get_user_by_name('newuser')
    assert new['role']=='user' and new['permissions']=={'system_update':False}


def test_revocation_during_reauthentication_and_regrant_expire_old_csrf(persisted,monkeypatch):
    _,host,client=persisted;grant();c=client('sagesaint');h=csrf(c)
    authenticate=users.authenticate_user
    def revoke(name,password):
        result=authenticate(name,password);grant(False);return result
    monkeypatch.setattr(users,'authenticate_user',revoke)
    host.reset_mock()
    body={'sha':'b'*40,'digest':'sha256:'+'b'*64,'password':'SYNTHETIC-sagesaint','confirm':True}
    assert c.post('/api/system-update/install',json=body,headers=h).status_code==403
    host.call.assert_not_called()
    monkeypatch.setattr(users,'authenticate_user',authenticate);grant()
    assert c.post('/api/system-update/install',json=body,headers=h).status_code==403


def test_reset_and_recreated_identity_invalidate_old_session_and_permission(persisted):
    main,host,client=persisted;grant();c=client('sagesaint')
    users.admin_reset_password_to_4digit('sagesaint','4321')
    host.reset_mock()
    assert c.get('/api/system-update/status').status_code==401
    users.force_set_user_password('sagesaint','SYNTHETIC-new')
    assert client('sagesaint').get('/api/system-update/status').status_code==403
    db=users.load_users_db();db['users'][1]['id']='44444444-4444-4444-8444-444444444444';users.save_users_db(db)
    assert c.get('/api/auth/me').status_code==401
    host.call.assert_not_called()


def test_password_change_refreshes_session_and_invalidates_old_bound_cookie(persisted):
    main,_,client=persisted;grant();c=client('sagesaint');old=c.cookies.get(main.COOKIE_NAME)
    assert c.post('/api/auth/change-password',json={'old_password':'SYNTHETIC-sagesaint','new_password':'SYNTHETIC-new'}).status_code==200
    assert c.get('/api/system-update/status').status_code==200
    stale=TestClient(main.app);stale.cookies.set(main.COOKIE_NAME,old)
    assert stale.get('/api/auth/me').status_code==401


def test_legacy_session_keeps_financial_login_but_requires_fresh_updater_login(persisted):
    main,_,client=persisted;grant();c=client('sagesaint')
    c.cookies.set(main.COOKIE_NAME,main._serializer.dumps({'user':'sagesaint','role':'admin'}))
    assert c.get('/api/auth/me').status_code==200
    assert c.get('/api/system-update/status').status_code==401


def test_concurrent_reset_and_grant_cannot_restore_reset_permission(persisted):
    gate=threading.Barrier(2);errors=[]
    def run(fn):
        try:gate.wait();fn()
        except ValueError as exc:errors.append(str(exc))
    threads=[threading.Thread(target=run,args=(grant,)),threading.Thread(target=run,args=(lambda:users.admin_reset_password_to_4digit('sagesaint','4321'),))]
    [t.start() for t in threads];[t.join() for t in threads]
    assert not errors or errors==['PERMISSION_TARGET_INACTIVE']
    assert users.get_user_by_name('sagesaint')['must_change_password']
    assert not can_system_update(users.get_user_by_name('sagesaint'))
    assert users.load_users_db()['future_top_field']=={'keep':True}


def test_failed_atomic_permission_write_preserves_original(persisted,monkeypatch):
    from pathlib import Path
    before=users.USERS_FILE.read_bytes();original=Path.replace
    def replace(path,target):
        if path==users.USERS_FILE.with_suffix('.tmp'):raise OSError('synthetic failure')
        return original(path,target)
    monkeypatch.setattr(Path,'replace',replace)
    with pytest.raises(OSError):grant()
    assert users.USERS_FILE.read_bytes()==before


def test_distinct_logins_have_distinct_session_bound_approvals(persisted):
    main,_,client=persisted;grant()
    first,second=client('sagesaint'),client('sagesaint')
    claims=[main._serializer.loads(c.cookies.get(main.COOKIE_NAME)) for c in (first,second)]
    assert all(len(c['sid'])==32 for c in claims)
    assert claims[0]['sid']!=claims[1]['sid']
    first_token=first.get('/api/system-update/cleanup-preview').json()['preview_token']
    body={'images':[IMAGE],'preview_token':first_token,'password':'SYNTHETIC-sagesaint','confirm':True}
    assert second.post('/api/system-update/cleanup',json=body,headers=csrf(second)).status_code==403


@pytest.mark.parametrize('form',[False,True])
def test_force_password_routes_cannot_bypass_own_password_reauthentication(persisted,form):
    _,_,client=persisted;grant();c=client('sagesaint')
    before=users.USERS_FILE.read_bytes()
    if form:r=c.post('/change-password-init',data={'new_password':'SYNTHETIC-hijack','new_password_confirm':'SYNTHETIC-hijack'})
    else:r=c.post('/api/auth/force-change-password',json={'new_password':'SYNTHETIC-hijack'})
    assert r.status_code==403
    assert users.USERS_FILE.read_bytes()==before


@pytest.mark.parametrize('form',[False,True])
def test_legitimate_pending_initial_password_change_still_works(persisted,form):
    _,_,client=persisted
    users.admin_reset_password_to_4digit('sagesaint','4321');c=client('sagesaint')
    if form:r=c.post('/change-password-init',data={'new_password':'SYNTHETIC-new','new_password_confirm':'SYNTHETIC-new'},follow_redirects=False)
    else:r=c.post('/api/auth/force-change-password',json={'new_password':'SYNTHETIC-new'})
    assert r.status_code==(303 if form else 200)
    assert c.get('/api/auth/me').status_code==200
    assert not users.get_user_by_name('sagesaint')['must_change_password']
    assert not can_system_update(users.get_user_by_name('sagesaint'))
