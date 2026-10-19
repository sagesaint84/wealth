"""Real DOM: legacy calendar/list consistency and original-ID application edits."""
import json
from copy import deepcopy
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_ipo_stored_compat import presented, aliases
from tests.test_ipo_schedule_lifecycle import market, events, ORIGINAL, DEMAND, WINDOW
from app.services.ipo.source_discovery import _apply_dart_schedules


def test_legacy_list_calendar_and_alias_application_ids(chrome_preview):
    call, evaluate, port = chrome_preview
    legacy = market()
    legacy["ipos"].extend(aliases()["ipos"])
    stopped = deepcopy(legacy)
    reads = {"failed": 0, "candidates": [{"index": 0, "corp_code": "01000001", "master_row": {},
        "status": "ok", "restriction": {"status": "postponed", "rcept_no": DEMAND["rcept_no"], "source_date": "20261001"},
        "filing": ORIGINAL, "raw_structured": {}}]}
    _apply_dart_schedules(stopped, dart=None, prefetched=reads, **WINDOW)
    apps = {"old-elice": {"target_owners": ["A", "B"], "applied_owners": ["A"],
                            "applicants": {"A": {"allocation": {"quantity": 3, "links": []}}}},
            "official-elice": {"target_owners": ["A", "B"], "applied_owners": ["B"],
                                "applicants": {"B": {"allocation": {"quantity": 2, "links": []}}}}}
    payload = json.dumps({"markets": [{"ipos": presented(m, apps)} for m in (legacy, stopped)],
                          "calendars": [events(m) for m in (legacy, stopped)], "apps": apps}, ensure_ascii=False)
    call("Page.addScriptToEvaluateOnNewDocument", {"source": """
      window.__compat = """ + payload + """;
      window.__phase=0;window.__writes=[];
      const naturalFetch=window.fetch;
      window.fetch=function(url,options={}){
        const path=new URL(String(url),location.href).pathname;
        const reply=data=>Promise.resolve(new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}}));
        if(path==='/api/ipo/market')return reply(__compat.markets[__phase]);
        if(path==='/api/ipo/applications')return reply({revision:1,applications:__compat.apps,family_members:['A','B']});
        if(path==='/api/moneylog/calendar')return reply({events:__compat.calendars[__phase]});
        if(path.startsWith('/api/ipo/applications/') && options.method==='PUT'){
          const id=decodeURIComponent(path.split('/').pop());const body=JSON.parse(options.body);
          __writes.push({id,body});__compat.apps[id].applied_owners=body.applied_owners;
          return reply({...__compat.apps[id],revision:2,state:'none',all_applied:false});
        }
        return naturalFetch.call(this,url,options);
      };
    """})
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#ipo"})
    wait_for(evaluate, "!!window.WealthIpoState && !!window.WealthCalendar && typeof window.loadIpoSchedule==='function'")
    evaluate("(async()=>{await loadIpoSchedule();WealthIpoState.setFilterGroup('ALL');WealthIpoState.setHistoryYear(2026);WealthIpoState.setHistoryMonth(10);WealthIpoState.setMonthExplicitlySelected(true);WealthIpoState.renderIpoList();return true;})()")
    wait_for(evaluate, "document.querySelectorAll('#ipoListWrapper .ipo-card').length===2")
    assert evaluate("document.querySelector('#ipoListWrapper').textContent.includes('일정 확인 필요') && !document.querySelector('#ipoListWrapper').textContent.includes('청약중')")
    assert evaluate("[...document.querySelectorAll('.ipo-card h3')].filter(n=>n.textContent.includes('엘리스그룹')).length===1")
    evaluate("document.querySelector('[data-ipo-id=\"official-elice\"] .ipo-card-detail-toggle').click(); true")
    assert evaluate("document.querySelector('.ipo-member-chk[data-ipo=\"old-elice\"][data-member=\"A\"]').checked && document.querySelector('.ipo-member-chk[data-ipo=\"official-elice\"][data-member=\"B\"]').checked")
    evaluate("document.querySelector('.ipo-member-chk[data-ipo=\"old-elice\"][data-member=\"A\"]').click(); true")
    wait_for(evaluate, "__writes.length===1")
    assert evaluate("__writes[0].id==='old-elice' && __writes[0].body.applied_owners.length===0 && __compat.apps['official-elice'].applied_owners[0]==='B' && __compat.apps['old-elice'].applicants.A.allocation.quantity===3")
    evaluate("(async()=>{__phase=1;await loadIpoSchedule();return true;})()")
    wait_for(evaluate, "document.querySelector('#ipoListWrapper').textContent.includes('청약 연기')")
    assert evaluate("!document.querySelector('#ipoListWrapper').textContent.includes('청약중')")
    evaluate("(async()=>{setIncomeTab('calendar');WealthCalendar.setSelectedDate('2026-10-19');await WealthCalendar.loadCalendar();return true;})()")
    wait_for(evaluate, "document.querySelector('#calendarPanel').getClientRects().length>0")
    assert evaluate("!document.querySelector('#calendarDetailPanel').textContent.includes('유캐스트')")
    evaluate("(async()=>{WealthCalendar.setSelectedDate('2026-10-20');await WealthCalendar.loadCalendar();return true;})()")
    assert evaluate("[...document.querySelectorAll('#calendarDetailPanel .calendar-event-item')].filter(n=>n.textContent.includes('엘리스그룹')).length===1")
