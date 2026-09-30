from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILTER_JS = ROOT / "app" / "static" / "wealth-income-period-broker-filter.js"
LOADER_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"


class IncomePeriodBrokerFilterFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.filter_js = FILTER_JS.read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")

    def test_loader_registers_versioned_income_filter_script_once(self) -> None:
        self.assertIn("wealthIncomePeriodBrokerFilterScript", self.loader_js)
        self.assertIn("/static/wealth-income-period-broker-filter.js?v=10.6d1", self.loader_js)

    def test_dividend_year_interaction_clears_existing_month_scope(self) -> None:
        self.assertIn("clearDividendMonthForYearSelection", self.filter_js)
        self.assertIn("selectedDividendMonth = null", self.filter_js)
        self.assertIn("event.target?.id === 'dividendYearSelect'", self.filter_js)
        self.assertIn("renderActualDividends(actualDividendData)", self.filter_js)

    def test_realized_pnl_has_broker_filter_next_to_year_select(self) -> None:
        self.assertIn("pnlBrokerFilter", self.filter_js)
        self.assertIn("전체 증권사", self.filter_js)
        self.assertIn("실현손익 증권사 선택", self.filter_js)
        self.assertIn("yearSelect.parentElement.appendChild(select)", self.filter_js)

    def test_broker_filter_uses_existing_record_broker_without_backend_mutation(self) -> None:
        self.assertIn("return text(record?.broker)", self.filter_js)
        self.assertIn("sourceRecords.filter((record) => brokerMatches(record, selectedBroker))", self.filter_js)
        self.assertNotIn("/api/realized-pnl?", self.filter_js)
        self.assertNotIn("method: 'POST'", self.filter_js)

    def test_broker_filter_rebuilds_summary_and_time_buckets(self) -> None:
        for marker in (
            "total_pnl_krw",
            "total_win_krw",
            "total_loss_krw",
            "win_rate",
            "record_count",
            "monthly_schedule",
            "yearly_schedule",
        ):
            self.assertIn(marker, self.filter_js)
        self.assertIn("buildBucket(records, 'month', idx + 1)", self.filter_js)
        self.assertIn("buildBucket(records, 'year', year)", self.filter_js)

    def test_broker_selection_is_reapplied_after_existing_render_flow(self) -> None:
        self.assertIn("window.renderRealizedPnl = function wealthRenderRealizedPnlWithBroker", self.filter_js)
        self.assertIn("latestRawPnlData = data", self.filter_js)
        self.assertIn("renderBrokerView(rawData)", self.filter_js)


if __name__ == "__main__":
    unittest.main()
