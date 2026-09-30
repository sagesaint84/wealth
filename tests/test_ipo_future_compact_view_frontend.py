from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPACT_JS = ROOT / "app" / "static" / "wealth-ipo-compact-view.js"
LOADER_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"
IPO_JS = ROOT / "app" / "static" / "wealth-ipo.js"


class IpoFutureCompactViewFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compact_js = COMPACT_JS.read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")
        cls.ipo_js = IPO_JS.read_text(encoding="utf-8")

    def test_existing_ipo_state_exposes_month_navigation_hooks(self) -> None:
        self.assertIn("window.WealthIpoState", self.ipo_js)
        self.assertIn("getHistoryYear", self.ipo_js)
        self.assertIn("getHistoryMonth", self.ipo_js)
        self.assertIn("renderIpoList", self.ipo_js)
        self.assertIn("shiftIpoMonth", self.ipo_js)

    def test_all_view_can_advance_past_current_kst_month(self) -> None:
        self.assertIn("state.getFilterGroup?.() !== 'ALL'", self.compact_js)
        self.assertIn("event.stopImmediatePropagation()", self.compact_js)
        self.assertIn("date.shiftIpoMonth(year, month, 1)", self.compact_js)
        self.assertIn("state.setMonthExplicitlySelected?.(true)", self.compact_js)
        self.assertIn("state.renderIpoList?.()", self.compact_js)
        self.assertIn("nextButton.disabled = false", self.compact_js)

    def test_compact_cards_use_one_row_and_hide_details_until_expanded(self) -> None:
        self.assertIn("grid-template-columns: minmax(0, 1fr) !important", self.compact_js)
        self.assertIn(".ipo-card-body", self.compact_js)
        self.assertIn(".ipo-card-footer", self.compact_js)
        self.assertIn(".ipo-card-expanded", self.compact_js)
        self.assertIn("'자세히'", self.compact_js)
        self.assertIn("'접기'", self.compact_js)
        self.assertIn("aria-expanded", self.compact_js)

    def test_compact_state_survives_ipo_rerender(self) -> None:
        self.assertIn("const expandedIpoIds = new Set()", self.compact_js)
        self.assertIn("MutationObserver", self.compact_js)
        self.assertIn("expandedIpoIds.has(ipoId)", self.compact_js)

    def test_loader_registers_compact_view_once(self) -> None:
        self.assertIn("wealthIpoCompactViewScript", self.loader_js)
        self.assertIn("/static/wealth-ipo-compact-view.js?v=10.6g1", self.loader_js)


if __name__ == "__main__":
    unittest.main()
