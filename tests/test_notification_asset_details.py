"""UI-only ratios and real Chrome disclosure/layout regressions."""
import base64
import json
from pathlib import Path
import subprocess

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_settings_surface_chrome import start, loaded, click, no_overflow, FRAMES


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('stock,property_value,expected', [
    ('60000000', '40000000', ['60.0%', '40.0%']),
    ('100', '0', ['100.0%', '0.0%']),
    ('0', '100', ['0.0%', '100.0%']),
    ('0', '0', ['—', '—']),
    ('-10', '5', ['—', '—']),
    ('NaN', '10', ['—', '—']),
    ('10', 'Infinity', ['—', '—']),
    ('-Infinity', '10', ['—', '—']),
    ('"bad"', '10', ['—', '—']),
    ('1e308', '1e308', ['—', '—']),
    ('1', '2', ['33.3%', '66.7%']),
])
def test_investment_shares_display_contract(stock, property_value, expected):
    script = r'''
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const code=source.slice(source.indexOf('  const won ='),source.indexOf("  window.addEventListener('wealth:summary'"));
const sandbox={};vm.createContext(sandbox);
vm.runInContext(code+`;result=investmentShares(${process.argv[2]},${process.argv[3]});amount=investmentDetail(1234567890123,'60.0%');invalid=investmentDetail(NaN,'—');`,sandbox);
process.stdout.write(JSON.stringify({shares:sandbox.result,amount:sandbox.amount,invalid:sandbox.invalid}));
'''
    result = subprocess.run(['node', '-e', script, str(ROOT/'app/static/wealth-layout.js'),
        stock, property_value], capture_output=True, text=True, encoding='utf-8', check=True)
    value = json.loads(result.stdout)
    assert value['shares'] == expected
    assert value['amount'] == '1,234,567,890,123원 (60.0%)'
    assert value['invalid'] == '— (—)'


@pytest.mark.parametrize('width', [1280, 390])
def test_notification_disclosure_preserves_history_and_browser_preference(chrome_preview, width, tmp_path):
    boot = r'''
window.__historyEvents=[{event_type:'integration_test',created_at:'2026-10-09T12:34:56+09:00',status:'sent',event_key_fingerprint:'synthetic-trace',providers:{telegram:{status:'sent'}}}];
const historyFetch=window.fetch;
window.fetch=async function(url,options={}){
 if(new URL(String(url),location.href).pathname==='/api/settings/notifications/history'){
   __settingsProbe.requests.push({path:'/api/settings/notifications/history',method:options.method||'GET'});
   return {ok:true,status:200,json:async()=>({events:structuredClone(__historyEvents),count:__historyEvents.length,retention:100})};
 }return historyFetch.apply(this,arguments);
};
'''
    call, evaluate = start(chrome_preview, width, boot)
    loaded(evaluate)
    click(call, evaluate, '#settingsNotificationsTab')
    loaded(evaluate, 'Notifications')
    wait_for(evaluate, "document.querySelectorAll('.settings-history-item').length===1")
    state = "(()=>{const b=document.getElementById('settingsNotificationHistoryToggle'),l=document.getElementById('settingsNotificationHistoryList');return {expanded:b.getAttribute('aria-expanded'),controls:b.getAttribute('aria-controls'),hidden:l.hidden,display:getComputedStyle(l).display,text:l.textContent}})()"
    initial = evaluate(state)
    assert initial['expanded'] == 'false' and initial['hidden'] and initial['display'] == 'none'
    assert initial['controls'] == 'settingsNotificationHistoryList'
    assert '저장 1건' in evaluate("document.getElementById('settingsNotificationHistorySummary').textContent")
    evaluate("document.getElementById('settingsNotificationHistoryToggle').focus()")
    assert evaluate('document.activeElement.id') == 'settingsNotificationHistoryToggle'
    call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r','unmodifiedText':'\r'})
    call('Input.dispatchKeyEvent', {'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    wait_for(evaluate, "document.getElementById('settingsNotificationHistoryToggle').getAttribute('aria-expanded')==='true'")
    assert evaluate(state)['expanded'] == 'true'
    assert not evaluate(state)['hidden']
    assert evaluate(state)['text'] == initial['text']
    assert evaluate("localStorage.getItem('wealth.notificationHistory.expanded')") == 'true'
    old_origin = evaluate('performance.timeOrigin')
    call('Page.reload', {'ignoreCache':True})
    wait_for(evaluate, f"performance.timeOrigin!=={old_origin}&&document.readyState==='complete'&&!!document.getElementById('settingsNotificationHistoryToggle')&&!!window.WealthSettings")
    click(call, evaluate, '#settingsNotificationsTab')
    loaded(evaluate, 'Notifications')
    wait_for(evaluate, "document.querySelectorAll('.settings-history-item').length===1")
    assert evaluate(state)['expanded'] == 'true'
    assert evaluate(state)['text'] == initial['text']
    click(call, evaluate, '#settingsNotificationHistoryToggle')
    assert evaluate(state)['expanded'] == 'false' and evaluate(state)['hidden']
    evaluate("__historyEvents.push({...__historyEvents[0],event_key_fingerprint:'second'})")
    click(call, evaluate, '#settingsNotificationHistoryRefresh')
    wait_for(evaluate, "document.querySelectorAll('.settings-history-item').length===2")
    assert evaluate(state)['hidden'] and evaluate(state)['expanded'] == 'false'
    assert evaluate("localStorage.getItem('wealth.notificationHistory.expanded')") == 'false'
    click(call, evaluate, '#settingsNotificationHistoryToggle')
    no_overflow(evaluate, width)
    assert 'synthetic-trace' in evaluate(state)['text'] and 'second' in evaluate(state)['text']
    assert evaluate("__settingsProbe.requests.every(r=>r.method==='GET')")
    (tmp_path/f'notification-history-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
    click(call, evaluate, '#settingsNotificationHistoryToggle')
    old_origin = evaluate('performance.timeOrigin')
    call('Page.reload', {'ignoreCache':True})
    wait_for(evaluate, f"performance.timeOrigin!=={old_origin}&&document.readyState==='complete'&&!!window.WealthSettings")
    click(call, evaluate, '#settingsNotificationsTab')
    loaded(evaluate, 'Notifications')
    assert evaluate(state)['hidden'] and evaluate(state)['expanded'] == 'false'


@pytest.mark.parametrize('width', [1280, 390])
def test_home_detail_ratios_alignment_and_large_values(chrome_preview, width, tmp_path):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,'deviceScaleFactor':1,'mobile':width==390})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#home'})
    wait_for(evaluate, "document.readyState==='complete'&&!!document.getElementById('wealthAssetStockDetail')&&!!window.WealthDonutHitTest")
    evaluate(FRAMES)
    summary = dict(netWorth=777, invest=100000000, stock=60000000, property=40000000,
        expected=12, realized=34, safe=56, debt=7, cash=8, deposits=9, insurance=10,
        propertyExpected=1, stockExpected=2, propertyExpectedRate=3, stockExpectedRate=4,
        dayProfit=5, realizedTrade=6, dividendInterest=7, realizedYear=8, realizedMonth=9,
        owner='모두', classifications=[])
    def dispatch(values):
        evaluate(f"window.dispatchEvent(new CustomEvent('wealth:summary',{{detail:{json.dumps(values)}}}))")
    dispatch(summary)
    assert evaluate("document.getElementById('wealthAssetStockDetail').textContent") == '60,000,000원 (60.0%)'
    assert evaluate("document.getElementById('wealthAssetPropertyDetail').textContent") == '40,000,000원 (40.0%)'
    for ident, expected in [('wealthAssetNetWorth','777원'),('wealthAssetInvest','100,000,000원'),
        ('wealthAssetExpected','12원'),('wealthAssetRealized','34원'),('wealthAssetSafe','56원')]:
        assert evaluate(f"document.getElementById('{ident}').textContent") == expected
    dispatch({**summary,'stock':1234567890123,'property':987654321098,'invest':2222222211221})
    evaluate("document.querySelector('.wealth-asset-kpi.tone-invest em').textContent='아주 긴 한글 투자자산 상세 항목 이름'")
    evaluate(FRAMES)
    no_overflow(evaluate, width)
    geometry = evaluate(r'''[...document.querySelectorAll('#homeAssetPortfolioPanel .wealth-asset-kpi')].map(card=>{
      const content=card.querySelector(':scope>div'),title=content.querySelector(':scope>span:not(.wealth-asset-secondary-row)'),total=content.querySelector(':scope>strong');
      const rect=e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right});
      return {content:rect(content),title:rect(title),total:rect(total),titleAlign:getComputedStyle(title).textAlign,totalAlign:getComputedStyle(total).textAlign,
        rows:[...card.querySelectorAll('.wealth-asset-secondary-row')].map(row=>({label:rect(row.querySelector('em')),value:rect(row.querySelector('small')),right:rect(row).right,align:getComputedStyle(row.querySelector('small')).textAlign}))};})''')
    for card in geometry:
        assert abs(card['title']['left']-card['content']['left']) < 1
        assert abs(card['total']['left']-card['content']['left']) < 1
        assert card['titleAlign'] in ('start','left') and card['totalAlign'] in ('start','left')
        for row in card['rows']:
            assert row['align'] == 'right'
            assert abs(row['right']-card['content']['right']) < 1
            assert row['label']['right'] <= row['value']['left']
            assert row['value']['right'] <= card['content']['right'] + 1
    assert '1,234,567,890,123원' in evaluate("document.getElementById('wealthAssetStockDetail').textContent")
    (tmp_path/f'home-asset-details-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
