"""Display-only broker identities and canonical all-period PAST reconciliation."""
import json

from tests.test_ipo_history_month_frontend import _run_js_suite


def test_frontend_uses_presentation_keys_without_own_aliases_or_new_requests():
    from pathlib import Path
    from app.services.ipo.presentation import derive_lead_manager_filters
    rows = [
        {'ipo_id': 'raw', 'company_name': 'raw', 'filter_group': 'PAST', 'presentation_sort_date': '2026-09-10', 'lead_managers': ['삼성증권']},
        {'ipo_id': 'legal', 'company_name': 'legal', 'filter_group': 'PAST', 'presentation_sort_date': '2026-08-10', 'lead_managers': ['삼성증권(주)']},
        {'ipo_id': 'short', 'company_name': 'short', 'filter_group': 'PAST', 'presentation_sort_date': '2026-07-10', 'lead_managers': ['유진증권']},
        {'ipo_id': 'full', 'company_name': 'full', 'filter_group': 'PAST', 'presentation_sort_date': '2026-06-10', 'lead_managers': ['유진투자증권']},
    ]
    for row in rows:
        row['lead_manager_filters'] = derive_lead_manager_filters(row['lead_managers'])
    output = json.loads(_run_js_suite(f"""
      MockElement.prototype.focus = () => {{}};
      let requests = 0;
      globalThis.fetch = () => {{requests++;throw new Error('unexpected fetch')}};
      window.WealthIpoState.setMarketIpos({json.dumps(rows, ensure_ascii=False)});
      window.WealthIpoState.setFilterGroup('PAST');
      window.WealthIpoState.renderIpoList();
      const optionsHtml = mockWrapper.innerHTML;
      const select = mockWrapper.querySelector('#ipoBrokerFilter');
      select.value = 'samsung';
      select.dispatchEvent({{type:'change',target:select}});
      const samsungIds = mockWrapper.querySelectorAll('.ipo-card').map(c=>c.dataset.ipoId);
      const eugeneSelect = mockWrapper.querySelector('#ipoBrokerFilter');
      eugeneSelect.value = 'eugene';
      eugeneSelect.dispatchEvent({{type:'change',target:eugeneSelect}});
      process.stdout.write(JSON.stringify({{
        optionsHtml, requests, samsungIds, ids:mockWrapper.querySelectorAll('.ipo-card').map(c=>c.dataset.ipoId),
        raw:window.WealthIpoState.getCanonicalMarketIpos().map(r=>r.lead_managers)
      }}));
    """))
    assert output['optionsHtml'].count('value="samsung"') == 1
    assert '>삼성증권</option>' in output['optionsHtml']
    assert output['optionsHtml'].count('value="eugene"') == 1
    assert '>유진투자증권</option>' in output['optionsHtml']
    assert output['samsungIds'] == ['raw', 'legal']
    assert output['ids'] == ['short', 'full']
    assert output['raw'] == [row['lead_managers'] for row in rows]
    assert output['requests'] == 0
    source = (Path(__file__).resolve().parents[1] / 'app/static/wealth-ipo.js').read_text(encoding='utf-8')
    assert 'normalizeBrokerFilterName' not in source
    assert 'WealthIpoFilter' not in source
    assert 'lead_manager_filters' in source
    assert 'item.key === ipoBrokerFilter' in source


def test_past_uses_canonical_dates_not_month_projection_and_keeps_raw_snapshot():
    output = json.loads(_run_js_suite("""
      const rows = [
        {ipo_id:'older',company_name:'older',filter_group:'PAST',presentation_sort_date:'2026-07-10',lead_managers:['삼성증권(주)']},
        {ipo_id:'newer',company_name:'newer',filter_group:'PAST',presentation_sort_date:'2026-09-10',lead_managers:['삼성증권','미래에셋증권 주식회사']},
        {ipo_id:'fallback',company_name:'fallback',filter_group:'PAST',presentation_sort_date:'',lead_managers:['대신증권(주)']},
      ];
      const before = JSON.stringify(rows);
      rows.forEach(row=>{Object.freeze(row.lead_managers);Object.freeze(row)});
      Object.freeze(rows);
      window.WealthIpoState.setMarketIpos(rows);
      window.WealthIpoState.setMarketIpos(rows.map(row=>({...row,presentation_sort_date:row.ipo_id==='older'?'2026-12-10':'2026-01-10'})),{projection:true});
      window.WealthIpoState.setFilterGroup('PAST');
      window.WealthIpoState.setHistoryYear(2026);
      window.WealthIpoState.setHistoryMonth(3);
      window.WealthIpoState.renderIpoList();
      process.stdout.write(JSON.stringify({
        ids:mockWrapper.querySelectorAll('.ipo-card').map(c=>c.dataset.ipoId),
        rawUnchanged:before===JSON.stringify(rows)&&before===JSON.stringify(window.WealthIpoState.getCanonicalMarketIpos()),
        month:window.WealthIpoState.getHistoryMonth(),
        controls:!!mockWrapper.querySelector('#ipoMonthPicker'),
      }));
    """))
    assert output == {'ids': ['newer', 'older', 'fallback'], 'rawUnchanged': True, 'month': 3, 'controls': False}
