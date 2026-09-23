"""Small DOM-free contracts for conic-gradient donut geometry and metadata."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _hit_test(points: list[dict[str, float]]) -> list[str | None]:
    source = (ROOT / "app" / "static" / "wealth-layout.js").read_text(encoding="utf-8")
    script = f"""
globalThis.window = {{}};
globalThis.document = {{ getElementById: () => null }};
eval({json.dumps(source)});
const segments = [
  {{ key: 'first', start: 0, end: 25 }},
  {{ key: 'second', start: 25, end: 50 }},
  {{ key: 'third', start: 50, end: 75 }},
  {{ key: 'fourth', start: 75, end: 100 }},
];
const results = {json.dumps(points)}.map(point => window.WealthDonutHitTest(segments, {{
  ...point, innerRadius: 20, outerRadius: 100,
}}));
process.stdout.write(JSON.stringify(results));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        completed = subprocess.run(["node", str(script_path)], cwd=ROOT, text=True, capture_output=True, check=True)
        return json.loads(completed.stdout)
    finally:
        script_path.unlink(missing_ok=True)


class DonutInteractionFrontendTests(unittest.TestCase):
    def test_conic_gradient_cardinal_angles_and_boundaries(self):
        # CSS conic-gradient: 0% is twelve o'clock and progresses clockwise.
        self.assertEqual(
            _hit_test([
                {"x": 0, "y": -80},  # 12:00 -> 0%
                {"x": 80, "y": 0},   # 03:00 -> 25%
                {"x": 0, "y": 80},   # 06:00 -> 50%
                {"x": -80, "y": 0},  # 09:00 -> 75%
            ]),
            ["first", "second", "third", "fourth"],
        )

    def test_conic_gradient_ignores_hole_and_outer_area(self):
        self.assertEqual(_hit_test([{"x": 0, "y": -10}, {"x": 101, "y": 0}]), [None, None])
