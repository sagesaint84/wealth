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
        source = (ROOT / "app" / "static" / "wealth-donut-chart.js").read_text(encoding="utf-8")
        script = "const source = " + json.dumps(source) + ";\n" + r"""
globalThis.window = {};
globalThis.getComputedStyle = () => ({top: '24px'});
eval(source);
const filtered = [];
class ClassList {
  constructor() { this.values = new Set(); }
  toggle(value, enabled) { if (enabled) this.values.add(value); else this.values.delete(value); }
  contains(value) { return this.values.has(value); }
}
class Node {
  constructor(key) {
    this.dataset = key ? {donutKey: key} : {};
    this.classList = new ClassList(); this.style = {}; this.listeners = {};
  }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  removeEventListener(type, listener) {
    this.listeners[type] = (this.listeners[type] || []).filter(value => value !== listener);
  }
  getBoundingClientRect() { return {left: 0, top: 0, width: 150, height: 150}; }
  fire(type, event = {}) {
    event.preventDefault ||= () => { event.prevented = true; };
    this['on' + type]?.(event);
    (this.listeners[type] || []).forEach(listener => listener(event));
  }
}
const donut = new Node(), root = new Node();
const legendA = new Node('classification:미국 대표지수');
const legendB = new Node('classification:반도체');
const legend = {querySelectorAll: () => [legendA, legendB]};
const segments = window.WealthDonutChart.segments([
  {key: legendA.dataset.donutKey, name: '미국 대표지수', color: '#ff0000', colorKey: 'a'},
  {key: legendB.dataset.donutKey, name: '반도체', color: '#0000ff', colorKey: 'b'},
], () => 50);
const bind = () => window.WealthDonutChart.bind(donut, segments, {
  legend, root, onSelect: item => filtered.push(item.name),
});
const state = () => ({
  root: root.classList.contains('has-donut-hover'),
  donut: donut.classList.contains('has-donut-hover'),
  a: legendA.classList.contains('is-donut-active'),
  b: legendB.classList.contains('is-donut-active'),
  background: donut.style.background,
  colorKey: donut.dataset.colorKey || null,
});
bind();
donut.fire('pointermove', {clientX: 140, clientY: 75});
const afterDonutMove = state();
donut.fire('pointerleave'); const afterLeave = state();
legendB.fire('pointerenter'); const afterLegendEnter = state();
legendB.fire('pointerleave'); const afterLegendLeave = state();
legendB.fire('focus'); const afterLegendFocus = state();
legendB.fire('blur'); const afterBlur = state();
donut.fire('pointermove', {clientX: 10, clientY: 75});
const afterOtherSegment = state();
donut.fire('pointermove', {clientX: 75, clientY: 75});
const afterHole = state();
donut.fire('pointermove', {clientX: 160, clientY: 75});
const afterOutside = state();
bind(); bind();
const enterEvent = {key: 'Enter'}, spaceEvent = {key: ' '}, otherKey = {key: 'ArrowRight'};
legendA.fire('keydown', enterEvent);
legendB.fire('keydown', spaceEvent);
legendA.fire('keydown', otherKey);
donut.fire('click', {clientX: 140, clientY: 75});
donut.fire('click', {clientX: 75, clientY: 75});
process.stdout.write(JSON.stringify({afterDonutMove, afterLeave, afterLegendEnter, afterLegendLeave,
  afterLegendFocus, afterBlur, afterOtherSegment, afterHole, afterOutside, filtered,
  enterPrevented: !!enterEvent.prevented, spacePrevented: !!spaceEvent.prevented,
  otherPrevented: !!otherKey.prevented}));
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
        neutral = {"root": False, "donut": False, "a": False, "b": False,
                   "background": "conic-gradient(#ff0000 0% 50%,#0000ff 50% 100%)", "colorKey": None}
        active_a = {"root": True, "donut": True, "a": True, "b": False,
                    "background": "conic-gradient(#ff0000 0% 50%,#0000ff80 50% 100%)", "colorKey": "a"}
        active_b = {"root": True, "donut": True, "a": False, "b": True,
                    "background": "conic-gradient(#ff000080 0% 50%,#0000ff 50% 100%)", "colorKey": "b"}
        self.assertEqual(output["afterDonutMove"], active_a)
        self.assertEqual(output["afterLegendEnter"], active_b)
        self.assertEqual(output["afterLegendFocus"], active_b)
        self.assertEqual(output["afterOtherSegment"], active_b)
        for phase in ("afterLeave", "afterLegendLeave", "afterBlur", "afterHole", "afterOutside"):
            self.assertEqual(output[phase], neutral, phase)
        self.assertEqual(output["filtered"], ["미국 대표지수", "반도체", "미국 대표지수"])
        self.assertTrue(output["enterPrevented"])
        self.assertTrue(output["spacePrevented"])
        self.assertFalse(output["otherPrevented"])
