"""Native Chrome, synthetic planning endpoint and session-only navigation."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_settings_surface_chrome import start
from tests.test_workflow_ux_chrome import FRAMES, click, no_overflow


BOOT = r'''
window.__qLoad=Number(sessionStorage.getItem('q-load')||0)+1;sessionStorage.setItem('q-load',String(__qLoad));
window.__qRequests=[];
window.__qState=JSON.parse(sessionStorage.getItem('q-planning')||'null')||{revision:0,history:[],buckets:[{id:'core',name:'코어',target:40},{id:'growth',name:'성장',target:40},{id:'cash',name:'현금',target:20,color:'#1D4ED8'}],accounts:{a:'core',b:'growth'},holdings:{}};
window.__qView={owner:'모두',fxRates:{USD:1300},accounts:[{id:'a',name:'연금저축',broker:'가상증권',cash_krw:1000},{id:'b',name:'계좌 B',broker:'가상증권',cash_krw:100}],holdings:[{id:'h1',account_id:'a',code:'SAME',name:'가상 인덱스',quantity:5,market_value_krw:5000},{id:'h2',account_id:'b',code:'SAME',name:'가상 인덱스',quantity:3,market_value_krw:3000}]};
const qFetch=window.fetch;
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(path.startsWith('/api/planning')){
  if(options.method==='POST'){
   const body=JSON.parse(options.body);__qRequests.push({path,body});
   if(body.revision!==__qState.revision)return {ok:false,json:async()=>({detail:'revision conflict'})};
   if(path.endsWith('/bucket-assignment')){
    if(body.mode==='inherit')delete __qState.holdings[body.target_id];
    else __qState.holdings[body.target_id]=body.mode==='unclassified'?'':body.bucket_id;
   }else if(path.endsWith('/buckets')){__qState={...__qState,buckets:body.buckets,accounts:body.accounts,holdings:body.holdings};}
   __qState.revision++;sessionStorage.setItem('q-planning',JSON.stringify(__qState));
  }
  return {ok:true,json:async()=>structuredClone(__qState)};
 }
 return qFetch.apply(this,arguments);
};
window.__qPaint=[];
const qFrame=()=>{const p=document.getElementById('catPanelSecurities');
 if(location.hash==='#assets'&&document.documentElement.dataset.wealthAssetCategory!=='securities'&&p&&p.getBoundingClientRect().width>0)__qPaint.push('securities');requestAnimationFrame(qFrame);};requestAnimationFrame(qFrame);
'''


def prepare(preview, width):
    call, evaluate = start(preview, width, BOOT)
    wait_for(evaluate, "!!document.querySelector('[data-bucket-filter=core]')")
    evaluate("location.hash='invest'")
    evaluate(FRAMES)
    click(call, evaluate, '[data-invest="buckets"]')
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__qView}))")
    return call, evaluate


def assignment(call, evaluate, value):
    click(call, evaluate, '[data-assign-holding="h1"]')
    evaluate(f"(()=>{{const s=document.querySelector('.wealth-holding-picker');s.value={json.dumps(value)};s.dispatchEvent(new Event('change',{{bubbles:true}}))}})()")
    wait_for(evaluate, "document.querySelector('.wealth-holding-picker')===null")
    evaluate(FRAMES)


def reload_page(call, evaluate):
    generation = evaluate('__qLoad')
    call('Page.reload', {})
    wait_for(evaluate, f"window.__qLoad==={generation + 1}&&document.readyState==='complete'&&!!window.WealthSettings&&!!document.querySelector('[data-bucket-filter=core]')")
    evaluate(FRAMES)


@pytest.mark.parametrize('width', [1280, 390])
def test_asset_categories_restore_all_tabs_toolbar_and_first_paint(chrome_preview, width):
    call, evaluate = prepare(chrome_preview, width)
    evaluate("location.hash='assets'")
    evaluate(FRAMES)
    ids = {'securities': ('Securities', 'securities'), 'banking': ('Banking', 'banking'),
           'insurance': ('Insurance', 'insurance'), 'real_estate': ('RealEstate', 'realEstate')}
    assert evaluate("[...document.querySelectorAll('#assetCategoryTabs [role=tab]')].map(b=>b.dataset.cat)") == list(ids)
    for category, (panel, toolbar) in ids.items():
        click(call, evaluate, f'[data-cat="{category}"]')
        assert evaluate("sessionStorage.getItem('wealth_asset_category')") == category
        reload_page(call, evaluate)
        evaluate(FRAMES)
        assert evaluate('WealthAssetCategoryState.current()') == category
        assert evaluate(f"document.querySelector('[data-cat={category}]').getAttribute('aria-selected')") == 'true'
        assert evaluate(f"getComputedStyle(document.getElementById('catPanel{panel}')).display") == 'block'
        assert evaluate(f"getComputedStyle(document.getElementById('{toolbar}Actions')).display") == 'flex'
        assert evaluate('__qPaint') == []
        no_overflow(evaluate, width)
    evaluate("sessionStorage.setItem('wealth_asset_category','deleted-category')")
    reload_page(call, evaluate)
    assert evaluate('WealthAssetCategoryState.current()') == 'securities'


@pytest.mark.parametrize('width', [1280, 390])
def test_direct_assignment_modes_filters_cash_and_reload(chrome_preview, width):
    call, evaluate = prepare(chrome_preview, width)
    before = evaluate('JSON.stringify(__qView)')
    click(call, evaluate, '[data-bucket-filter="core"]')
    assignment(call, evaluate, 'growth')
    assert evaluate('__qState.holdings') == {'h1': 'growth'}
    assert evaluate("document.querySelectorAll('[data-assign-holding=h1]').length") == 0
    assert evaluate("document.querySelector('[data-bucket-filter=core] strong').textContent") == '0원'
    assert evaluate("document.querySelector('[data-bucket-filter=growth] strong').textContent") == '8,000원'
    click(call, evaluate, '[data-bucket-filter="core"]')
    assignment(call, evaluate, '')
    assert evaluate('__qState.holdings') == {'h1': ''}
    assignment(call, evaluate, '__inherit__')
    assert evaluate('__qState.holdings') == {}
    assert evaluate("document.querySelector('[data-assign-holding=h1]').textContent.trim()") == '코어 ▾'
    assignment(call, evaluate, 'cash')  # Deliberate security classification as cash remains allowed.
    assert evaluate('__qState.holdings.h1') == 'cash'
    assignment(call, evaluate, 'growth')
    reload_page(call, evaluate)
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__qView}))")
    assert evaluate('__qState.holdings.h1') == 'growth'
    assert evaluate("document.querySelectorAll('[aria-label=\"예수금은 현금 버킷으로 고정됩니다\"]').length") == 2
    assert evaluate("document.querySelector('[aria-label=\"예수금은 현금 버킷으로 고정됩니다\"]').tagName") == 'SMALL'
    click(call, evaluate, '#wealthBucketEditor > summary')
    evaluate("(()=>{const s=document.querySelector('#wealthAccountAssignments select[data-id=a]');s.value='growth';s.dispatchEvent(new Event('change',{bubbles:true}))})()")
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.accounts.a==='growth'")
    assert evaluate("document.querySelector('[data-bucket-filter=cash] strong').textContent") == '1,100원'
    # Remove override, then changing the account default affects just inherited holdings.
    assignment(call, evaluate, '__inherit__')
    evaluate("document.querySelector('#wealthAccountAssignments select[data-id=a]').value='core';document.querySelector('#wealthAccountAssignments select[data-id=a]').dispatchEvent(new Event('change',{bubbles:true}))")
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.accounts.a==='core'")
    assert evaluate("document.querySelector('[data-assign-holding=h1]').textContent.trim()") == '코어 ▾'
    assert evaluate("document.querySelector('[data-bucket-filter=cash] strong').textContent") == '1,100원'
    assert evaluate('JSON.stringify(__qView)') == before
    assert evaluate("document.querySelector('#wealthHoldingAssignments')===null")
    no_overflow(evaluate, width)


@pytest.mark.parametrize('width', [1280, 390])
def test_dirty_editor_blocks_inline_request_and_preserves_draft(chrome_preview, width):
    call, evaluate = prepare(chrome_preview, width)
    click(call, evaluate, '#wealthBucketEditor > summary')
    evaluate("(()=>{const n=document.querySelector('[name=bucketName]');n.value='미저장 이름';n.dispatchEvent(new Event('input',{bubbles:true}))})()")
    click(call, evaluate, '[data-assign-holding=h1]')
    assert evaluate('__qRequests') == []
    assert evaluate("document.querySelector('[name=bucketName]').value") == '미저장 이름'
    assert evaluate("document.querySelector('.wealth-holding-picker')===null")
    assert '먼저 저장' in evaluate("document.getElementById('wealthBucketStatus').textContent")
    assert evaluate('__qState.revision') == 0


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_shared_color_picker_save_reload_rename_theme_and_density(chrome_preview, width, theme, tmp_path):
    call, evaluate = prepare(chrome_preview, width)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    click(call, evaluate, '#wealthBucketEditor > summary')
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=core] .wealth-color-trigger')
    assert evaluate("document.querySelector('.wealth-color-palette:not([hidden]) [aria-pressed=true]').dataset.color") == '#A78BFA'
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    assert evaluate("document.querySelectorAll('.wealth-color-palette:not([hidden])').length") == 0
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=core] .wealth-color-trigger')
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'ArrowRight', 'code': 'ArrowRight', 'windowsVirtualKeyCode': 39})
    assert evaluate('document.activeElement.dataset.color') == '#FB7185'
    click(call, evaluate, '#bucketPanel > h3')
    assert evaluate("document.querySelectorAll('.wealth-color-palette:not([hidden])').length") == 0
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=core] .wealth-color-trigger')
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=core] .wealth-color-palette [data-color="#5FC5D9"]')
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.buckets[0].color==='#5FC5D9'")
    for selector in ('[data-bucket-filter=core]', '.wealth-bucket-legend-row[data-bucket-key=core]', '[data-assign-holding=h1]'):
        assert evaluate(f"getComputedStyle(document.querySelector({json.dumps(selector)})).getPropertyValue('--bucket-color').trim()") == '#5FC5D9'
    assert '#5FC5D9'.lower() in evaluate("document.querySelector('.wealth-bucket-donut[data-bucket-chart=current]').style.background").lower() or '95, 197, 217' in evaluate("document.querySelector('.wealth-bucket-donut[data-bucket-chart=current]').style.background")
    evaluate("(()=>{const n=document.querySelector('[name=bucketName]');n.value='새 이름';n.dispatchEvent(new Event('input',{bubbles:true}))})()")
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.buckets[0].name==='새 이름'")
    assert evaluate('__qState.buckets[0].color') == '#5FC5D9'
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=cash] .wealth-color-trigger')
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=cash] .wealth-color-palette [data-color="#CF788B"]')
    click(call, evaluate, '#wealthBucketForm button[type=submit]')
    wait_for(evaluate, "__qState.buckets[2].color==='#CF788B'")
    assert evaluate("getComputedStyle(document.querySelector('[aria-label=\"예수금은 현금 버킷으로 고정됩니다\"]')).getPropertyValue('--bucket-color').trim()") == '#CF788B'
    reload_page(call, evaluate)
    evaluate(f"document.documentElement.dataset.theme='{theme}';window.dispatchEvent(new CustomEvent('wealth:portfolio',{{detail:__qView}}))")
    click(call, evaluate, '#wealthBucketEditor > summary')
    assert evaluate("document.querySelector('.wealth-bucket-edit-row[data-id=core] .wealth-color-picker').dataset.color") == '#5FC5D9'
    click(call, evaluate, '.wealth-bucket-edit-row[data-id=core] .wealth-color-trigger')
    no_overflow(evaluate, width)
    assert evaluate("(()=>{const r=document.querySelector('.wealth-color-palette:not([hidden])').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth})()")
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    assert evaluate("getComputedStyle(document.querySelector('#wealthBucketForm input')).fontSize") == '13px'
    geometry = evaluate("""(()=>{const row=document.querySelector('.wealth-bucket-edit-row'), s=getComputedStyle(row), r=row.getBoundingClientRect();
      return {viewport:innerWidth,rowWidth:r.width,columns:s.gridTemplateColumns,padding:s.padding,
      labelFont:getComputedStyle(row.querySelector('label')).fontSize,inputFont:getComputedStyle(row.querySelector('input')).fontSize,
      accountFont:getComputedStyle(document.querySelector('.wealth-assignment')).fontSize,
      overflow:document.documentElement.scrollWidth>innerWidth,
      labelColor:getComputedStyle(document.querySelector('[data-bucket-filter=core] h4')).color,
      themeText:getComputedStyle(document.documentElement).getPropertyValue('--text').trim()};})()""")
    assert geometry['overflow'] is False
    assert len(geometry['columns'].split()) == (2 if width == 390 else 5)
    assert geometry['labelFont'] == '12px'
    tmp_path.joinpath(f'planning-{width}-{theme}.json').write_text(json.dumps(geometry, indent=2), encoding='utf-8')
    tmp_path.joinpath(f'planning-{width}-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format': 'png'})['data']))
