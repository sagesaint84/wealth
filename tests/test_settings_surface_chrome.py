"""Native Chrome, pre-parse shadow instrumentation, synthetic settings only."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_workflow_ux_chrome import FRAMES, click, no_overflow


BOOT = r'''
window.__settingsProbe={requests:[],legacy:0,forms:0,moves:0,dialogs:0,errors:[],legacyVisibleFrames:0,hold:false,pending:[],fail:false};
const banned=['userOpenApiModal','notificationSettingsDialog','userOpenApiBtn','notificationSettingsBtn'];
const inspect=node=>{
 if(node.nodeType!==1)return;
 const nodes=[node,...node.querySelectorAll('[id]')];
 for(const item of nodes){if(banned.includes(item.id))__settingsProbe.legacy++;
 if(item.id==='userOpenApiForm')__settingsProbe.forms++;}
};
const htmlDescriptor=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
Object.defineProperty(Element.prototype,'innerHTML',{...htmlDescriptor,set(value){htmlDescriptor.set.call(this,value);for(const child of this.children)inspect(child);}});
const sampleFrame=()=>{if(banned.some(id=>{const e=document.getElementById(id);return e&&e.getBoundingClientRect().width>0;}))__settingsProbe.legacyVisibleFrames++;requestAnimationFrame(sampleFrame);};requestAnimationFrame(sampleFrame);
new MutationObserver(records=>{for(const r of records)for(const n of r.addedNodes){if(n.nodeType===1&&banned.includes(n.id))__settingsProbe.legacy++;}}).observe(document,{subtree:true,childList:true});
for(const method of ['appendChild','insertBefore']){
 const original=Node.prototype[method];Node.prototype[method]=function(node,...rest){
 if(['settingsApiPanel','settingsNotificationsPanel','userOpenApiForm'].includes(node.id)&&node.parentNode)__settingsProbe.moves++;
 return original.call(this,node,...rest);};
}
const show=HTMLDialogElement.prototype.showModal;
HTMLDialogElement.prototype.showModal=function(){__settingsProbe.dialogs++;return show.call(this);};
window.addEventListener('error',e=>__settingsProbe.errors.push(e.message));
window.addEventListener('unhandledrejection',e=>__settingsProbe.errors.push(String(e.reason)));
window.confirm=()=>true;window.alert=message=>__settingsProbe.errors.push(message);
const config=Object.fromEntries(['toss','kb','nh','kis','kiwoom'].map(name=>[name,{app_key:name+'****',app_secret:'********',account_no:'1234****',configured:true,has_app_key:true,has_app_secret:true}]));
config.dart={configured:true,has_api_key:true};
const notifications={telegram:{enabled:true,chat_id:101,allowed_user_id:202,allowed_chat_id:101,bot_token_configured:true,bot_token_source:'stored',webhook_secret_configured:true,webhook_secret_source:'stored'},discord:{enabled:true},kakao:{enabled:true}};
const automation={timezone:'Asia/Seoul',ipo_refresh_morning:{enabled:true,time:'08:00'},ipo_refresh_evening:{enabled:true,time:'20:50'},ipo_reminders:{enabled:true,times:['09:00']},ipo_listing_reminders:{enabled:true,times:['08:30']},daily_close:{enabled:true,time:'21:00'},_status:{counts:{enabled:5,success:5},jobs:[],recent:[]}};
const system={can_manage:true,public_base_url:'https://synthetic.invalid',public_base_url_source:'stored',automation_owner:'DEMO',automation_owner_source:'stored',current_username:'DEMO',telegram_webhook_owner:'DEMO'};
const discord={webhook_url_configured:true,webhook_url_source:'stored'};
const kakao={rest_api_key_configured:true,rest_api_key_source:'stored',client_secret_configured:true,client_secret_source:'stored',app_configured:true,connected:true,public_base_url_configured:true,redirect_uri:'https://synthetic.invalid/oauth',access_expires_at:'2026-12-01',refresh_expires_at:'2027-01-01'};
const toss={enabled:true,allowed:true,expected_version:'0.50.3',session_check_enabled:true};
const krx={configured:true,login_id:'demo****',login_id_configured:true,password_configured:true};
const nativeFetch=window.fetch;
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname,method=options.method||'GET',body=options.body?JSON.parse(options.body):null;
 if(!path.startsWith('/api/settings/')&&!path.startsWith('/api/user/openapi-config')&&!path.startsWith('/api/user/krx-marketplace-config'))return nativeFetch.apply(this,arguments);
 __settingsProbe.requests.push({path,method,body});
 if(__settingsProbe.hold&&method==='GET')await new Promise(resolve=>__settingsProbe.pending.push(resolve));
 if((__settingsProbe.fail||__settingsProbe.failPath===path)&&method==='GET')return {ok:false,status:503,json:async()=>({detail:'SYNTHETIC_UNAVAILABLE'})};
 let result={valid:true,message:'synthetic success'};
 if(path==='/api/user/openapi-config'){
   if(method==='POST')for(const [broker,patch] of Object.entries(body)){if(broker==='dart')config.dart={configured:true,has_api_key:true};else config[broker]={...config[broker],app_key:patch.app_key,configured:true};}
   result=config;
 }else if(path.startsWith('/api/user/openapi-config/')&&method==='DELETE'){config[path.split('/').at(-1)]={configured:false};}
 else if(path==='/api/user/krx-marketplace-config'){if(method==='DELETE')Object.assign(krx,{configured:false,login_id_configured:false,password_configured:false,login_id:''});result=krx;}
 else if(path==='/api/settings/notifications'){if(body)for(const [provider,patch] of Object.entries(body))Object.assign(notifications[provider],patch);result=notifications;}
 else if(path==='/api/settings/automation'){if(body)Object.assign(automation,body.automation);result={automation};}
 else if(path==='/api/settings/system')result=system;
 else if(path==='/api/settings/discord')result=discord;
 else if(path==='/api/settings/kakao')result=kakao;
 else if(path==='/api/settings/toss-wts'){if(body)Object.assign(toss,body);result={toss_wts:toss};}
 else if(path==='/api/settings/toss-wts/status')result={active:true,valid:true,session_present:true,hours_remaining:24,server_expires_at:'2026-10-10',checked_at:'2026-10-09'};
 else if(path==='/api/settings/toss-wts/login/start')result={attempt_id:'synthetic-attempt'};
 else if(path==='/api/settings/toss-wts/login/synthetic-attempt')result={status:'pending'};
 else if(path==='/api/settings/telegram/status')result={bot:{username:'synthetic'},webhook:{configured:true,matches_expected:true,actual_url:'https://synthetic.invalid/webhook',pending_update_count:0}};
 else if(path==='/api/settings/notifications/history')result={events:[],count:0,retention:100};
 return {ok:true,status:200,json:async()=>structuredClone(result)};
};
'''


def start(preview, width, boot=''):
    call, evaluate, port = preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source': BOOT + boot})
    call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 900,
         'deviceScaleFactor': 1, 'mobile': width == 390})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#settings'})
    wait_for(evaluate, "document.readyState==='complete'&&!!window.WealthSettings&&!!window.WealthAutomationStatus&&!!document.getElementById('settingsApiFields')")
    evaluate(FRAMES)
    return call, evaluate


def loaded(evaluate, panel='Api'):
    wait_for(evaluate, f"!document.getElementById('settings{panel}Fields').disabled")


def request(evaluate, path, method):
    wait_for(evaluate, f"__settingsProbe.requests.some(r=>r.path==={json.dumps(path)}&&r.method==={json.dumps(method)})")
    return evaluate(f"__settingsProbe.requests.filter(r=>r.path==={json.dumps(path)}&&r.method==={json.dumps(method)}).at(-1)")


def fill(evaluate, selector, value):
    evaluate(f"document.querySelector({json.dumps(selector)}).value={json.dumps(value)}")


def assert_single_surface(evaluate):
    assert evaluate('__settingsProbe.legacy') == 0
    assert evaluate('__settingsProbe.legacyVisibleFrames') == 0
    assert evaluate('__settingsProbe.forms') == 1
    assert evaluate('__settingsProbe.moves') == 0
    assert evaluate('__settingsProbe.dialogs') == 0
    assert evaluate("document.querySelectorAll('#userOpenApiForm').length") == 1
    assert evaluate("document.querySelectorAll('#settingsContent').length") == 1
    assert evaluate("(()=>{const ids=[...document.querySelectorAll('#settingsSurface [id]')].map(e=>e.id);return new Set(ids).size===ids.length})()")
    assert evaluate('__settingsProbe.errors') == []


@pytest.mark.parametrize('width', [1280, 390])
def test_direct_settings_tabs_status_keyboard_and_layout(chrome_preview, width, tmp_path):
    call, evaluate = start(chrome_preview, width)
    loaded(evaluate)
    assert evaluate("document.querySelector('.wealth-workspace').dataset.activeView") == 'settings'
    assert evaluate("document.getElementById('settingsApiTab').getAttribute('aria-selected')") == 'true'
    assert evaluate("document.getElementById('settingsApiPanel').getBoundingClientRect().width") > 0
    assert evaluate("['Toss','Kb','Nh','Kis','Kiwoom','Krx','Dart'].every(n=>document.getElementById('openapi'+n+'Badge').classList.contains('connected'))")
    assert evaluate("document.getElementById('openapiKbAccountNo').value") == ''
    assert '*' in evaluate("document.getElementById('openapiKbAccountNo').placeholder")
    assert evaluate("[...document.querySelectorAll('#settingsSurface input[type=password]')].every(e=>!e.value)")
    assert '0.50.3' in evaluate("document.getElementById('settingsTossConfigured').textContent")
    assert evaluate("document.getElementById('settingsTossSessionSection').closest('[role=tabpanel]').id") == 'settingsApiPanel'
    assert evaluate("document.getElementById('tossWtsCard').closest('#realizedPnlPanel')!==null")
    for theme in ['purple', 'white']:
        evaluate(f"document.documentElement.dataset.theme='{theme}'")
        evaluate(FRAMES)
        no_overflow(evaluate, width)
        assert evaluate("[...document.querySelectorAll('#settingsApiPanel .openapi-broker-card')].every(e=>e.getBoundingClientRect().right<=innerWidth)")
        image = call('Page.captureScreenshot', {'format': 'png'})['data']
        (tmp_path / f'settings-api-{width}-{theme}.png').write_bytes(base64.b64decode(image))
    api_gets = evaluate("__settingsProbe.requests.filter(r=>r.method==='GET').length")
    click(call, evaluate, '#settingsNotificationsTab')
    loaded(evaluate, 'Notifications')
    assert evaluate("document.getElementById('settingsApiPanel').hidden")
    assert evaluate("['Telegram','Discord','Kakao'].every(p=>document.getElementById('settings'+p+'Enabled').checked)")
    assert evaluate("document.querySelector('#settingsNotificationsPanel #settingsTossSessionSection')") is None
    assert evaluate("document.getElementById('settingsDailyCloseTime').value") == '21:00'
    assert '사용 5' in evaluate("document.getElementById('settingsAutomationStatusSummary').textContent")
    no_overflow(evaluate, width)
    (tmp_path / f'settings-notifications-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format': 'png'})['data']))
    total_gets = evaluate("__settingsProbe.requests.filter(r=>r.method==='GET').length")
    assert total_gets > api_gets
    click(call, evaluate, '#settingsApiTab')
    click(call, evaluate, '#settingsNotificationsTab')
    assert evaluate("__settingsProbe.requests.filter(r=>r.method==='GET').length") == total_gets
    evaluate("document.getElementById('settingsNotificationsTab').focus()")
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Home', 'code': 'Home', 'windowsVirtualKeyCode': 36})
    assert evaluate('document.activeElement.id') == 'settingsApiTab'
    assert evaluate("document.getElementById('settingsApiTab').getAttribute('aria-selected')") == 'true'
    evaluate("location.hash='#assets'")
    wait_for(evaluate, "document.querySelector('.wealth-workspace').dataset.activeView==='assets'")
    evaluate("location.hash='#settings'")
    wait_for(evaluate, "document.querySelector('.wealth-workspace').dataset.activeView==='settings'")
    loaded(evaluate)
    assert evaluate("document.getElementById('settingsApiTab').getAttribute('aria-selected')") == 'true'
    assert evaluate("!document.getElementById('topbarFamilyBtn').closest('[role=tabpanel]')")
    assert evaluate("!document.getElementById('changePwBtn').closest('[role=tabpanel]')")
    assert_single_surface(evaluate)


@pytest.mark.parametrize('width', [1280, 390])
def test_settings_save_delete_test_and_secret_payloads(chrome_preview, width, tmp_path, monkeypatch):
    call, evaluate = start(chrome_preview, width)
    loaded(evaluate)
    fill(evaluate, '#openapiKbSecret', 'synthetic-kb-secret')
    click(call, evaluate, '#saveUserOpenApiBtn')
    payload = request(evaluate, '/api/user/openapi-config', 'POST')['body']
    assert payload == {'kb': {'app_key': 'kb****', 'app_secret': 'synthetic-kb-secret'}}
    # Replay the captured UI payload against the real storage contract in temp.
    from app.services import user_openapi
    users = tmp_path / 'users'
    monkeypatch.setattr(user_openapi, 'USERS_DIR', users)
    initial = {broker: {'app_key': broker + '-synthetic-key', 'app_secret': broker + '-old-secret',
                       'account_no': '12345678901'} for broker in ['toss', 'kb', 'nh', 'kis', 'kiwoom']}
    initial['kb'].update(account11='12345678901', gnl_ac_no='123456789', gds_no='01')
    initial['dart'] = {'api_key': 'synthetic-stored-dart'}
    target = users / 'settings-fixture' / 'openapi_config.json'
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(initial), encoding='utf-8')
    def fixture_config(username):
        assert username == 'settings-fixture'
        return json.loads(target.read_text(encoding='utf-8'))
    # Keep the full-suite credential guard intact; supply only this pinned fixture.
    monkeypatch.setattr(user_openapi, 'get_user_openapi_config', fixture_config)
    saved = user_openapi.save_user_openapi_config('settings-fixture', payload)
    expected = json.loads(json.dumps(initial))
    expected['kb']['app_secret'] = 'synthetic-kb-secret'
    assert saved == expected
    assert json.loads(target.read_text(encoding='utf-8')) == expected
    wait_for(evaluate, "document.getElementById('openapiKbSecret').value===''")
    fill(evaluate, '#openapiKrxPassword', 'synthetic-krx-secret')
    click(call, evaluate, '[onclick="saveKrxMarketplaceConfig()"]')
    assert request(evaluate, '/api/user/krx-marketplace-config', 'POST')['body'] == {'password': 'synthetic-krx-secret'}
    click(call, evaluate, '[onclick="testKrxMarketplaceConfig()"]')
    request(evaluate, '/api/user/krx-marketplace-config/test', 'POST')
    fill(evaluate, '#openapiDartKey', 'a' * 40)
    click(call, evaluate, '[onclick="handleSaveDartApi()"]')
    wait_for(evaluate, "__settingsProbe.requests.filter(r=>r.path==='/api/user/openapi-config'&&r.method==='POST').length===2")
    assert request(evaluate, '/api/user/openapi-config', 'POST')['body'] == {'dart': {'api_key': 'a' * 40}}
    click(call, evaluate, '[onclick="handleTestDartApi()"]')
    request(evaluate, '/api/user/openapi-config/dart/test', 'POST')
    for selector, path in [('#openapiDartDeleteBtn', '/api/user/openapi-config/dart'),
                           ('#openapiKrxDeleteBtn', '/api/user/krx-marketplace-config'),
                           ('#openapiNhDeleteBtn', '/api/user/openapi-config/nh')]:
        click(call, evaluate, selector)
        request(evaluate, path, 'DELETE')
    click(call, evaluate, '#settingsSaveTossSession')
    assert request(evaluate, '/api/settings/toss-wts', 'PATCH')['body'] == {'session_check_enabled': True}
    click(call, evaluate, '#settingsCheckTossSession')
    request(evaluate, '/api/settings/toss-wts/status', 'POST')
    click(call, evaluate, '#settingsTossLoginStart')
    assert request(evaluate, '/api/settings/toss-wts/login/start', 'POST')['body'] == {'reauthenticate': True}
    wait_for(evaluate, "!document.getElementById('settingsTossLoginCancel').hidden")
    click(call, evaluate, '#settingsTossLoginCancel')
    request(evaluate, '/api/settings/toss-wts/login/synthetic-attempt/cancel', 'POST')
    click(call, evaluate, '#settingsNotificationsTab')
    loaded(evaluate, 'Notifications')
    for provider in ['Telegram', 'Discord', 'Kakao']:
        click(call, evaluate, '#settings' + provider + 'Enabled')
        selector = '#settingsSave' + ('KakaoSecrets' if provider == 'Kakao' else provider)
        click(call, evaluate, selector)
        wait_for(evaluate, f"!document.querySelector({json.dumps(selector)}).disabled")
        patch = request(evaluate, '/api/settings/notifications', 'PATCH')['body']
        assert list(patch) == [provider.lower()]
        assert patch[provider.lower()]['enabled'] is False
        click(call, evaluate, '#settings' + provider + 'Enabled')
        click(call, evaluate, selector)
        wait_for(evaluate, f"!document.querySelector({json.dumps(selector)}).disabled")
        assert request(evaluate, '/api/settings/notifications', 'PATCH')['body'][provider.lower()]['enabled'] is True
    assert evaluate("!__settingsProbe.requests.some(r=>r.path.endsWith('/secrets'))")
    for selector, path in [('#settingsSendTest', '/api/settings/telegram/test'),
                           ('#settingsDiscordTest', '/api/settings/discord/test'),
                           ('#settingsKakaoTest', '/api/settings/kakao/test')]:
        click(call, evaluate, selector)
        request(evaluate, path, 'POST')
    click(call, evaluate, '#settingsSaveAutomation')
    assert request(evaluate, '/api/settings/automation', 'PATCH')['body']['automation']['daily_close']['time'] == '21:00'
    assert evaluate("[...document.querySelectorAll('#settingsSurface input[type=password]')].every(e=>!e.value)")
    assert_single_surface(evaluate)
    no_overflow(evaluate, width)


@pytest.mark.parametrize('width', [1280, 390])
def test_settings_delayed_load_failure_and_explicit_retry(chrome_preview, width):
    call, evaluate = start(chrome_preview, width, '__settingsProbe.hold=true;')
    wait_for(evaluate, '__settingsProbe.pending.length===3')
    assert evaluate("document.getElementById('settingsApiFields').disabled")
    assert evaluate("document.getElementById('settingsApiLoading').hidden") is False
    evaluate('__settingsProbe.fail=true;__settingsProbe.hold=false;__settingsProbe.pending.splice(0).forEach(resolve=>resolve())')
    wait_for(evaluate, "!document.getElementById('settingsApiError').hidden")
    assert evaluate("document.getElementById('settingsApiFields').disabled")
    evaluate('__settingsProbe.fail=false')
    click(call, evaluate, '[data-settings-retry=api]')
    loaded(evaluate)
    assert_single_surface(evaluate)


@pytest.mark.parametrize('width', [1280, 390])
def test_krx_failure_and_notification_retry_are_local(chrome_preview, width):
    call, evaluate = start(chrome_preview, width, "__settingsProbe.failPath='/api/user/krx-marketplace-config';")
    wait_for(evaluate, "!document.getElementById('settingsApiError').hidden")
    assert evaluate("document.getElementById('settingsApiFields').disabled")
    evaluate("__settingsProbe.failPath=''")
    click(call, evaluate, '[data-settings-retry=api]')
    loaded(evaluate)
    evaluate("__settingsProbe.failPath='/api/settings/notifications'")
    click(call, evaluate, '#settingsNotificationsTab')
    wait_for(evaluate, "!document.getElementById('settingsNotificationsError').hidden")
    assert evaluate("document.getElementById('settingsNotificationsFields').disabled")
    evaluate("__settingsProbe.failPath=''")
    click(call, evaluate, '[data-settings-retry=notifications]')
    loaded(evaluate, 'Notifications')
    assert evaluate("document.getElementById('settingsTelegramEnabled').checked")
    assert_single_surface(evaluate)
