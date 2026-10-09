"""Native Chromium payment UI using the shared safe preview fixture."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_settings_surface_chrome import start, click, FRAMES, no_overflow


BOOT = r'''
window.__contributions={writes:[],banks:[{id:'bank',owner:'아빠',bank_name:'가상은행',account_name:'생활비',balance:1000000}],savings:['installment','free','housing','deposit'].map(kind=>({id:kind,saving_type:kind,owner:'아빠',bank_name:'가상은행',product_name:kind==='housing'?'주택청약종합저축':kind,monthly_amount:100000,target_amount:8000000,current_paid_amount:8000000,current_value:8000000,duration_months:12,interest_rate:3,start_date:'2020-01-04',end_date:kind==='housing'?'':'2027-10-04',auto_transfer_day:4,calc:{total_principal:1200000,pre_tax_interest:10000,maturity_total:1210000}}))};
const paymentFetch=window.fetch;
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname,method=options.method||'GET';
 const body=options.body?JSON.parse(options.body):{};
 const response=data=>({ok:true,status:200,json:async()=>structuredClone(data)});
 if(path==='/api/savings')return response({savings_accounts:__contributions.savings,bank_accounts:__contributions.banks});
 if(path==='/api/dashboard'){
  const base=await paymentFetch.apply(this,arguments);const data=await base.json();
  data.savings_accounts=structuredClone(__contributions.savings);data.bank_accounts=structuredClone(__contributions.banks);return response(data);
 }
 const match=path.match(/^\/api\/savings-accounts\/([^/]+)\/contributions(?:\/([^/]+))?$/);
 if(match){
  __contributions.writes.push({path,method,body});const saving=__contributions.savings.find(s=>s.id===match[1]);
  saving.contribution_opening_amount??=saving.current_paid_amount;saving.contributions??=[];
  if(method==='POST'&&!saving.contributions.some(r=>r.id===body.id))saving.contributions.push({...body,withdraw_account_name:body.withdraw_account_id?'생활비':'',created_at:'2026-10-10T00:00:00+09:00',updated_at:'2026-10-10T00:00:00+09:00'});
  if(method==='PUT')Object.assign(saving.contributions.find(r=>r.id===match[2]),body);
  if(method==='DELETE')saving.contributions=saving.contributions.filter(r=>r.id!==match[2]);
  saving.current_paid_amount=saving.contribution_opening_amount+saving.contributions.reduce((a,r)=>a+r.amount,0);saving.current_value=saving.current_paid_amount;
  return response({message:'synthetic saved'});
 }
 return paymentFetch.apply(this,arguments);
};
'''


def prepare(preview,width):
    call,evaluate=start(preview,width,BOOT)
    wait_for(evaluate,'!!window.WealthSavingsContributions&&rawSavingsAccounts.length===4')
    evaluate("currentOwner='모두';location.hash='assets';switchAccountCategory('banking');renderSavings(__contributions.savings,__contributions.banks,[],'모두')")
    evaluate(FRAMES)
    return call,evaluate


def fill(evaluate,name,value):
    evaluate(f"(()=>{{const e=document.querySelector('#savingContributionForm [name={json.dumps(name)}]');e.value={json.dumps(value)};e.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")


def fits(evaluate,width):
    no_overflow(evaluate,width)
    assert evaluate("(()=>{const d=document.getElementById('savingContributionsDialog');return d.scrollWidth<=d.clientWidth+1})()")
    assert evaluate("[...document.querySelectorAll('#savingContributionForm input,#savingContributionForm select,#savingContributionForm button')].filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect(),d=e.closest('dialog').getBoundingClientRect();return r.left>=d.left&&r.right<=d.right+1})")


@pytest.mark.parametrize('width',[1280,390])
def test_native_payment_crud_and_history_total_readonly(chrome_preview,width,tmp_path):
    call,evaluate=prepare(chrome_preview,width)
    for kind in ('installment','free','housing'):
        assert evaluate(f"!!document.querySelector('[data-saving-contributions-id={kind}]')")
    assert not evaluate("document.querySelector('[data-order-id=deposit] [data-saving-contributions-id]')!==null")
    click(call,evaluate,'[data-saving-contributions-id=installment]')
    wait_for(evaluate,"document.getElementById('savingContributionsDialog').open")
    assert '₩8,000,000' in evaluate("document.getElementById('savingContributionSummary').textContent")
    assert evaluate('__contributions.writes.length')==0
    fill(evaluate,'date','2026-10-04');fill(evaluate,'amount','100000');fill(evaluate,'withdraw_account_id','bank');fill(evaluate,'memo','실제 납입 메모')
    assert '10만' in evaluate("document.querySelector('#savingContributionForm label[for=savingContributionAmount]').textContent").replace(' ','')
    click(call,evaluate,'#savingContributionSave')
    wait_for(evaluate,"document.getElementById('savingContributionNotice').textContent.includes('저장되었습니다')")
    text=evaluate("document.getElementById('savingContributionHistory').textContent")
    for value in ('2026-10-04','₩100,000','생활비','수동','실제 납입 메모'): assert value in text
    assert '₩8,100,000' in evaluate("document.getElementById('savingContributionSummary').textContent")
    fits(evaluate,width)
    (tmp_path/f'contribution-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
    click(call,evaluate,'[data-contribution-edit]')
    fill(evaluate,'amount','150000')
    click(call,evaluate,'#savingContributionSave')
    wait_for(evaluate,"document.getElementById('savingContributionSummary').textContent.includes('₩8,150,000')")
    click(call,evaluate,'[data-contribution-delete]')
    wait_for(evaluate,"document.getElementById('savingContributionHistory').textContent.includes('아직 기록된')")
    assert evaluate('__contributions.savings[0].contribution_opening_amount')==8000000
    assert evaluate('__contributions.banks[0].balance')==1000000
    click(call,evaluate,'#savingContributionsClose')
    evaluate("openSavingAccountDialog(rawSavingsAccounts.find(s=>s.id==='installment'))")
    assert evaluate("document.getElementById('savingCurrentPaid').readOnly")
    evaluate("document.getElementById('savingAccountDialog').close();openSavingAccountDialog(rawSavingsAccounts.find(s=>s.id==='free'))")
    assert not evaluate("document.getElementById('savingCurrentPaid').readOnly")
    assert evaluate('__settingsProbe.errors')==[]


@pytest.mark.parametrize('width',[1280,390])
def test_native_housing_sort_snapshot_manual_auto_badges(chrome_preview,width):
    call,evaluate=prepare(chrome_preview,width)
    evaluate(r'''
const saving=__contributions.savings.find(s=>s.id==='housing');saving.contribution_opening_amount=8000000;
saving.contributions=[{id:'older',date:'2026-10-04',amount:100000,source:'manual',withdraw_account_id:'deleted',withdraw_account_name:'삭제된 통장 표시명',memo:'긴 한글 메모 '.repeat(20),created_at:'2026-10-04',updated_at:'2026-10-04'},{id:'newer',date:'2026-11-04',amount:200000,source:'auto',withdraw_account_id:'bank',withdraw_account_name:'생활비',memo:'synthetic future record only',created_at:'2026-11-04',updated_at:'2026-11-04'}];
saving.current_paid_amount=8300000;saving.current_value=8300000;
''')
    click(call,evaluate,'[data-saving-contributions-id=housing]')
    wait_for(evaluate,"document.getElementById('savingContributionsDialog').open")
    assert evaluate("[...document.querySelectorAll('[data-contribution-id]')].map(n=>n.dataset.contributionId)")==['newer','older']
    text=evaluate("document.getElementById('savingContributionHistory').textContent")
    for value in ('수동','자동','삭제된 통장 표시명'): assert value in text
    assert evaluate("document.querySelector('[data-contribution-id=newer]').querySelectorAll('button').length")==0
    assert '₩8,300,000' in evaluate("document.getElementById('savingContributionSummary').textContent")
    fits(evaluate,width)
    assert evaluate('__contributions.writes.length')==0
    assert evaluate('__settingsProbe.errors')==[]
