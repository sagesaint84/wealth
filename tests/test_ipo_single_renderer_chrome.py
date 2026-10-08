"""Native Chrome observes the first render and every refresh frame, without a decorator."""
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_ipo_direct_refresh_startup import BOOT, FRAMES
from tests.test_workflow_ux_chrome import click, no_overflow


INSTRUMENT = r'''(() => {
  window.__compactFrames = [];
  window.__sampleCompact = () => ({
    columns: [...document.querySelectorAll('.ipo-cards-container')].map(container =>
      getComputedStyle(container).gridTemplateColumns.split(' ').length),
    cards: [...document.querySelectorAll('.ipo-card')].map(card => ({
      id: card.dataset.ipoId, compact: card.classList.contains('ipo-compact-card'),
      expanded: card.classList.contains('ipo-card-expanded'),
      toggle: card.querySelector('.ipo-card-detail-toggle')?.getAttribute('aria-expanded'),
      details: [...card.querySelectorAll('.ipo-card-body,.ipo-card-footer,.ipo-score-box')]
        .map(detail => ({hidden:detail.hidden, display:getComputedStyle(detail).display}))
    }))
  });
  window.addEventListener('wealth:ipo-market-rendered', () =>
    __compactFrames.push({phase:'synchronous-render',...__sampleCompact()}));
})();'''


def assert_compact(frame, expanded=()):
    assert frame['columns'] and all(count == 1 for count in frame['columns']), frame
    assert frame['cards'], frame
    for card in frame['cards']:
        is_expanded = card['id'] in expanded
        assert card['compact'], card
        assert card['expanded'] == is_expanded, card
        assert card['toggle'] == str(is_expanded).lower(), card
        assert len(card['details']) == 3, card
        for detail in card['details']:
            assert detail['hidden'] == (not is_expanded), card
            assert (detail['display'] == 'none') == (not is_expanded), card


@pytest.mark.parametrize('width', [1280, 390])
def test_initial_and_refresh_never_paint_legacy_cards(chrome_preview, width):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,
         'deviceScaleFactor':1,'mobile':width == 390})
    # A late/unavailable former decorator must never change core presentation.
    # This makes the old full-card-first production path fail deterministically.
    call('Network.setBlockedURLs', {'urls':['*wealth-ipo-compact-view.js*']})
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT + INSTRUMENT})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#ipo'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthIpoState")
    evaluate('__releaseIpoApplications()')
    wait_for(evaluate, "!!document.querySelector('.ipo-card')")
    for frame in evaluate('__compactFrames'):
        assert_compact(frame)
    assert evaluate('__ipoCalls') == [
        {'path':'/api/ipo/applications','method':'GET'},
        {'path':'/api/ipo/market','method':'GET'}]
    # Three cards expose the former multi-column layout at desktop width.
    immediate = evaluate(r'''(() => {
      __rows = Array.from({length:3},(_,i)=>({...WealthIpoState.getMarketIpos()[0],
        ipo_id:'compact-'+i, company_name:'Compact fixture '+i, market:i ? 'KOSDAQ' : null,
        refund_date:'2026-10-16',payment_date:'2026-10-16',
        score:{score:null,coverage:60,core_missing:['tradable_share_ratio'],is_calculating:true},
        sources:{metalogos160:{url:'https://metalogos.ai/160ipo/stock/B_SYNTHETIC',attractiveness_score:86}}}));
      WealthIpoState.setMarketIpos(__rows); WealthIpoState.renderIpoList();
      return __sampleCompact(); // No animation frame or observer callback.
    })()''')
    assert len(immediate['cards']) == 3
    assert_compact(immediate)
    assert evaluate("document.querySelector('.ipo-market-badge').textContent") == '시장 미확인'
    assert evaluate("document.querySelector('.ipo-score-diagnostic').textContent") == '데이터 60% · 부족: 유통가능주식비율'
    assert evaluate("document.querySelector('.ipo-metalogos-reference').textContent") == '160 원문 · 매력지수 86'
    evaluate(r'''(() => {
      __refreshCalls=0; __compactFrames=[];
      __refreshGate=new Promise(resolve=>window.__resolveRefresh=resolve);
      window.fetchJson=(url)=>{
        if(url!=='/api/ipo/market/refresh')throw new Error('unexpected metadata GET '+url);
        __refreshCalls++;return __refreshGate;
      };
      __compactObserver=new MutationObserver(()=>__compactFrames.push({phase:'mutation',...__sampleCompact()}));
      __compactObserver.observe(document.getElementById('ipoListWrapper'),{childList:true,subtree:true});
    })()''')
    click(call, evaluate, '#ipoRefreshBtn')
    evaluate(r'''(async()=>{
      __resolveRefresh({market:{ipos:__rows.map(row=>({...row,
        score:{score:61.9,grade:'C',coverage:75,core_missing:[],is_calculating:false}}))}});
      for(let i=0;i<8;i++){
        await new Promise(requestAnimationFrame);
        __compactFrames.push({phase:'frame',...__sampleCompact()});
      }
      __compactObserver.disconnect();
    })()''')
    frames = evaluate('__compactFrames')
    assert sum(frame['phase'] == 'frame' for frame in frames) == 8
    assert any(frame['phase'] == 'synchronous-render' for frame in frames)
    for frame in frames:
        assert_compact(frame)
    assert evaluate('__refreshCalls') == 1
    assert evaluate("document.querySelector('.ipo-score-diagnostic')===null")
    assert evaluate("document.querySelector('.ipo-score-box').textContent.includes('61.9')")
    assert evaluate("document.querySelector('.ipo-metalogos-reference').textContent") == '160 원문 · 매력지수 86'
    assert evaluate("document.getElementById('wealthIpoCompactViewStyles')===null")
    assert evaluate("document.getElementById('wealthIpoCompactViewScript')===null")
    no_overflow(evaluate, width)

    click(call, evaluate, '[data-ipo-id="compact-0"] .ipo-card-detail-toggle')
    assert_compact(evaluate('__sampleCompact()'), expanded=['compact-0'])
    assert evaluate("document.querySelector('[data-ipo-id=compact-0] .ipo-card-detail-toggle').textContent") == '접기'
    assert evaluate("document.querySelector('[data-ipo-id=compact-0] .ipo-card-body').textContent.includes('환불일')")
    # Broker filtering, month navigation, and application rerenders retain IDs.
    evaluate("document.getElementById('ipoBrokerFilter').value='eugene';document.getElementById('ipoBrokerFilter').dispatchEvent(new Event('change',{bubbles:true}))")
    assert_compact(evaluate('__sampleCompact()'), expanded=['compact-0'])
    click(call, evaluate, '#ipoNextMonthBtn')
    click(call, evaluate, '#ipoPrevMonthBtn')
    assert_compact(evaluate('__sampleCompact()'), expanded=['compact-0'])
    evaluate(r"""(() => {
      __appWrites=[];
      __currentRows=WealthIpoState.getCanonicalMarketIpos();
      window.fetchJson=async(url)=>{
        if(url==='/api/ipo/market')return {ipos:__currentRows};
        throw new Error('unexpected application reload '+url);
      };
      window.fetch=async(url,options)=>{
        if(options?.method==='PUT'){
          const payload=JSON.parse(options.body); __appWrites.push(payload);
          return {ok:true,json:async()=>({revision:2,target_owners:['아빠'],
            applied_owners:payload.applied_owners,state:'all',all_applied:true})};
        }
        if(url==='/api/ipo/applications')return {ok:true,json:async()=>({revision:2,
          family_members:['아빠'],applications:{'compact-0':{target_owners:['아빠'],applied_owners:['아빠']}}})};
        return {ok:true,json:async()=>({brokers:[]})};
      };
    })()""")
    click(call, evaluate, '[data-ipo-id="compact-0"] .ipo-member-chk')
    evaluate(FRAMES)
    assert evaluate('__appWrites[0].applied_owners') == ['아빠']
    evaluate('WealthIpoState.renderIpoList()')
    assert evaluate("!!document.querySelector('[data-ipo-id=compact-0] .ipo-applicant-account-select')")
    assert evaluate("!!document.querySelector('[data-ipo-id=compact-0] .ipo-allocation-save')")
    assert evaluate("!!document.querySelector('[data-ipo-id=compact-0] .ipo-sale-link-save')")
    assert_compact(evaluate('__sampleCompact()'), expanded=['compact-0'])
    click(call, evaluate, '[data-ipo-id="compact-0"] .ipo-card-detail-toggle')
    assert_compact(evaluate('__sampleCompact()'))
    for theme in ['purple','white','oled']:
        evaluate(f"document.documentElement.dataset.theme='{theme}'")
        evaluate(FRAMES)
        assert_compact(evaluate('__sampleCompact()'))
        no_overflow(evaluate, width)
        click(call, evaluate, '[data-ipo-id="compact-0"] .ipo-card-detail-toggle')
        assert_compact(evaluate('__sampleCompact()'), expanded=['compact-0'])
        no_overflow(evaluate, width)
        click(call, evaluate, '[data-ipo-id="compact-0"] .ipo-card-detail-toggle')
