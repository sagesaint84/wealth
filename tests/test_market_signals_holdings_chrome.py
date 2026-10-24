"""Real Chromium DOM/keyboard coverage over synthetic, loopback-only responses.

No screenshots or portfolio files are created. Mutation payloads are intercepted.
"""
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.ui_preview import DASHBOARD


BOOT = r"""
sessionStorage.setItem('wealth_invest_tab','holdings');
window.__signalsFixture={requests:[],writes:[],fail:false,signalReads:[],marketReads:[],phase:'startup',assetsReady:false};
window.addEventListener('wealth:assets-ready',()=>{
  __signalsFixture.assetsReady=true;
  __signalsFixture.assetsReadyAt=performance.now();
  __signalsFixture.phase='ready';
});
const originalFetch=window.fetch;
window.fetch=async function(url,options={}) {
  const address=new URL(url instanceof Request ? url.url : String(url),location.origin);
  const path=address.pathname;
  const method=String(options.method || (url instanceof Request ? url.method : 'GET')).toUpperCase();
  let payload={};
  try { payload=JSON.parse(options.body || '{}'); }
  catch (_) { payload=String(options.body); }
  const entry={path,method,payload,url:address.href,sequence:__signalsFixture.requests.length,
    at_ms:performance.now(),phase:__signalsFixture.phase,ready_state:document.readyState,
    route:location.hash,stack:new Error('fixture request').stack};
  __signalsFixture.requests.push(entry);
  if(!['GET','HEAD'].includes(method)) {
    entry.intercepted=true;
    __signalsFixture.writes.push(entry);
    return {ok:true,json:async()=>({message:'synthetic intercepted save'})};
  }
  if(path==='/api/market-overview' && window.__marketFixture) {
    __signalsFixture.marketReads.push(address.href);
    return {ok:true,json:async()=>structuredClone(window.__marketFixture)};
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


def start(chrome_preview, width, market_payload=None):
    call, evaluate, port = chrome_preview
    boot = BOOT + "\nwindow.__dashboardFixture=" + json.dumps(boot_dashboard(), ensure_ascii=False) + ";"
    if market_payload is not None:
        boot += "\nwindow.__marketFixture=" + json.dumps(market_payload, ensure_ascii=False) + ";"
    call("Page.addScriptToEvaluateOnNewDocument", {"source": boot})
    call("Emulation.setDeviceMetricsOverride", {"width": width, "height": 900, "deviceScaleFactor": 1, "mobile": width < 768})
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#invest"})
    wait_for(evaluate, "document.readyState==='complete' && typeof rawDashboard!=='undefined' && rawDashboard && typeof openHoldingDialog==='function'")
    # Dashboard availability precedes the second startup POST. Wait for the
    # existing startup pipeline and supplementary reads before taking a baseline.
    wait_for(evaluate, "__signalsFixture.assetsReady && !loadAssetDataForUser.pending")
    evaluate("(async()=>{await loadAssetDataForUser.supplementary;return true;})()")
    initial = evaluate("__signalsFixture.writes")
    print("Initial intercepted requests: " + json.dumps(initial, ensure_ascii=False))
    assert [(r["method"], r["path"]) for r in initial] == [
        ("POST", "/api/refresh-prices"), ("POST", "/api/planning/snapshot-all")]
    assert initial[0]["payload"] == {}
    assert initial[1]["payload"] == {"source": "auto"}
    assert all(r["phase"] == "startup" and r["intercepted"] for r in initial)
    assert all(r["ready_state"] in {"interactive", "complete"} for r in initial)
    assert all(r["at_ms"] <= evaluate("__signalsFixture.assetsReadyAt") for r in initial)
    return call, evaluate


def checkpoint(evaluate, phase):
    evaluate("__signalsFixture.phase=" + json.dumps(phase))
    return evaluate("__signalsFixture.writes")


def writes_since(evaluate, before):
    actual = evaluate("__signalsFixture.writes")
    # Retain and compare the complete startup history; never clear or filter it.
    assert actual[:len(before)] == before, actual
    return actual[len(before):]


@pytest.mark.parametrize("width", [360, 390, 768, 1280])
def test_all_registered_accounts_ids_owner_filter_and_keyboard(chrome_preview, width):
    call, evaluate = start(chrome_preview, width)
    before = checkpoint(evaluate, "account-selection")
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
    assert len(writes_since(evaluate, before)) == 0


def test_edit_and_manual_save_preserve_explicit_link(chrome_preview):
    _, evaluate = start(chrome_preview, 390)
    before = checkpoint(evaluate, "edit-save")
    evaluate("openHoldingDialog(rawDashboard.holdings[0]);")
    assert evaluate("document.querySelector('#holdingAccountSelect').value") == "mother-isa"
    evaluate("document.querySelector('#holdingForm').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));")
    wait_for(evaluate, f"__signalsFixture.writes.slice({len(before)}).some(r=>r.method==='PUT' && r.path==='/api/holdings/synthetic-holding')")
    wait_for(evaluate, "!document.querySelector('#holdingDialog').open")
    added = writes_since(evaluate, before)
    assert len(added) == 1, added
    saved = added[0]
    assert saved["method"] == "PUT" and saved["payload"]["account_id"] == "mother-isa"
    assert saved["path"] == "/api/holdings/synthetic-holding"
    assert saved["payload"]["owner"] == "엄마"
    assert saved["payload"]["code"] == "TEST"
    assert (saved["payload"]["broker"], saved["payload"]["account_name"]) == ("가상증권", "동일이름")
    before = checkpoint(evaluate, "manual-save")
    evaluate("""openHoldingDialog();const form=document.querySelector('#holdingForm');
      form.broker.value='직접증권';form.broker.dispatchEvent(new Event('input',{bubbles:true}));
      form.account_name.value='직접계좌';form.owner.value='자녀';form.code.value='TEST';form.name.value='합성';
      form.quantity.value='1';form.avg_price.value='100';form.current_price.value='100';
      form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));""")
    wait_for(evaluate, f"__signalsFixture.writes.slice({len(before)}).some(r=>r.method==='POST' && r.path==='/api/holdings')")
    wait_for(evaluate, "!document.querySelector('#holdingDialog').open")
    added = writes_since(evaluate, before)
    assert len(added) == 1, added
    saved = added[0]
    assert saved["method"] == "POST" and saved["payload"]["account_id"] == ""
    assert saved["path"] == "/api/holdings"
    assert saved["payload"]["code"] == "TEST" and saved["payload"]["broker"] == "직접증권"
    assert saved["payload"]["owner"] == "자녀" and saved["payload"]["account_name"] == "직접계좌"


@pytest.mark.parametrize("width", [360, 390, 768, 1280])
def test_signals_filters_errors_and_existing_holdings_ui(chrome_preview, width):
    _, evaluate = start(chrome_preview, width)
    before = checkpoint(evaluate, "signals-success")
    reads = evaluate("__signalsFixture.signalReads.length")
    evaluate("window.WealthInvestTabState.select('holdings');window.dispatchEvent(new CustomEvent('wealth:view',{detail:'invest'}));")
    evaluate("document.querySelector('#holdingSignalsRefresh').click();")
    wait_for(evaluate, f"__signalsFixture.signalReads.length>{reads} && !holdingSignalState.pending")
    wait_for(evaluate, "document.querySelector('#holdingSignalsRows').textContent.includes('20일선 이탈')")
    assert evaluate("document.querySelectorAll('.holding-signals').length") == 1
    assert evaluate("document.querySelector('#holdingsBody')!==null")
    assert len(writes_since(evaluate, before)) == 0
    for value, expected in [("SMA20_BREAKDOWN", True), ("SMA50_BREAKDOWN", False), ("GOLDEN_CROSS", False), ("DEAD_CROSS", True), ("ALL", True)]:
        evaluate(f"document.querySelector('#holdingSignalsFilter').value='{value}';document.querySelector('#holdingSignalsFilter').dispatchEvent(new Event('change'));")
        assert evaluate("!!document.querySelector('.holding-signal-row')") is expected
    assert evaluate("document.querySelector('.holding-signals').getBoundingClientRect().right<=innerWidth")
    assert evaluate("document.documentElement.scrollWidth<=innerWidth")
    before_failure = checkpoint(evaluate, "signals-failure")
    reads = evaluate("__signalsFixture.signalReads.length")
    evaluate("__signalsFixture.fail=true;document.querySelector('#holdingSignalsRefresh').click();")
    wait_for(evaluate, f"__signalsFixture.signalReads.length>{reads} && !holdingSignalState.pending")
    wait_for(evaluate, "document.querySelector('#holdingSignalsStatus').textContent.includes('신호 조회 실패')")
    assert len(writes_since(evaluate, before_failure)) == 0
    assert len(writes_since(evaluate, before)) == 0


@pytest.mark.parametrize("width", [360, 390, 768, 1280])
def test_existing_market_cards_daily_units_dates_and_official_links(chrome_preview, width):
    payload = {"markets": [
                   {"symbol": symbol, "label": label, "price": 2500, "change_rate": 1, "series": [2400, 2500]}
                   for symbol, label in [("^KS11", "코스피"), ("^KQ11", "코스닥"), ("^GSPC", "S&P"), ("^IXIC", "나스닥"), ("^SOX", "반도체")]],
               "exchange_rate": {"rate": 1350}, "rates": [
                   {"kind": "yield", "symbol": "^TNX", "label": "미국 10년 국채", "value": 4.15,
                    "change_pp": .05, "change_bp": 5, "series": [4.1, 4.15], "observed_date": "2026-10-22",
                    "observed_at": "2026-10-22T20:00:00Z", "quote_delay_minutes": 15,
                    "retrieved_at": "2026-10-23T01:00:00Z", "source": "Yahoo Finance / CBOE 10-Year Treasury Note Yield",
                    "source_url": "https://finance.yahoo.com/quote/%5ETNX/"}],
               "fear_greed": {"source": "CNN", "label": "미국 공포·탐욕", "score": None,
                              "reason": "공식 자동 연동 허용 경로 미확인", "source_url": "https://www.cnn.com/markets/fear-and-greed"}}
    _, evaluate = start(chrome_preview, width, market_payload=payload)
    before = checkpoint(evaluate, "market-home")
    assert evaluate("document.querySelector('#marketGrid').closest('[data-wealth-page]').dataset.wealthPage") == "home"
    assert evaluate("document.querySelector('[data-wealth-page=home]').hidden")
    # Use the existing navigation link and hashchange router, as a user would.
    evaluate("document.querySelector('.wealth-nav a[href=\"#home\"]').click();")
    wait_for(evaluate, "location.hash==='#home' && document.querySelector('.wealth-workspace').dataset.activeView==='home' && !document.querySelector('[data-wealth-page=home]').hidden")
    wait_for(evaluate, "__signalsFixture.marketReads.length>0 && document.querySelectorAll('#marketGrid .market-card').length===8 && document.querySelector('#marketGrid').getBoundingClientRect().width>0")
    text = evaluate("document.querySelector('#marketGrid').textContent")
    for expected in ["코스피", "코스닥", "나스닥", "S&P", "반도체", "미국 10년 국채", "%p", "+5bp", "2026-10-22T20:00:00Z", "Yahoo Finance / CBOE 10-Year Treasury Note Yield", "거래소 제공 지연 15분", "미국 공포·탐욕", "공식 수치 미연동", "공식 자동 연동 허용 경로 미확인"]:
        assert expected in text
    assert "한국 10년 국채" not in text
    assert evaluate("document.querySelectorAll('#marketGrid .market-card').length") == 8
    assert evaluate("document.querySelectorAll('#marketGrid a[href=\"https://www.cnn.com/markets/fear-and-greed\"]').length") == 1
    assert evaluate("document.querySelectorAll('#marketGrid a[href=\"https://finance.yahoo.com/quote/%5ETNX/\"]').length") == 1
    assert evaluate("document.querySelectorAll('#marketGrid a[href*=\"treasury.gov\"],#marketGrid a[href*=\"ecos.bok.or.kr\"]').length") == 0
    assert evaluate("[...document.querySelectorAll('#marketGrid .market-card')].find(n=>n.textContent.includes('미국 10년 국채')).querySelector('.market-price').textContent") == "4.15%"
    assert evaluate("[...document.querySelectorAll('#marketGrid .market-card')].find(n=>n.textContent.includes('미국 공포·탐욕')).querySelector('.market-price').textContent") == "미연동"
    assert evaluate("document.querySelector('#marketGrid').getBoundingClientRect().width>0")
    assert evaluate("[...document.querySelectorAll('#marketGrid .market-card')].every(n=>n.getBoundingClientRect().right<=innerWidth)")
    assert len(writes_since(evaluate, before)) == 0
    # Re-enter home through the same user navigation to exercise delayed/error
    # responses without clicking the existing financial price-refresh action.
    for failed in [False, True]:
        evaluate("document.querySelector('.wealth-nav a[href=\"#invest\"]').click();")
        wait_for(evaluate, "document.querySelector('.wealth-workspace').dataset.activeView==='invest'")
        reads = evaluate("__signalsFixture.marketReads.length")
        patch = {"observation_stale": True, "status": "stale"} if not failed else {
            "value": None, "change_pp": None, "change_bp": None, "observed_at": None,
            "observed_date": None, "series": [], "status": "source_error", "reason": "조회 불가", "update_delayed": True}
        evaluate("Object.assign(__marketFixture.rates[0]," + json.dumps(patch, ensure_ascii=False) + ");document.querySelector('.wealth-nav a[href=\"#home\"]').click();")
        expected_price = "조회 불가" if failed else "4.15%"
        wait_for(evaluate, f"document.querySelector('.wealth-workspace').dataset.activeView==='home' && __signalsFixture.marketReads.length>{reads} && document.querySelector('#marketGrid').textContent.includes('업데이트 지연') && [...document.querySelectorAll('#marketGrid .market-card')].find(n=>n.textContent.includes('미국 10년 국채'))?.querySelector('.market-price').textContent==={json.dumps(expected_price, ensure_ascii=False)}")
        assert evaluate("[...document.querySelectorAll('#marketGrid .market-card')].find(n=>n.textContent.includes('미국 10년 국채')).querySelector('.market-price').textContent") == expected_price
        assert evaluate("document.querySelectorAll('#marketGrid .market-card').length") == 8
        assert len(writes_since(evaluate, before)) == 0
