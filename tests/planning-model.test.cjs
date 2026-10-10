const {test} = require('node:test');
const assert = require('node:assert/strict');
const {bucketConstituents,bucketTotals,bucketAllocationComparison,historyView} = require('../app/static/wealth-planning-model.js');
const state = {buckets:[{id:'growth'},{id:'income'}],accounts:{a:'growth',b:'income'},holdings:{h1:'income',h2:''}};
const view = {accounts:[{id:'a',cash_krw:100,cash_usd:1},{id:'b',cash_krw:200}],fxRates:{USD:1300},
  holdings:[{id:'h1',account_id:'a',code:'SAME',market_value_krw:500},{id:'h2',account_id:'b',code:'SAME',market_value_krw:800}]};
test('account defaults, same ticker exceptions and explicit unclassified do not double count',()=>{
  const {totals,total}=bucketTotals(state,view);
  assert.equal(total,2900); assert.equal(totals.get('growth'),0); assert.equal(totals.get('income'),500); assert.equal(totals.get(''),800);
});
test('constituents share totals classification, owner scope and FX without mutation',()=>{
  const before=JSON.stringify({state,view});
  const rows=bucketConstituents(state,view), {totals}=bucketTotals(state,view);
  assert.equal(rows.find(r=>r.holding_id==='h1').bucket_id,'income');
  assert.equal(rows.find(r=>r.holding_id==='h2').bucket_id,'');
  assert.equal(rows.find(r=>r.account_id==='a'&&r.kind==='cash').value,1400);
  assert.equal(rows.find(r=>r.account_id==='a'&&r.kind==='cash').bucket_id,'__cash__');
  for(const [key,value] of totals) assert.equal(rows.filter(r=>r.bucket_id===key).reduce((s,r)=>s+r.value,0),value);
  assert.deepEqual(bucketConstituents(state,{...view,accounts:[view.accounts[0]]}).map(r=>r.account_id),['a','a']);
  assert.equal(JSON.stringify({state,view}),before);
  assert.ok(bucketConstituents({...state,accounts:{},holdings:{}},view).every(r=>r.bucket_id===(r.kind==='cash'?'__cash__':'')));
});
test('other owner holdings are excluded by account scope',()=>{
  const result=bucketTotals(state,{...view,accounts:[view.accounts[0]]});
  assert.equal(result.total,1900);
});
test('unassigned positions remain unclassified',()=>{
  assert.equal(bucketTotals({buckets:[],accounts:{},holdings:{}},view).totals.get(''),1300);
});
test('missing USD FX blocks totals rather than treating foreign cash as zero',()=>{
  assert.throws(()=>bucketTotals(state,{...view,fxRates:{}}),/USD/);
});

test('cash resolver is pure, Korean first, virtual fallback has no target',()=>{
  const fixture={buckets:[{id:'core',name:'코어',target:30},{id:'growth',name:'성장',target:70}],accounts:{a:'growth'},holdings:{h2:'core'}};
  const positions={accounts:[{id:'a',cash_krw:1000}],holdings:[{id:'h1',account_id:'a',market_value_krw:5000},{id:'h2',account_id:'a',market_value_krw:3000}]};
  for(const definition of [[],[{id:'saved',name:'현금',color:'#FF1234'}],[{id:'english',name:'cash'},{id:'saved',name:'현금'}]]) {
    const data={...fixture,buckets:[...fixture.buckets,...definition]},before=JSON.stringify(data);
    for(const accountDefault of ['growth','core','',undefined]) {
      const input={...data,accounts:accountDefault===undefined?{}:{a:accountDefault}};
      const result=bucketAllocationComparison(input,positions),cash=result.current.find(b=>b.name==='현금');
      assert.equal(cash.id,definition.length?'saved':'__cash__');assert.equal(cash.value,1000);assert.equal(result.total,9000);
      assert.equal(result.current.reduce((sum,b)=>sum+b.value,0),9000);
      assert.equal(result.current.find(b=>b.id==='core').value,3000+(accountDefault==='core'?5000:0));
      assert.equal(result.current.find(b=>b.id==='growth').value,accountDefault==='growth'?5000:0);
      assert.ok(!result.target.some(b=>b.id==='__cash__'));
      assert.ok(Math.abs(result.current.reduce((sum,b)=>sum+b.percent,0)-100)<1e-9);
    }
    assert.equal(JSON.stringify(data),before);
  }
});

test('override, explicit unclassified and absent inheritance remain distinct from cash',()=>{
  const buckets=[{id:'growth',name:'성장'},{id:'dividend',name:'배당'},{id:'cash-id',name:'현금'}];
  const scoped={accounts:[{id:'a',cash_krw:100,cash_usd:1}],holdings:[{id:'h1',account_id:'a',market_value_krw:5000}],fxRates:{USD:1300}};
  for(const [holdings, expected] of [[{h1:'dividend'},'dividend'],[{h1:''},''],[{},'growth'],[{h1:'cash-id'},'cash-id']]) {
    const rows=bucketConstituents({buckets,accounts:{a:'growth'},holdings},scoped);
    assert.equal(rows.find(r=>r.kind==='holding').bucket_id,expected);
    assert.equal(rows.find(r=>r.kind==='cash').bucket_id,'cash-id');
    assert.equal(rows.find(r=>r.kind==='cash').value,1400);
  }
  for(const fx of [undefined,0,-1,Infinity,NaN]) assert.throws(()=>bucketTotals(state,{...view,fxRates:{USD:fx}}),/USD/);
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
