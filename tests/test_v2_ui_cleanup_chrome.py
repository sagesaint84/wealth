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


@pytest.mark.parametrize('width', [1280, 390, 320])
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
        geometry = evaluate(f'''(()=>{{
          const select=document.getElementById('{selector}'),control=select.parentElement;
          const head=control.querySelector('.toss-wts-account-head');
          const label=head.querySelector('label'),buttons=[...head.querySelectorAll('button')];
          const r=control.getBoundingClientRect(),h=head.getBoundingClientRect(),s=select.getBoundingClientRect();
          return {{inside:buttons.every(b=>{{const x=b.getBoundingClientRect();return x.left>=r.left-1&&x.right<=r.right+1&&x.top>=h.top-1&&x.bottom<=h.bottom+1;}}),
            buttonsApart:buttons[0].getBoundingClientRect().right<=buttons[1].getBoundingClientRect().left+1,
            singleHeader:buttons.every(b=>{{const x=b.getBoundingClientRect();return Math.abs(x.top+x.height/2-(h.top+h.height/2))<=1;}}),
            noClipping:[head,...buttons].every(e=>e.scrollWidth<=e.clientWidth+1),
            labelInside:label.getBoundingClientRect().right<=buttons[0].getBoundingClientRect().left+1,
            secondRow:s.top>=h.bottom-1,fullWidth:Math.abs(s.width-r.width)<=1,
            twoRows:Math.abs(s.bottom-r.bottom)<=1,
            described:select.getAttribute('aria-describedby'),
            status:document.getElementById('{selector}DefaultNotice').getAttribute('role')}};
        }})()''')
        assert geometry['inside'] and geometry['labelInside']
        assert geometry['buttonsApart'] and geometry['singleHeader'] and geometry['noClipping']
        assert geometry['secondRow'] and geometry['fullWidth'] and geometry['twoRows']
        assert geometry['described'] == selector + 'DefaultNotice'
        assert geometry['status'] == 'status'
        evaluate(f"document.getElementById('{selector}').value='';document.getElementById('{selector}Remember').click()")
        assert evaluate(f"document.getElementById('{selector}DefaultNotice').textContent") == '계좌를 먼저 선택해 주세요.'
        assert evaluate(f"__defaults.imports.{workflow}") == 'toss-a'
        evaluate(f"document.getElementById('{selector}').value='toss-a'")
        evaluate(r'''window.__v201Fetch=window.fetch;window.fetch=(url,opts)=>
          String(url).includes('/api/import-destination-defaults')&&opts?.method==='PUT'
          ? Promise.resolve(new Response(JSON.stringify({detail:'합성 저장 실패'}),{status:400,headers:{'Content-Type':'application/json'}}))
          : __v201Fetch(url,opts);''')
        evaluate(f"document.getElementById('{selector}Remember').click()")
        wait_for(evaluate, f"document.getElementById('{selector}DefaultNotice').textContent.includes('합성 저장 실패')")
        assert evaluate(f"document.querySelector('label[for={selector}]').title.includes('합성 저장 실패')")
        assert evaluate(f"__defaults.imports.{workflow}") == 'toss-a'
        evaluate("window.fetch=__v201Fetch")
        evaluate(f"__defaults.imports.{workflow}='deleted-account';document.getElementById('{selector}').value='';{populate}()")
        wait_for(evaluate, f"document.getElementById('{selector}DefaultNotice').textContent.includes('저장된 기본값을 사용할 수 없습니다')")
        assert evaluate(f"document.getElementById('{selector}').value") == ''
        status_geometry = evaluate(f'''(()=>{{
          const select=document.getElementById('{selector}'),control=select.parentElement;
          const label=control.querySelector('label'),status=document.getElementById('{selector}DefaultNotice');
          const before=control.getBoundingClientRect().height;
          label.focus();
          const r=control.getBoundingClientRect(),s=status.getBoundingClientRect();
          return {{live:status.getAttribute('aria-live'),position:getComputedStyle(status).position,
            visible:getComputedStyle(status).clipPath==='none'&&s.height>1,
            inside:s.left>=r.left-1&&s.right<=r.right+1,
            noExtraRow:Math.abs(r.height-before)<=1,
            focus:document.activeElement===label}};
        }})()''')
        assert status_geometry['live'] == 'polite'
        assert status_geometry['position'] == 'absolute'
        assert status_geometry['visible'] and status_geometry['inside']
        assert status_geometry['noExtraRow'] and status_geometry['focus']
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


@pytest.mark.parametrize('width', [1280, 390, 320])
@pytest.mark.parametrize('theme', ['purple', 'white', 'oled'])
def test_insurance_expected_simple_return_preserves_home_amounts(chrome_preview, width, theme):
    call, evaluate = prepare(chrome_preview, width)
    evaluate(f"document.documentElement.dataset.theme={json.dumps(theme)};location.hash='home';window.dispatchEvent(new Event('hashchange'))")
    baseline = dict(owner='아빠', netWorth=777, safe=888, insurance=120,
                    classifications=[dict(name='보험', market_value_krw=120,
                      cost_value_krw=120, profit_krw=0, return_rate=0, holding_count=1, weight=100)])
    evaluate(f"window.__roiSummary={json.dumps(baseline)};window.__roiOriginal=JSON.stringify(__roiSummary)")
    base = dict(owner='아빠', payout_type='lump_sum', total_paid_amount=100, expected_amount=120, converted_total_asset=120)
    cases = [
        ([base], '+20.00%', 'up'),
        ([dict(base, expected_amount=80, converted_total_asset=80)], '-20.00%', 'down'),
        ([dict(base, expected_amount=100, converted_total_asset=100)], '0.00%', 'up'),
        ([dict(base, total_paid_amount=0)], '—', 'muted'),
        ([dict(base, expected_amount=None)], '—', 'muted'),
        ([base, dict(base, total_paid_amount=0)], '+20.00%', 'up'),
        ([base, dict(base, insurance_type='national_pension', payout_type='monthly_pension')], '+20.00%', 'up'),
        ([base, dict(base, owner='엄마', total_paid_amount=0)], '+20.00%', 'up'),
        ([dict(base, payout_type='monthly_pension', monthly_payout=1, payout_duration_years=20,
               expected_amount=240, converted_total_asset=240)], '—', 'muted'),
    ]
    for accounts, expected, color in cases:
        evaluate(f"window.__roiAccounts={json.dumps(accounts)};__roiSummary.insuranceReturn=WealthInsuranceReturnDisplay(__roiAccounts,'아빠');window.dispatchEvent(new CustomEvent('wealth:summary',{{detail:__roiSummary}}))")
        evaluate(FRAMES)
        actual = evaluate("(()=>{const e=document.querySelector('#wealthMixLegend [data-metric=return-rate]');return {text:e.textContent,title:e.title,label:e.getAttribute('aria-label'),color:e.className};})()")
        assert actual['text'] == expected
        assert actual['color'] == color
        assert '예상 단순수익률' in actual['title'] and '예상 단순수익률' in actual['label']
        assert '향후 추가 납입' in actual['title']
        scope = evaluate("document.querySelector('[data-insurance-roi-scope]').textContent")
        assert '개 상품 산정' in scope
        if len(accounts) == 2 and accounts[1]['owner'] == '아빠':
            assert scope == '일부 상품 기준 · 1/2개 상품 산정'
        assert evaluate("document.querySelector('[data-insurance-roi-scope]').getBoundingClientRect().height>0")
        assert evaluate("document.getElementById('homeAssetAllocationTotal').textContent") == '120원'
        assert evaluate("document.getElementById('wealthAssetNetWorth').textContent") == '777원'
        assert evaluate("document.querySelector('#wealthMixLegend small').textContent.includes('100.0%')")
        assert evaluate("(()=>{const copy={...__roiSummary};delete copy.insuranceReturn;return JSON.stringify(copy)===__roiOriginal;})()")
        no_overflow(evaluate, width)
