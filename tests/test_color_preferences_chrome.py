"""Shared controls drive real visualization producers; all HTTP data is synthetic."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_asset_bucket_chrome import BOOT as PLANNING_BOOT
from tests.test_settings_surface_chrome import start
from tests.test_workflow_ux_chrome import FRAMES, click, no_overflow

BOOT = PLANNING_BOOT + r'''
window.__colorRequests=[];window.__colorData=JSON.parse(sessionStorage.getItem('test-colors')||'null')||{calendar_event_colors:{},asset_category_colors:{},stock_category_colors:{}};
const colorFetch=window.fetch;
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(path==='/api/color-preferences'){
  if(options.method==='PATCH'){const b=JSON.parse(options.body);__colorRequests.push(b);if(b.color===null)delete __colorData[b.group][b.key];else __colorData[b.group][b.key]=b.color;sessionStorage.setItem('test-colors',JSON.stringify(__colorData));}
  return {ok:true,json:async()=>structuredClone(__colorData)};
 }
 if(path==='/api/moneylog/calendar'){
  const month=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date()).slice(0,7);
  return {ok:true,json:async()=>({events:['ipo_subscription','ipo_listing','realized_pnl','realized_pnl','dividend','ledger_income','ledger_expense'].map((type,i)=>({id:'c'+i,type,date:month+'-0'+(i+1),amount_krw:i===3?-100:100,title:'Synthetic',meta:{company_name:'합성',ipo_id:'c'+i}}))})};
 }
 return colorFetch.apply(this,arguments);
};
'''

SETUP = r'''(()=>{
 const rows=[{name:'부동산',market_value_krw:60000,weight:60,holding_count:1,profit_krw:100,return_rate:1},{name:'현금·예수금',market_value_krw:40000,weight:40,holding_count:0,profit_krw:0,return_rate:0}];
 window.__colorSummary={owner:'모두',classifications:rows,netWorth:100000,invest:60000,cash:40000,expected:0,realized:0,safe:0};
 window.dispatchEvent(new CustomEvent('wealth:summary',{detail:__colorSummary}));
 dashboard.sector_classifications=[{...rows[0],name:'반도체'},rows[1]];
 renderClassifications([]);
 window.__financialSnapshot=JSON.stringify({summary:__colorSummary,view:__qView,rows:dashboard.sector_classifications});
})()'''


def open_group(call, evaluate, group):
    evaluate("location.hash='settings'")
    evaluate(FRAMES)
    for selector in ('#wealthColorSettings', f'[data-color-group="{group}"]'):
        if not evaluate(f'document.querySelector({json.dumps(selector)}).open'):
            click(call, evaluate, selector+' > summary')


def select_save(call, evaluate, group, key, color, width):
    open_group(call, evaluate, group)
    row = f'[data-color-group="{group}"] .wealth-color-setting-row[data-color-key="{key}"]'
    click(call, evaluate, row+' .wealth-color-trigger')
    assert evaluate(f'document.querySelector({json.dumps(row+" .wealth-color-palette")}).dataset.mode') == ('palette' if width == 390 else 'advanced')
    assert evaluate(f'document.querySelectorAll({json.dumps(row+" .wealth-color-choices button")}).length') == 8
    click(call, evaluate, row+f' [data-color="{color}"]')
    count = evaluate('__colorRequests.length')
    assert evaluate(f'WealthColorPreferences.resolve({json.dumps(group)},{json.dumps(key)})') == color
    click(call, evaluate, row+' [data-color-save]')
    wait_for(evaluate, f'__colorRequests.length==={count+1}&&!document.querySelector({json.dumps(row)}).inert')
    assert evaluate(f'__colorData[{json.dumps(group)}][{json.dumps(key)}]') == color


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_shared_preferences_render_round_trip_without_financial_changes(chrome_preview, width, theme, tmp_path):
    call, evaluate = start(chrome_preview, width, BOOT)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    wait_for(evaluate, "!!window.WealthColorPreferences&&!document.querySelector('[data-color-save]').disabled&&!!dashboard")
    evaluate(SETUP)
    evaluate('loadCalendar()')
    keys = ['ipo_subscription','ipo_listing','profit','loss','dividend','income','expense']
    palette = ['#FF5A5F','#FF9F1C','#FFD60A','#2ECF73','#22C7B8','#4D96FF','#FF5FA2']
    for key, color in zip(keys, palette):
        select_save(call, evaluate, 'calendar_event_colors', key, color, width)
        assert evaluate(f"getComputedStyle(document.querySelector('.calendar-legend-item[data-color-key={key}]')).getPropertyValue('--event-color').trim()") == color
        assert evaluate(f"getComputedStyle(document.querySelector('.cal-badge[data-color-key={key}]')).getPropertyValue('--event-color').trim()") == color
        assert evaluate(f"getComputedStyle(document.querySelector('.cal-badge[data-color-key={key}]')).borderLeftColor") == evaluate(f"(()=>{{const s=document.createElement('span');s.style.color='{color}';document.body.append(s);const c=getComputedStyle(s).color;s.remove();return c}})()")
    select_save(call, evaluate, 'asset_category_colors','real_estate','#22C7B8',width)
    assert '#22c7b8' in evaluate("document.getElementById('homeAssetAllocationDonut').style.background.toLowerCase()") or '34, 199, 184' in evaluate("document.getElementById('homeAssetAllocationDonut').style.background")
    for selector in ('#homeAssetAllocationLegend [data-color-key=real_estate]', '#wealthMixLegend [data-color-key=real_estate] span'):
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)})).getPropertyValue("--mix-color").trim()') == '#22C7B8'
    select_save(call, evaluate, 'stock_category_colors','semiconductor','#FF5FA2',width)
    assert evaluate("document.querySelector('circle[data-color-key=semiconductor]').getAttribute('stroke')") == '#FF5FA2'
    assert evaluate("getComputedStyle(document.querySelector('.classification-row[data-color-key=semiconductor] .bar i')).backgroundColor") == 'rgb(255, 95, 162)'
    assert evaluate("document.querySelector('.sector-legend-item[data-color-key=semiconductor]')!==null")
    assert evaluate('JSON.stringify({summary:__colorSummary,view:__qView,rows:dashboard.sector_classifications})') == evaluate('__financialSnapshot')
    no_overflow(evaluate, width)
    tmp_path.joinpath(f'colors-{width}-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
    for route, target in [('home','#homeAssetAllocationDonut'), ('invest','#sectorDonutWrap'), ('income','#calendarGridWrapper')]:
        evaluate(f"location.hash='{route}'")
        evaluate(FRAMES)
        if route == 'invest':
            click(call,evaluate,'[data-invest=overview]')
        if route == 'income':
            click(call,evaluate,'[data-income=calendar]')
            evaluate('loadCalendar()')
        assert evaluate(f'document.querySelector({json.dumps(target)}).getBoundingClientRect().width>0')
        no_overflow(evaluate,width)
        tmp_path.joinpath(f'{route}-{width}-{theme}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
    evaluate("location.hash='invest'")
    evaluate(FRAMES)
    click(call,evaluate,'[data-invest=buckets]')
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__qView}))")
    assert evaluate("getComputedStyle(document.querySelector('.wealth-bucket-constituent[data-bucket-id=core]')).getPropertyValue('--bucket-color').trim()") == '#A78BFA'
    assert evaluate("document.querySelectorAll('.wealth-bucket-constituent[data-bucket-id=cash] [data-assign-holding]').length") == 0
    generation = evaluate('__qLoad')
    call('Page.reload', {})
    wait_for(evaluate, f"window.__qLoad==={generation+1}&&document.readyState==='complete'&&!!window.WealthColorPreferences&&typeof dashboard!=='undefined'&&!!dashboard&&WealthColorPreferences.resolve('stock_category_colors','semiconductor')==='#FF5FA2'")
    evaluate(SETUP)
    assert evaluate("document.querySelector('circle[data-color-key=semiconductor]').getAttribute('stroke')") == '#FF5FA2'
    open_group(call,evaluate,'stock_category_colors')
    row='[data-color-group=stock_category_colors] [data-color-key=semiconductor]'
    click(call,evaluate,row+' [data-color-reset]')
    wait_for(evaluate,"!Object.hasOwn(__colorData.stock_category_colors,'semiconductor')")
    assert evaluate("document.querySelector('circle[data-color-key=semiconductor]').getAttribute('stroke')") != '#FF5FA2'
    assert evaluate('__settingsProbe.errors') == []
