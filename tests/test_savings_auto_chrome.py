"""Scheduled savings opt-in UI; shared native Chrome harness, synthetic API."""
import base64
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_savings_contributions_chrome import prepare
from tests.test_settings_surface_chrome import click, FRAMES, no_overflow


def field(evaluate, name, value):
    evaluate(f"(()=>{{const e=document.querySelector('#savingAccountForm [name={json.dumps(name)}]');e.value={json.dumps(value)};e.dispatchEvent(new Event('input',{{bubbles:true}}));}})()")


def fits(evaluate, width):
    evaluate(FRAMES)
    no_overflow(evaluate, width)
    assert evaluate("(()=>{const d=document.getElementById('savingAccountDialog'),r=d.getBoundingClientRect();return d.scrollWidth<=d.clientWidth+1&&r.left>=0&&r.right<=innerWidth+1})()")
    assert evaluate("[...document.querySelectorAll('#savingAutoContributionSettings input,#savingAutoContributionSettings span')].filter(e=>e.getClientRects().length).every(e=>{const r=e.getBoundingClientRect(),d=e.closest('dialog').getBoundingClientRect();return r.left>=d.left&&r.right<=d.right+1})")


@pytest.mark.parametrize('width', [1280, 390])
def test_native_optin_validation_explicit_debit_modes_and_restoration(chrome_preview, width, tmp_path):
    call, evaluate = prepare(chrome_preview, width)
    evaluate(r'''
window.__autoWrites=[];
const autoFetch=window.fetch;
window.fetch=async function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(path==='/api/savings-accounts'&&options.method==='POST'){
  const payload=JSON.parse(options.body);__autoWrites.push(payload);
  const record=__contributions.savings.find(s=>s.id===payload.id);Object.assign(record,payload);
  record.auto_contribution_enabled_at=payload.auto_contribution_enabled?'2026-10-10T00:10:00+09:00':undefined;
  return {ok:true,status:200,json:async()=>({message:'synthetic saved'})};
 }
 return autoFetch.apply(this,arguments);
};
openSavingAccountDialog(rawSavingsAccounts.find(s=>s.id==='housing'));
''')
    assert not evaluate("document.getElementById('savingAutoContributionEnabled').checked")
    assert evaluate("document.getElementById('savingAutoDebitBalance').checked")
    click(call, evaluate, '#savingAutoContributionEnabled')
    assert evaluate("document.getElementById('savingAutoDebitBalance').checked")
    assert evaluate("document.getElementById('savingWithdrawAccountSelect').required")
    field(evaluate, 'auto_transfer_day', '0')
    assert not evaluate("document.getElementById('savingAccountForm').checkValidity()")
    field(evaluate, 'auto_transfer_day', '15')
    field(evaluate, 'monthly_amount', '0')
    assert not evaluate("document.getElementById('savingAccountForm').checkValidity()")
    field(evaluate, 'monthly_amount', '100000')
    field(evaluate, 'withdraw_account_id', '')
    assert not evaluate("document.getElementById('savingAccountForm').checkValidity()")
    click(call, evaluate, '#savingAutoDebitBalance')
    assert not evaluate("document.getElementById('savingAutoDebitWarning').hidden")
    assert '총자산' in evaluate("document.getElementById('savingAutoDebitWarning').textContent")
    assert not evaluate("document.getElementById('savingAccountForm').checkValidity()")
    field(evaluate, 'withdraw_account_id', 'bank')
    assert evaluate("document.getElementById('savingAccountForm').checkValidity()")
    fits(evaluate, width)
    (tmp_path/f'savings-auto-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
    click(call, evaluate, '#savingAccountForm button[type=submit]')
    wait_for(evaluate, '__autoWrites.length===1&&!document.getElementById("savingAccountDialog").open')
    assert evaluate('__autoWrites[0].auto_contribution_enabled') is True
    assert evaluate('__autoWrites[0].auto_contribution_debit_balance') is False
    assert evaluate("'auto_contribution_enabled_at' in __autoWrites[0]") is False
    evaluate("openSavingAccountDialog(rawSavingsAccounts.find(s=>s.id==='housing'))")
    assert evaluate("document.getElementById('savingAutoContributionEnabled').checked")
    assert not evaluate("document.getElementById('savingAutoDebitBalance').checked")
    click(call, evaluate, '#savingAutoContributionEnabled')
    assert not evaluate("document.getElementById('savingWithdrawAccountSelect').required")
    click(call, evaluate, '#savingAccountForm button[type=submit]')
    wait_for(evaluate, '__autoWrites.length===2')
    assert not evaluate('__autoWrites[1].auto_contribution_enabled')
    assert evaluate('__contributions.banks[0].balance') == 1000000
    assert evaluate('__settingsProbe.errors') == []


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('kind', ['installment', 'free', 'housing', 'deposit'])
def test_native_types_legacy_disabled_and_default_debit(chrome_preview, width, kind):
    call, evaluate = prepare(chrome_preview, width)
    evaluate(f"openSavingAccountDialog(rawSavingsAccounts.find(s=>s.id==={json.dumps(kind)}))")
    eligible = kind != 'deposit'
    assert evaluate("document.getElementById('savingAutoContributionSettings').hidden") is not eligible
    assert evaluate("document.getElementById('savingAutoContributionEnabled').disabled") is not eligible
    assert not evaluate("document.getElementById('savingAutoContributionEnabled').checked")
    if eligible:
        click(call, evaluate, '#savingAutoContributionEnabled')
        assert evaluate("document.getElementById('savingAutoDebitBalance').checked")
        assert evaluate("document.getElementById('savingAutoDebitWarning').hidden")
    fits(evaluate, width)
    assert evaluate('__contributions.writes.length') == 0
    assert evaluate('__contributions.banks[0].balance') == 1000000
    assert evaluate('__settingsProbe.errors') == []
