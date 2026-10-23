"""Real IPO/calendar DOM using synthetic server projections; no screenshots."""
import json
from datetime import date
from unittest.mock import patch

import pytest

from tests.test_account_reorder_runtime import wait_for
from tests.test_ipo_calendar_ui_chrome import ui_chrome_preview, open_list
from tests.test_ipo_naver_primary import observed_market
from app.services.ipo.presentation import present_market_store
from app.services.ipo.store import get_ipo_calendar_events


@pytest.mark.parametrize("width", [360, 390, 1280])
def test_younggwang_primary_schedule_with_unlinked_dart_in_list_and_calendar(ui_chrome_preview, width):
    call, evaluate, port = ui_chrome_preview
    market = observed_market()
    with patch("app.services.ipo.presentation._read_portfolio_for_presentation", return_value={}), \
         patch("app.services.ipo.presentation.read_pnl_records_readonly", return_value=[]), \
         patch("app.services.ipo.store.read_market_store", return_value=market):
        row = present_market_store("synthetic", market, date(2026, 10, 23))["ipos"][0]
        events = get_ipo_calendar_events(None, "2026-10-01", "2026-11-30")
    open_list(call, evaluate, port, width)
    evaluate("""(()=>{
      window.__uiRows = [""" + json.dumps(row, ensure_ascii=False) + """];
      WealthIpoState.setMarketIpos(__uiRows);
      WealthIpoState.renderIpoList(); return true;
    })()""")
    wait_for(evaluate, "document.querySelector('.ipo-company-name')?.textContent==='영광'")
    assert evaluate("document.querySelector('.ipo-subscription-status').textContent==='청약중'")
    # Test JS/KST boundary helper as well as the backend state label.
    assert evaluate("[21,22,23,24].map(d=>WealthIpoDate.subscriptionStatus(__uiRows[0],'2026-10-'+d))") == ["예정", "중", "중", "마감"]
    assert evaluate("WealthIpoDate.todayKst(new Date('2026-10-22T15:00:00Z'))") == "2026-10-23"
    evaluate("document.querySelector('.ipo-card-detail-toggle').click();true")
    text = evaluate("document.querySelector('.ipo-card').textContent")
    for value in ("17,000", "한국투자증권", "2026-10-22", "2026-10-23", "2026-11-02", "Npay", "2026-10-21"):
        assert value in text
    assert evaluate("document.documentElement.scrollWidth<=innerWidth")
    evaluate("""(()=>{
      const natural=window.fetch;
      const events=""" + json.dumps(events, ensure_ascii=False) + """;
      window.fetch=function(url,...args){
        if(String(url).includes('/api/moneylog/calendar?'))return Promise.resolve(new Response(
          JSON.stringify({events}),{status:200,headers:{'Content-Type':'application/json'}}));
        return natural.call(this,url,...args);
      };return true;
    })()""")
    evaluate("""(async()=>{
      setIncomeTab('calendar');
      for(let n=0;n<120;n++){
        const serial=WealthCalendar.getCurrentYear()*12+WealthCalendar.getCurrentMonth();
        if(serial===2026*12+10)break;
        document.getElementById(serial>2026*12+10?'calendarPrevMonthBtn':'calendarNextMonthBtn').click();
        await WealthCalendar.loadCalendar();
      }
      WealthCalendar.setSelectedDate('2026-10-23');await WealthCalendar.loadCalendar();return true;
    })()""")
    wait_for(evaluate, "document.querySelector('#calendarDetailPanel').textContent.includes('영광 청약 마지막날')")
    assert evaluate("!document.querySelector('#calendarDetailPanel').textContent.includes('확인 필요')")
    assert evaluate("document.documentElement.scrollWidth<=innerWidth && __uiWrites.length===0")
