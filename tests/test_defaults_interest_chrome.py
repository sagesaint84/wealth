"""Native Chrome defaults, edit protection and bank interest controls, no real APIs."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_settings_surface_chrome import start, click, FRAMES, no_overflow


BOOT = r'''
window.__defaults={ledger:{'아빠':{income_account_id:'demo-bank',expense_payment_method:'credit_card',expense_card_id:'card-dad',expense_account_id:'demo-bank',transfer_account_id:'demo-bank'},'엄마':{income_account_id:'bank-mom',expense_payment_method:'bank_account',expense_account_id:'bank-mom'},'모두':{expense_payment_method:'cash'}},imports:{toss_wts_realized:'toss-a',toss_wts_income:'toss-a'},writes:[]};
const preferenceFetch=window.fetch;
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname,method=options.method||'GET';
 const body=options.body?JSON.parse(options.body):{};
 if(path==='/api/ledger/preferences'||path==='/api/ledger/preferences/transaction-defaults'){
  if(method==='PUT'){__defaults.writes.push({path,body});if(Object.keys(body.defaults).length)__defaults.ledger[body.owner]=body.defaults;else delete __defaults.ledger[body.owner];}
  return {ok:true,status:200,json:async()=>({transaction_defaults:structuredClone(__defaults.ledger)})};
 }
 if(path==='/api/import-destination-defaults'){
  if(method==='PUT'){__defaults.writes.push({path,body});if(body.account_id)__defaults.imports[body.workflow]=body.account_id;else delete __defaults.imports[body.workflow];}
  return {ok:true,status:200,json:async()=>({defaults:structuredClone(__defaults.imports)})};
 }
 return preferenceFetch.apply(this,arguments);
};
'''


def prepare(preview, width):
    call, evaluate = start(preview, width, BOOT)
    wait_for(evaluate, '!!rawDashboard&&!!window.WealthTransactionDefaults')
    evaluate(r'''
currentOwner='아빠';
rawDashboard.bank_accounts.push({id:'bank-mom',owner:'엄마',currency:'KRW',account_name:'급여',balance:2000000});
rawDashboard.accounts.push({id:'toss-a',broker:'토스증권',owner:'아빠',account_name:'투자'});
dashboard.accounts=rawDashboard.accounts;
rawLedgerData={categories:{income:['급여/상여','배당/금융수익'],expense:['식비/외식'],transfer:['계좌이체/저축']},cards:[{id:'card-dad',owner:'아빠',card_company:'가상카드',card_name:'생활카드',payment_day:14}],transactions:[{id:'edit',type:'income',owner:'아빠',category:'배당/금융수익',amount:10000,account_id:'',merchant:'기존 거래',memo:'저장된 내용'}]};
''')
    return call, evaluate


def change(evaluate, name, value):
    evaluate(f"(()=>{{const e=document.querySelector('#ledgerTxForm [name={json.dumps(name)}]');e.value={json.dumps(value)};e.dispatchEvent(new Event('change',{{bubbles:true}}));}})()")


def value(evaluate, name):
    return evaluate(f"document.querySelector('#ledgerTxForm [name={json.dumps(name)}]').value")


@pytest.mark.parametrize('width', [1280,390])
def test_ledger_defaults_new_edit_owner_stale_clear_and_interest_eligibility(chrome_preview, width, tmp_path):
    call, evaluate = prepare(chrome_preview, width)
    evaluate('openLedgerTxModal()')
    wait_for(evaluate,"document.getElementById('ledgerTxDialog').open")
    assert value(evaluate,'card_id') == 'card-dad'
    assert value(evaluate,'pay_method_type') == 'credit_card'
    change(evaluate,'type','income')
    assert value(evaluate,'account_id') == 'demo-bank'
    change(evaluate,'category','배당/금융수익')
    assert evaluate("!document.getElementById('ledgerInterestLinkBox').hidden&&!document.getElementById('ledgerInterestLink').disabled")
    change(evaluate,'account_id','demo-stock-a')
    assert evaluate("document.getElementById('ledgerInterestLink').disabled")
    change(evaluate,'account_id','demo-bank')
    click(call,evaluate,'#ledgerInterestLink')
    assert evaluate("document.getElementById('ledgerInterestLink').checked")
    no_overflow(evaluate,width)
    assert evaluate("(()=>{const d=document.getElementById('ledgerTxDialog');return d.scrollWidth<=d.clientWidth+1})()")
    (tmp_path/f'ledger-interest-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
    change(evaluate,'type','expense')
    assert evaluate("document.getElementById('ledgerInterestLinkBox').hidden&&!document.getElementById('ledgerInterestLink').checked")
    change(evaluate,'owner','엄마')
    assert value(evaluate,'pay_method_type') == 'bank_account' and value(evaluate,'account_id') == 'bank-mom'
    change(evaluate,'type','income')
    change(evaluate,'account_id','')
    change(evaluate,'category','배당/금융수익')
    assert value(evaluate,'account_id') == ''  # unrelated category edit must not reapply a default
    change(evaluate,'owner','아빠')
    assert value(evaluate,'account_id') == 'demo-bank'
    change(evaluate,'type','transfer')
    assert value(evaluate,'account_id') == 'demo-bank'
    assert evaluate('__defaults.writes.length') == 0
    no_overflow(evaluate,width)
    (tmp_path/f'ledger-defaults-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot',{'format':'png'})['data']))
    click(call,evaluate,'#ledgerDefaultClear')
    wait_for(evaluate,"document.getElementById('ledgerDefaultNotice').textContent.includes('해제')")
    assert evaluate("!__defaults.ledger['아빠'].transfer_account_id")
    click(call,evaluate,'#ledgerDefaultSave')
    wait_for(evaluate,"document.getElementById('ledgerDefaultNotice').textContent.includes('지정')")
    assert evaluate("__defaults.ledger['아빠'].transfer_account_id") == 'demo-bank'
    evaluate("document.getElementById('ledgerTxDialog').close();openLedgerTxModal('edit')")
    wait_for(evaluate,"document.getElementById('ledgerTxDialog').open")
    assert value(evaluate,'account_id') == '' and value(evaluate,'amount') == '10000'
    evaluate("document.getElementById('ledgerTxDialog').close();__defaults.ledger['아빠'].expense_card_id='deleted';openLedgerTxModal()")
    wait_for(evaluate,"document.getElementById('ledgerTxDialog').open")
    assert value(evaluate,'card_id') == ''
    assert '사용할 수 없습니다' in evaluate("document.getElementById('ledgerDefaultNotice').textContent")
    evaluate("document.getElementById('ledgerTxDialog').close();__defaults.ledger['아빠'].income_account_id='deleted';openLedgerTxModal()")
    wait_for(evaluate,"document.getElementById('ledgerTxDialog').open")
    change(evaluate,'type','income')
    change(evaluate,'owner','엄마'); change(evaluate,'owner','아빠')
    assert value(evaluate,'account_id') == ''
    assert evaluate('__settingsProbe.errors') == []


@pytest.mark.parametrize('workflow,selector,populate', [
    ('toss_wts_realized','wtsDestinationAccount','populateWtsAccounts'),
    ('toss_wts_income','wtsIncomeDestinationAccount','populateTossWtsIncomeAccounts')])
@pytest.mark.parametrize('width',[1280,390])
def test_import_default_restore_clear_stale_and_manual_preserved(chrome_preview,width,workflow,selector,populate):
    call,evaluate = prepare(chrome_preview,width)
    evaluate(f'{populate}()')
    wait_for(evaluate,f"document.getElementById('{selector}').value==='toss-a'")
    assert evaluate(f"document.getElementById('{selector}DefaultNotice').textContent") == '기본 목적 계좌'
    # Explicit clear action only, then opening a new selector with one candidate stays unselected.
    evaluate(f"document.getElementById('{selector}Clear').click()")
    wait_for(evaluate,f"!__defaults.imports.{workflow}")
    evaluate(f"document.getElementById('{selector}').value='';{populate}()")
    evaluate(FRAMES)
    assert evaluate(f"document.getElementById('{selector}').value") == ''
    evaluate(f"document.getElementById('{selector}').value='toss-a';document.getElementById('{selector}Remember').click()")
    wait_for(evaluate,f"__defaults.imports.{workflow}==='toss-a'")
    evaluate(f"document.getElementById('{selector}').value='';{populate}()")
    wait_for(evaluate,f"document.getElementById('{selector}').value==='toss-a'")
    evaluate(f"__defaults.imports.{workflow}='deleted';document.getElementById('{selector}').value='';{populate}()")
    wait_for(evaluate,f"document.getElementById('{selector}DefaultNotice').textContent.includes('사용할 수 없습니다')")
    assert evaluate(f"document.getElementById('{selector}').value") == ''
    evaluate(f"document.getElementById('{selector}').value='toss-a';{populate}()")
    evaluate(FRAMES)
    assert evaluate(f"document.getElementById('{selector}').value") == 'toss-a'
    evaluate(f"currentOwner='엄마';document.getElementById('{selector}').value='';__defaults.imports.{workflow}='toss-a';{populate}()")
    evaluate(FRAMES)
    assert evaluate(f"document.getElementById('{selector}').value") == ''


@pytest.mark.parametrize('provider,state,selector,populate', [
    ('kis','kisRealizedState','kisDestinationAccount','populateKisDestinationAccounts'),
    ('nh','nhRealizedState','nhDestinationAccount','populateNhDestinationAccounts'),
    ('kb','kbRealizedState','kbDestinationAccount','populateKbDestinationAccounts'),
    ('kiwoom','kiwoomRealizedState','kiwoomDestinationAccount','populateKiwoomDestinationAccounts')])
def test_provider_mapping_selects_authoritative_account_without_workflow_remap(chrome_preview,provider,state,selector,populate):
    call,evaluate = prepare(chrome_preview,1280)
    evaluate(f"dashboard.accounts.push({{id:'saved',broker:'{provider}',owner:'아빠',account_name:'저장된 목적지'}});{state}.sourceAccountKey='source';{state}.mappedDestAccountId='saved';{state}.accounts=[{{source_account_key:'source',candidate_account_ids:['saved']}}];document.getElementById('{selector}').value='';{populate}()")
    assert evaluate(f"document.getElementById('{selector}').value") == 'saved'


@pytest.mark.parametrize('width',[1280,390])
def test_ledger_interest_badge_account_amount_owner_and_no_direct_controls(chrome_preview,width):
    call,evaluate = prepare(chrome_preview,width)
    evaluate("currentOwner='모두';actualDividendData={year:'all',records:[],interest_records:[{id:'mirror',source:'ledger_interest',income_type:'account_interest',name:'생활비 이자',account_name:'생활비',owner:'아빠',date:'2026-10-10',currency:'KRW',amount:10000,amount_krw:10000}]};renderActualDividendDetail()")
    text = evaluate("document.getElementById('dividendMonthlyDetail').textContent")
    for expected in ('가계부 연동','가계부에서 수정','생활비','아빠','2026-10-10','10,000'):
        assert expected in text
    assert evaluate("document.querySelectorAll('#dividendMonthlyDetail .edit-actual-div-btn,#dividendMonthlyDetail .delete-actual-div-btn').length") == 0
