"""Real Chromium, five widths; update APIs are synthetic in-memory fixtures."""
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_workflow_ux_chrome import click, no_overflow

BOOT=r'''
window.__u={requests:[],errors:[],current:'a',job:null,confirmed:false,offline:false,fail:false,identity:'sagesaint',access:true,userGrant:false,adminRequests:[],finance:[]};
addEventListener('error',e=>__u.errors.push(e.message));
addEventListener('unhandledrejection',e=>__u.errors.push(String(e.reason)));
const previous=window.fetch;
const digest=c=>'sha256:'+c.repeat(64),sha=c=>c.repeat(40);
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(path==='/api/auth/me')return {ok:true,json:async()=>({username:__u.identity,role:__u.identity==='admin'?'admin':'user',can_system_update:!__u.mustChange&&(__u.identity==='admin'||__u.access),must_change_password:!!__u.mustChange})};
 if(path==='/api/auth/force-change-password'){__u.mustChange=false;return {ok:true,json:async()=>({message:'synthetic changed'})};}
 if(['/api/dashboard','/api/refresh-prices','/api/planning/snapshot-all'].includes(path))__u.finance.push(path);
 if(path.startsWith('/api/admin/')){
  const body=options.body?JSON.parse(options.body):null;__u.adminRequests.push({path,body});
  const rows=[{id:'11111111-1111-4111-8111-111111111111',username:'admin',role:'admin',created_at:'2026-10-26'},
    {id:'22222222-2222-4222-8222-222222222222',username:'sagesaint',role:'user',created_at:'2026-10-26',permissions:{system_update:__u.userGrant}},
    {id:'33333333-3333-4333-8333-333333333333',username:'newuser',role:'user',must_change_password:true,permissions:{system_update:false}}];
  if(path==='/api/admin/users')return {ok:true,json:async()=>({users:rows})};
  if(path.endsWith('/challenge'))return {ok:true,json:async()=>({csrf_token:'synthetic-admin-csrf',intent_token:'synthetic-intent'})};
  if(path.endsWith('/system-update')){__u.userGrant=body.enabled;return {ok:true,json:async()=>({role:'user',permissions:{system_update:body.enabled}})};}
 }

 if(!path.startsWith('/api/system-update/'))return previous.apply(this,arguments);
 const action=path.split('/').at(-1),body=options.body?JSON.parse(options.body):null;
 if(__u.identity!=='admin'&&!__u.access)return {ok:false,status:403,json:async()=>({detail:{code:'SYSTEM_UPDATE_FORBIDDEN'}})};
 __u.requests.push({action,method:options.method||'GET',body});
 if(__u.offline)throw TypeError('synthetic disconnect');
 if(options.method==='POST'&&__u.reauthFail)return {ok:false,status:403,json:async()=>({detail:{code:'UPDATE_REAUTH_FAILED'}})};
 let result={};
 if(action==='status')result={app_version:'2.1.5',csrf_token:'synthetic-csrf',host_available:true,current:{sha:sha(__u.current),digest:digest(__u.current)},rollback:__u.current==='b'?{digest:digest('a')}:null,busy:__u.job&&['pulling','verifying'].includes(__u.job.stage),jobs:__u.job?[{...__u.job,confirmed:__u.confirmed}]:[]};
 else if(action==='check'){
  if(__u.fail)return {ok:false,json:async()=>({detail:{code:'BUILD_NOT_SUCCESSFUL'}})};
  result={sha:sha('b'),digest:digest('b'),available:__u.current!=='b',build:'success',url:'https://github.com/sagesaint84/wealth/actions/runs/123',checked_at:123,compressed_bytes:100,free_bytes:9999999999,required_bytes:2147483648,changes:[{message:'Synthetic change <img id="unsafeUpdateNode" src=x onerror=alert(1)>'}]};
 }else if(action==='install'){__u.job={id:'b'.repeat(32),kind:'install',stage:'pulling',created_at:123,digest:digest('b')};result=__u.job;}
 else if(action==='confirm'){__u.confirmed=true;result=__u.job;}
 else if(action==='cleanup-preview')result={images:[digest('e')],preview_token:'synthetic-preview',preserved:[digest('a'),digest('b')]};
 else if(action==='cleanup')result={id:'c'.repeat(32),kind:'cleanup',stage:'succeeded',created_at:124};
 return {ok:true,json:async()=>structuredClone(result)};
};
'''


def start(preview,width,extra='',route='settings'):
    call,evaluate,port=preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT+extra})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<768})
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#{route}'})
    wait_for(evaluate,"document.readyState==='complete' && !!window.WealthSystemUpdate && !!currentUserProfile")
    return call,evaluate,port


def authorize(evaluate):
    evaluate("document.getElementById('updatePassword').value='SYNTHETIC-PASSWORD';document.getElementById('updateConsent').checked=true")


@pytest.mark.parametrize('width',[320,360,390,768,1280])
def test_update_ui_readonly_install_progress_confirmation_cleanup_and_width(chrome_preview,width):
    call,evaluate,_=start(chrome_preview,width)
    assert evaluate('__u.requests.length')==0  # no inactive settings update lookup
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,"document.getElementById('updateVersion').textContent==='v2.1.5'")
    assert evaluate("document.getElementById('settingsSystemTab').getAttribute('aria-selected')")=='true'
    assert evaluate("document.getElementById('settingsSystemPanel').getAttribute('aria-labelledby')")=='settingsSystemTab'
    assert evaluate("__u.requests.every(r=>r.action==='status'&&r.method==='GET')")
    click(call,evaluate,'#updateCheck')
    wait_for(evaluate,"!document.getElementById('updateInstall').disabled")
    assert not evaluate("!!document.getElementById('unsafeUpdateNode')")
    assert 'Synthetic change <img' in evaluate("document.getElementById('updateChanges').textContent")
    assert not evaluate("__u.requests.some(r=>r.method==='POST')")
    click(call,evaluate,'#updateInstall')
    assert not evaluate("__u.requests.some(r=>r.method==='POST')")
    authorize(evaluate);click(call,evaluate,'#updateInstall')
    wait_for(evaluate,"__u.requests.some(r=>r.action==='install')")
    assert evaluate("document.getElementById('updatePassword').value") == ''
    assert not evaluate("document.getElementById('updateConsent').checked")
    assert evaluate("__u.requests.filter(r=>r.action==='install').length")==1
    evaluate("__u.current='b';__u.job.stage='succeeded'")
    click(call,evaluate,'#updateRefresh')
    wait_for(evaluate,"!document.getElementById('updateConfirm').disabled")
    assert evaluate("document.getElementById('updateCleanupPreview').disabled")
    authorize(evaluate);click(call,evaluate,'#updateConfirm')
    wait_for(evaluate,"!document.getElementById('updateCleanupPreview').disabled")
    click(call,evaluate,'#updateCleanupPreview')
    wait_for(evaluate,"!document.getElementById('updateCleanup').disabled")
    assert evaluate("document.getElementById('updateCleanupImages').textContent")=='sha256:'+'e'*64
    authorize(evaluate);click(call,evaluate,'#updateCleanup')
    wait_for(evaluate,"__u.requests.some(r=>r.action==='cleanup')")
    assert evaluate("__u.requests.find(r=>r.action==='cleanup').body.images")==['sha256:'+'e'*64]
    assert not evaluate("JSON.stringify(localStorage).includes('SYNTHETIC-PASSWORD')||JSON.stringify(sessionStorage).includes('SYNTHETIC-PASSWORD')")
    no_overflow(evaluate,width)
    assert evaluate("(()=>{const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return new Set(ids).size===ids.length})()")
    assert evaluate('__u.errors')==[]


def test_non_admin_tab_hidden_and_keyboard_skips_it(chrome_preview):
    call,evaluate,_=start(chrome_preview,360,"__u.access=false;")
    assert evaluate("document.getElementById('settingsSystemTab').hidden")
    evaluate("document.getElementById('settingsApiTab').focus()")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'End'})
    assert evaluate('document.activeElement.id')=='settingsNotificationsTab'
    assert evaluate('__u.requests')==[]


def test_status_resume_reload_build_failure_and_reconnection(chrome_preview):
    call,evaluate,port=start(chrome_preview,360)
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,"!document.getElementById('updateCheck').disabled")
    evaluate('__u.fail=true')
    click(call,evaluate,'#updateCheck')
    assert evaluate("document.getElementById('updateInstall').disabled")
    assert '빌드가 성공하지' in evaluate("document.getElementById('updateError').textContent")
    call('Page.addScriptToEvaluateOnNewDocument',{'source':"__u.job={id:'b'.repeat(32),kind:'install',stage:'verifying',created_at:123,digest:'sha256:'+'b'.repeat(64)};"})
    previous=evaluate('performance.timeOrigin')
    call('Page.reload',{'ignoreCache':True})
    wait_for(evaluate,f"performance.timeOrigin!=={previous!r} && document.readyState==='complete' && !!window.WealthSystemUpdate && !!document.getElementById('settingsSystemTab') && !!currentUserProfile")
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,"document.getElementById('updateJobs').textContent.includes('서버 검증')")
    assert evaluate("document.getElementById('updateInstall').disabled")
    evaluate("__u.offline=true")
    click(call,evaluate,'#updateRefresh')
    wait_for(evaluate,"document.getElementById('updateStatus').textContent.includes('재연결')")
    evaluate("__u.offline=false;__u.job.stage='rolled_back';__u.job.rollback_result='verified'")
    click(call,evaluate,'#updateRefresh')
    wait_for(evaluate,"document.getElementById('updateJobs').textContent.includes('이전 이미지 복구 확인')")
    assert evaluate('__u.errors')==[]


@pytest.mark.parametrize('width',[320,360,390,768,1280])
def test_actual_admin_console_reaches_single_update_panel_and_grants_by_id(chrome_preview,width):
    call,evaluate,_=start(chrome_preview,width,"__u.identity='admin';",route='home')
    wait_for(evaluate,"document.getElementById('adminMainUserListTbody').querySelector('input[data-update-user]') && document.getElementById('adminMainPanel').getClientRects().length>0")
    assert evaluate('currentUserProfile.username')=='admin'
    assert evaluate('currentUserProfile.role')=='admin'
    assert not evaluate("!!document.getElementById('userAssetDashboardWrapper').getClientRects().length")
    assert evaluate('__u.finance')==[]
    assert evaluate('__u.requests')==[]
    selector='#adminMainUserListTbody input[data-update-name="sagesaint"]'
    assert not evaluate(f'document.querySelector({selector!r}).checked')
    assert evaluate("document.querySelector('#adminMainUserListTbody input[data-update-name=newuser]').disabled")
    for enabled in [True,False]:
        click(call,evaluate,selector)
        wait_for(evaluate,"!document.getElementById('adminUpdatePermissionApproval').hidden")
        # Toggle retains actual stored state until reauth+explicit approval succeeds.
        assert evaluate(f'document.querySelector({selector!r}).checked') is not enabled
        evaluate("document.getElementById('adminUpdatePermissionPassword').value='SYNTHETIC-admin';document.getElementById('adminUpdatePermissionConsent').checked=true")
        click(call,evaluate,'#adminUpdatePermissionSave')
        wait_for(evaluate,f"document.querySelector({selector!r}).checked==={str(enabled).lower()} && document.getElementById('adminUpdatePermissionApproval').hidden")
        assert evaluate("document.getElementById('adminUpdatePermissionPassword').value") == ''
    changes=evaluate("__u.adminRequests.filter(r=>r.body)")
    assert [r['body']['enabled'] for r in changes]==[True,False]
    assert all(r['path'].endswith('/22222222-2222-4222-8222-222222222222/system-update') for r in changes)
    click(call,evaluate,'#adminSystemTab')
    wait_for(evaluate,"document.getElementById('updateVersion').textContent==='v2.1.5'")
    assert evaluate("document.getElementById('settingsSystemPanel').getClientRects().length")>0
    assert evaluate("document.getElementById('settingsSystemPanel').parentElement.id")=='adminSystemUpdateSlot'
    assert evaluate("document.getElementById('settingsSystemPanel').getAttribute('aria-labelledby')")=='adminSystemTab'
    click(call,evaluate,'#updateCheck')
    wait_for(evaluate,"!document.getElementById('updateRelease').hidden")
    assert evaluate('__u.finance')==[]
    assert evaluate("document.querySelectorAll('#settingsSystemPanel').length")==1
    assert evaluate("(()=>{const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);return new Set(ids).size===ids.length})()")
    no_overflow(evaluate,width)
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Home'})
    # Focus the actual console tab before testing tablist keyboard navigation.
    evaluate("document.getElementById('adminSystemTab').focus()")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Home'})
    assert evaluate('document.activeElement.id')=='adminUsersTab'
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'End'})
    assert evaluate('document.activeElement.id')=='adminSystemTab'
    previous=evaluate('performance.timeOrigin');call('Page.reload',{'ignoreCache':True})
    wait_for(evaluate,f"performance.timeOrigin!=={previous!r} && document.readyState==='complete' && !!window.WealthSystemUpdate && !!currentUserProfile && !!document.getElementById('settingsSystemPanel')?.getClientRects().length")
    assert evaluate('currentUserProfile.username')=='admin'
    assert evaluate('__u.finance')==[]
    assert evaluate('__u.errors')==[]


@pytest.mark.parametrize('username',['sagesaint','other'])
def test_plain_user_profile_has_no_updater_or_admin_console(chrome_preview,username):
    call,evaluate,_=start(chrome_preview,360,f"__u.identity={json.dumps(username)};__u.access=false;")
    assert evaluate('currentUserProfile.role')=='user'
    assert evaluate("document.getElementById('settingsSystemTab').hidden")
    assert not evaluate("!!document.getElementById('adminMainPanel').getClientRects().length")
    assert evaluate('__u.requests')==[]
    assert evaluate('__u.adminRequests')==[]


def test_delegated_revoke_hides_ui_and_keeps_started_host_job(chrome_preview):
    call,evaluate,_=start(chrome_preview,360)
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,"!document.getElementById('updateCheck').disabled")
    evaluate("__u.job={id:'b'.repeat(32),kind:'install',stage:'pulling',created_at:123};__u.access=false")
    click(call,evaluate,'#updateRefresh')
    wait_for(evaluate,"document.getElementById('settingsSystemTab').hidden")
    assert evaluate('__u.job.stage')=='pulling'
    assert not evaluate("__u.requests.some(r=>r.action==='cancel')")
    evaluate("__u.access=true;window.dispatchEvent(new Event('focus'))")
    wait_for(evaluate,"!document.getElementById('settingsSystemTab').hidden")
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,"document.getElementById('updateStatus').textContent.includes('다운로드')")
    assert evaluate('currentUserProfile.role')=='user'
    assert evaluate('__u.errors')==[]


def test_delegated_reauth_failure_asks_own_password_without_install(chrome_preview):
    call,evaluate,_=start(chrome_preview,360)
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,"!document.getElementById('updateCheck').disabled")
    click(call,evaluate,'#updateCheck')
    wait_for(evaluate,"!document.getElementById('updateInstall').disabled")
    evaluate('__u.reauthFail=true');authorize(evaluate)
    click(call,evaluate,'#updateInstall')
    assert '본인 비밀번호' in evaluate("document.getElementById('updateError').textContent")
    assert '관리자 비밀번호' not in evaluate("document.getElementById('updateError').textContent")
    assert evaluate('__u.job') is None
    assert evaluate("document.getElementById('updatePassword').value")==''
    assert evaluate('__u.errors')==[]


def test_pending_admin_password_completion_refreshes_server_capability(chrome_preview):
    call,evaluate,_=start(chrome_preview,360,"__u.identity='admin';__u.mustChange=true;")
    wait_for(evaluate,"document.getElementById('forcePasswordModal').open")
    assert evaluate('__u.requests')==[]
    assert not evaluate("!!document.getElementById('adminMainPanel').getClientRects().length")
    evaluate("document.getElementById('forceNewPassword').value='SYNTHETIC-new';document.getElementById('forceNewPasswordConfirm').value='SYNTHETIC-new'")
    click(call,evaluate,'#forcePasswordForm button[type=submit]')
    wait_for(evaluate,"document.getElementById('updateVersion').textContent==='v2.1.5' && !!document.getElementById('settingsSystemPanel').getClientRects().length")
    assert evaluate('currentUserProfile.can_system_update') is True
    assert not evaluate("document.getElementById('forcePasswordModal').open")
    assert evaluate('__u.finance')==[]
    assert evaluate('__u.errors')==[]
