"""Synthetic page-entry work: no production accounts or stores."""
import pytest
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_static_transport_chrome import transport_server
from tests.test_ledger_single_renderer_chrome import BOOT


@pytest.mark.parametrize('width',[320,360,390,1280])
def test_hidden_stock_dom_and_ledger_wait_for_entry(chrome_preview,width):
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,"typeof startupIncomeReuse!=='undefined' && startupIncomeReuse===false && !!window.WealthUnifiedTimeseries && document.getElementById('wealthAssetNetWorth').textContent==='397,000,000원'")
        assert evaluate("document.getElementById('classificationList').children.length") == 0
        assert evaluate("document.getElementById('holdingsBody').children.length") == 0
        assert evaluate('__ledgerCalls.length') == 0
        evaluate("location.hash='invest'")
        wait_for(evaluate,"document.getElementById('classificationList').children.length>0 && document.getElementById('holdingsBody').children.length>0")
        evaluate("window.__stockWrites=0;new MutationObserver(()=>__stockWrites++).observe(document.getElementById('holdingsBody'),{childList:true,subtree:true});location.hash='home'")
        wait_for(evaluate,"document.querySelector('.wealth-workspace').dataset.activeView==='home'")
        evaluate("location.hash='invest'")
        wait_for(evaluate,"document.querySelector('.wealth-workspace').dataset.activeView==='invest'")
        assert evaluate('__stockWrites') == 0
        evaluate("location.hash='home'")
        wait_for(evaluate,"document.querySelector('.wealth-workspace').dataset.activeView==='home'")
        evaluate("selectOwner('엄마')")
        assert evaluate('__stockWrites') == 0
        evaluate("location.hash='invest'")
        wait_for(evaluate,"investmentRenderedData===dashboard && __stockWrites>0")
        evaluate("location.hash='ledger'")
        wait_for(evaluate,"rawLedgerData?.owner==='엄마' && document.querySelectorAll('.ledger-cat-row').length===1")
        assert evaluate("document.documentElement.scrollWidth<=innerWidth+1")
        before=evaluate('__ledgerCalls.length')
        evaluate("location.hash='home'")
        wait_for(evaluate,"document.querySelector('.wealth-workspace').dataset.activeView==='home'")
        evaluate("location.hash='ledger'")
        wait_for(evaluate,f'__ledgerCalls.length>{before}')
        assert evaluate("document.getElementById('ledgerTrendContainer').closest('.ledger-sub-panel').querySelector('h3').textContent")=='월간 현금흐름 추이'
