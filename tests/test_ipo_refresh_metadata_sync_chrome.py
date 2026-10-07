"""Controlled promises and real Chrome: one snapshot for score and decoration."""
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_ipo_reference_chrome import reference_browser, SETUP, FRAMES, TEXT


@pytest.mark.parametrize('get_first', [True, False])
def test_old_get_cannot_leave_stale_refresh_diagnostics(reference_browser, get_first):
    call, evaluate, port, _browser = reference_browser
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#ipo'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthIpoState")
    evaluate(SETUP)
    assert evaluate("document.querySelector('.ipo-score-diagnostic').textContent") == '데이터 60% · 부족: 유통가능주식비율'
    evaluate(r'''(()=>{
      __old = structuredClone(__ipo);
      __latest = structuredClone(__ipo);
      __latest.score = {score:61.9,grade:'C',coverage:75,core_missing:[],is_calculating:false};
      __latest.presentation_month_sort_dates = {'2026-10':'2026-10-12','2026-11':'2026-11-05'};
      __getCalls = 0; __postCalls = 0; __renderFrames = [];
      __getGate = new Promise(resolve=>window.__resolveGet=resolve);
      __postGate = new Promise(resolve=>window.__resolvePost=resolve);
      window.fetch = async()=>({ok:true,json:async()=>({applications:{}})});
      window.fetchJson = (url)=>{
        if(url==='/api/ipo/market/refresh'){__postCalls++;return __postGate;}
        if(url==='/api/ipo/market'){__getCalls++;return __getGate;}
        throw new Error('unexpected synthetic request '+url);
      };
      window.addEventListener('wealth:ipo-market-rendered',()=>__renderFrames.push({
        score:WealthIpoState.getMarketIpos()[0].score.score,
        diagnostic:document.querySelector('.ipo-score-diagnostic')?.textContent || null,
        reference:document.querySelector('.ipo-metalogos-reference')?.textContent
      }));
      __load = window.loadIpoSchedule();
      document.getElementById('ipoRefreshBtn').click();
    })()''')
    evaluate(FRAMES)
    assert evaluate('__postCalls') == 1
    assert evaluate('__getCalls') == 1, 'compact decoration must not start another market GET'
    if get_first:
        evaluate('(async()=>{__resolveGet({ipos:[__old]});await __load;})()')
        evaluate(FRAMES)
    evaluate('__resolvePost({market:{ipos:[__latest]}})')
    evaluate(FRAMES)
    assert evaluate("__renderFrames.filter(f=>f.score===61.9).every(f=>f.diagnostic===null&&f.reference==='160 원문 · 매력지수 86')")
    assert evaluate('__renderFrames.some(f=>f.score===61.9)')
    if not get_first:
        evaluate('(async()=>{__resolveGet({ipos:[__old]});await __load;})()')
        evaluate(FRAMES)
    assert evaluate("document.querySelector('.ipo-score-box').textContent.includes('61.9')"), evaluate("({text:document.querySelector('.ipo-score-box').textContent,snapshot:WealthIpoState.getMarketIpos(),frames:__renderFrames})")
    assert evaluate("document.querySelector('.ipo-score-diagnostic')===null")
    assert evaluate("document.querySelector('.ipo-metalogos-reference').textContent") == TEXT
    assert evaluate('WealthIpoState.getMarketIpos()[0].score.coverage') == 75
    assert evaluate("(()=>{const c=document.querySelector('.ipo-card'),b=c.querySelector('.ipo-card-detail-toggle');b.click();const v=c.classList.contains('ipo-card-expanded');b.click();return v!==c.classList.contains('ipo-card-expanded');})()")
    evaluate("document.getElementById('ipoNextMonthBtn').click()")
    evaluate(FRAMES)
    assert evaluate('WealthIpoState.getMarketIpos()[0].presentation_sort_date') == '2026-11-05'
    assert evaluate("document.querySelector('.ipo-score-box').textContent.includes('61.9')")
    evaluate("document.getElementById('ipoPrevMonthBtn').click()")
    evaluate(FRAMES)
    assert evaluate('WealthIpoState.getMarketIpos()[0].presentation_sort_date') == '2026-10-12'
    assert evaluate('__getCalls') == 1


def test_refresh_failure_preserves_snapshot_and_numeric_score_fail_safe(reference_browser):
    call, evaluate, port, _browser = reference_browser
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#ipo'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthIpoState")
    evaluate(SETUP)
    before = evaluate("({snapshot:JSON.stringify(WealthIpoState.getMarketIpos()),diagnostic:document.querySelector('.ipo-score-diagnostic').textContent,reference:document.querySelector('.ipo-metalogos-reference').textContent})")
    evaluate("window.fetchJson=async()=>{throw new Error('synthetic refresh failure')};document.getElementById('ipoRefreshBtn').click()")
    evaluate(FRAMES)
    after = evaluate("({snapshot:JSON.stringify(WealthIpoState.getMarketIpos()),diagnostic:document.querySelector('.ipo-score-diagnostic').textContent,reference:document.querySelector('.ipo-metalogos-reference').textContent})")
    assert after == before
    assert evaluate("!!document.querySelector('.ipo-refresh-error')")
    # Even an internally inconsistent status cannot show missing-data text
    # alongside an already numeric canonical score.
    evaluate("__ipo.score.score=61.9;WealthIpoState.setMarketIpos([__ipo]);WealthIpoState.renderIpoList()")
    assert evaluate("document.querySelector('.ipo-score-diagnostic')===null")
