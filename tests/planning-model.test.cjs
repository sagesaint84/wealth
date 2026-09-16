const {test} = require('node:test');
const assert = require('node:assert/strict');
const {bucketTotals,bucketAllocationComparison,historyView} = require('../app/static/wealth-planning-model.js');
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
test('target allocation stays user-defined and fills only the unallocated remainder',()=>{
  const configured={...state,buckets:[{id:'growth',name:'성장',target:60},{id:'income',name:'배당',target:20}]};
  const result=bucketAllocationComparison(configured,view);
  assert.equal(result.targetConfigured,true);assert.equal(result.targetTotal,80);
  assert.deepEqual(result.target.map(item=>[item.name,item.value]),[['성장',60],['배당',20],['미배정',20]]);
  assert.equal(result.target.reduce((sum,item)=>sum+item.value,0),100);
});
test('current allocation preserves the existing total and includes unclassified assets',()=>{
  const configured={...state,buckets:[{id:'growth',name:'성장',target:60},{id:'income',name:'배당',target:40}]};
  const result=bucketAllocationComparison(configured,view);
  assert.equal(result.total,2900);
  assert.equal(result.current.find(item=>item.name==='미분류').value,800);
  assert.equal(Math.round(result.current.reduce((sum,item)=>sum+item.percent,0)*1e9)/1e9,100);
});
test('zero targets remain an unconfigured target rather than fabricated allocation',()=>{
  const result=bucketAllocationComparison({buckets:[{id:'growth',name:'성장',target:0}],accounts:{},holdings:{}},view);
  assert.equal(result.targetConfigured,false);assert.deepEqual(result.target,[]);
});
test('owner scope changes current allocation without rewriting global targets',()=>{
  const configured={...state,buckets:[{id:'growth',name:'성장',target:55},{id:'income',name:'배당',target:45}]};
  const all=bucketAllocationComparison(configured,view);
  const owner=bucketAllocationComparison(configured,{...view,accounts:[view.accounts[0]]});
  assert.deepEqual(owner.target,all.target);assert.equal(owner.total,1900);assert.notDeepEqual(owner.current,all.current);
});

test('history empty state disables selection actions',()=>{
  assert.deepEqual(historyView([],'모두',0,''),{records:[],selectedDate:'',canEdit:false});
});
test('history one manual negative record is selectable',()=>{
  const result=historyView([{date:'2001-01-01',owner:'모두',net_worth:-1,source:'manual'}],'모두',0,'');
  assert.equal(result.records.length,1);assert.equal(result.canEdit,true);assert.equal(result.selectedDate,'2001-01-01');
});
test('history sorts mixed sources and isolates literal owner scope',()=>{
  const records=[{date:'2026-09-08',owner:'모두',source:'user_confirmed'},{date:'2001-01-01',owner:'엄마',source:'manual'},{date:'2001-01-01',owner:'모두',source:'manual'}];
  const before=JSON.stringify(records),result=historyView(records,'모두',0,'2001-01-01');
  assert.deepEqual(result.records.map(r=>r.date),['2001-01-01','2026-09-08']);assert.equal(result.selectedDate,'2001-01-01');assert.equal(JSON.stringify(records),before);
  assert.equal(historyView(records,'아빠',0,'').canEdit,false);
});
test('history response replacement reflects add edit and delete immediately',()=>{
  let records=[{date:'2001-01-01',owner:'모두'}];
  assert.equal(historyView(records,'모두',0,'').records.length,1);
  records=[{date:'2000-01-01',owner:'모두'},{date:'2001-01-01',owner:'모두'}];
  assert.equal(historyView(records,'모두',0,'2000-01-01').selectedDate,'2000-01-01');
  records=[{date:'2002-01-01',owner:'모두'}];
  assert.equal(historyView(records,'모두',0,'2000-01-01').selectedDate,'2002-01-01');
  assert.equal(historyView([],'모두',0,'2002-01-01').canEdit,false);
});
test('history range excludes old dates without changing stored records',()=>{
  const records=[{date:'2001-01-01',owner:'모두'},{date:'2026-09-08',owner:'모두'}];
  assert.equal(historyView(records,'모두',30,'',Date.parse('2026-09-08T00:00:00Z')).records.length,1);
  assert.equal(historyView(records,'모두',0,'').records.length,2);
});
