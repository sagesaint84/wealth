"""Display-only model checks using Node and invented values, no app startup."""
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_asset_return_policy_preserves_values_and_never_substitutes_weight():
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
globalThis.window = {};
globalThis.document = {getElementById: () => null};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const display = window.WealthAssetReturnDisplay;
const stock = Object.freeze({name:'국내주식',cost_value_krw:100,market_value_krw:110,profit_krw:10,return_rate:10,weight:55});
const before = JSON.stringify(stock);
assert.equal(display(stock), 10);
assert.equal(JSON.stringify(stock), before);
assert.equal(display({...stock,profit_krw:-10,return_rate:-10}), -10);
assert.equal(display({...stock,profit_krw:0,return_rate:0}), 0);
for (const name of ['현금·예수금','보험','임차보증금']) {
  assert.equal(display({...stock,name,weight:17}), null, name);
}
for (const cost of [0,-1,undefined,null,NaN,Infinity]) {
  assert.equal(display({...stock,cost_value_krw:cost}), null);
}
for (const rate of [undefined,null,'10',NaN,Infinity,-Infinity]) {
  assert.equal(display({...stock,return_rate:rate}), null);
}
assert.equal(display({...stock,profit_krw:NaN}), null);
const property = Object.freeze({rate:25,profit:200,cost:800});
assert.equal(display({...stock,name:'부동산'}, property), 25);
assert.equal(display({...stock,name:'부동산'}), null);
assert.equal(display({...stock,name:'부동산'}, {...property,cost:0}), null);
assert.equal(JSON.stringify(property), '{"rate":25,"profit":200,"cost":800}');
assert.equal(display({...stock,name:'새 자산군'}), 10);

// Exercise the actual classification producer with synthetic balances and
// ownership. Its property value is gross valuation, not debt-netted equity.
const source = fs.readFileSync(process.argv[2], 'utf8');
const classificationSource = 'function computeFilteredClassifications(' +
  source.split('function computeFilteredClassifications(')[1].split('function computeFilteredSectors(')[0];
const classify = eval('(' + classificationSource.trim() + ')');
globalThis.classifyHolding = () => '국내주식';
const raw = {
  real_estates: [
    {property_type:'rental',current_price:1000,purchase_price:600,deposit_amount:900,
      ownerships:[{owner:'아빠',ratio:40},{owner:'엄마',ratio:60}]},
    {property_type:'lease',deposit_amount:80,owner:'아빠'}
  ],
  bank_accounts:[{owner:'아빠',balance:30},{owner:'엄마',balance:999}],
  savings_accounts:[{owner:'아빠',current_value:20}],
  insurance_accounts:[{owner:'아빠',expected_amount:70,expected_refund_amount:999}],
};
const inputsBefore = JSON.stringify(raw);
const classifications = classify([stock], [{cash_krw:50}], {USD:1385}, '아빠', raw);
const byName = Object.fromEntries(classifications.map(item => [item.name,item]));
assert.equal(byName['부동산'].market_value_krw, 400);
assert.equal(byName['부동산'].holding_count, 1);
assert.equal(byName['임차보증금'].market_value_krw, 80);
assert.equal(byName['현금·예수금'].market_value_krw, 100);
assert.equal(byName['현금·예수금'].holding_count, 3);
assert.equal(byName['보험'].market_value_krw, 70);
assert.equal(byName['국내주식'].return_rate, 10);
assert.equal(classifications.reduce((sum,item) => sum+item.market_value_krw,0), 760);
assert.equal(byName['부동산'].weight, 400/760*100);
// Classification's placeholder zero return cannot replace the HOME purchase
// basis: (400 - 240) / 240. No financial field is recalculated by display().
const propertyBasis = {rate:160/240*100,profit:160,cost:240};
assert.equal(display(byName['부동산'], propertyBasis), propertyBasis.rate);
assert.notEqual(display(byName['부동산'], propertyBasis), byName['부동산'].return_rate);
for (const name of ['현금·예수금', '보험', '임차보증금']) {
  assert.equal(display(byName[name]), null);
}
assert.equal(JSON.stringify(raw), inputsBefore);
'''
    result = subprocess.run(
        ['node', '-e', script, str(ROOT / 'app/static/wealth-layout.js'), str(ROOT / 'app/static/wealth.js')],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_import_default_controls_keep_existing_ids_and_explicit_actions():
    html = (ROOT / 'app/static/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'app/static/wealth-transaction-defaults.js').read_text(encoding='utf-8')
    for selector in ('wtsDestinationAccount', 'wtsIncomeDestinationAccount'):
        blocks = re.findall(r'<div class="toss-wts-control-item toss-wts-account-control">(.*?)</small>\s*</div>', html, re.S)
        block = next(block for block in blocks if f'for="{selector}"' in block)
        assert '귀속 Wealth 계좌' in block
        assert f'id="{selector}Remember"' in block
        assert f'id="{selector}Clear"' in block
        assert f'id="{selector}DefaultNotice"' in block
        assert '기본계좌로 지정' in block
        assert 'role="status"' in block
        assert 'class="import-default-controls"' in block
        assert 'class="toss-wts-account-head"' in block
        assert block.index(f'for="{selector}"') < block.index(f'id="{selector}Remember"') < block.index(f'id="{selector}"')
        assert f'aria-describedby="{selector}DefaultNotice"' in block
    assert "account_id: clear ? '' : select.value" in js
    assert "'기본계좌 해제됨' : '기본계좌 지정됨'" in js
    assert '저장된 기본값을 사용할 수 없습니다. 직접 선택해 주세요.' in js


def test_insurance_simple_return_is_owner_scoped_complete_and_display_only():
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
globalThis.window = {}; globalThis.document = {getElementById: () => null};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const roi = window.WealthInsuranceReturnDisplay;
const display = window.WealthAssetReturnDisplay;
const base = Object.freeze({owner:'아빠',payout_type:'lump_sum',total_paid_amount:100,
  expected_amount:120,converted_total_asset:120,marginal_tax_rate:99});
assert.equal(roi([base]).rate, 20);
assert.equal(roi([{...base,expected_amount:80,converted_total_asset:80}]).rate, -20);
assert.equal(roi([{...base,expected_amount:100,converted_total_asset:100}]).rate, 0);
assert.equal(roi([{...base,expected_amount:0,converted_total_asset:0}]).rate, -100);
for (const paid of [0,-1,undefined,null,'100',NaN,Infinity]) {
  assert.equal(roi([{...base,total_paid_amount:paid}]).rate, null);
}
for (const expected of [undefined,null,'120',-1,NaN,Infinity]) {
  assert.equal(roi([{...base,expected_amount:expected}]).rate, null);
}
assert.equal(roi([{...base,converted_total_asset:999}]).rate, null);
for (const monthly of [-1,'0',NaN,Infinity]) {
  assert.equal(roi([{...base,monthly_payout:monthly}]).rate, null);
}
assert.equal(roi([{total_paid_amount:100,expected_refund_amount:120}]).rate, null);
assert.equal(roi([{accumulated_paid_amount:100,expected_amount:120}]).rate, null);
const missing = {...base,owner:'엄마',total_paid_amount:0};
assert.equal(roi([base,missing], '아빠').rate, 20);
assert.equal(roi([base,missing], '엄마').rate, null);
assert.equal(roi([base,missing], '모두').rate, 20);
assert.equal(roi([base,missing], '모두').included, 1);
assert.equal(roi([base,missing], '모두').total, 2);
assert.match(roi([base,missing], '모두').scope, /일부 상품 기준 · 1\/2개 상품 산정/);
assert.equal(roi([base], '엄마').rate, null);
assert.equal(roi([base,{...base,total_paid_amount:300,expected_amount:300,converted_total_asset:300}]).rate, 5);
const pension = {...base,payout_type:'monthly_pension',monthly_payout:1,payout_duration_years:20,
  expected_amount:240,converted_total_asset:240};
for (const item of [pension,{...pension,converted_total_asset:999},
  {...base,insurance_type:'national_pension'}, {...base,insurance_type:'irp'},
  {...base,monthly_payout:1}]) {
  assert.equal(roi([item]).rate, null);
  assert.equal(roi([base,item]).rate, 20);
  assert.equal(roi([base,item]).included, 1);
  assert.equal(roi([base,item]).total, 2);
}
const inputs = [base,missing,pension]; const before = JSON.stringify(inputs);
roi(inputs); assert.equal(JSON.stringify(inputs), before);
const category = Object.freeze({name:'보험',market_value_krw:120,cost_value_krw:120,profit_krw:0,return_rate:0,weight:30});
const categoryBefore = JSON.stringify(category);
assert.equal(display(category, null, roi([base])), 20);
assert.equal(display(category), null);
assert.equal(JSON.stringify(category), categoryBefore);
assert.match(roi([base]).description, /예상 단순수익률/);
assert.match(roi([base]).description, /향후 추가 납입/);
assert.match(roi([base]).description, /세금 절감액 미반영/);
assert.match(roi([base,missing]).description, /일부 상품/);
assert.match(roi([pension]).description, /연금형/);
'''
    result = subprocess.run(['node', '-e', script, str(ROOT / 'app/static/wealth-layout.js')],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    source = (ROOT / 'app/static/wealth.js').read_text(encoding='utf-8')
    assert 'insuranceReturn: window.WealthInsuranceReturnDisplay?.(data.insurance_accounts || rawInsuranceAccounts || [], o)' in source
    assert 'market_value_krw: insuranceTotal' in source
    assert 'cost_value_krw: insuranceTotal' in source
    assert 'const totalSafeAssets = totalAllCash + totalTenantDepositVal + insuranceTotal' in source


def test_tax_card_header_roles_keep_filter_and_edit_contracts():
    source = (ROOT / 'app/static/wealth.js').read_text(encoding='utf-8')
    renderer = source.split('function renderTaxAccountHoldings(owner = currentOwner) {', 1)[1].split('// ── 9.', 1)[0]
    assert renderer.count('class="tax-card-head"') == 5
    assert renderer.count('class="tax-card-selected"') == 5
    for value in ('all', 'isa', 'irp', 'pension_savings', 'acc_' + '$' + '{acct.id}'):
        assert f'data-tax-filter="{value}"' in renderer
    assert 'data-account-edit-id="' + '$' + '{acct.id}"' in renderer
    assert 'title="' + '$' + '{html(acct.name)}"' in renderer
    assert '선택됨' not in renderer
