from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_JS = ROOT / "app" / "static" / "wealth-period-filter-core.js"
FILTER_JS = ROOT / "app" / "static" / "wealth-income-period-broker-filter.js"
LOADER_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"


class IncomePeriodBrokerFilterFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.core_js = CORE_JS.read_text(encoding="utf-8")
        cls.filter_js = FILTER_JS.read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")

    def test_loader_registers_shared_core_before_income_filter(self) -> None:
        self.assertIn("wealthPeriodFilterCoreScript", self.loader_js)
        self.assertIn("/static/wealth-period-filter-core.js?v=10.6f1", self.loader_js)
        self.assertIn("wealthIncomePeriodBrokerFilterScript", self.loader_js)
        self.assertIn("/static/wealth-income-period-broker-filter.js?v=10.6f1", self.loader_js)
        self.assertLess(
            self.loader_js.index("wealthPeriodFilterCoreScript"),
            self.loader_js.index("wealthIncomePeriodBrokerFilterScript"),
        )

    def test_shared_period_core_exposes_common_year_month_scope(self) -> None:
        for marker in (
            "normalizeYear",
            "normalizeMonth",
            "matchesPeriod",
            "filterRecords",
            "availableYears",
            "fixedYearRange",
            "scopeLabel",
            "groupByMonth",
            "groupByYear",
        ):
            self.assertIn(marker, self.core_js)
        self.assertIn("window.WealthPeriodFilter", self.core_js)

    def test_income_filter_uses_shared_period_core(self) -> None:
        self.assertIn("const period = window.WealthPeriodFilter", self.filter_js)
        self.assertIn("period.availableYears", self.filter_js)
        self.assertIn("period.filterRecords", self.filter_js)
        self.assertIn("period.matchesPeriod", self.filter_js)
        self.assertIn("period.scopeLabel", self.filter_js)

    def test_dividend_year_interaction_clears_existing_month_scope(self) -> None:
        self.assertIn("clearDividendMonthForYearSelection", self.filter_js)
        self.assertIn("selectedDividendMonth = null", self.filter_js)
        self.assertIn("event.target?.id === 'dividendYearSelect'", self.filter_js)
        self.assertIn("renderActualDividends(actualDividendData)", self.filter_js)

    def test_dividend_year_options_are_derived_from_full_dividend_and_interest_history(self) -> None:
        self.assertIn("function allDividendIncomeRecords", self.filter_js)
        self.assertIn("rawData?.records", self.filter_js)
        self.assertIn("rawData?.interest_records", self.filter_js)
        self.assertIn("function dividendAvailableYears", self.filter_js)
        self.assertIn("period.availableYears(allDividendIncomeRecords(rawData)", self.filter_js)
        self.assertIn("&year=all", self.filter_js)

    def test_dividend_has_broker_filter_next_to_year_select(self) -> None:
        self.assertIn("dividendBrokerFilter", self.filter_js)
        self.assertIn("배당·이자 증권사 선택", self.filter_js)
        self.assertIn("전체 증권사", self.filter_js)
        self.assertIn("증권사 미지정", self.filter_js)
        self.assertIn("yearSelect.parentElement.appendChild(select)", self.filter_js)

    def test_dividend_broker_counts_follow_selected_year_scope(self) -> None:
        self.assertIn("function dividendBrokerChoices(rawData, year", self.filter_js)
        self.assertIn("period.filterRecords(allDividendIncomeRecords(rawData), { year, month: null })", self.filter_js)
        self.assertIn("dividendBrokerChoices(rawData, activeYear)", self.filter_js)

    def test_dividend_broker_filter_rebuilds_dividend_interest_and_time_buckets(self) -> None:
        self.assertIn("function buildDividendFilteredData", self.filter_js)
        for marker in (
            "total_actual_dividend_krw",
            "total_actual_interest_krw",
            "record_count",
            "interest_record_count",
            "monthly_schedule",
            "yearly_schedule",
            "interest_records",
        ):
            self.assertIn(marker, self.filter_js)
        self.assertIn("dividendRecordMatches(record, selectedYear, broker)", self.filter_js)
        self.assertIn("buildDividendMonthBucket(records, idx + 1)", self.filter_js)
        self.assertIn("buildDividendYearBucket(brokerScopedDividends, availableYear)", self.filter_js)

    def test_dividend_filter_keeps_backend_read_only_and_owner_scoped(self) -> None:
        self.assertIn("/api/actual-dividends?owner=${encodeURIComponent(activeOwner)}&year=all", self.filter_js)
        self.assertIn("dividendRequestSequence", self.filter_js)
        self.assertNotIn("method: 'POST'", self.filter_js)
        self.assertNotIn("method: 'DELETE'", self.filter_js)

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
        self.assertIn("buildBucket(records, 'year', availableYear)", self.filter_js)
        self.assertIn("period.filterRecords(records, scope)", self.filter_js)

    def test_broker_selection_is_reapplied_after_existing_render_flow(self) -> None:
        self.assertIn("window.renderRealizedPnl = function wealthRenderRealizedPnlWithBroker", self.filter_js)
        self.assertIn("latestRawPnlData = data", self.filter_js)
        self.assertIn("renderBrokerView(rawData)", self.filter_js)


if __name__ == "__main__":
    unittest.main()
