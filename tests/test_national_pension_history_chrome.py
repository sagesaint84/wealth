"""User-entered synthetic annual premiums; existing native Chrome fixture."""
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_defaults_interest_chrome import prepare
from tests.test_workflow_ux_chrome import FRAMES, no_overflow


@pytest.mark.parametrize('width', [1280, 390, 320])
def test_national_pension_history_edit_restore_missing_zero_and_mobile(chrome_preview, width):
    call, evaluate = prepare(chrome_preview, width)
    evaluate(r'''(()=>{
      const year=new Date().getFullYear();window.__npInitial=[];
      for(let y=2013;y<=year;y++) if(y!==2014) __npInitial.push({year:String(y),deposit:y===2015?0:120000});
      const item={id:'synthetic-np',owner:'아빠',insurance_type:'national_pension',product_name:'국민연금',
        total_paid_amount:8000000,payout_type:'monthly_pension',monthly_payout:100000,
        payout_duration_years:20,expected_amount:24000000,converted_total_asset:24000000,
        maturity_date:'2045-01-01',yearly_contributions:structuredClone(__npInitial)};
      window.__npData=[item,{...item,id:'synthetic-mom',owner:'엄마'}];
      window.__npBefore=JSON.stringify(__npData);window.__npWrites=[];
      const previous=window.fetch;
      window.fetch=async (url,options={})=>{
        if(String(url).includes('/api/insurance-accounts/synthetic-np/yearly-contributions')&&options.method==='PUT'){
          const body=JSON.parse(options.body);__npWrites.push(body);
          return {ok:true,status:200,json:async()=>({insurance:{...item,yearly_contributions:body.yearly_contributions}})};
        }
        return previous(url,options);
      };
      window.confirm=()=>true;
      location.hash='assets';window.dispatchEvent(new Event('hashchange'));
      renderInsurance(__npData,'아빠');switchAccountCategory('insurance');
    })()''')
    evaluate(FRAMES)
    assert '연금·보험' in evaluate("document.querySelector('#assetCategoryTabs [data-cat=insurance]').textContent")
    assert evaluate("document.getElementById('insuranceTabCount').textContent") == '1'
    assert evaluate("document.querySelectorAll('[data-national-history-id]').length") == 1
    assert evaluate("(()=>{const tabs=document.getElementById('assetCategoryTabs');return tabs.scrollWidth<=tabs.clientWidth+1;})()")
    assert evaluate("document.querySelector('.np-history').textContent.includes('미확인')")
    assert evaluate("document.querySelector('.np-history').textContent.includes('납부 없음 (0원)')")
    assert evaluate("document.querySelector('.np-history').textContent.includes('자동 변경 없음')")
    evaluate("document.querySelector('.np-history>summary').click();document.querySelector('[data-national-history-id]').click()")
    assert evaluate("document.getElementById('nationalPensionHistoryDialog').open")
    assert evaluate("document.querySelectorAll('.np-history-edit-row').length===__npInitial.length")
    evaluate("document.getElementById('addNationalPensionYear').click()")
    evaluate("(()=>{const row=document.querySelector('#nationalPensionYearlyList').lastElementChild;row.querySelector('[data-np-year]').value='2014';row.querySelector('[data-np-amount]').value='';document.querySelector('#nationalPensionHistoryForm [type=submit]').click();})()")
    assert evaluate("__npWrites.length") == 0
    assert '실제 납부액' in evaluate("document.getElementById('nationalPensionHistoryNotice').textContent")
    evaluate("document.querySelector('#nationalPensionYearlyList').lastElementChild.querySelector('[data-np-amount]').value='0'")
    evaluate("document.querySelector('[data-np-year]').value='2013';document.querySelector('[data-np-amount]').value='150000'")
    evaluate(FRAMES)
    assert evaluate("(()=>{const d=document.getElementById('nationalPensionHistoryDialog');return d.scrollWidth<=d.clientWidth+1;})()")
    assert evaluate("[...document.querySelectorAll('.np-history-edit-row')].every(e=>e.scrollWidth<=e.clientWidth+1)")
    evaluate("document.querySelector('#nationalPensionHistoryForm [type=submit]').click()")
    wait_for(evaluate, "__npWrites.length===1&&!document.getElementById('nationalPensionHistoryDialog').open")
    assert evaluate("__npWrites[0].expected_history.length===__npInitial.length")
    assert evaluate("__npData[0].total_paid_amount") == 8000000
    assert evaluate("__npData[0].expected_amount") == 24000000
    assert evaluate("__npData[0].maturity_date") == '2045-01-01'
    assert evaluate("JSON.stringify(__npData[1])===JSON.stringify(JSON.parse(__npBefore)[1])")
    evaluate("renderInsurance(__npData,'아빠');document.querySelector('.np-history>summary').click();document.querySelector('[data-national-history-id]').click()")
    assert evaluate("[...document.querySelectorAll('.np-history-edit-row')].some(row=>row.querySelector('[data-np-year]').value==='2014'&&row.querySelector('[data-np-amount]').value==='0')")
    evaluate("(()=>{const row=[...document.querySelectorAll('.np-history-edit-row')].find(row=>row.querySelector('[data-np-year]').value==='2014');row.querySelector('button').click();document.querySelector('#nationalPensionHistoryForm [type=submit]').click();})()")
    wait_for(evaluate, "__npWrites.length===2&&!document.getElementById('nationalPensionHistoryDialog').open")
    assert evaluate("!__npData[0].yearly_contributions.some(row=>row.year==='2014')")
    evaluate("renderInsuranceWithOwner('엄마')")
    assert evaluate("document.querySelector('[data-national-history-id]').dataset.nationalHistoryId") == 'synthetic-mom'
    no_overflow(evaluate, width)
