"""Retired KFTC UI must never be created, even without its former hide/remove shim."""
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_workflow_ux_chrome import click, no_overflow


BOOT = r'''(() => {
  const ids = ['kftcOpenBankingCard','openapiKftcSection'];
  window.__retiredAudit = {created:[],removed:[],calls:[],frames:[]};
  const find = node => node.nodeType === 1 ? [node,...node.querySelectorAll('[id]')]
    .filter(child => ids.includes(child.id)).map(child => child.id) : [];
  new MutationObserver(records => records.forEach(record => {
    record.addedNodes.forEach(node => __retiredAudit.created.push(...find(node)));
    record.removedNodes.forEach(node => __retiredAudit.removed.push(...find(node)));
  })).observe(document, {childList:true,subtree:true});
  const nativeFetch = window.fetch;
  window.fetch = function(url,options) {
    const path = new URL(String(url),location.href).pathname;
    if(path.startsWith('/api/kftc/') || path.startsWith('/api/user/kftc')) {
      __retiredAudit.calls.push(path);
      return Promise.resolve({ok:false,status:403,json:async()=>({detail:'retired synthetic path'})});
    }
    if(['/api/refresh-prices','/api/asset-records/snapshot'].includes(path))
      return Promise.resolve({ok:true,json:async()=>({message:'synthetic'})});
    return nativeFetch.apply(this,arguments);
  };
  function frame() {
    if(__retiredAudit.stop)return;
    __retiredAudit.frames.push(ids.filter(id=>document.getElementById(id)));
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();'''
FRAMES = '(async()=>{for(let i=0;i<6;i++)await new Promise(requestAnimationFrame);})()'


def assert_retired(evaluate):
    report = evaluate('__retiredAudit')
    assert not report['created'], report
    assert not report['removed'], report  # No create-then-remove strategy.
    assert not report['calls'], report
    assert report['frames'] and all(not frame for frame in report['frames']), report
    assert evaluate("document.getElementById('wealthKftcRetirementStyle')===null")
    assert evaluate("document.getElementById('wealthKftcRetirementScript')===null")
    assert evaluate("typeof window.WealthKftcRetirement==='undefined'")
    assert evaluate("typeof window.refreshKftcStatus==='undefined'")


@pytest.mark.parametrize('width', [1280,390])
def test_reload_bank_settings_and_refresh_need_no_retirement_shim(chrome_preview, width):
    call,evaluate,port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,
         'deviceScaleFactor':1,'mobile':width == 390})
    call('Network.setBlockedURLs', {'urls':['*wealth-kftc-retirement.js*']})
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#assets'})
    for reloaded in [False,True]:
        if reloaded:
            call('Page.reload', {'ignoreCache':True})
        wait_for(evaluate, "document.readyState==='complete'&&!!window.WealthUnifiedTimeseries")
        evaluate(FRAMES)
        assert_retired(evaluate)
        click(call,evaluate,'.account-cat-tab[data-cat=banking]')
        evaluate(FRAMES)
        assert_retired(evaluate)
        click(call,evaluate,'#refreshButton')
        evaluate(FRAMES)
        assert_retired(evaluate)
        no_overflow(evaluate,width)
        click(call,evaluate,'.wealth-settings-link')
        evaluate(FRAMES)
        assert evaluate("!document.getElementById('settingsApiPanel').hidden && !document.getElementById('userOpenApiModal')")
        assert evaluate("!!document.getElementById('openapiDartKey')")
        assert_retired(evaluate)
        evaluate("location.hash='#assets'")
        evaluate(FRAMES)
