"""
Tests for Wealth UI/UX Batch 5: Visual Hierarchy & Consistency Polish.
Covers:
1. Net Worth History record card information hierarchy & semantic styling.
2. Secondary navigation typography consistency (13px scale across Stock, Assets, Money Log).
3. Strategy Bucket card visual color connection to donuts/legend.
"""

from pathlib import Path
import unittest


class TestUIUXBatch5(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.layout_css = (cls.root / "app/static/wealth-layout.css").read_text(encoding="utf-8")
        cls.layout_js = (cls.root / "app/static/wealth-layout.js").read_text(encoding="utf-8")
        cls.planning_js = (cls.root / "app/static/wealth-planning.js").read_text(encoding="utf-8")

    # ── 1. Net Worth History Record Card Hierarchy ────────────────────────────
    def test_record_card_markup_contains_semantic_amount_and_metadata_classes(self) -> None:
        # Check amounts container and semantic classes
        self.assertIn('class="wealth-history-record-amounts"', self.planning_js)
        self.assertIn('class="record-asset"', self.planning_js)
        self.assertIn('class="record-debt"', self.planning_js)
        # Check metadata spans
        self.assertIn('class="record-source"', self.planning_js)
        self.assertIn('class="record-memo"', self.planning_js)
        # Check primary date and net worth amount
        self.assertIn('class="wealth-history-record-head"', self.planning_js)
        self.assertIn('${won(r.net_worth)}', self.planning_js)
        # Check action buttons preserved
        self.assertIn('data-history-edit=', self.planning_js)
        self.assertIn('data-history-delete=', self.planning_js)

    def test_record_card_css_hierarchy_and_semantic_colors(self) -> None:
        # Amounts styling: horizontal separation and prominent font
        self.assertIn(".wealth-history-record-amounts {", self.layout_css)
        self.assertIn("justify-content:space-between", self.layout_css)
        # Total assets soft blue (#6ea6ec)
        self.assertIn(".wealth-history-record-amounts .record-asset { color:#6ea6ec;", self.layout_css)
        # Total liabilities restrained amber (#d6a85f)
        self.assertIn(".wealth-history-record-amounts .record-debt { color:#d6a85f;", self.layout_css)
        # Secondary metadata de-emphasized
        self.assertIn(".wealth-history-record-note {", self.layout_css)
        self.assertIn("flex-direction:column", self.layout_css)
        self.assertIn("color:var(--muted)", self.layout_css)

    # ── 2. Secondary Navigation Typography Consistency ─────────────────────────
    def test_secondary_navigation_shared_typography_scale(self) -> None:
        # 13px scale applied to Stock Investment, Comprehensive Assets, Money Log
        self.assertIn(".wealth-layout .wealth-invest-tabs button {", self.layout_css)
        self.assertIn("font-size: 13px;", self.layout_css)
        self.assertIn(".wealth-layout .wealth-section-tabs > button {", self.layout_css)
        # Shared selector rule unifying secondary navigation typography scale
        self.assertIn(".wealth-layout :is(.wealth-invest-tabs, .wealth-section-tabs) > button", self.layout_css)

    def test_secondary_navigation_touch_targets_and_icons_preserved(self) -> None:
        # Control min-height 38px and padding preserved
        self.assertIn("min-height: 38px;", self.layout_css)
        self.assertIn("padding: 9px 13px;", self.layout_css)
        # Stock Investment icons
        for tab in ("📊 포트폴리오", "🗺️ 히트맵", "🗓️ 주식기록", "🎯 전략 버킷", "🧾 절세계좌", "📋 보유종목"):
            self.assertIn(tab, self.planning_js)
        # Money Log icons
        for tab in ("📈 실현손익", "💰 배당·이자", "🧾 가계부"):
            self.assertIn(tab, self.layout_js)
        # Comprehensive Assets icons
        for tab in ("📈 증권", "🏦 은행", "🛡️ 보험", "🏠 부동산"):
            self.assertIn(tab, self.layout_js)

    # ── 3. Strategy Bucket Card Visual Color Connection ────────────────────────
    def test_bucket_cards_receive_bucket_color_property(self) -> None:
        # Card article template binds --bucket-color via bucketColor(b.id)
        self.assertIn('style="--bucket-color:${bucketColor(b.id)}"', self.planning_js)

    def test_bucket_cards_css_restrained_accent_and_background(self) -> None:
        # Left accent border using bucket color
        self.assertIn("border-left: 4px solid var(--bucket-color", self.layout_css)
        # Soft background tint
        self.assertIn("background: color-mix(in srgb, var(--bucket-color, transparent) 4%, var(--panel));", self.layout_css)
        # Title tint
        self.assertIn(".wealth-bucket-cards h4 {", self.layout_css)
        self.assertIn("color-mix(in srgb, var(--bucket-color, var(--text)) 75%, var(--text))", self.layout_css)

    def test_unclassified_bucket_neutral_color_preserved(self) -> None:
        # bucketColor returns '#697386' for __unclassified__
        self.assertIn("if(id === '__unclassified__') return '#697386';", self.planning_js)


if __name__ == "__main__":
    unittest.main()
