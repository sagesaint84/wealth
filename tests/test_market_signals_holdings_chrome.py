"""Real Chromium DOM/keyboard coverage over synthetic, loopback-only responses.

No screenshots or portfolio files are created. Mutation payloads are intercepted.
"""
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.ui_preview import DASHBOARD


BOOT = r"""
sessionStorage.setItem('wealth_invest_tab','holdings');
window.__signalsFixture={writes:[],fail:false,signalReads:[]};
const originalFetch=window.fetch;
window.fetch=async function(url,options={}) {
  const path=new URL(String(url),location.origin).pathname;
  if(options.method && options.method!=='GET') {
    __signalsFixture.writes.push({path,method:options.method,payload:JSON.parse(options.body || '{}')});
    return {ok:true,json:async()=>({message:'synthetic intercepted save'})};
  }
  if(path==='/api/holdings/signals') {
    __signalsFixture.signalReads.push(String(url));
    if(__signalsFixture.fail) return {ok:false,status:503,json:async()=>({detail:'synthetic failure'})};
    return {ok:true,json:async()=>({owner:'모두',items:window.__signalRows})};
  }
  if(path==='/api/dashboard') return {ok:true,json:async()=>structuredClone(window.__dashboardFixture)};
  return originalFetch.apply(this,arguments);
};
window.__signalRows=[{name:'가상 주식',code:'TEST',status:'ok',events:['SMA20_BREAKDOWN','DEAD_CROSS'],
 as_of:'2026-10-22',close:90,sma20:99.5,sma50:99.8,below_sma20:true,below_sma50:true,
 source:'synthetic Yahoo',retrieved_at:'2026-10-23T01:00:00Z',
 accounts:[{account_id:'mother-isa',owner:'엄마',broker:'가상증권',account_name:'동일이름'}]}];
"""


def boot_dashboard():
    from copy import deepcopy
    data = deepcopy(DASHBOARD)
    data["accounts"] = [
        {"id": identity, "owner": owner, "broker": "가상증권", "name": "동일이름", "account_type": kind,
         "cash_krw": 0, "market_value_krw": 100}
        for identity, owner, kind in [
            ("father", "아빠", "general"), ("mother-isa", "엄마", "isa"),
            ("child-pension", "자녀", "pension_savings"), ("mother-irp", "엄마", "irp"),
            ("legacy-pension", "엄마", "pension"), ("not-stock-bank", "아빠", "bank")]]
    data["holdings"] = [{**data["holdings"][0], "id": "synthetic-holding", "account_id": "mother-isa",
                         "account_name": "동일이름", "owner": "엄마", "code": "TEST"}]
    return data


def start(chrome_preview, width):
    call, evaluate, port = chrome_preview
    boot = BOOT + "\nwindow.__dashboardFixture=" + json.dumps(boot_dashboard(), ensure_ascii=False) + ";"
    call("Page.addScriptToEvaluateOnNewDocument", {"source": boot})
    call("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 768})
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#invest"})
    wait_for(evaluate, "document.readyState==='complete' && typeof rawDashboard!=='undefined' && rawDashboard && typeof openHoldingDialog==='function'")
    return call, evaluate


@pytest.mark.parametrize("width", [360, 390, 768, 1280])
def test_all_registered_accounts_ids_owner_filter_and_keyboard(chrome_preview, width):
    call, evaluate = start(chrome_preview, width)
    evaluate("currentOwner='아빠';renderWithOwner(rawDashboard,'아빠');openHoldingDialog();")
    assert evaluate("[...document.querySelector('#holdingAccountSelect').options].map(o=>o.value)") == [
        "", "father", "mother-isa", "child-pension", "mother-irp", "legacy-pension"]
    assert evaluate("document.querySelector('#holdingAccountSelect').textContent.includes('엄마 · 가상증권 · 동일이름 · ISA · mother-isa')")
    evaluate("document.querySelector('#holdingAccountSelect').focus();document.querySelector('#holdingAccountSelect').selectedIndex=1;")
    call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40})
    call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "ArrowDown", "code": "ArrowDown", "windowsVirtualKeyCode": 40})
    call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9})
    call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9})
    assert evaluate("document.querySelector('#holdingAccountSelect').value") == "mother-isa"
    # Dispatch change explicitly as well: closed native-select commit timing differs by OS.
    evaluate("document.querySelector('#holdingAccountSelect').dispatchEvent(new Event('change',{bubbles:true}));")
    assert evaluate("Object.fromEntries(new FormData(document.querySelector('#holdingForm'))).account_id") == "mother-isa"
    assert evaluate("document.querySelector('#holdingForm [name=owner]').value") == "엄마"
    assert evaluate("document.querySelectorAll('#holdingAccountSelect').length") == 1
    assert evaluate("document.querySelector('#holdingDialog').getBoundingClientRect().right<=innerWidth")
    assert evaluate("__signalsFixture.writes.length") == 0


def test_edit_and_manual_save_preserve_explicit_link(chrome_preview):
    _, evaluate = start(chrome_preview, 390)
    evaluate("openHoldingDialog(rawDashboard.holdings[0]);")
    assert evaluate("document.querySelector('#holdingAccountSelect').value") == "mother-isa"
    evaluate("document.querySelector('#holdingForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));")
    wait_for(evaluate, "__signalsFixture.writes.length===1")
    saved = evaluate("__signalsFixture.writes[0]")
    assert saved["method"] == "PUT" and saved["payload"]["account_id"] == "mother-isa"
    assert saved["payload"]["owner"] == "엄마"
    wait_for(evaluate, "!document.querySelector('#holdingDialog').open")
    evaluate("""openHoldingDialog();const form=document.querySelector('#holdingForm');
      form.broker.value='직접증권';form.broker.dispatchEvent(new Event('input',{bubbles:true}));
      form.account_name.value='직접계좌';form.owner.value='자녀';form.code.value='TEST';form.name.value='합성';
      form.quantity.value='1';form.avg_price.value='100';form.current_price.value='100';
      form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));""")
    wait_for(evaluate, "__signalsFixture.writes.length===2")
    saved = evaluate("__signalsFixture.writes[1]")
    assert saved["method"] == "POST" and saved["payload"]["account_id"] == ""
    assert saved["payload"]["owner"] == "자녀" and saved["payload"]["account_name"] == "직접계좌"


@pytest.mark.parametrize("width", [360, 390, 768, 1280])
def test_signals_filters_errors_and_existing_holdings_ui(chrome_preview, width):
    _, evaluate = start(chrome_preview, width)
    evaluate("window.WealthInvestTabState.select('holdings');window.dispatchEvent(new CustomEvent('wealth:view',{detail:'invest'}));")
    wait_for(evaluate, "document.querySelector('#holdingSignalsRows').textContent.includes('20일선 이탈')")
    assert evaluate("document.querySelectorAll('.holding-signals').length") == 1
    assert evaluate("document.querySelector('#holdingsBody')!==null")
    assert evaluate("__signalsFixture.writes.length") == 0
    for value, expected in [("SMA20_BREAKDOWN", True), ("SMA50_BREAKDOWN", False), ("GOLDEN_CROSS", False), ("DEAD_CROSS", True), ("ALL", True)]:
        evaluate(f"document.querySelector('#holdingSignalsFilter').value='{value}';document.querySelector('#holdingSignalsFilter').dispatchEvent(new Event('change'));")
        assert evaluate("!!document.querySelector('.holding-signal-row')") is expected
    assert evaluate("document.querySelector('.holding-signals').getBoundingClientRect().right<=innerWidth")
    assert evaluate("document.documentElement.scrollWidth<=innerWidth")
    evaluate("__signalsFixture.fail=true;document.querySelector('#holdingSignalsRefresh').click();")
    wait_for(evaluate, "document.querySelector('#holdingSignalsStatus').textContent.includes('신호 조회 실패')")
    assert evaluate("__signalsFixture.writes.length") == 0


@pytest.mark.parametrize("width", [360, 390, 768, 1280])
def test_existing_market_cards_daily_units_dates_and_official_links(chrome_preview, width):
    _, evaluate = start(chrome_preview, width)
    evaluate("window.WealthInvestTabState.select('overview');")
    payload = {"markets": [{"symbol": "KOSPI", "label": "코스피", "price": 2500, "change_rate": 1, "series": [2400, 2500]}],
               "exchange_rate": {"rate": 1350}, "rates": [
                   {"kind": "yield", "symbol": "US10Y", "label": "미국 10년 국채", "value": 4.15,
                    "change_pp": .05, "change_bp": 5, "series": [4.1, 4.15], "observed_date": "2026-10-22",
                    "retrieved_at": "2026-10-23T01:00:00Z", "source": "U.S. Treasury",
                    "source_url": "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed"},
                   {"kind": "yield", "symbol": "KR10Y", "label": "한국 10년 국채", "value": None,
                    "status": "not_configured", "reason": "ECOS_API_KEY 미설정", "source": "한국은행 ECOS",
                    "source_url": "https://ecos.bok.or.kr/", "series": []}],
               "fear_greed": {"source": "CNN", "label": "미국 공포·탐욕", "score": None,
                              "reason": "공식 자동 연동 허용 경로 미확인", "source_url": "https://www.cnn.com/markets/fear-and-greed"}}
    evaluate("renderMarkets(" + json.dumps(payload, ensure_ascii=False) + ");")
    text = evaluate("document.querySelector('#marketGrid').textContent")
    for expected in ["코스피", "미국 10년 국채", "%p", "bp", "2026-10-22", "U.S. Treasury", "ECOS_API_KEY 미설정", "미국 공포·탐욕"]:
        assert expected in text
    assert evaluate("document.querySelectorAll('#marketGrid .market-card').length") == 5
    assert evaluate("document.querySelectorAll('#marketGrid a[href=\"https://www.cnn.com/markets/fear-and-greed\"]').length") == 1
    assert evaluate("document.querySelector('#marketGrid').getBoundingClientRect().width>0")
    assert evaluate("[...document.querySelectorAll('#marketGrid .market-card')].every(n=>n.getBoundingClientRect().right<=innerWidth)")
    assert evaluate("__signalsFixture.writes.length") == 0
