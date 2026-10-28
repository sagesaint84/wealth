"""v2.1.9 layout and owner totals using loopback-only invented inputs."""
import datetime

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_market_signals_holdings_chrome import start


@pytest.mark.parametrize('width', [320, 360, 390, 768, 1280])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_market_settings_and_bank_four_cards(chrome_preview, width, theme):
    call, evaluate, _ = chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source': f"localStorage.setItem('app_theme',{theme!r});"})
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {'markets': [{'label': '합성 지수', 'price': 123, 'change': 1, 'change_rate': 1,
                            'series': [120, 121, 123]}],
               'fear_greed': {'status': 'ok', 'score': 33.6, 'rating': 'Fear',
                             'observed_date': now.date().isoformat(), 'relay_updated_at': now.isoformat(),
                             'valid_until': (now + datetime.timedelta(hours=1)).isoformat()}}
    call, evaluate = start(chrome_preview, width, payload, route='home')
    evaluate('document.querySelector("#homeTabs [data-home-tab=markets]").click()')
    wait_for(evaluate,'location.hash==="#home/markets" && document.querySelector("#homeTabs [data-home-tab=markets]").getAttribute("aria-selected")==="true"')
    wait_for(evaluate, '!!document.querySelector("#marketFearGreed [data-cnn-score]")')
    assert evaluate('document.querySelector("#marketFearGreed .market-title").textContent') == '공포탐욕지수'
    assert evaluate('document.querySelector("#marketFearGreed [data-cnn-score]").textContent') == '33.6 (공포)'
    evaluate('document.getElementById("marketCardSettings").click()')
    assert evaluate('document.getElementById("marketCardDialog").open')
    assert evaluate('document.querySelector("#marketCardDialog input[value=cnn-fng]").parentElement.textContent') == '공포탐욕지수'
    assert evaluate('''(() => {
      const d=document.getElementById('marketCardDialog'), box=d.getBoundingClientRect();
      return box.left>=0 && box.right<=innerWidth && [...d.querySelectorAll('label')].every(n=>{
        const c=n.querySelector('input').getBoundingClientRect(),t=n.querySelector('span').getBoundingClientRect();
        return c.width>=18 && c.width<=20 && c.right<t.left && n.scrollWidth<=n.clientWidth+1;
      });
    })()''')
    evaluate('document.querySelector("#marketCardDialog input[value=cnn-fng]").checked=false;document.querySelector("#marketCardDialog form").requestSubmit()')
    assert not evaluate('!!document.getElementById("marketFearGreed")')
    evaluate('document.getElementById("marketCardSettings").click()')
    assert not evaluate('document.querySelector("#marketCardDialog input[value=cnn-fng]").checked')
    evaluate('document.querySelector("#marketCardDialog input").focus()')
    call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
    wait_for(evaluate, '!document.getElementById("marketCardDialog").open')

    evaluate('location.hash="#assets";switchAccountCategory("banking")')
    wait_for(evaluate, 'document.querySelector(".wealth-workspace").dataset.activeView==="assets" && !!window.WealthAccountSectionSummary')
    evaluate('''window.__bankData={
      bank_accounts:[{id:'cash-a',owner:'아빠',bank_name:'합성은행',balance:300000},
        {id:'minus-a',owner:'아빠',bank_name:'합성은행',balance:-100000,limit_amount:200000,interest_rate:12},
        {id:'cash-b',owner:'엄마',bank_name:'가상은행',balance:700000},
        {id:'minus-b',owner:'엄마',bank_name:'가상은행',balance:-50000,limit_amount:100000,interest_rate:12}],
      savings_accounts:[{id:'saving-a',owner:'아빠',bank_name:'합성은행',current_paid_amount:200000,calc:{maturity_total:220000}}],
      loan_accounts:[{id:'loan-a',owner:'아빠',loan_type:'minus',overdraft_bank_account_id:'minus-a',current_balance:100000,monthly_interest:1000},
        {id:'loan-b',owner:'엄마',loan_type:'personal',current_balance:400000,monthly_interest:4000}]};
      Object.assign(rawDashboard,__bankData);
    ''')
    for owner, cash, debt, interest, paid in [('모두', '1,000,000', '550,000', '5,500', '200,000'),
                                            ('아빠', '300,000', '100,000', '1,000', '200,000'),
                                            ('엄마', '700,000', '450,000', '4,500', '0')]:
        evaluate(f'''currentOwner={owner!r};document.querySelectorAll('.family-tab').forEach(n=>n.classList.toggle('active',n.dataset.owner===currentOwner));
          renderSavings(__bankData.savings_accounts,__bankData.bank_accounts,__bankData.loan_accounts,currentOwner);
          WealthAccountSectionSummary.renderBankSummary(rawDashboard,currentOwner);''')
        assert evaluate('document.getElementById("totalBankBalanceVal").textContent') == '₩' + cash
        assert evaluate('document.getElementById("totalLoanBalanceVal").textContent') == '₩' + debt
        assert '₩' + interest in evaluate('document.getElementById("totalLoanInterestSub").textContent')
        assert evaluate('document.getElementById("totalSavingsPaidVal").textContent') == '₩' + paid
        assert evaluate('document.getElementById("totalSavingsMaturityVal").textContent') == ('₩0' if owner == '엄마' else '₩220,000')
        assert evaluate('document.querySelectorAll("#catPanelBanking .saving-stat-card").length') == 4
        assert not evaluate('!!document.getElementById("bankAccountSectionSummary")')
        assert not evaluate('document.getElementById("catPanelBanking").textContent.includes("소유자별 계좌")')
        assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert evaluate('getComputedStyle(document.getElementById("savingsSummaryCards")).gridTemplateColumns.split(" ").length') == (4 if width == 1280 else 2 if width == 768 else 1)
    evaluate('document.querySelector(".family-tab[data-owner=아빠]").click()')
    wait_for(evaluate,'document.getElementById("totalBankBalanceVal").textContent==="₩300,000"')
    assert evaluate('document.getElementById("totalLoanBalanceVal").textContent')=='₩100,000'
    wait_for(evaluate,'document.getElementById("bankAccountSummarySub").textContent.includes("전체 은행계좌 3개") && document.getElementById("savingsAccountSummarySub").textContent==="예·적금 1개" && document.getElementById("loanAccountSummarySub").textContent==="대출·한도약정 1건"')
    assert evaluate('document.getElementById("allBankCount").textContent')=='3'
    evaluate('__bankData.bank_accounts[0].balance=12345678901234;renderSavingsWithOwner("아빠")')
    assert evaluate('document.getElementById("totalBankBalanceVal").textContent')=='₩12,345,678,901,234'
    assert evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert evaluate("(()=>{const cards=[...document.querySelectorAll('#savingsSummaryCards .saving-stat-card')].map(n=>n.getBoundingClientRect());return cards.every((a,i)=>cards.every((b,j)=>i===j||a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top));})()")
    assert evaluate('!!document.getElementById("securitiesAccountSectionSummary")')
    assert evaluate('__signalsFixture.writes.filter(r=>r.phase!=="startup").length') == 0
    assert not [e for e in evaluate.load_errors if e.get('method') == 'Runtime.exceptionThrown']
