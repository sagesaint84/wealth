const {test} = require('node:test');
const assert = require('node:assert/strict');
const {bucketTotals} = require('../app/static/wealth-planning-model.js');
const state = {buckets:[{id:'growth'},{id:'income'}],accounts:{a:'growth',b:'income'},holdings:{h1:'income',h2:''}};
const view = {accounts:[{id:'a',cash_krw:100,cash_usd:1},{id:'b',cash_krw:200}],fxRates:{USD:1300},
  holdings:[{id:'h1',account_id:'a',code:'SAME',market_value_krw:500},{id:'h2',account_id:'b',code:'SAME',market_value_krw:800}]};
test('account defaults, same ticker exceptions and explicit unclassified do not double count',()=>{
  const {totals,total}=bucketTotals(state,view);
  assert.equal(total,2900); assert.equal(totals.get('growth'),1400); assert.equal(totals.get('income'),700); assert.equal(totals.get(''),800);
});
test('other owner holdings are excluded by account scope',()=>{
  const result=bucketTotals(state,{...view,accounts:[view.accounts[0]]});
  assert.equal(result.total,1900);
});
test('unassigned positions remain unclassified',()=>{
  assert.equal(bucketTotals({buckets:[],accounts:{},holdings:{}},view).totals.get(''),2900);
});
test('missing USD FX blocks totals rather than treating foreign cash as zero',()=>{
  assert.throws(()=>bucketTotals(state,{...view,fxRates:{}}),/USD/);
});
test('calculation does not mutate account, holding or classification data',()=>{
  const before=JSON.stringify({state,view});bucketTotals(state,view);assert.equal(JSON.stringify({state,view}),before);
});
