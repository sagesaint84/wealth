"""
Tests for Wealth UI/UX Batch 6: Responsive Secondary Navigation + Net Worth Chart No-Scroll Polish.
Covers:
1. Secondary navigation typography:
   - Desktop font-size increased to 14px across Stock Investment, Comprehensive Assets, and Money Log.
   - Mobile breakpoint (<= 760px) preserves 13px font-size for touch density.
   - Touch horizontal scroll, badges, button heights, and icons preserved.
2. Net Worth History chart no-scroll polish:
   - SVG width matches container width without forced minimum widths based on record count.
   - Elimination of fixed pixel width on SVG (width: 100%).
   - Container `#wealthHistoryPlot` removes overflow-x: auto.
   - Adaptive label density with collision avoidance for date and amount presentation text.
   - 100% of financial data points (circles, tooltips, polyline, delta bars) remain plotted.
"""

from pathlib import Path
import re
import unittest


class TestUIUXBatch6(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.layout_css = (cls.root / "app/static/wealth-layout.css").read_text(encoding="utf-8")
        cls.overrides_css = (cls.root / "app/static/wealth-overrides.css").read_text(encoding="utf-8")
        cls.layout_js = (cls.root / "app/static/wealth-layout.js").read_text(encoding="utf-8")
        cls.planning_js = (cls.root / "app/static/wealth-planning.js").read_text(encoding="utf-8")

    # ── 1. Secondary Navigation Typography Scale ────────────────────────────────
    def test_secondary_nav_desktop_font_size_14px(self) -> None:
        # Stock Investment secondary nav button font-size is 14px on desktop
        self.assertIn(".wealth-layout .wealth-invest-tabs button", self.layout_css)
        self.assertIn("font-size: 14px;", self.layout_css)

        # Shared rule for secondary navigation buttons specifies 14px
        shared_rule_match = re.search(
            r"\.wealth-layout\s+:is\(\.wealth-invest-tabs,\s*\.wealth-section-tabs\)\s*>\s*button,\s*\.wealth-layout\s+\.wealth-invest-tabs\s+button\s*\{([^}]+)\}",
            self.layout_css,
        )
        self.assertIsNotNone(shared_rule_match)
        self.assertIn("font-size: 14px;", shared_rule_match.group(1))

    def test_secondary_nav_mobile_font_size_13px_under_760px(self) -> None:
        # Mobile media query <= 760px preserves 13px scale
        mobile_blocks = re.findall(r"@media\s*\(\s*max-width\s*:\s*760px\s*\)\s*\{([^}]+(?:\{[^}]+\}[^}]*)*)\}", self.layout_css)
        self.assertTrue(len(mobile_blocks) > 0)
        found_mobile_override = any(
            ":is(.wealth-invest-tabs, .wealth-section-tabs)" in block and "font-size: 13px;" in block
            for block in mobile_blocks
        )
        self.assertTrue(found_mobile_override, "Mobile <= 760px override must restore font-size: 13px for secondary nav buttons")

    def test_secondary_nav_horizontal_scroll_and_touch_affordance_preserved(self) -> None:
        # Touch scrolling (overflow-x: auto) and non-wrapping preserved
        self.assertIn(".wealth-layout .wealth-invest-tabs {", self.layout_css)
        self.assertIn("overflow-x: auto;", self.layout_css)
        self.assertIn("scrollbar-width: thin;", self.layout_css)
        self.assertIn("white-space: nowrap;", self.layout_css)
        self.assertIn("min-height: 38px;", self.layout_css)
        self.assertIn("padding: 9px 13px;", self.layout_css)

    def test_secondary_nav_icons_and_labels_preserved(self) -> None:
        # Stock Investment tabs
        for tab in ("📊 포트폴리오", "🗺️ 히트맵", "🗓️ 주식기록", "🎯 전략 버킷", "🧾 절세계좌", "📋 보유종목"):
            self.assertIn(tab, self.planning_js)
        # Money Log tabs
        for tab in ("📈 실현손익", "💰 배당·이자", "🧾 가계부"):
            self.assertIn(tab, self.layout_js)
        # Comprehensive Assets tabs
        for tab in ("📈 증권", "🏦 은행", "🛡️ 보험", "🏠 부동산"):
            self.assertIn(tab, self.layout_js)

    # ── 2. Net Worth History Chart No-Scroll Polish ─────────────────────────────
    def test_chart_svg_width_fits_container_without_record_inflation(self) -> None:
        # Chart width is derived from containerWidth, NOT multiplied by records.length * minSpacing
        self.assertNotIn("records.length * minSpacing", self.planning_js)
        self.assertIn("const containerWidth = plot.clientWidth || 800;", self.planning_js)
        self.assertIn("const width = containerWidth;", self.planning_js)

    def test_chart_svg_has_responsive_width_and_no_fixed_pixel_style(self) -> None:
        # SVG style must be responsive (width:100%) and not style="width:${width}px"
        self.assertNotIn('style="width:${width}px', self.planning_js)
        self.assertIn('style="width:100%;height:250px;display:block"', self.planning_js)
        self.assertIn('viewBox="0 0 ${width} 250"', self.planning_js)

    def test_chart_css_eliminates_horizontal_overflow(self) -> None:
        # #wealthHistoryPlot must not have overflow-x: auto
        self.assertNotIn("#wealthHistoryPlot { min-width:0; overflow-x:auto;", self.layout_css)
        self.assertIn("#wealthHistoryPlot { min-width:0; overflow:hidden;", self.layout_css)
        # .wealth-history-chart must fit width 100% and not max-width: none
        self.assertIn(".wealth-history-chart { display:block; width:100%; max-width:100%;", self.layout_css)
        self.assertNotIn(".wealth-history-chart { display:block; height:250px; max-width:none;", self.layout_css)

    def test_chart_preserves_all_financial_data_points(self) -> None:
        # Plotted data circles, polyline, and titles must be rendered for all points
        self.assertIn('<circle cx="${p[0]}" cy="${p[1]}" r="4"', self.planning_js)
        self.assertIn('<title>${esc(records[i].date)} · 순자산 ${won(records[i].net_worth)}', self.planning_js)
        self.assertIn('<polyline points="${points.map(p=>p.join(\',\')).join(\' \')}"', self.planning_js)
        self.assertIn('class="wealth-history-bar', self.planning_js)

    def test_chart_adapts_label_density_with_collision_avoidance(self) -> None:
        # Label visibility calculation exists and keeps first and last
        self.assertIn("showLabels[0] = true;", self.planning_js)
        self.assertIn("showLabels[records.length - 1] = true;", self.planning_js)
        self.assertIn("minSpacing = 64;", self.planning_js)
        # Text elements are conditionally rendered based on showLabels
        self.assertIn("${showLabels[i] ?", self.planning_js)
        self.assertIn("font-size=\"10\"", self.planning_js)

    # ── 3. Batch 6.1 Secondary Nav Typography Consistency ──────────────────────
    def test_batch6_1_legacy_conflicts_removed_from_overrides_css(self) -> None:
        # .account-cat-tab must NOT be trapped in the legacy 29px/11.5px/line-height:1 standardization rule
        legacy_standard_match = re.search(
            r"/\* ── 탭 버튼 규격 표준화[^*]+\*/\s*([^{]+)\{([^}]+)\}",
            self.overrides_css,
        )
        self.assertIsNotNone(legacy_standard_match)
        self.assertNotIn(".account-cat-tab", legacy_standard_match.group(1))
        # .account-cat-tab must not specify stale font-size: 12.5px or font-weight: 600
        cat_tab_rule = re.search(r"\.account-cat-tab\s*\{([^}]+)\}", self.overrides_css)
        self.assertIsNotNone(cat_tab_rule)
        self.assertNotIn("font-size", cat_tab_rule.group(1))
        self.assertNotIn("font-weight", cat_tab_rule.group(1))

    def test_batch6_1_desktop_secondary_nav_typography_unified_14px_650_normal(self) -> None:
        # Desktop layout rules define font-size 14px, font-weight 650, line-height normal
        shared_rule_match = re.search(
            r"\.wealth-layout\s+:is\(\.wealth-invest-tabs,\s*\.wealth-section-tabs\)\s*>\s*button,\s*\.wealth-layout\s+\.wealth-invest-tabs\s+button\s*\{([^}]+)\}",
            self.layout_css,
        )
        self.assertIsNotNone(shared_rule_match)
        shared_content = shared_rule_match.group(1)
        self.assertIn("font-size: 14px;", shared_content)
        self.assertIn("font-weight: 650;", shared_content)
        self.assertIn("line-height: normal;", shared_content)

        # Explicit rule for .account-category-tabs > button
        cat_rule_match = re.search(
            r"\.wealth-layout\s+\.account-category-tabs\s*>\s*button\s*\{([^}]+)\}",
            self.layout_css,
        )
        self.assertIsNotNone(cat_rule_match)
        cat_content = cat_rule_match.group(1)
        self.assertIn("font-size: 14px;", cat_content)
        self.assertIn("font-weight: 650;", cat_content)
        self.assertIn("line-height: normal;", cat_content)

    def test_batch6_1_mobile_secondary_nav_typography_unified_13px_650_normal(self) -> None:
        # Extract full content of @media (max-width: 760px) blocks with brace matching
        def get_media_blocks(css: str, query: str) -> list[str]:
            idx = 0
            blocks = []
            while True:
                pos = css.find(query, idx)
                if pos == -1:
                    break
                open_brace = css.find("{", pos)
                if open_brace == -1:
                    break
                depth = 1
                curr = open_brace + 1
                while curr < len(css) and depth > 0:
                    if css[curr] == "{":
                        depth += 1
                    elif css[curr] == "}":
                        depth -= 1
                    curr += 1
                blocks.append(css[open_brace + 1 : curr - 1])
                idx = curr
            return blocks

        mobile_blocks = get_media_blocks(self.layout_css, "@media (max-width: 760px)")
        self.assertTrue(len(mobile_blocks) > 0)
        found_mobile_rule = any(
            ":is(.wealth-invest-tabs, .wealth-section-tabs)" in block
            and "font-size: 13px;" in block
            and "font-weight: 650;" in block
            and "line-height: normal;" in block
            for block in mobile_blocks
        )
        self.assertTrue(found_mobile_rule, "Mobile <= 760px override must set 13px / 650 / normal")

        # Mobile rule for .account-category-tabs must not shrink to 11px
        for block in mobile_blocks:
            if ".account-category-tabs" in block:
                cat_rules = re.findall(r"\.account-category-tabs[^{]*\{([^}]+)\}", block)
                for cr in cat_rules:
                    self.assertNotIn("font-size: 11px", cr)
        found_cat_mobile = any(
            ".account-category-tabs" in block
            and "font-size: 13px;" in block
            and "font-weight: 650;" in block
            and "line-height: normal;" in block
            for block in mobile_blocks
        )
        self.assertTrue(found_cat_mobile, "Mobile .account-category-tabs must maintain 13px / 650 / normal")

    def test_batch6_1_no_one_off_important_workaround_added(self) -> None:
        # Verify no hacky !important was added for secondary navigation typography
        self.assertNotIn(".account-category-tabs > button", self.overrides_css)
        cat_tab_rule = re.search(r"\.account-cat-tab\s*\{([^}]+)\}", self.overrides_css)
        if cat_tab_rule:
            self.assertNotIn("!important", cat_tab_rule.group(1))
        for selector in (
            r"\.wealth-layout\s+:is\(\.wealth-invest-tabs,\s*\.wealth-section-tabs\)\s*>\s*button",
            r"\.wealth-layout\s+\.account-category-tabs\s*>\s*button",
        ):
            match = re.search(rf"{selector}[^{{]*\{{([^}}]+)\}}", self.layout_css)
            if match:
                self.assertNotIn("!important", match.group(1))


if __name__ == "__main__":
    unittest.main()
