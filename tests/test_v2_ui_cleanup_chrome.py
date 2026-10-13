"""Synthetic UI-only geometry/meaning checks; reuses the native Chrome harness."""
import json

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_defaults_interest_chrome import prepare
from tests.test_workflow_ux_chrome import FRAMES, no_overflow


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_tax_cards_keep_titles_and_selection_on_one_line(chrome_preview, width, theme):
    call, evaluate = prepare(chrome_preview, width)
    evaluate(f"document.documentElement.dataset.theme={json.dumps(theme)}")
    evaluate(r'''(()=>{
      currentOwner='모두';
      const types=['isa','irp','pension_savings'];
      const accounts=types.map((type,i)=>({id:'v2-'+type,name:i===0?'매우 긴 한글 절세계좌 이름을 가진 중개형 ISA 계좌':type,
        broker:'합성',owner:'모두',account_type:type,cash_krw:1000,cash_usd:0}));
      dashboard.accounts.push(...accounts);
      rawDashboard.holdings=types.map((type,i)=>({id:'v2-h'+i,account_id:'v2-'+type,name:'합성 종목 '+i,
        code:'V2'+i,currency:'KRW',quantity:1,current_price:1100,avg_price:1000,
        market_value_krw:1100,cost_value_krw:1000,profit_krw:100,owner:'모두'}));
      dashboard.holdings=rawDashboard.holdings;
      location.hash='invest';window.dispatchEvent(new Event('hashchange'));
      document.querySelector('[data-invest=tax_accounts]').click();
      currentTaxAccountFilter='all';renderTaxAccountHoldings('모두');
    })()''')
    wait_for(evaluate, "document.querySelectorAll('.tax-card-head').length>=7")
    for selected in ('all', 'isa', 'irp', 'pension_savings', 'acc_v2-isa'):
        evaluate(f"currentTaxAccountFilter={json.dumps(selected)};renderTaxAccountHoldings('모두')")
        evaluate(FRAMES)
        state = evaluate(r'''[...document.querySelectorAll('.tax-card')].map(card=>{
          const title=card.querySelector('.tax-card-title'),badge=card.querySelector('.tax-card-selected');
          const t=title.getBoundingClientRect(),r=card.getBoundingClientRect();
          return {filter:card.dataset.taxFilter,titleText:title.textContent,
            font:parseFloat(getComputedStyle(title).fontSize),height:t.height,
            titleRight:t.right,cardRight:r.right,scroll:card.scrollWidth,client:card.clientWidth,
            badge:badge&&{text:badge.textContent,whiteSpace:getComputedStyle(badge).whiteSpace,
              left:badge.getBoundingClientRect().left,right:badge.getBoundingClientRect().right}};
        })''')
        assert state
        assert len([row for row in state if row['badge']]) == 1
        for row in state:
            assert row['height'] < row['font'] * 2
            assert row['scroll'] <= row['client'] + 1
            assert row['titleRight'] <= row['cardRight'] + 1
            if row['badge']:
                assert row['filter'] == selected
                assert row['badge']['text'] == '선택'
                assert row['badge']['whiteSpace'] == 'nowrap'
                assert row['titleRight'] <= row['badge']['left'] + 1
                assert row['badge']['right'] <= row['cardRight'] + 1
        no_overflow(evaluate, width)


@pytest.mark.parametrize('width', [1280, 390])
def test_import_default_controls_keep_explicit_save_clear_and_no_overflow(chrome_preview, width):
    call, evaluate = prepare(chrome_preview, width)
    for workflow, selector, populate, route in (
        ('toss_wts_realized', 'wtsDestinationAccount', 'populateWtsAccounts', 'pnl'),
        ('toss_wts_income', 'wtsIncomeDestinationAccount', 'populateTossWtsIncomeAccounts', 'dividend'),
    ):
        evaluate(f"location.hash={json.dumps(route)};window.dispatchEvent(new Event('hashchange'));{populate}()")
        wait_for(evaluate, f"document.getElementById('{selector}').value==='toss-a'")
        assert evaluate(f"document.querySelector('label[for={selector}]').textContent") == '귀속 Wealth 계좌'
        assert evaluate(f"document.getElementById('{selector}Remember').textContent") == '기본계좌로 지정'
        assert evaluate(f"document.getElementById('{selector}Clear').textContent") == '해제'
        evaluate(f"document.getElementById('{selector}Clear').click()")
        wait_for(evaluate, f"!__defaults.imports.{workflow}")
        assert evaluate(f"document.getElementById('{selector}DefaultNotice').textContent") == '기본계좌 해제됨'
        evaluate(f"document.getElementById('{selector}Remember').click()")
        wait_for(evaluate, f"__defaults.imports.{workflow}==='toss-a'")
        assert evaluate(f"document.getElementById('{selector}DefaultNotice').textContent") == '기본계좌 지정됨'
        evaluate(FRAMES)
        assert evaluate(f"(()=>{{const e=document.getElementById('{selector}').parentElement;return e.scrollWidth<=e.clientWidth+1;}})()")
        no_overflow(evaluate, width)


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_asset_weights_and_return_rates_have_separate_meanings(chrome_preview, width, theme):
    call, evaluate = prepare(chrome_preview, width)
    evaluate(f"document.documentElement.dataset.theme={json.dumps(theme)};location.hash='home';window.dispatchEvent(new Event('hashchange'))")
    rows = [dict(name=name, market_value_krw=1000, cost_value_krw=800,
                 profit_krw=200, return_rate=25, weight=20, holding_count=1)
            for name in ['국내주식', '부동산', '현금·예수금', '보험', '임차보증금']]
    summary = dict(owner='모두', classifications=rows, netWorth=4321, invest=1234,
                   stock=1000, property=1000, propertyExpected=200, propertyExpectedRate=25,
                   propertyPurchaseValue=800, expected=7, realized=8, safe=9)
    evaluate(f"window.__v2Summary={json.dumps(summary)};window.__v2Before=JSON.stringify(__v2Summary);window.dispatchEvent(new CustomEvent('wealth:summary',{{detail:__v2Summary}}))")
    evaluate(FRAMES)
    actual = evaluate("[...document.querySelectorAll('#wealthMixLegend>div')].map(row=>({name:row.querySelector('span').textContent,weight:row.querySelector('small').textContent,metric:row.querySelector('[data-metric=return-rate]').textContent,label:row.querySelector('[data-metric=return-rate]').getAttribute('aria-label')}))")
    assert len(actual) == 5
    descriptions = {item['name']: item['weight'] for item in actual}
    assert '부동산 평가액' in descriptions['부동산']
    assert '순자산' not in descriptions['부동산']
    assert '은행 예수금 포함' in descriptions['현금·예수금']
    assert '예적금 포함' in descriptions['현금·예수금']
    assert '예상 수령액/해약환급금' in descriptions['보험']
    for item in actual:
        assert '20.0%' in item['weight']
        assert '비중' in item['weight']
        expected = '+25.00%' if item['name'] in ('국내주식', '부동산') else '—'
        assert item['metric'] == expected
        assert item['label'].startswith('수익률')
    assert evaluate("JSON.stringify(__v2Summary)===__v2Before")
    assert evaluate("document.getElementById('homeAssetAllocationTotal').textContent") == '5,000원'
    assert evaluate("document.getElementById('wealthAssetNetWorth').textContent") == '4,321원'
    evaluate("__v2Summary.propertyPurchaseValue=0;window.dispatchEvent(new CustomEvent('wealth:summary',{detail:__v2Summary}))")
    assert evaluate("[...document.querySelectorAll('#wealthMixLegend>div')].find(row=>row.querySelector('span').textContent==='부동산').querySelector('[data-metric=return-rate]').textContent") == '—'
    no_overflow(evaluate, width)
