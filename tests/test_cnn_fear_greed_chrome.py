"""Synthetic home-tab relay rendering; CSP permits loopback only."""
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_static_transport_chrome import transport_server
from tests.test_home_three_tabs_chrome import BOOT, choose

FEED = r"""
window.__cnnFixture={status:'ok',score:42.25,rating:'Fear',observed_date:new Date().toISOString().slice(0,10),
 relay_updated_at:new Date().toISOString(),valid_until:new Date(Date.now()+3600000).toISOString()};
window.__cnnRealTimeout=setTimeout;
window.setTimeout=function(fn,delay,...args){
 if(delay>3500000&&delay<3700000)window.__cnnExpiry=fn;
 return __cnnRealTimeout(fn,delay,...args);
};
"""
HOME = BOOT.replace('response({markets:', 'response({fear_greed:window.__cnnFixture,markets:')

@pytest.mark.parametrize('width', [320,360,390,768,1280])
@pytest.mark.parametrize('theme', ['purple','white','oled'])
def test_relay_tab_lazy_states_sources_expiry_late_response_and_width(chrome_preview,width,theme):
    assert BOOT.count('response({markets:')==1, 'Home mock response contract changed'
    assert HOME!=BOOT and 'fear_greed:window.__cnnFixture' in HOME
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':f"localStorage.setItem('app_theme','{theme}');"+FEED+HOME})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<500})
    call('Emulation.setTouchEmulationEnabled',{'enabled':width<500})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,"!!window.WealthUnifiedTimeseries && WealthStartup.canRead()")
        assert evaluate('__tabs.markets')==0
        assert evaluate("document.querySelectorAll('#marketFearGreed').length")==0
        choose(evaluate,'history'); assert evaluate('__tabs.markets')==0
        choose(evaluate,'markets')
        wait_for(evaluate,"!!document.querySelector('#marketFearGreed [data-cnn-score]')")
        assert evaluate('__tabs.markets')==1
        assert '42.25 (공포)' in evaluate("document.getElementById('marketFearGreed').textContent")
        for expected in ['CNN 지수 · 비공식 데이터 중계','중계 기준일','중계 파일 갱신','KST','실시간 보장 없음']:
            assert expected in evaluate("document.getElementById('marketFearGreed').textContent")
        assert evaluate("[...document.querySelectorAll('#marketFearGreed a')].map(a=>a.href)")==[
            'https://www.cnn.com/markets/fear-and-greed','https://github.com/chirag127/fear-greed-index-api']
        assert evaluate("[...document.querySelectorAll('#marketFearGreed a')].every(a=>a.rel.includes('noopener'))")
        assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert evaluate("document.querySelectorAll('#marketFearGreed').length")==1
        # Exercise the actual captured expiration callback with a synthetic clock.
        evaluate("window.__cnnNow=Date.now;Date.now=()=>__cnnNow()+7200000;__cnnExpiry();Date.now=__cnnNow")
        assert evaluate("document.querySelectorAll('[data-cnn-score]').length")==0
        assert '갱신 지연' in evaluate("document.getElementById('marketFearGreed').textContent")
        assert evaluate('__tabs.markets')==1  # expiration makes no API call
        for status in ['source_error','stale','not_connected']:
            evaluate(f"renderMarkets({{...marketOverviewData,fear_greed:{{...__cnnFixture,status:'{status}',score:null,rating:null}}}})")
            assert evaluate("document.querySelectorAll('[data-cnn-score]').length")==0
        for value in ['0','100']:
            evaluate(f"renderMarkets({{...marketOverviewData,fear_greed:{{...__cnnFixture,score:{value}}}}})")
            assert evaluate("document.querySelectorAll('[data-cnn-score]').length")==1
        for value in ['true','null','NaN','Infinity','-1','101',"'<img src=x onerror=alert(1)>'"]:
            evaluate(f"renderMarkets({{...marketOverviewData,fear_greed:{{...__cnnFixture,score:{value}}}}})")
            assert evaluate("document.querySelectorAll('[data-cnn-score]').length")==0
        evaluate("renderMarkets({...marketOverviewData,fear_greed:{...__cnnFixture,rating:'<img src=x onerror=alert(1)>'}})")
        assert evaluate("document.querySelectorAll('#marketFearGreed img,#marketFearGreed script').length")==0
        assert evaluate("document.querySelectorAll('[data-cnn-score]').length")==0
        choose(evaluate,'portfolio')
        evaluate('__tabs.hold=true');choose(evaluate,'markets')
        wait_for(evaluate,'__tabs.pending.length===1')
        choose(evaluate,'history')
        before=evaluate("document.getElementById('marketGrid').innerHTML")
        evaluate('__tabs.pending.shift()();__tabs.hold=false')
        wait_for(evaluate,'!startupReadPending.size')
        assert evaluate("document.getElementById('marketGrid').innerHTML")==before
        choose(evaluate,'markets')
        wait_for(evaluate,"!!document.querySelector('#marketFearGreed [data-cnn-score]')")
        assert evaluate('__tabs.errors')==[]
        assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')
