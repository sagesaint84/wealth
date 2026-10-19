"""Render real calendar DOM with synthetic backend projections only."""
import json

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_ipo_schedule_lifecycle import market, events, SyntheticDart, ORIGINAL, DEMAND, WINDOW
from app.services.ipo.source_discovery import _apply_dart_schedules


def test_eucast_calendar_stop_and_unknown_state_in_real_dom(chrome_preview):
    call, evaluate, port = chrome_preview
    data = market()
    original = events(data)
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, DEMAND]), **WINDOW)
    postponed = events(data)
    unknown = market()
    _apply_dart_schedules(unknown, dart=SyntheticDart([ORIGINAL], fail_structured=True), **WINDOW)
    unverified = events(unknown)
    payload = json.dumps([original, postponed, unverified], ensure_ascii=False)
    call('Page.addScriptToEvaluateOnNewDocument', {'source': '''
      window.__calendarPhases = ''' + payload + ''';
      window.__calendarPhase = 0;
      const originalFetch = window.fetch;
      window.fetch = function(url, ...args) {
        if (String(url).includes('/api/moneylog/calendar?'))
          return Promise.resolve(new Response(JSON.stringify({events:window.__calendarPhases[window.__calendarPhase]}),
            {status:200,headers:{'Content-Type':'application/json'}}));
        return originalFetch.call(this,url,...args);
      };
    '''})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#income'})
    wait_for(evaluate, "!!window.WealthCalendar && typeof window.setIncomeTab === 'function'")
    evaluate("window.setIncomeTab('calendar'); true")
    # Keep the actual month controls; do not substitute a fake calendar DOM.
    evaluate("""(async()=>{
      for(let n=0;n<120;n++){
        const serial=WealthCalendar.getCurrentYear()*12+WealthCalendar.getCurrentMonth();
        if(serial===2026*12+10)break;
        document.getElementById(serial>2026*12+10?'calendarPrevMonthBtn':'calendarNextMonthBtn').click();
        await WealthCalendar.loadCalendar();
      }
      WealthCalendar.setSelectedDate('2026-10-19');
      await WealthCalendar.loadCalendar();return true;
    })()""")
    wait_for(evaluate, "document.querySelector('#calendarPanel').getClientRects().length > 0 && document.querySelector('#calendarDetailPanel').textContent.includes('유캐스트 청약 첫째날')")
    assert evaluate("document.querySelector('#calendarGridWrapper').textContent.includes('유캐스트')")
    evaluate("(async()=>{window.__calendarPhase=1;await WealthCalendar.loadCalendar();return true;})()")
    assert evaluate("!document.querySelector('#calendarGridWrapper').textContent.includes('유캐스트') && !document.querySelector('#calendarDetailPanel').textContent.includes('청약 첫째날')")
    evaluate("(async()=>{window.__calendarPhase=2;await WealthCalendar.loadCalendar();return true;})()")
    assert evaluate("document.querySelector('#calendarDetailPanel').textContent.includes('청약 일정 확인 필요') && !document.querySelector('#calendarDetailPanel').textContent.includes('청약 첫째날')")
