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

    def test_missing_market_is_explicitly_labeled_without_guessing_exchange(self) -> None:
        self.assertIn("fetch('/api/ipo/market'", self.compact_js)
        self.assertIn("const market = String(meta?.market || '').trim()", self.compact_js)
        self.assertIn("market || '시장 미확인'", self.compact_js)
        self.assertIn("ipo-market-unknown", self.compact_js)
        self.assertNotIn("market || 'KOSDAQ'", self.compact_js)

    def test_calculating_score_explains_coverage_and_core_missing_inputs(self) -> None:
        self.assertIn("institutional_competition_ratio: '기관경쟁률'", self.compact_js)
        self.assertIn("lockup_commitment_ratio: '의무보유확약률'", self.compact_js)
        self.assertIn("tradable_share_ratio: '유통가능주식비율'", self.compact_js)
        self.assertIn("pricing_discipline: '공모가 결정정보'", self.compact_js)
        self.assertIn("`데이터 ${coverage}%`", self.compact_js)
        self.assertIn("정식 점수 기준 75% 미만", self.compact_js)
        self.assertIn("ipo-score-diagnostic", self.compact_js)

    def test_refresh_invalidates_market_and_score_metadata_cache(self) -> None:
        self.assertIn("function invalidateIpoMetadata()", self.compact_js)
        self.assertIn("'ipoRefreshBtn'", self.compact_js)
        self.assertIn("metadataDirty = true", self.compact_js)

    def test_loader_registers_compact_view_once(self) -> None:
        self.assertIn("wealthIpoCompactViewScript", self.loader_js)
        self.assertIn("/static/wealth-ipo-compact-view.js?v=10.6g2", self.loader_js)


if __name__ == "__main__":
    unittest.main()
