"""Synthetic UI contracts for the v2.1.8 cleanup, across supported themes and widths."""
import pytest
from tests.test_home_three_tabs_chrome import chrome_preview, BOOT, choose, wait_for
from tests.test_static_transport_chrome import transport_server

@pytest.mark.parametrize('width', [320,360,390,768,1280])
@pytest.mark.parametrize('theme', ['purple','white','oled'])
def test_cleanup_typography_and_metric_contract(chrome_preview,width,theme):
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT.replace('return nativeFetch.apply(this,arguments);', "if(path==='/api/asset-records')return Promise.resolve(response({records:[{date:'2026-10-01',owner:'모두',total_value_krw:1234567.89,day_profit_krw:1}]}));return nativeFetch.apply(this,arguments);")+f"localStorage.setItem('app_theme',{theme!r});"})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<500})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,'!!window.WealthUnifiedTimeseries && !!document.querySelector("#wealthHistoryPlot")')
        assert evaluate('document.getElementById("wealthPageDescription").hidden')
        assert not evaluate('document.getElementById("homeAssetPortfolioPanel").textContent.includes("전체 자산의 핵심")')
        choose(evaluate,'history')
        wait_for(evaluate,'!!document.querySelector("#wealthHistoryPlot .wealth-latest-amount")')
        assert evaluate('document.querySelector("#wealthHistoryPlot .wealth-latest-amount").textContent')=='1,400원'
        assert not evaluate('document.querySelector(".wealth-history").textContent.includes("확인해 저장한 날짜별")')
        evaluate("location.hash='#invest'")
        wait_for(evaluate,'document.querySelector(".wealth-workspace").dataset.activeView==="invest"')
        assert evaluate('document.getElementById("wealthPageDescription").hidden')
        assert not evaluate('!!document.getElementById("recordChangeVal")')
        evaluate('window.__rateUi=structuredClone(dashboard);__rateUi.summary.total_stock_value_krw=1368081330;__rateUi.day_change={date:"2026-10-27",day_profit_krw:36316081,price_profit_status:"complete"};renderSummary(__rateUi)')
        assert evaluate('document.getElementById("dayProfitVal").textContent')=='일 수익 +₩36,316,081 (+2.65%)'
        assert evaluate('document.getElementById("dayProfitVal").title')=='당일 가격변동 손익 ÷ 총 주식자산'
        assert evaluate('document.getElementById("dayProfitVal").getBoundingClientRect().bottom<=document.getElementById("dayCaption").getBoundingClientRect().top+1')
        evaluate('document.querySelector("[data-invest=records]").click();WealthUnifiedTimeseries.renderStock()')
        wait_for(evaluate,'document.querySelector("#assetChart .wealth-latest-amount")?.textContent.includes("1,234,567.89")')
        assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert evaluate('__tabs.errors')==[]


@pytest.mark.parametrize('width',[320,360,390,768,1280])
def test_market_card_preferences_are_local_per_account(chrome_preview,width):
    from tests.test_cnn_fear_greed_chrome import FEED, HOME
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':FEED+HOME})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<500})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,'!!window.WealthUnifiedTimeseries && WealthStartup.canRead()')
        assert evaluate('__tabs.markets')==0
        choose(evaluate,'markets')
        wait_for(evaluate,'!!document.getElementById("marketCardSettings") && !!document.querySelector("[data-cnn-score]")')
        assert evaluate('document.querySelectorAll("#marketFearGreed.market-card").length')==1
        assert evaluate('getComputedStyle(document.querySelector("#marketGrid .market-card"),"::after").content') in ['none','normal']
        evaluate('document.getElementById("marketCardSettings").click();document.querySelectorAll("#marketCardDialog input").forEach(n=>n.checked=false);document.querySelector("#marketCardDialog form").requestSubmit()')
        assert evaluate('document.querySelectorAll("#marketGrid .market-card").length')==0
        assert '표시할 지수를 선택하세요' in evaluate('document.getElementById("marketGrid").textContent')
        reads=evaluate('__tabs.markets')
        evaluate('renderMarkets()')
        assert evaluate('__tabs.markets')==reads
        assert evaluate('document.querySelectorAll("#marketGrid .market-card").length')==0
        evaluate('window.__savedProfile=currentUserProfile;currentUserProfile={...currentUserProfile,id:"synthetic-other",username:"synthetic-other"};window.dispatchEvent(new CustomEvent("wealth:role",{detail:{isAdminUser:false}}))')
        assert evaluate('document.querySelectorAll("#marketGrid .market-card").length')>0
        evaluate('currentUserProfile=__savedProfile;window.dispatchEvent(new CustomEvent("wealth:role",{detail:{isAdminUser:false}}))')
        assert evaluate('document.querySelectorAll("#marketGrid .market-card").length')==0
        call('Page.reload',{'ignoreCache':True})
        wait_for(evaluate,'typeof WealthStartup!=="undefined" && WealthStartup.canRead() && document.getElementById("marketCardSettings") && __tabs.markets===1')
        assert evaluate('document.querySelectorAll("#marketGrid .market-card").length')==0
        assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')

@pytest.mark.parametrize('width',[320,360,390,768,1280])
def test_cleanup_empty_preview_keeps_images_protected(chrome_preview,width):
    from tests.test_system_update_chrome import start
    from tests.test_workflow_ux_chrome import click
    extra=r"""
__u.current='b';__u.confirmed=true;__u.job={id:'b'.repeat(32),kind:'install',stage:'succeeded',created_at:123,digest:'sha256:'+'b'.repeat(64)};
const originalUpdateFetch=fetch;
window.fetch=async function(url,options={}){
 const response=await originalUpdateFetch(url,options),path=new URL(String(url),location.href).pathname;
 if(path==='/api/system-update/status'||path==='/api/system-update/cleanup-preview'){
   const data=await response.json();
   if(path.endsWith('/status')){data.current.image_id='sha256:'+'b'.repeat(64);data.rollback.image_id='sha256:'+'a'.repeat(64);}
   else data.images=[];
   return {ok:true,json:async()=>data};
 }
 return response;
};
"""
    call,evaluate,_=start(chrome_preview,width,extra)
    click(call,evaluate,'#settingsSystemTab')
    wait_for(evaluate,'!document.getElementById("updateCleanupPreview").disabled')
    assert not evaluate('!!document.getElementById("updateJobs")')
    click(call,evaluate,'#updateCleanupPreview')
    wait_for(evaluate,'document.getElementById("updateCleanupHint").textContent.includes("정리할 이미지가 없습니다")')
    assert evaluate('document.getElementById("updateCleanup").disabled')
    for text in ['현재 사용 이미지','롤백 이미지','보호 중']:
        assert text in evaluate('document.getElementById("updateCleanupPreserved").textContent')
    assert not evaluate('__u.requests.some(r=>r.method==="POST")')
    assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')

def test_profit_summary_uses_session_money_not_record_delta(chrome_preview):
    from tests.test_market_signals_holdings_chrome import start
    _,evaluate=start(chrome_preview,360)
    baseline=evaluate('[document.getElementById("totalProfit").textContent,document.getElementById("profitRate").textContent]')
    evaluate('window.__summaryInput=structuredClone(dashboard);__summaryInput.day_change={date:"2026-10-01",day_profit_krw:12345,price_profit_status:"partial",record_change_krw:999999,record_change_rate:99};renderSummary(__summaryInput)')
    text=evaluate('document.getElementById("dayProfitVal").textContent')
    assert '12,345' in text and '일부 종목 기준 없음' in text and '(—)' in text
    assert '999,999' not in text and '99%' not in text
    assert evaluate('[document.getElementById("totalProfit").textContent,document.getElementById("profitRate").textContent]')==baseline
    assert evaluate('document.getElementById("dayCaption").textContent')=='2026-10-01 기록 기준'
    evaluate('__summaryInput.day_change.day_profit_krw=null;renderSummary(__summaryInput)')
    assert evaluate('document.getElementById("dayProfitVal").textContent')=='일 수익 — (—)'
    assert not evaluate('!!document.getElementById("recordChangeVal")')


def test_daily_profit_rate_current_stock_value_and_owner_scope(chrome_preview):
    from tests.test_market_signals_holdings_chrome import start
    _, evaluate = start(chrome_preview, 360)
    evaluate(r"""(() => {
      const check=(yes,msg)=>{if(!yes)throw Error(msg);};
      const data=structuredClone(dashboard);
      const before=JSON.stringify(data);
      const totals=()=>['totalProfit','profitRate','summaryRealizedPnl','summaryActualDividend'].map(id=>document.getElementById(id).textContent);
      renderSummary(data);const baseline=totals();
      for(const [profit,value,status,expected] of [
        [36316081,1368081330,'complete','+2.65%'],
        [-36316081,1368081330,'complete','-2.65%'],
        [0,100,'complete','+0.00%'],
        [null,100,'complete','—'],[undefined,100,'complete','—'],
        [1,0,'complete','—'],[1,-100,'complete','—'],
        [1,null,'complete','—'],[1,undefined,'complete','—'],
        [1,NaN,'complete','—'],[Infinity,100,'complete','—'],
        [10,100,'partial','—'],[10,100,'unavailable','—']]) {
        const sample=structuredClone(data);
        sample.summary.total_stock_value_krw=value;
        sample.day_change={date:'2026-10-27',day_profit_krw:profit,price_profit_status:status,record_change_rate:99,value_krw:1};
        renderSummary(sample);
        const text=document.getElementById('dayProfitVal').textContent;
        check(text.includes('('+expected+')'),'rate '+String([profit,value,status])+': '+text);
        if(Number.isFinite(profit))check(text.includes(money(profit)),'price profit preserved');
        if(status==='partial')check(text.includes('일부 종목 기준 없음'),'partial warning retained');
        check(JSON.stringify(totals())===JSON.stringify(baseline),'other totals unchanged');
        check(document.getElementById('dayCaption').textContent==='2026-10-27 기록 기준','date unchanged');
        check(!text.includes('99%'),'record change not reused');
      }
      check(JSON.stringify(data)===before,'input not mutated');
      const saved=rawDashboard, owner=currentOwner;
      try {
        rawDashboard=structuredClone(data);
        rawDashboard.accounts=[{id:'a',owner:'아빠',currency:'KRW'},{id:'b',owner:'엄마',currency:'KRW'}];
        rawDashboard.holdings=[{account_id:'a',owner:'아빠',currency:'KRW',market_value_krw:1000,cost_value_krw:900},{account_id:'b',owner:'엄마',currency:'KRW',market_value_krw:2000,cost_value_krw:1800}];
        rawDashboard.summary.total_stock_value_krw=3000;
        rawDashboard.daily_metrics_by_owner={
          '아빠':{date:'2026-10-26',day_profit_krw:10,price_profit_status:'complete'},
          '엄마':{date:'2026-10-27',day_profit_krw:-40,price_profit_status:'complete'},
          '모두':{date:'2026-10-27',day_profit_krw:-30,price_profit_status:'complete'}};
        for(const [who,rate,date] of [['아빠','+1.00%','2026-10-26'],['엄마','-2.00%','2026-10-27'],['모두','-1.00%','2026-10-27']]) {
          currentOwner=who;renderWithOwner(rawDashboard,who);
          check(document.getElementById('dayProfitVal').textContent.includes('('+rate+')'),who+' isolated rate');
          check(document.getElementById('dayCaption').textContent===date+' 기록 기준',who+' isolated date');
        }
      } finally {rawDashboard=saved;currentOwner=owner;renderWithOwner(saved,owner);}
      return true;
    })()""")
