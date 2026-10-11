const {test} = require('node:test');
const assert = require('node:assert/strict');
const c = require('../app/static/wealth-color-picker.js');
test('opaque HEX normalization and invalid values', () => {
  assert.equal(c.normalizeHexColor('  #ab12Ef  '),'#AB12EF');
  for(const value of [null,undefined,0,{},'#abc','#12345678','red','123456','#zzzzzz','#12 456','']) {
    assert.equal(c.normalizeHexColor(value),null); assert.equal(c.isValidHexColor(value),false);
  }
  assert.equal(c.isValidHexColor('#000000'),true); assert.equal(c.isValidHexColor('#FFFFFF'),true);
});
test('fallback is canonical and palette source cannot be mutated by a consumer', () => {
  assert.equal(c.getFallbackColor('bad','#a1b2c3'),'#A1B2C3');
  assert.equal(c.getFallbackColor('bad','bad'),c.getRecommendedPalette()[0]);
  const palette=c.getRecommendedPalette(); assert.ok(palette.length>=16);
  assert.ok(palette.every(c.isValidHexColor)); assert.equal(new Set(palette).size,palette.length);
  palette.length=0; assert.ok(c.getRecommendedPalette().length>=16);
});
test('responsive picker policy', () => {
  for(const width of [390,767,NaN,Infinity,undefined]) assert.equal(c.getPickerMode(width),'palette');
  for(const width of [768,1280]) assert.equal(c.getPickerMode(width),'advanced');
});
test('HSV controls roundtrip every opaque color within RGB rounding', () => {
  for(const color of ['#000000','#FFFFFF','#FF0000','#00FF00','#0000FF','#13579B',...c.getRecommendedPalette()]) {
    const {h,s,v}=c.hexToHsv(color); assert.equal(c.hsvToHex(h,s,v),color);
  }
  assert.equal(c.hsvToHex(360,1,1),'#FF0000'); assert.equal(c.hsvToHex(-120,1,1),'#0000FF');
  assert.equal(c.hsvToHex(120,2,2),'#00FF00'); assert.equal(c.hsvToHex(120,-1,-1),'#000000');
});
