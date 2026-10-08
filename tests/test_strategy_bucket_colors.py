from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def hex_to_rgb(hex_code: str) -> tuple[float, float, float]:
    h = hex_code.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_code: str) -> float:
    r, g, b = hex_to_rgb(hex_code)
    return 0.2126 * srgb_to_lin(r) + 0.7152 * srgb_to_lin(g) + 0.0722 * srgb_to_lin(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


class TestStrategyBucketColors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planning_js = (ROOT / "app" / "static" / "wealth-planning.js").read_text(encoding="utf-8")
        cls.layout_js = (ROOT / "app" / "static" / "wealth-layout.js").read_text(encoding="utf-8")
        cls.wealth_js = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
        cls.overrides_css = (ROOT / "app" / "static" / "wealth-overrides.css").read_text(encoding="utf-8")

    def test_asset_allocation_donut_uses_v123_original_palette(self):
        v123_palette = [
            "#9b8afb", "#61c9b2", "#6ea6ec", "#e7bc71",
            "#c891bd", "#5aa9cf", "#ef7b8e", "#8bbf74", "#a9a1d6",
        ]
        palette_match = re.search(r"const palette\s*=\s*(\[[^\]]+\]);", self.layout_js)
        self.assertIsNotNone(palette_match, "Palette array not found in wealth-layout.js")
        palette_str = palette_match.group(1)
        for color in v123_palette:
            self.assertIn(color, palette_str)

    def test_sector_donut_uses_v123_original_palette(self):
        v123_sector_first_five = ["#8e70fa", "#38bdf8", "#34d399", "#f59e0b", "#ec4899"]
        self.assertIn("const SECTOR_COLORS =", self.wealth_js)
        for color in v123_sector_first_five:
            self.assertIn(color, self.wealth_js)

    def test_all_eight_preset_bucket_colors_defined_and_unique(self):
        presets = ["코어", "성장", "배당", "섹터", "테마", "전술", "방어", "현금"]
        for p in presets:
            self.assertIn(f"'{p}':", self.planning_js)

        # Extract BUCKET_PRESET_COLORS mapping
        preset_colors_match = re.search(r"const BUCKET_PRESET_COLORS\s*=\s*\{([^}]+)\};", self.planning_js)
        self.assertIsNotNone(preset_colors_match, "BUCKET_PRESET_COLORS not found in wealth-planning.js")
        body = preset_colors_match.group(1)

        extracted = {}
        for p in presets:
            m = re.search(rf"'{p}'\s*:\s*'([^']+)'", body)
            self.assertIsNotNone(m, f"Preset '{p}' missing from BUCKET_PRESET_COLORS")
            extracted[p] = m.group(1)

        # Ensure all 8 preset colors are unique
        self.assertEqual(len(set(extracted.values())), 8, "All 8 preset bucket colors must be distinct")

    def test_risk_palette_and_english_aliases(self):
        expected = {
            ('현금','cash'):'#1D4ED8', ('방어','defensive'):'#60A5FA',
            ('배당','dividend'):'#7DD3FC', ('전술','tactical'):'#8B5CF6',
            ('코어','core'):'#A78BFA', ('성장','growth'):'#FB7185',
            ('섹터','sector'):'#E11D48', ('테마','theme'):'#BE123C',
        }
        for aliases, color in expected.items():
            for name in aliases:
                self.assertIn(f"'{name}': '{color}'", self.planning_js)

    def test_safe_investment_blue_uses_theme_text_for_readable_labels(self):
        css = (ROOT / 'app/static/wealth-layout.css').read_text(encoding='utf-8')
        self.assertRegex(css, r"\.wealth-bucket-cards h4\s*\{[^}]*color: var\(--text\)")
        self.assertIn('border-left: 4px solid var(--bucket-color', css)
        self.assertIn('.wealth-bucket-card[aria-pressed="true"]', css)
        self.assertGreaterEqual(contrast_ratio('#60A5FA', '#111a31'), 4)
        self.assertGreaterEqual(contrast_ratio('#60A5FA', '#000000'), 5)

    def test_preset_buttons_render_swatch_dot_and_style(self):
        self.assertIn('<i class="wealth-bucket-preset-dot"></i>', self.planning_js)
        self.assertIn('style="--bucket-color:${bucketColor(name)}"', self.planning_js)
        self.assertIn('data-bucket-preset="${esc(name)}"', self.planning_js)

    def test_bucket_color_semantics_and_fallbacks(self):
        self.assertIn("if(id === '__unclassified__') return '#697386';", self.planning_js)
        self.assertIn("if(id === '__unallocated__') return '#35415b';", self.planning_js)
        self.assertIn("BUCKET_PRESET_COLORS[key]", self.planning_js)
        self.assertIn("BUCKET_COLORS[hash%BUCKET_COLORS.length]", self.planning_js)

    def test_swatch_dot_css_rules_present(self):
        self.assertIn(".wealth-bucket-preset-dot", self.overrides_css)
        self.assertIn("var(--bucket-color", self.overrides_css)
        self.assertIn("border-radius: 50%", self.overrides_css)
        self.assertIn("display: inline-flex", self.overrides_css)


if __name__ == "__main__":
    unittest.main()
