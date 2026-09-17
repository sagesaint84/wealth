from __future__ import annotations

import colorsys
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def hex_to_rgb(hex_code: str) -> tuple[float, float, float]:
    h = hex_code.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def hex_to_hsv(hex_code: str) -> tuple[float, float, float]:
    r, g, b = hex_to_rgb(hex_code)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s * 100.0, v * 100.0


def hue_difference(h1: float, h2: float) -> float:
    diff = abs(h1 - h2) % 360.0
    return min(diff, 360.0 - diff)


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

    def test_dividend_and_cash_colors_have_significant_hue_separation(self):
        m_div = re.search(r"'배당'\s*:\s*'([^']+)'", self.planning_js)
        m_cash = re.search(r"'현금'\s*:\s*'([^']+)'", self.planning_js)
        self.assertIsNotNone(m_div)
        self.assertIsNotNone(m_cash)

        div_color = m_div.group(1)
        cash_color = m_cash.group(1)

        h_div, s_div, v_div = hex_to_hsv(div_color)
        h_cash, s_cash, v_cash = hex_to_hsv(cash_color)

        diff = hue_difference(h_div, h_cash)
        self.assertGreaterEqual(
            diff,
            30.0,
            f"Hue difference between Dividend ({div_color}, {h_div:.1f}°) and Cash ({cash_color}, {h_cash:.1f}°) must be >= 30°, got {diff:.1f}°",
        )

        # Dividend must lean indigo/blue-violet (230-260°) and Cash must lean sky/azure (195-225°)
        self.assertTrue(230 <= h_div <= 260, f"Dividend hue {h_div:.1f}° should be in blue-violet range (230-260°)")
        self.assertTrue(195 <= h_cash <= 225, f"Cash hue {h_cash:.1f}° should be in sky-blue range (195-225°)")

    def test_tactical_and_defensive_colors_have_significant_hue_separation(self):
        m_tac = re.search(r"'전술'\s*:\s*'([^']+)'", self.planning_js)
        m_def = re.search(r"'방어'\s*:\s*'([^']+)'", self.planning_js)
        self.assertIsNotNone(m_tac)
        self.assertIsNotNone(m_def)

        tac_color = m_tac.group(1)
        def_color = m_def.group(1)

        h_tac, s_tac, v_tac = hex_to_hsv(tac_color)
        h_def, s_def, v_def = hex_to_hsv(def_color)

        diff = hue_difference(h_tac, h_def)
        self.assertGreaterEqual(
            diff,
            40.0,
            f"Hue difference between Tactical ({tac_color}, {h_tac:.1f}°) and Defensive ({def_color}, {h_def:.1f}°) must be >= 40°, got {diff:.1f}°",
        )

        # Tactical is warm amber (15-45°) and Defensive is muted sage/olive (75-100°)
        self.assertTrue(15 <= h_tac <= 45, f"Tactical hue {h_tac:.1f}° should be warm amber range (15-45°)")
        self.assertTrue(75 <= h_def <= 100, f"Defensive hue {h_def:.1f}° should be sage/olive range (75-100°)")

    def test_defensive_color_muted_sage_and_contrast(self):
        m_def = re.search(r"'방어'\s*:\s*'([^']+)'", self.planning_js)
        self.assertIsNotNone(m_def)
        def_color = m_def.group(1)

        # Contrast against dark surfaces and light background
        cr_dark = contrast_ratio(def_color, "#111a31")
        cr_oled = contrast_ratio(def_color, "#000000")
        cr_white = contrast_ratio(def_color, "#ffffff")

        self.assertGreaterEqual(cr_dark, 4.0, f"Defensive contrast against dark {cr_dark:.2f}:1 must be >= 4.0:1")
        self.assertGreaterEqual(cr_oled, 5.0, f"Defensive contrast against OLED black {cr_oled:.2f}:1 must be >= 5.0:1")
        self.assertGreaterEqual(cr_white, 3.0, f"Defensive contrast against white {cr_white:.2f}:1 must be >= 3.0:1")

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
