"""Telemetry may read geometry only when explicitly enabled; synthetic only."""
import json
from pathlib import Path
import pytest

from tests.test_startup_performance_p0 import fragment, run
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_static_transport_chrome import transport_server, PROFILE

SOURCE=Path(__file__).resolve().parents[1]/'app/static/wealth.js'


@pytest.mark.parametrize('opt_in',[None,False,True])
def test_telemetry_geometry_and_visible_loader_have_separate_opt_in_contracts(opt_in):
    code=fragment(SOURCE.read_text(encoding='utf-8'),'globalThis.WealthStartup = (() => {','const startupReadPending = new Map();')
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const enabled=JSON.parse(process.argv[2]),shown=new Set(),marks=[],reads=[];
let forbid=false,marketCalls=0;
const context={__WEALTH_SYNTHETIC_PERF__:enabled,
 currentUserProfile:{username:'SYNTHETIC'},startupReadEpoch:0,currentOwner:'all',
 selectedDividendYear:2026,selectedPnlYear:2026,currentPnlTradeType:'all',currentDividendMode:'actual',
 currentLedgerYear:2026,currentLedgerMonth:10,
 performance:{now:()=>0,clearMarks(){},mark:name=>marks.push(name)},
 document:{getElementById(id){
   if(forbid)throw Error('disabled telemetry must not query DOM');
   if(!['wealthAssetNetWorth','marketGrid'].includes(id))return null;
   return {getClientRects(){reads.push(id);return shown.has(id)?[{}]:[];}};
 }},loadMarkets:()=>{marketCalls++;return Promise.resolve();}};
vm.createContext(context);vm.runInContext(process.argv[1],context);
const startup=context.WealthStartup,valid={summary:{total_value_krw:123}};
forbid=enabled!==true;
startup.dashboardRendered(null);startup.dashboardRendered({summary:{total_value_krw:'invalid'}});
startup.dashboardRendered(valid);
assert.equal(startup.snapshot().counters['dashboard:visible']||0,0);
shown.add('wealthAssetNetWorth');startup.dashboardRendered(valid);startup.dashboardRendered(valid);
assert.equal(startup.snapshot().counters['dashboard:visible']||0,enabled===true?1:0);
assert.equal(marks.filter(n=>n==='wealth-startup:dashboard:visible').length,enabled===true?1:0);
if(enabled!==true)assert.deepEqual(reads,[]);
else assert(reads.includes('wealthAssetNetWorth'));
// Presentation loaders retain their visibility checks when telemetry is OFF.
forbid=false;shown.add('marketGrid');assert.equal(startup.visible('marketGrid'),false);
startup.ready();assert.equal(startup.visible('marketGrid'),true);
const first=startup.loadVisible(),second=startup.loadVisible();assert.equal(first,second);
assert.equal(marketCalls,1);
first.then(async()=>{shown.delete('marketGrid');assert.equal(startup.visible('marketGrid'),false);
 await startup.loadVisible();assert.equal(marketCalls,1);
 context.currentUserProfile.must_change_password=true;
 assert.equal(startup.visible('marketGrid'),false);assert.equal(startup.loadVisible(),undefined);
}).catch(error=>{console.error(error);process.exitCode=1;});
""",code,json.dumps(opt_in))


@pytest.mark.parametrize('opt_in',[False,True])
def test_dashboard_values_and_startup_api_order_with_telemetry_on_or_off(chrome_preview,opt_in):
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':f'window.__WEALTH_SYNTHETIC_PERF__={json.dumps(opt_in)};'+PROFILE})
    call('Emulation.setDeviceMetricsOverride',{'width':360,'height':900,'deviceScaleFactor':1,'mobile':False})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,'!!window.WealthUnifiedTimeseries && WealthStartup.canRead() && !loadAssetDataForUser.pending && __transport.pending===0')
        assert evaluate('document.getElementById("wealthAssetNetWorth").textContent')=='397,000,000원'
        paths=evaluate('__transport.api.map(r=>r.path)')
        expected=['/api/refresh-prices','/api/dashboard','/api/planning/snapshot-all']
        assert [paths.count(path) for path in expected]==[1,1,1]
        assert paths.index(expected[0])<paths.index(expected[1])<paths.index(expected[2])
        assert '/api/market-overview' not in paths
        evaluate('WealthStartup.dashboardRendered(rawDashboard);WealthStartup.dashboardRendered(rawDashboard)')
        assert evaluate('WealthStartup.snapshot().counters["dashboard:visible"]||0')==int(opt_in)
        assert not evaluate('__transport.errors')
