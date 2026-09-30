from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTENT_JS = ROOT / "app" / "static" / "wealth-pnl-year-intent.js"
LOADER_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"


class PnlYearIntentFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.intent_js = INTENT_JS.read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")

    def test_loader_registers_pnl_year_intent_after_shared_period_filter(self) -> None:
        self.assertIn("wealthPnlYearIntentScript", self.loader_js)
        self.assertIn("/static/wealth-pnl-year-intent.js?v=10.6f2", self.loader_js)
        self.assertLess(
            self.loader_js.index("wealthIncomePeriodBrokerFilterScript"),
            self.loader_js.index("wealthPnlYearIntentScript"),
        )

    def test_same_year_pointer_intent_clears_month_scope_immediately(self) -> None:
        self.assertIn("function clearPnlMonthForYearSelection", self.intent_js)
        self.assertIn("selectedPnlMonth = null", self.intent_js)
        self.assertIn("event.target?.id === 'pnlYearSelect'", self.intent_js)
        self.assertIn("document.addEventListener('pointerdown'", self.intent_js)
        self.assertIn("renderRealizedPnl(pnlData)", self.intent_js)

    def test_keyboard_year_intent_uses_same_annual_transition(self) -> None:
        self.assertIn("document.addEventListener('keydown'", self.intent_js)
        self.assertIn("event.key === 'Enter' || event.key === ' '", self.intent_js)
        self.assertIn("clearPnlMonthForYearSelection()", self.intent_js)

    def test_pnl_nav_sync_treats_null_month_as_annual_scope(self) -> None:
        self.assertIn("selectedPnlMonth === null", self.intent_js)
        self.assertIn("period.scopeLabel(year, null)", self.intent_js)
        self.assertIn("pickerEl.value = ''", self.intent_js)
        self.assertIn("window.syncPnlMonthNavUI = syncPnlPeriodNavUI", self.intent_js)

    def test_existing_month_navigation_remains_delegated_to_legacy_sync(self) -> None:
        self.assertIn("originalSyncPnlMonthNavUI", self.intent_js)
        self.assertIn("originalSyncPnlMonthNavUI?.()", self.intent_js)


if __name__ == "__main__":
    unittest.main()
