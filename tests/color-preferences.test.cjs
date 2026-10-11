const test = require('node:test');
const assert = require('node:assert/strict');
const colors = require('../app/static/wealth-color-preferences.js');

test('calendar exposes seven preferences with no independent interest entry', () => {
  assert.deepEqual(colors.calendar.map(([key])=>key),[
    'ipo_subscription','ipo_listing','profit','loss','dividend','income','expense'
  ]);
  assert.equal(colors.calendar.find(([key])=>key==='dividend')[2],'#FFE082');
  assert.equal(colors.calendar.some(([key])=>key==='interest'),false);
});
test('canonical IDs survive renaming, known aliases and dynamic categories', () => {
  assert.equal(colors.keyFor('asset_category_colors','현금·예수금'),'cash');
  assert.equal(colors.keyFor('stock_category_colors',{sector_id:'stable',name:'before'}),colors.keyFor('stock_category_colors',{sector_id:'stable',name:'after'}));
  const key=colors.keyFor('stock_category_colors','새로운 테마');
  assert.ok(colors.validKey(key));
  assert.match(colors.fallback(key),/^#[0-9A-F]{6}$/);
  assert.equal(colors.register('stock_category_colors','새로운 테마','#123456'),'#123456');
  assert.equal(colors.register('stock_category_colors','새로운 테마','#ABCDEF'),'#123456');
});
test('uppercase round-trip, invalid stored values fall back, isolated group keys', () => {
  colors.replace({asset_category_colors:{cash:'#abcdef',bad:'red',constructor:'#123456'},stock_category_colors:{cash:'#22C7B8'}});
  assert.equal(colors.resolve('asset_category_colors','cash','#FF5A5F'),'#ABCDEF');
  assert.equal(colors.resolve('stock_category_colors','cash','#FF5A5F'),'#22C7B8');
  assert.equal(colors.resolve('asset_category_colors','bad','#FF5A5F'),'#FF5A5F');
  const saved=colors.snapshot();colors.replace(JSON.parse(JSON.stringify(saved)));assert.deepEqual(colors.snapshot(),saved);
  assert.equal(colors.validKey('constructor'),false);
  assert.equal(colors.validKey('bad key'),false);
  assert.throws(()=>colors.keyFor('unknown','cash'));
});
