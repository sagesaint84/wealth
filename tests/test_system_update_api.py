"""Web authorization boundary with synthetic users, IPC stub and no real files."""
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import system_update as web
from app.updater.protocol import UpdateError


@pytest.fixture
def boundary(monkeypatch):
    app = FastAPI()
    user = {'username': 'synthetic-admin', 'id': '11111111-1111-4111-8111-111111111111', 'role': 'admin'}
    @app.middleware('http')
    async def auth(request, call_next):
        request.state.user_id = user['id']
        return await call_next(request)
    host = Mock()
    host.call.return_value = {'current': {'sha': 'a'*40, 'digest': 'sha256:'+'a'*64}, 'jobs': [], 'busy': False}
    monkeypatch.setattr(web, 'client', host)
    password = Mock(return_value=user.copy())
    monkeypatch.setattr('app.services.user_manager.authenticate_user', password)
    monkeypatch.setattr('app.services.user_manager.get_user_by_name',lambda name:user)
    web.register_update_routes(app, app_version='2.1.5', secret='synthetic-only',
        session_current=lambda r,u:True, username=lambda r:user['username'],
        origin=lambda r:r.headers.get('origin')=='https://synthetic.invalid')
    client = TestClient(app)
    client.cookies.set('dashboard_session_v2', 'synthetic-session')
    return client,user,host,password


def headers(client):
    token=client.get('/api/system-update/status').json()['csrf_token']
    return {'Origin':'https://synthetic.invalid','X-Wealth-Update-CSRF':token}


@pytest.mark.parametrize('path',['status','check','cleanup-preview','install','confirm','cleanup'])
def test_all_endpoints_require_current_admin_not_cookie_role(boundary,path):
    client,user,host,_=boundary
    user['role']='user'
    response=client.post('/api/system-update/'+path,json={}) if path in {'install','confirm','cleanup'} else client.get('/api/system-update/'+path)
    assert response.status_code==403
    host.call.assert_not_called()


def test_read_only_status_and_check_have_no_deploy_calls(boundary):
    client,_,host,password=boundary
    assert client.get('/api/system-update/status').json()['app_version']=='2.1.5'
    assert client.get('/api/system-update/status').headers['cache-control']=='no-store'
    assert client.get('/api/system-update/check').status_code==200
    assert [c.args[0] for c in host.call.call_args_list]==['status','status','check']
    password.assert_not_called()


@pytest.mark.parametrize('mutate', ['origin','csrf','cookie','identity','missing_confirmation','wrong_password','extra_command'])
def test_mutation_security_rejects_without_execution(boundary,mutate):
    client,user,host,password=boundary
    h=headers(client)
    body={'sha':'b'*40,'digest':'sha256:'+'b'*64,'password':'synthetic-password','confirm':True}
    if mutate=='origin': h['Origin']='https://evil.invalid'
    if mutate=='csrf': h['X-Wealth-Update-CSRF']='tampered'
    if mutate=='cookie': client.cookies.set('dashboard_session_v2','different-session')
    if mutate=='identity': user['id']='new-identity'
    if mutate=='missing_confirmation': body['confirm']=False
    if mutate=='wrong_password': password.return_value=None
    if mutate=='extra_command': body['command']='rm -rf /'
    host.reset_mock()
    response=client.post('/api/system-update/install',json=body,headers=h)
    assert response.status_code in (400,403)
    host.call.assert_not_called()
    assert 'synthetic-password' not in response.text


@pytest.mark.parametrize('action,args',[('install',{'sha':'b'*40,'digest':'sha256:'+'b'*64}),('confirm',{'job_id':'b'*32}),('cleanup',{'images':['sha256:'+'b'*64]})])
def test_destructive_actions_reauthenticate_each_time_and_forward_no_password(boundary,action,args):
    client,_,host,password=boundary
    h=headers(client)
    expected=args.copy()
    if action=='cleanup':
        host.call.return_value={'images':args['images'],'preserved':[]}
        args={**args,'preview_token':client.get('/api/system-update/cleanup-preview').json()['preview_token']}
    host.reset_mock()
    response=client.post('/api/system-update/'+action,json={**args,'password':'synthetic-password','confirm':True},headers=h)
    assert response.status_code in (200,202)
    password.assert_called_once_with('synthetic-admin','synthetic-password')
    host.call.assert_called_once_with(action,expected,'11111111-1111-4111-8111-111111111111')
    assert 'synthetic-password' not in response.text


def test_reauth_and_check_rate_limits(boundary):
    client,_,host,password=boundary
    h=headers(client);password.return_value=None
    body={'sha':'b'*40,'digest':'sha256:'+'b'*64,'password':'bad','confirm':True}
    assert [client.post('/api/system-update/install',json=body,headers=h).status_code for _ in range(6)]==[403]*5+[429]
    assert [client.get('/api/system-update/check').status_code for _ in range(4)]==[200]*3+[429]


def test_host_unavailable_and_fixed_error_no_sensitive_details(boundary):
    client,_,host,_=boundary
    host.call.side_effect=UpdateError('UPDATER_UNAVAILABLE')
    result=client.get('/api/system-update/status').json()
    assert result['host_available'] is False and result['error']=='UPDATER_UNAVAILABLE'
    assert 'csrf_token' in result and 'app_version' in result
    assert client.get('/api/system-update/check').status_code==503


def test_oversized_body_wrong_content_type_and_expired_csrf(boundary,monkeypatch):
    client,_,host,_=boundary
    h=headers(client);host.reset_mock()
    assert client.post('/api/system-update/install',content='x'*8193,headers={**h,'Content-Type':'application/json'}).status_code==413
    assert client.post('/api/system-update/install',content='{}',headers=h).status_code==415
    with monkeypatch.context() as m:
        m.setattr('itsdangerous.timed.TimestampSigner.get_timestamp',lambda self:int(__import__('time').time())+601)
        assert client.post('/api/system-update/install',json={},headers=h).status_code==403
    host.call.assert_not_called()
