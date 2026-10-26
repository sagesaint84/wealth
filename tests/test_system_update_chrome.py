"""Real Chromium, five widths; update APIs are synthetic in-memory fixtures."""
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_workflow_ux_chrome import click, no_overflow

BOOT=r'''
window.__u={requests:[],errors:[],current:'a',job:null,confirmed:false,offline:false,fail:false};
addEventListener('error',e=>__u.errors.push(e.message));
addEventListener('unhandledrejection',e=>__u.errors.push(String(e.reason)));
const previous=window.fetch;
const digest=c=>'sha256:'+c.repeat(64),sha=c=>c.repeat(40);
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(path==='/api/auth/me')return {ok:true,json:async()=>({username:'SYNTHETIC',role:window.__updateRole||'admin',must_change_password:false})};
 if(!path.startsWith('/api/system-update/'))return previous.apply(this,arguments);
 const action=path.split('/').at(-1),body=options.body?JSON.parse(options.body):null;
 __u.requests.push({action,method:options.method||'GET',body});
 if(__u.offline)throw TypeError('synthetic disconnect');
 let result={};
 if(action==='status')result={app_version:'2.1.4',csrf_token:'synthetic-csrf',host_available:true,current:{sha:sha(__u.current),digest:digest(__u.current)},rollback:__u.current==='b'?{digest:digest('a')}:null,busy:__u.job&&['pulling','verifying'].includes(__u.job.stage),jobs:__u.job?[{...__u.job,confirmed:__u.confirmed}]:[]};
 else if(action==='check'){
  if(__u.fail)return {ok:false,json:async()=>({detail:{code:'BUILD_NOT_SUCCESSFUL'}})};
  result={sha:sha('b'),digest:digest('b'),available:__u.current!=='b',build:'success',url:'https://github.com/sagesaint84/wealth/actions/runs/123',checked_at:123,compressed_bytes:100,free_bytes:9999999999,required_bytes:2147483648,changes:[{message:'Synthetic change <img id="unsafeUpdateNode" src=x onerror=alert(1)>'}]};
 }else if(action==='install'){__u.job={id:'b'.repeat(32),kind:'install',stage:'pulling',created_at:123,digest:digest('b')};result=__u.job;}
 else if(action==='confirm'){__u.confirmed=true;result=__u.job;}
 else if(action==='cleanup-preview')result={images:[digest('e')],preserved:[digest('a'),digest('b')]};
 else if(action==='cleanup')result={id:'c'.repeat(32),kind:'cleanup',stage:'succeeded',created_at:124};
 return {ok:true,json:async()=>structuredClone(result)};
};
'''


def start(preview,width,extra=''):
    call,evaluate,port=preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT+extra})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<768})
    call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#settings'})
    wait_for(evaluate,"document.readyState==='complete' && !!window.WealthSystemUpdate && !!currentUserProfile")
    return call,evaluate,port


def authorize(evaluate):
    evaluate("document.getElementById('updatePassword').value='SYNTHETIC-PASSWORD';document.getElementById('updateConsent').checked=true")


@pytest.mark.parametrize('width',[320,360,390,768,1280])
def test_update_ui_readonly_install_progress_confirmation_cleanup_and_width(chrome_preview,width):
    call,evaluate,_=start(chrome_preview,width)
    assert evaluate('__u.requests.length')==0  # no inactive settings update lookup
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,"document.getElementById('updateVersion').textContent==='v2.1.4'")
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
    call,evaluate,_=start(chrome_preview,360,"window.__updateRole='user';")
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
