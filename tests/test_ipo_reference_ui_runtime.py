from pathlib import Path
import shutil
import subprocess

import pytest


def test_reference_link_is_first_and_supplemental_tooltip_survives_rerender(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required for frontend runtime test')
    source = (Path(__file__).resolve().parents[1] / 'app/static/wealth-ipo-compact-view.js').read_text(encoding='utf-8')
    functions = source[source.index('  function trustedMetalogosUrl('):source.index('  function decorateCard(')]
    script = tmp_path / 'reference-ui.js'
    script.write_text('''
const assert = require('node:assert/strict');
let metadataLoaded = true;
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.textContent = ''; this.dataset = {}; }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  querySelector() { return this.children.find(child => child.className === 'ipo-metalogos-reference') || null; }
}
const document = {createElement: tag => new Element(tag)};
const location = {href: 'https://wealth.example/'};
''' + functions + '''
const box = new Element('div');
const card = {querySelector: () => box};
const reference = {url:'https://metalogos.ai/160ipo/stock/B202605261', attractiveness_score:79,
  demand_participant_count_reference:2367, lockup_participant_count_reference:355, tradable_share_ratio_reference:20.81};
decorateMetalogosReference(card, {sources:{metalogos160:reference}});
let note = box.children[0];
assert.equal(note.children[0].tagName, 'a');
assert.equal(note.children[0].textContent, '160 원문');
assert.equal(note.children[0].rel, 'noopener noreferrer');
assert.equal(note.children[1].textContent, ' · 매력지수 79 · 수요예측기관 2,367 · 확약기관 355 · 유통가능 20.81%');
assert.equal(note.children.map(child => child.textContent).join(''), '160 원문 · 매력지수 79 · 수요예측기관 2,367 · 확약기관 355 · 유통가능 20.81%');
const originalLink = note.children[0];
decorateMetalogosReference(card, {sources:{metalogos160:reference}});
assert.equal(note.children[0], originalLink, 'unchanged observer decoration must preserve the pressed anchor');
assert.ok(note.title.includes('Wealth IPO Score 산정에는 사용하지 않습니다.'));
for (const url of ['http://metalogos.ai/160ipo/stock/A', 'https://evil.example/160ipo/stock/A',
                  'https://metalogos.ai/not-stock/A']) {
  decorateMetalogosReference(card, {sources:{metalogos160:{...reference,url}}});
  assert.equal(note.children.length, 1);
  assert.equal(note.children[0].tagName, 'span');
  assert.ok(!note.children[0].textContent.startsWith(' · '));
}
decorateMetalogosReference(card, {sources:{metalogos160:reference}});
assert.equal(box.children.length, 1);
assert.equal(note.children[0].tagName, 'a');
console.log('link-first, metrics, tooltip, trusted URL and rerender passed');
''', encoding='utf-8')
    result = subprocess.run([node, str(script)], text=True, capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
