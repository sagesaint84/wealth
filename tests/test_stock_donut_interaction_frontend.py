"""Event-level regression coverage for the stock allocation donut pairing."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StockDonutInteractionFrontendTests(unittest.TestCase):
    def test_slice_and_legend_activate_each_other_without_listener_accumulation(self):
        source = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
        script = f"""
const source = {json.dumps(source)};
const start = source.indexOf('function bindSectorDonutInteractions');
let depth = 0, end = start;
for (; end < source.length; end += 1) {{
  if (source[end] === '{{') depth += 1;
  else if (source[end] === '}}' && --depth === 0) {{ end += 1; break; }}
}}
const filtered = [];
function filterHoldingsByClassification(value) {{ filtered.push(value); }}
eval(source.slice(start, end));

class ClassList {{
  constructor() {{ this.values = new Set(); }}
  toggle(value, enabled) {{ if (enabled) this.values.add(value); else this.values.delete(value); }}
  contains(value) {{ return this.values.has(value); }}
}}
class Node {{
  constructor(key, sector) {{ this.dataset = {{ donutKey: key, sectorFilter: sector }}; this.classList = new ClassList(); }}
  fire(type, event = {{}}) {{ this['on' + type]?.({{ preventDefault: () => {{ event.prevented = true; }}, ...event }}); }}
}}
const sliceA = new Node('classification:미국 대표지수', '미국 대표지수');
const legendA = new Node('classification:미국 대표지수', '미국 대표지수');
const sliceB = new Node('classification:반도체', '반도체');
const legendB = new Node('classification:반도체', '반도체');
const nodes = [sliceA, legendA, sliceB, legendB];
const container = {{ classList: new ClassList(), querySelectorAll: () => nodes }};
bindSectorDonutInteractions(container);
sliceA.fire('pointerenter');
const afterSliceEnter = {{
  container: container.classList.contains('has-donut-hover'),
  sliceA: sliceA.classList.contains('is-donut-active'),
  legendA: legendA.classList.contains('is-donut-active'),
  otherDimmed: !sliceB.classList.contains('is-donut-active') && !legendB.classList.contains('is-donut-active'),
}};
sliceA.fire('pointerleave');
const afterLeave = nodes.every(node => !node.classList.contains('is-donut-active')) && !container.classList.contains('has-donut-hover');
legendB.fire('focus');
const afterLegendFocus = sliceB.classList.contains('is-donut-active') && legendB.classList.contains('is-donut-active');
legendB.fire('blur');
const afterBlur = nodes.every(node => !node.classList.contains('is-donut-active')) && !container.classList.contains('has-donut-hover');
bindSectorDonutInteractions(container);
const keyEvent = {{ key: 'Enter' }};
legendA.fire('keydown', keyEvent);
process.stdout.write(JSON.stringify({{ afterSliceEnter, afterLeave, afterLegendFocus, afterBlur, filtered, prevented: keyEvent.prevented }}));
"""
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(script)
            script_path = Path(handle.name)
        try:
            result = subprocess.run(
                ["node", str(script_path)], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=True
            )
        finally:
            script_path.unlink(missing_ok=True)
        output = json.loads(result.stdout)
        self.assertEqual(output["afterSliceEnter"], {"container": True, "sliceA": True, "legendA": True, "otherDimmed": True})
        self.assertTrue(output["afterLeave"])
        self.assertTrue(output["afterLegendFocus"])
        self.assertTrue(output["afterBlur"])
        self.assertEqual(output["filtered"], ["미국 대표지수"])
        self.assertTrue(output["prevented"])
