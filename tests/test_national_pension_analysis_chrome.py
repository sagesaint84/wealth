"""Synthetic metadata editing and result readability; no provider or real data."""
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_defaults_interest_chrome import prepare
from tests.test_workflow_ux_chrome import FRAMES, no_overflow


@pytest.mark.parametrize('width', [1280,390,320])
@pytest.mark.parametrize('theme', ['purple','white','oled'])
def test_pension_analysis_sections_draft_save_cancel_conflict_and_mobile(chrome_preview,width,theme):
    call,evaluate=prepare(chrome_preview,width)
    evaluate(f"document.documentElement.dataset.theme={json.dumps(theme)}")
    evaluate(r'''(()=>{
      window.__analysisItem={id:'np-analysis-fixture',owner:'아빠',insurance_type:'national_pension',product_name:'합성 국민연금',
        total_paid_amount:8000000,monthly_payout:100000,payout_type:'monthly_pension',payout_duration_years:20,
        expected_amount:24000000,converted_total_asset:24000000,maturity_date:'2045-01-01',yearly_contributions:[{year:'2013',deposit:120000}]};
      window.__analysisOriginal=JSON.stringify(__analysisItem);
      window.__analysisMeta={revision:0,analysis:{membership_periods:[],annual_details:[],tax_years:[],scenario:{}}};
      window.__analysisWrites=[];window.__analysisConflict=false;
      const previous=window.fetch;
      window.fetch=async(url,options={})=>{
        const path=new URL(String(url),location.href).pathname;
        if(path.includes('/national-pension-analysis')){
          const method=options.method||'GET',body=options.body?JSON.parse(options.body):{};
          if(path.endsWith('/calculate'))return {ok:true,status:200,json:async()=>({tax_years:[{year:2024,status:'estimated',allowed_deduction:2000000,applied_deduction:2000000,tax_before:990000,tax_after:780000,estimated_reduction:210000,actual_tax_saving:null,source_url:'https://t.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7667&mi=2227',notice:'예상 감소분은 환급액이 아닙니다.'}],returns:{status:'scenario',basis:'nominal',personal_cost_assumed:false,annual_dates_approximated:false,notice:'종료 나이는 시나리오 가정입니다.',scenarios:[{age:75,status:'scenario',future_premiums:0,pension_receipts:12000,future_net_cash_flow:12000,net_cash_flow:null,payback_date:null,pre_tax_irr:{status:'incomplete',rate:null,reason:'본인 부담액 미확인'},tax_benefit_irr:null,after_tax_irr:{status:'unsupported',reason:'세후 세법 미등록'}}]}})};
          if(method!=='GET'){
            __analysisWrites.push({method,body});
            if(__analysisConflict)return {ok:false,status:409,json:async()=>({detail:'합성 revision 충돌'})};
            __analysisMeta={revision:__analysisMeta.revision+1,analysis:method==='DELETE'?{}:body.analysis};
          }
          return {ok:true,status:200,json:async()=>({...structuredClone(__analysisMeta),history:structuredClone(__analysisItem.yearly_contributions),total_paid_amount:8000000,monthly_payout:100000,maturity_date:'2045-01-01'})};
        }
        return previous(url,options);
      };
      window.confirm=()=>true;
      location.hash='assets';window.dispatchEvent(new Event('hashchange'));
      renderInsurance([__analysisItem],'아빠');switchAccountCategory('insurance');
      openNationalPensionHistory(__analysisItem);
    })()''')
    wait_for(evaluate,"!document.getElementById('npAnalysisFields').disabled")
    assert evaluate("document.querySelectorAll('#npAnalysisFields>details').length") == 4
    evaluate("document.querySelectorAll('#npAnalysisFields>details').forEach(e=>e.open=true)")
    evaluate("document.querySelector('[data-np-add=membership_periods]').click()")
    evaluate(r'''(()=>{const row=document.querySelector('#npAnalysis-membership_periods [data-row]');
      for(const [key,value] of Object.entries({year:'2024',start_month:'1',end_month:'4',membership_type:'workplace',workplace_role:'employee'}))row.querySelector(`[data-key=${key}]`).value=value;
    })()''')
    assert evaluate("__analysisWrites.length") == 0
    evaluate("document.querySelector('[data-np-action=save]').click()")
    wait_for(evaluate,"__analysisWrites.length===1&&document.getElementById('npAnalysisNotice').textContent.includes('저장했습니다')")
    assert evaluate("__analysisWrites[0].body.revision") == 0
    assert evaluate("__analysisWrites[0].body.expected_history[0].deposit") == 120000
    assert evaluate("__analysisWrites[0].body.analysis.membership_periods[0].workplace_role") == 'employee'
    evaluate("document.querySelector('#npAnalysis-membership_periods [data-key=end_month]').value='5';document.querySelector('[data-np-action=cancel]').click()")
    assert evaluate("document.querySelector('#npAnalysis-membership_periods [data-key=end_month]').value") == '4'
    evaluate("__analysisConflict=true;document.querySelector('#npAnalysis-membership_periods [data-key=end_month]').value='6';document.querySelector('[data-np-action=save]').click()")
    wait_for(evaluate,"document.getElementById('npAnalysisNotice').textContent.includes('합성 revision 충돌')")
    assert evaluate("document.querySelector('#npAnalysis-membership_periods [data-key=end_month]').value") == '6'
    assert evaluate("__analysisMeta.analysis.membership_periods[0].end_month") == 4
    evaluate("__analysisConflict=false;document.querySelector('[data-np-action=reload]').click()")
    wait_for(evaluate,"!document.getElementById('npAnalysisFields').disabled&&document.querySelector('#npAnalysis-membership_periods [data-key=end_month]').value==='4'")
    for kind in ('annual_details','tax_years'):
        evaluate(f"document.querySelector('[data-np-add={kind}]').click()")
        assert evaluate(f"[...document.querySelectorAll('#npAnalysis-{kind} input[type=number]')].every(e=>e.value==='')")
        assert evaluate(f"document.querySelector('#npAnalysis-{kind} [data-key=source]').value") == 'unknown'
        evaluate(f"document.querySelector('#npAnalysis-{kind} [data-key=year]').value='2024'")
    assert evaluate("[...document.querySelectorAll('#npAnalysisPanel label')].every(label=>!!document.getElementById(label.htmlFor))")
    evaluate(r'''(()=>{
      const tax=document.querySelector('#npAnalysis-tax_years [data-row]');
      tax.querySelector('[data-key=taxable_before]').value='15000000';
      tax.querySelector('[data-key=allowed_deduction]').value='2000000';
      tax.querySelector('[data-key=source]').value='tax_return';tax.querySelector('[data-key=verified]').checked=true;
      const scenario=document.getElementById('npAnalysis-scenario');
      for(const [key,value] of Object.entries({birth_date:'1960-01-01',as_of_date:'2025-01-01',pension_start:'2030-01-01',monthly_pension:'200',inflation:'0',future_monthly_premium:'0',pension_value_basis:'future_nominal'}))scenario.querySelector(`[data-key=${key}]`).value=value;
    })()''')
    evaluate("document.querySelector('[data-np-action=calculate]').click()")
    wait_for(evaluate,"document.getElementById('npAnalysisResults').textContent.includes('본인 부담액 미확인')")
    assert '환급액이 아닙니다' in evaluate("document.getElementById('npAnalysisResults').textContent")
    assert '210,000' in evaluate("document.getElementById('npAnalysisResults').textContent")
    assert evaluate("__analysisWrites.length") == 2  # one successful save and one rejected save; calculation is read-only
    evaluate(FRAMES)
    assert evaluate("(()=>{const d=document.getElementById('nationalPensionHistoryDialog');return d.scrollWidth<=d.clientWidth+1;})()")
    assert evaluate("[...document.querySelectorAll('#npAnalysisPanel .np-analysis-row')].every(e=>e.scrollWidth<=e.clientWidth+1)")
    evaluate("document.querySelector('[data-np-action=reset]').click()")
    wait_for(evaluate,"__analysisWrites.length===3&&document.getElementById('npAnalysisNotice').textContent.includes('삭제했습니다')")
    assert evaluate("__analysisWrites[2].method") == 'DELETE'
    assert evaluate("(()=>{const copy={...__analysisItem};delete copy.national_pension_analysis;return JSON.stringify(copy)===__analysisOriginal;})()")
    evaluate("closeDialog('nationalPensionHistoryDialog');openNationalPensionHistory(__analysisItem)")
    wait_for(evaluate,"!document.getElementById('npAnalysisFields').disabled")
    assert evaluate("document.querySelectorAll('#npAnalysis-membership_periods [data-row]').length") == 0
    no_overflow(evaluate,width)
