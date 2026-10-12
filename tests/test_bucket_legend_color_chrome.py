"""Native shared picker, synthetic canonical planning requests, no real data."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_asset_bucket_chrome import BOOT as PLANNING_BOOT
from tests.test_settings_surface_chrome import start
from tests.test_workflow_ux_chrome import FRAMES, click, no_overflow

BOOT = PLANNING_BOOT + r'''
window.__colorRequests=[];
const bucketColorFetch=window.fetch;
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(path==='/api/color-preferences'){
  if(options.method==='PATCH')__colorRequests.push(JSON.parse(options.body));
  return {ok:true,json:async()=>({calendar_event_colors:{},asset_category_colors:{},stock_category_colors:{}})};
 }
 if(path==='/api/planning/buckets'&&options.method==='POST'&&window.__failBucketColor){
  __qRequests.push({path,body:JSON.parse(options.body)});
  return {ok:false,json:async()=>({detail:'Synthetic bucket save failure'})};
 }
 return bucketColorFetch.apply(this,arguments);
};
'''


def prepare(preview,width,theme='purple'):
    call,evaluate=start(preview,width,BOOT)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    wait_for(evaluate,"!!document.querySelector('[data-bucket-filter=core]')&&!!window.WealthColorPreferences")
    evaluate("location.hash='invest'")
    evaluate(FRAMES)
    click(call,evaluate,'[data-invest=buckets]')
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__qView}))")
    return call,evaluate


def open_editor(call,evaluate,chart='target',key='core'):
    selector=f'.wealth-bucket-legend-row[data-bucket-chart={chart}] button[data-bucket-color={key}]'
    click(call,evaluate,selector)
    assert evaluate("!!document.querySelector('.wealth-visualization-editor .wealth-color-palette:not([hidden])')")
    assert evaluate("getComputedStyle(document.querySelector('.wealth-visualization-editor [data-color-reset]')).display") == 'none'
    assert evaluate("(()=>{const r=document.querySelector('.wealth-visualization-editor .wealth-color-palette').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight-(innerWidth<768?88:0)})()")
    assert evaluate("document.querySelector('.wealth-visualization-editor').dataset.colorGroup") == 'planning_bucket_colors'


def choose(call,evaluate,color):
    click(call,evaluate,f'.wealth-visualization-editor [data-color="{color}"]')


def assert_color(evaluate,color,key='core'):
    for chart in ('target','current'):
        selector=f'.wealth-bucket-legend-row[data-bucket-chart={chart}][data-bucket-key={key}]'
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)})).getPropertyValue("--bucket-color").trim()') == color
        assert evaluate(f'document.querySelector({json.dumps(selector+" button[data-bucket-color]")}).style.getPropertyValue("--chosen-color")') == color
        gradient=evaluate(f'document.querySelector(".wealth-bucket-donut[data-bucket-chart={chart}]").style.background.toLowerCase()')
        rgb=', '.join(str(int(color[i:i+2],16)) for i in (1,3,5))
        assert color.lower() in gradient or f'rgb({rgb})' in gradient
    for selector in (f'[data-bucket-filter={key}]',f'.wealth-bucket-constituent[data-bucket-id={key}]',f'.wealth-bucket-constituent[data-bucket-id={key}] .wealth-bucket-badge'):
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)})).getPropertyValue("--bucket-color").trim()') == color


@pytest.mark.parametrize('width',[1280,390])
@pytest.mark.parametrize('theme',['purple','white','oled'])
def test_bucket_legends_preview_save_reload_cancel_and_hover(chrome_preview,width,theme,tmp_path):
    call,evaluate=prepare(chrome_preview,width,theme)
    before=evaluate('JSON.stringify(__qView)')
    original=evaluate('structuredClone(__qState)')
    open_editor(call,evaluate)
    assert evaluate("document.querySelector('.wealth-visualization-editor .wealth-color-palette').dataset.mode") == ('palette' if width==390 else 'advanced')
    assert evaluate("document.querySelectorAll('.wealth-visualization-editor .wealth-color-choices button').length") == 8
    choose(call,evaluate,'#2ECF73')
    assert evaluate('__qRequests.length') == 0
    assert_color(evaluate,'#2ECF73')
    tmp_path.joinpath(f'bucket-inline-{width}-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
    click(call,evaluate,'.wealth-visualization-editor [data-color-save]')
    wait_for(evaluate,"__qState.buckets[0].color==='#2ECF73'&&!document.querySelector('.wealth-visualization-editor')")
    assert evaluate('__qRequests.length') == 1
    request=evaluate('__qRequests[0]')
    assert request['path'] == '/api/planning/buckets'
    expected=json.loads(json.dumps(original['buckets']))
    expected[0]['color']='#2ECF73'
    assert request['body'] == dict(revision=original['revision'],buckets=expected,accounts=original['accounts'],holdings=original['holdings'])
    assert_color(evaluate,'#2ECF73')
    assert evaluate("document.querySelector('.wealth-bucket-edit-row[data-id=core] .wealth-color-picker').dataset.color") == '#2ECF73'
    generation=evaluate('__qLoad')
    call('Page.reload',{})
    wait_for(evaluate,f"window.__qLoad==={generation+1}&&document.readyState==='complete'&&!!document.querySelector('[data-bucket-filter=core]')")
    evaluate("location.hash='invest'")
    evaluate(FRAMES)
    click(call,evaluate,'[data-invest=buckets]')
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__qView}))")
    assert_color(evaluate,'#2ECF73')
    open_editor(call,evaluate,'current')
    choose(call,evaluate,'#FF5FA2')
    assert_color(evaluate,'#FF5FA2')
    assert evaluate('__qRequests.length') == 0
    click(call,evaluate,'.wealth-visualization-editor [data-color-cancel]')
    assert_color(evaluate,'#2ECF73')
    assert evaluate("document.activeElement.closest('[data-bucket-chart]').dataset.bucketChart") == 'current'
    assert evaluate("document.activeElement.matches('button[data-bucket-color=core]')")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    wait_for(evaluate,"!!document.querySelector('.wealth-visualization-editor')")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
    assert evaluate('document.querySelector(".wealth-visualization-editor")===null')
    # Existing row hover and focus still highlight its own chart segment.
    selector='.wealth-bucket-legend-row[data-bucket-chart=current][data-bucket-key=core]'
    evaluate(f'document.querySelector({json.dumps(selector)}).scrollIntoView({{block:"center",behavior:"instant"}})')
    evaluate(FRAMES)
    point=evaluate(f'(()=>{{const r=document.querySelector({json.dumps(selector)}).getBoundingClientRect();return {{x:r.right-8,y:r.top+r.height/2}}}})()')
    call('Input.dispatchMouseEvent',{'type':'mouseMoved',**point})
    assert evaluate(f'document.querySelector({json.dumps(selector)}).classList.contains("is-donut-active")')
    evaluate(f'document.querySelector({json.dumps(selector)}).focus()')
    assert evaluate("document.querySelector('.wealth-bucket-donut[data-bucket-chart=current]').classList.contains('has-donut-hover')")
    # A configured cash bucket is editable without changing cash classification.
    open_editor(call,evaluate,'current','cash')
    choose(call,evaluate,'#4D96FF')
    click(call,evaluate,'.wealth-visualization-editor [data-color-save]')
    wait_for(evaluate,"__qState.buckets.find(b=>b.id==='cash').color==='#4D96FF'")
    assert_color(evaluate,'#4D96FF','cash')
    assert evaluate("document.querySelectorAll('.wealth-bucket-constituent[data-bucket-id=cash] [data-assign-holding]').length") == 0
    assert evaluate('JSON.stringify(__qView)') == before
    assert evaluate('__colorRequests.length') == 0
    no_overflow(evaluate,width)
    assert evaluate('__settingsProbe.errors') == []


@pytest.mark.parametrize('width',[1280,390])
def test_bucket_color_dirty_failure_conflict_and_system_items(chrome_preview,width):
    call,evaluate=prepare(chrome_preview,width)
    original=evaluate('structuredClone(__qState)')
    open_editor(call,evaluate)
    choose(call,evaluate,'#FF5FA2')
    evaluate('__failBucketColor=true')
    click(call,evaluate,'.wealth-visualization-editor [data-color-save]')
    wait_for(evaluate,"document.querySelector('.wealth-inline-color-status')?.textContent.includes('Synthetic bucket save failure')")
    assert_color(evaluate,'#A78BFA')
    assert evaluate('__qState') == original
    click(call,evaluate,'.wealth-visualization-editor [data-color-cancel]')
    evaluate('__failBucketColor=false')
    open_editor(call,evaluate,'current')
    choose(call,evaluate,'#FF5FA2')
    # Another client advances the canonical revision and color before our save.
    evaluate("__qState.revision++;__qState.buckets[0].color='#22C7B8'")
    latest=evaluate('structuredClone(__qState)')
    click(call,evaluate,'.wealth-visualization-editor [data-color-save]')
    wait_for(evaluate,"document.querySelector('.wealth-inline-color-status')?.textContent.includes('revision conflict')")
    assert evaluate('__qState') == latest
    assert_color(evaluate,'#22C7B8')
    assert evaluate('__qRequests.length') == 2
    click(call,evaluate,'.wealth-visualization-editor [data-color-cancel]')
    click(call,evaluate,'#wealthBucketEditor > summary')
    evaluate("(()=>{const i=document.querySelector('.wealth-bucket-edit-row[data-id=core] [name=bucketName]');i.value='미저장 이름';i.dispatchEvent(new Event('input',{bubbles:true}));})()")
    draft=evaluate("document.getElementById('wealthBucketRows').innerHTML")
    count=evaluate('__qRequests.length')
    click(call,evaluate,'.wealth-bucket-legend-row[data-bucket-chart=target] [data-bucket-color=core]')
    assert evaluate("document.getElementById('wealthBucketStatus').textContent.includes('저장하지 않은 버킷 설정')")
    assert evaluate('document.querySelector(".wealth-visualization-editor")===null')
    assert evaluate("document.getElementById('wealthBucketRows').innerHTML") == draft
    assert evaluate("document.querySelector('.wealth-bucket-edit-row[data-id=core] [name=bucketName]').value") == '미저장 이름'
    assert evaluate('__qRequests.length') == count
    click(call,evaluate,'#wealthReloadPlanning')
    wait_for(evaluate,"document.querySelector('.wealth-bucket-edit-row[data-id=core] [name=bucketName]').value==='코어'")
    # No configured cash bucket: system fallback and unclassified are read-only.
    evaluate("__qState.buckets=__qState.buckets.filter(b=>b.id!=='cash');delete __qState.accounts.a;__qState.buckets[0].target=20;sessionStorage.setItem('q-planning',JSON.stringify(__qState));window.dispatchEvent(new CustomEvent('wealth:planning-refresh'))")
    wait_for(evaluate,"!!document.querySelector('.wealth-bucket-legend-row[data-bucket-key=__cash__]')")
    assert evaluate("document.querySelectorAll('[data-bucket-color=__cash__],[data-bucket-color=__unclassified__],[data-bucket-color=__unallocated__]').length") == 0
    assert evaluate("getComputedStyle(document.querySelector('.wealth-bucket-legend-row[data-bucket-key=__cash__]')).getPropertyValue('--bucket-color').trim()") == '#1D4ED8'
    assert evaluate('__colorRequests.length') == 0
    assert evaluate('__settingsProbe.errors') == []
