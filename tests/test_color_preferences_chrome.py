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
  if(options.method==='PATCH'){const b=JSON.parse(options.body);__colorRequests.push(b);if(window.__colorFailPatch)return {ok:false,json:async()=>({detail:'Synthetic save failure'})};if(b.color===null)delete __colorData[b.group][b.key];else __colorData[b.group][b.key]=b.color;sessionStorage.setItem('test-colors',JSON.stringify(__colorData));}
  return {ok:true,json:async()=>structuredClone(__colorData)};
 }
 if(path==='/api/moneylog/calendar'){
  const month=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date()).slice(0,7);
  return {ok:true,json:async()=>({events:['ipo_subscription','ipo_listing','realized_pnl','realized_pnl','dividend','ledger_income','ledger_expense','interest'].map((type,i)=>({id:'c'+i,type,date:month+'-0'+(type==='interest'?5:i+1),amount_krw:i===3?-100:100,title:'Synthetic',meta:{company_name:'합성',ipo_id:'c'+i}}))})};
 }
 return colorFetch.apply(this,arguments);
};
'''

SETUP = r'''(()=>{
 const rows=[{name:'부동산',market_value_krw:60000,weight:60,holding_count:1,profit_krw:100,return_rate:1},{name:'현금·예수금',market_value_krw:40000,weight:40,holding_count:0,profit_krw:0,return_rate:0}];
 window.__colorSummary={owner:'모두',classifications:rows,netWorth:100000,invest:60000,cash:40000,expected:0,realized:0,safe:0};
 window.dispatchEvent(new CustomEvent('wealth:summary',{detail:__colorSummary}));
 dashboard.sector_classifications=[{...rows[0],name:'반도체'},rows[1],{name:'새로운 테마',market_value_krw:100,weight:0.1,holding_count:1,profit_krw:0,return_rate:0}];
 renderClassifications([]);
 window.__financialSnapshot=JSON.stringify({summary:__colorSummary,view:__qView,rows:dashboard.sector_classifications});
})()'''


def open_editor(call, evaluate, group, key):
    route = {'calendar_event_colors':'income','asset_category_colors':'home','stock_category_colors':'invest'}[group]
    evaluate(f"location.hash='{route}'")
    evaluate(FRAMES)
    if group == 'calendar_event_colors':
        click(call,evaluate,'[data-income=calendar]')
        evaluate('loadCalendar()')
        selector = f'.calendar-legend-item[data-inline-color][data-color-key="{key}"]'
    elif group == 'asset_category_colors':
        selector = f'#wealthMixLegend button[data-inline-color][data-color-key="{key}"]'
    else:
        click(call,evaluate,'[data-invest=overview]')
        selector = f'.classification-row[data-color-key="{key}"] button[data-inline-color]'
    wait_for(evaluate,f'!!document.querySelector({json.dumps(selector)})')
    search = evaluate("document.getElementById('searchInput').value")
    click(call,evaluate,selector)
    assert evaluate("document.getElementById('searchInput').value") == search
    assert evaluate("!!document.querySelector('.wealth-visualization-editor .wealth-color-palette:not([hidden])')"), evaluate('__settingsProbe.errors')
    return '.wealth-visualization-editor'


def select_save(call, evaluate, group, key, color, width):
    editor = open_editor(call,evaluate,group,key)
    assert evaluate(f'document.querySelector({json.dumps(editor+" .wealth-color-palette")}).dataset.mode') == ('palette' if width == 390 else 'advanced')
    assert evaluate(f'document.querySelectorAll({json.dumps(editor+" .wealth-color-choices button")}).length') == 8
    assert evaluate("(()=>{const r=document.querySelector('.wealth-visualization-editor .wealth-color-palette').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight-(innerWidth<768?88:0)})()")
    count = evaluate('__colorRequests.length')
    click(call,evaluate,editor+f' [data-color="{color}"]')
    assert evaluate('__colorRequests.length') == count
    assert evaluate(f'WealthColorPreferences.resolve({json.dumps(group)},{json.dumps(key)})') == color
    click(call,evaluate,editor+' [data-color-save]')
    wait_for(evaluate,f'__colorRequests.length==={count+1}&&!document.querySelector(".wealth-visualization-editor")')
    assert evaluate(f'__colorData[{json.dumps(group)}][{json.dumps(key)}]') == color


def reset_color(call,evaluate,group,key):
    editor = open_editor(call,evaluate,group,key)
    click(call,evaluate,editor+' [data-color-reset]')
    wait_for(evaluate,f'!Object.hasOwn(__colorData[{json.dumps(group)}],{json.dumps(key)})&&!document.querySelector(".wealth-visualization-editor")')


def click_visible_stock_row(call,evaluate):
    evaluate("document.querySelector('.classification-row[data-color-key=semiconductor]').scrollIntoView({block:'center',behavior:'instant'})")
    evaluate(FRAMES)
    point=evaluate("(()=>{const e=document.querySelector('.classification-row[data-color-key=semiconductor]'),r=e.getBoundingClientRect();for(const xf of [.98,.02,.5])for(const yf of [.1,.5,.9]){const x=r.left+r.width*xf,y=r.top+r.height*yf,hit=document.elementFromPoint(x,y);if(e.contains(hit)&&!hit.closest('[data-inline-color]'))return {x,y};}return null})()")
    assert point is not None, 'No visible non-color area of the stock row'
    for kind in ('mousePressed','mouseReleased'):
        call('Input.dispatchMouseEvent',{'type':kind,**point,'button':'left','clickCount':1})
    evaluate(FRAMES)


def assert_dividend_interest_colors(call, evaluate, color, refresh=True):
    if refresh:
        evaluate("location.hash='income'")
        evaluate(FRAMES)
        click(call, evaluate, '[data-income=calendar]')
        evaluate('loadCalendar()')
        wait_for(evaluate, "!!document.querySelector('.cal-badge.tone-interest')")
        click(call, evaluate, '.cal-day-cell[data-date$="-05"]')
    expected_rgb = 'rgb('+', '.join(str(int(color[i:i+2],16)) for i in (1,3,5))+')'
    for selector in ('.cal-badge.tone-dividend', '.cal-badge.tone-interest',
                     '.calendar-event-item[data-event-id=c4]', '.calendar-event-item[data-event-id=c7]'):
        assert evaluate(f'document.querySelector({json.dumps(selector)}).dataset.colorKey') == 'dividend'
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)})).getPropertyValue("--event-color").trim()') == color
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)})).borderLeftColor') == expected_rgb
        if selector.startswith('.cal-badge'):
            assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)})).color') == expected_rgb
    assert evaluate("getComputedStyle(document.querySelector('.calendar-legend-item[data-color-key=dividend]')).getPropertyValue('--event-color').trim()") == color
    assert evaluate("getComputedStyle(document.querySelector('.calendar-legend-item[data-color-key=dividend]')).color") == expected_rgb
    assert evaluate("!Object.hasOwn(__colorData.calendar_event_colors,'interest')")


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_shared_preferences_render_round_trip_without_financial_changes(chrome_preview, width, theme, tmp_path):
    call, evaluate = start(chrome_preview, width, BOOT)
    evaluate(f"document.documentElement.dataset.theme='{theme}'")
    wait_for(evaluate, "!!window.WealthColorPreferences&&WealthColorPreferences.loaded&&!!dashboard")
    evaluate(SETUP)
    evaluate('loadCalendar()')
    keys = ['ipo_subscription','ipo_listing','profit','loss','dividend','income','expense']
    evaluate("location.hash='settings'")
    evaluate(FRAMES)
    assert evaluate("document.getElementById('wealthColorSettings')===null&&document.querySelector('.wealth-color-setting-row')===null")
    assert evaluate("WealthColorPreferences.calendar.map(row=>row[0])") == keys
    assert_dividend_interest_colors(call, evaluate, '#FFE082')
    palette = ['#FF5A5F','#FF9F1C','#FFD60A','#2ECF73','#22C7B8','#4D96FF','#FF5FA2']
    for key, color in zip(keys, palette):
        select_save(call, evaluate, 'calendar_event_colors', key, color, width)
        assert evaluate(f"getComputedStyle(document.querySelector('.calendar-legend-item[data-color-key={key}]')).getPropertyValue('--event-color').trim()") == color
        assert evaluate(f"getComputedStyle(document.querySelector('.cal-badge[data-color-key={key}]')).getPropertyValue('--event-color').trim()") == color
        assert evaluate(f"getComputedStyle(document.querySelector('.cal-badge[data-color-key={key}]')).borderLeftColor") == evaluate(f"(()=>{{const s=document.createElement('span');s.style.color='{color}';document.body.append(s);const c=getComputedStyle(s).color;s.remove();return c}})()")
        expected_rgb = 'rgb('+', '.join(str(int(color[i:i+2],16)) for i in (1,3,5))+')'
        assert evaluate(f"getComputedStyle(document.querySelector('.cal-badge[data-color-key={key}]')).color") == expected_rgb
        assert evaluate(f"getComputedStyle(document.querySelector('.calendar-legend-item[data-color-key={key}]')).color") == expected_rgb
        if key == 'dividend':
            assert_dividend_interest_colors(call, evaluate, color, refresh=False)
    assert_dividend_interest_colors(call, evaluate, '#22C7B8')
    select_save(call, evaluate, 'asset_category_colors','real_estate','#22C7B8',width)
    assert '#22c7b8' in evaluate("document.getElementById('homeAssetAllocationDonut').style.background.toLowerCase()") or '34, 199, 184' in evaluate("document.getElementById('homeAssetAllocationDonut').style.background")
    for selector in ('#homeAssetAllocationLegend [data-color-key=real_estate]', '#wealthMixLegend [data-color-key=real_estate] span'):
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)})).getPropertyValue("--mix-color").trim()') == '#22C7B8'
    select_save(call, evaluate, 'stock_category_colors','semiconductor','#FF5FA2',width)
    assert evaluate("document.querySelector('circle[data-color-key=semiconductor]').getAttribute('stroke')") == '#FF5FA2'
    assert evaluate("getComputedStyle(document.querySelector('.classification-row[data-color-key=semiconductor] .bar i')).backgroundColor") == 'rgb(255, 95, 162)'
    for selector in ('.classification-row[data-color-key=semiconductor] button[data-inline-color]',
                     '.sector-legend-item[data-color-key=semiconductor] button[data-inline-color]'):
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)}),"::before").backgroundColor') == 'rgb(255, 95, 162)'
    assert evaluate("document.querySelector('.sector-legend-item[data-color-key=semiconductor]')!==null")
    assert evaluate('JSON.stringify({summary:__colorSummary,view:__qView,rows:dashboard.sector_classifications})') == evaluate('__financialSnapshot')
    dynamic_key = evaluate("WealthColorPreferences.keyFor('stock_category_colors','새로운 테마')")
    assert evaluate(f"WealthColorPreferences.resolve('stock_category_colors',{json.dumps(dynamic_key)})").startswith('#')
    select_save(call,evaluate,'stock_category_colors',dynamic_key,'#4D96FF',width)
    # The row remains the holdings filter; its marker has a separate action.
    evaluate("location.hash='invest'")
    evaluate(FRAMES)
    click(call,evaluate,'[data-invest=overview]')
    click(call,evaluate,'.classification-row[data-color-key=semiconductor] .classification-value')
    assert evaluate("document.getElementById('searchInput').value") == '반도체'
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
    assert evaluate("WealthColorPreferences.resolve('asset_category_colors','real_estate')") == '#22C7B8'
    assert '#22c7b8' in evaluate("document.getElementById('homeAssetAllocationDonut').style.background.toLowerCase()") or '34, 199, 184' in evaluate("document.getElementById('homeAssetAllocationDonut').style.background")
    for selector in ('#wealthMixLegend button[data-color-key=real_estate]', '#homeAssetAllocationLegend button[data-color-key=real_estate]'):
        assert evaluate(f'getComputedStyle(document.querySelector({json.dumps(selector)}),"::before").backgroundColor') == 'rgb(34, 199, 184)'
    assert evaluate(f"WealthColorPreferences.resolve('stock_category_colors',{json.dumps(dynamic_key)})") == '#4D96FF'
    assert_dividend_interest_colors(call, evaluate, '#22C7B8')
    reset_color(call,evaluate,'calendar_event_colors','dividend')
    assert_dividend_interest_colors(call, evaluate, '#FFE082', refresh=False)
    assert_dividend_interest_colors(call, evaluate, '#FFE082')
    reset_color(call,evaluate,'stock_category_colors','semiconductor')
    assert evaluate("document.querySelector('circle[data-color-key=semiconductor]').getAttribute('stroke')") != '#FF5FA2'
    reset_color(call,evaluate,'asset_category_colors','real_estate')
    assert evaluate("WealthColorPreferences.resolve('asset_category_colors','real_estate')") != '#22C7B8'
    assert evaluate('__settingsProbe.errors') == []


@pytest.mark.parametrize('width', [1280, 390])
def test_inline_color_cancel_error_and_keyboard_keep_persisted_color(chrome_preview, width):
    call,evaluate=start(chrome_preview,width,BOOT)
    wait_for(evaluate,"!!window.WealthColorPreferences&&WealthColorPreferences.loaded&&!!dashboard")
    evaluate(SETUP)
    baseline=evaluate("WealthColorPreferences.resolve('stock_category_colors','semiconductor')")
    editor=open_editor(call,evaluate,'stock_category_colors','semiconductor')
    click(call,evaluate,editor+' [data-color="#FF5FA2"]')
    assert evaluate('__colorRequests.length') == 0
    assert evaluate("WealthColorPreferences.resolve('stock_category_colors','semiconductor')") == '#FF5FA2'
    click(call,evaluate,editor+' [data-color-cancel]')
    assert evaluate("WealthColorPreferences.resolve('stock_category_colors','semiconductor')") == baseline
    assert evaluate('document.querySelector(".wealth-visualization-editor")===null')
    assert evaluate('__colorRequests.length') == 0
    # Focus returns to the new marker after the visualization repaints.
    assert evaluate("document.activeElement.matches('button[data-inline-color][data-color-key=semiconductor]')")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    wait_for(evaluate,'!!document.querySelector(".wealth-visualization-editor")')
    assert evaluate("document.getElementById('searchInput').value") == ''
    click(call,evaluate,editor+' [data-color="#FF5FA2"]')
    evaluate('__colorFailPatch=true')
    click(call,evaluate,editor+' [data-color-save]')
    wait_for(evaluate,"document.querySelector('.wealth-inline-color-status')?.textContent.includes('Synthetic save failure')")
    assert evaluate("WealthColorPreferences.resolve('stock_category_colors','semiconductor')") == baseline
    assert evaluate("!Object.hasOwn(__colorData.stock_category_colors,'semiconductor')")
    assert evaluate("document.querySelector('.wealth-visualization-editor').dataset.color") == baseline
    click(call,evaluate,editor+' [data-color-cancel]')
    evaluate('__colorFailPatch=false')
    # Row keyboard activation retains the original holdings filter.
    evaluate("document.querySelector('.classification-row[data-color-key=semiconductor]').focus()")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    assert evaluate("document.getElementById('searchInput').value") == '반도체'
    # A row click still filters when an unsaved picker is open.
    click_visible_stock_row(call,evaluate)
    assert evaluate("document.getElementById('searchInput').value") == ''
    baseline_focus=evaluate("({tag:document.activeElement.tagName,id:document.activeElement.id,key:document.activeElement.dataset.colorKey})")
    click_visible_stock_row(call,evaluate)
    assert evaluate("document.getElementById('searchInput').value") == '반도체'
    open_editor(call,evaluate,'stock_category_colors','semiconductor')
    click(call,evaluate,editor+' [data-color="#FF5FA2"]')
    click_visible_stock_row(call,evaluate)
    assert evaluate("document.getElementById('searchInput').value") == ''
    assert evaluate("({tag:document.activeElement.tagName,id:document.activeElement.id,key:document.activeElement.dataset.colorKey})") == baseline_focus
    assert evaluate('document.querySelector(".wealth-visualization-editor")===null')
    assert evaluate("WealthColorPreferences.resolve('stock_category_colors','semiconductor')") == baseline
    evaluate("location.hash='income'")
    evaluate(FRAMES)
    click(call,evaluate,'[data-income=calendar]')
    evaluate('loadCalendar()')
    wait_for(evaluate,"!!document.querySelector('.calendar-legend-item[data-inline-color]')")
    evaluate("document.querySelector('.calendar-legend-item[data-color-key=dividend]').focus()")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':' ','code':'Space','windowsVirtualKeyCode':32})
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':' ','code':'Space','windowsVirtualKeyCode':32})
    assert evaluate("document.querySelector('.wealth-visualization-editor').dataset.colorKey") == 'dividend'
    click(call,evaluate,editor+' [data-color-cancel]')
    no_overflow(evaluate,width)
    assert evaluate('__settingsProbe.errors') == []
