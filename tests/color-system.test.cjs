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
  const palette=c.getRecommendedPalette();
  assert.deepEqual(palette,['#FF5A5F','#FF9F1C','#FFD60A','#2ECF73','#22C7B8','#4D96FF','#7C6CFF','#FF5FA2']);
  assert.ok(palette.every(c.isValidHexColor)); assert.equal(new Set(palette).size,palette.length);
  palette.length=0; assert.equal(c.getRecommendedPalette().length,8);
});

test('eight swatches remain distinct and visible against dark backgrounds', () => {
  const rgb = hex => [1,3,5].map(i => parseInt(hex.slice(i,i+2),16));
  const luminance = hex => rgb(hex).map(n => n/255).map(n => n<=.04045?n/12.92:((n+.055)/1.055)**2.4).reduce((sum,n,i) => sum+n*[.2126,.7152,.0722][i],0);
  for(const color of c.getRecommendedPalette()) {
    for(const background of ['#111A31','#000000']) assert.ok((luminance(color)+.05)/(luminance(background)+.05)>=3,color);
    // Hue separation measures the requested color families; raw RGB distance mixes brightness with hue.
    for(const other of c.getRecommendedPalette()) if(other!==color) {
      const difference=Math.abs(c.hexToHsv(color).h-c.hexToHsv(other).h);
      assert.ok(Math.min(difference,360-difference)>=15,`${color} / ${other}`);
    }
  }
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
