"""Pure core reference renderer preserves URL and supplemental contracts."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_reference_link_is_first_and_supplemental_tooltip_survives_rerender(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js required for frontend runtime test')
    source = (Path(__file__).resolve().parents[1] / 'app/static/wealth-ipo.js').read_text(encoding='utf-8')
    functions = source[source.index('  function trustedMetalogosUrl('):source.index('  // Presentation metadata')]
    script = tmp_path / 'reference-ui.js'
    script.write_text("""
const assert = require('node:assert/strict');
const escapeHtml = value => String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
""" + functions + """
const reference = {url:'https://metalogos.ai/160ipo/stock/B202605261', attractiveness_score:79,
 demand_participant_count_reference:2367, lockup_participant_count_reference:355, tradable_share_ratio_reference:20.81};
const render = ref => renderMetalogosReference({sources:{metalogos160:ref}});
const html = render(reference);
assert.ok(html.includes('target="_blank" rel="noopener noreferrer">160 원문</a> · 매력지수 79'));
assert.ok(html.includes('Wealth IPO Score 산정에는 사용하지 않습니다.'));
assert.equal(render(reference), html);
assert.equal(render({...reference,tradable_share_ratio_reference:99}), html);
for(const url of ['http://metalogos.ai/160ipo/stock/A','https://evil.example/160ipo/stock/A',
 'https://metalogos.ai/not-stock/A','javascript:alert(1)','https://metalogos.ai.evil.example/160ipo/stock/A']) {
 const rejected = render({...reference,url});
 assert.ok(!rejected.includes('<a '));
 assert.ok(rejected.includes('>매력지수 79</span>'));
}
assert.ok(render({...reference,url:'https://www.metalogos.ai/160ipo/stock/A'}).includes('<a '));
assert.equal(renderMetalogosReference({}), '');
assert.equal(render({...reference,url:'',attractiveness_score:'invalid'}), '');
assert.ok(!html.includes('2367')&&!html.includes('355')&&!html.includes('20.81'));
""", encoding='utf-8')
    result = subprocess.run([node, str(script)], text=True, capture_output=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
