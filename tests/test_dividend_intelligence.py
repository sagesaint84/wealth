from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from app.services.dividend_intelligence import (
    build_dividend_intelligence_summary,
    dispatch_family_financial_income_alerts,
    dispatch_scheduled_dividend_intelligence_alerts,
)
from app.services.dividend_intelligence_async import (
    dispatch_scheduled_family_financial_income_alerts,
)


class DividendIntelligenceSummaryTests(unittest.TestCase):
    def _summary(self) -> dict:
        return {
            "total_annual_dividend_krw": 1000,
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "currency": "KRW",
                    "annual_payout_krw": 900,
                    "forecast_source": {
                        "numeric_source": "opendart_confirmed_disclosure",
                        "official_data_available": True,
                        "confirmed_amount": True,
                        "confirmed_numeric_override": True,
                        "structured_decision_disclosure": {
                            "receipt_no": "202609270001",
                            "viewer_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=202609270001",
                        },
                    },
                }
            ],
            "portfolio_after_tax": {
                "calculation_status": "partial",
                "gross_annual_dividend_krw": 1000,
                "calculable_after_known_tax_cash_krw": 761,
                "unattributed_annual_dividend_krw": 100,
                "instruments": [
                    {
                        "code": "005930",
                        "name": "삼성전자",
                        "currency": "KRW",
                        "display_asset_class": "국내 배당주",
                        "gross_annual_dividend_krw": 900,
                        "known_tax_krw": 139,
                        "after_known_tax_cash_krw": 761,
                        "gross_yield_market_pct": 2.0,
                        "after_known_tax_yield_market_pct": 1.69,
                        "gross_yield_cost_pct": 2.2,
                        "after_known_tax_yield_cost_pct": 1.86,
                        "calculation_status": "calculated",
                    }
                ],
            },
        }

    def _holdings(self) -> list[dict]:
        return [
            {
                "code": "005930",
                "currency": "KRW",
                "quantity": 60,
                "account_id": "a",
                "account_name": "ISA",
                "owner": "아빠",
                "market_value_krw": 30000,
                "cost_value_krw": 25000,
            },
            {
                "code": "005930",
                "currency": "KRW",
                "quantity": 40,
                "account_id": "b",
                "account_name": "일반",
                "owner": "아빠",
                "market_value_krw": 20000,
                "cost_value_krw": 18000,
            },
        ]

    def test_preserves_residual_and_adds_trust_and_contribution(self) -> None:
        result = build_dividend_intelligence_summary(
            self._summary(), self._holdings(), username=None, as_of=date(2026, 9, 28)
        )

        self.assertEqual(result["trust"]["unattributed_residual_krw"], 100)
        self.assertFalse(result["trust"]["residual_assigned_to_instrument"])
        self.assertEqual(result["trust"]["official_confirmed_applied_count"], 1)
        row = result["instruments"][0]
        self.assertEqual(row["gross_portfolio_contribution_pct"], 90.0)
        self.assertEqual(row["calculable_after_known_tax_contribution_pct"], 100.0)
        self.assertEqual(row["forecast_evidence"]["level"], "official_confirmed_applied")
        self.assertTrue(row["forecast_evidence"]["evidence_url"].startswith("https://"))
        self.assertTrue(result["contracts"]["canonical_gross_total_unchanged"])

    def test_account_split_is_quantity_estimate_and_sums_exactly(self) -> None:
        result = build_dividend_intelligence_summary(
            self._summary(), self._holdings(), username=None, as_of=date(2026, 9, 28)
        )
        row = result["instruments"][0]
        accounts = row["accounts"]

        self.assertEqual(row["account_attribution_status"], "estimated_current_holding_allocation")
        self.assertEqual(sum(item["gross_annual_dividend_krw"] for item in accounts), 900)
        self.assertEqual(sum(item["known_tax_krw"] for item in accounts), 139)
        self.assertEqual(sum(item["after_known_tax_cash_krw"] for item in accounts), 761)
        self.assertEqual([item["quantity_share_pct"] for item in accounts], [60.0, 40.0])
        self.assertTrue(all(item["attribution_basis"] == "current_holding_quantity" for item in accounts))
        self.assertTrue(all(item["entitlement_confirmed"] is False for item in accounts))

    @patch("app.services.dividend_records.read_dividend_records", return_value=[])
    @patch("app.services.dividend_forecast_snapshots.evaluate_dividend_forecast_snapshot")
    @patch("app.services.dividend_forecast_snapshots.list_dividend_forecast_snapshots")
    def test_accuracy_reuses_point_in_time_evaluator(
        self, list_snapshots, evaluate, _read_records
    ) -> None:
        list_snapshots.return_value = [
            {
                "id": "snap-1",
                "owner": "모두",
                "as_of_date": "2026-06-30",
                "captured_at": "2026-06-30T21:00:00+09:00",
            }
        ]
        evaluate.return_value = {
            "status": "ok",
            "snapshot_id": "snap-1",
            "snapshot_as_of_date": "2026-06-30",
            "through_date": "2026-09-28",
            "evaluated_months": ["2026-07", "2026-08"],
            "amount_accuracy_complete": True,
            "mae_krw": 1000,
            "wape_percent": 5.5,
            "absolute_error_krw": 2000,
            "predicted_remaining_krw": 40000,
            "actual_comparable_gross_krw": 38000,
            "gross_comparable_record_count": 2,
            "cash_only_record_count": 0,
            "forecast_attribution_complete": True,
            "official_event_identity_match_count": 1,
            "source_metrics": {"opendart_confirmed": {"sample_count": 1}},
        }

        result = build_dividend_intelligence_summary(
            self._summary(), self._holdings(), username="tester", as_of=date(2026, 9, 28)
        )
        accuracy = result["accuracy"]
        self.assertEqual(accuracy["status"], "ready")
        self.assertEqual(accuracy["evaluated_month_count"], 2)
        self.assertEqual(accuracy["mae_krw"], 1000)
        self.assertEqual(accuracy["wape_percent"], 5.5)
        self.assertTrue(accuracy["historical_point_in_time_only"])
        self.assertTrue(accuracy["current_month_excluded"])
        evaluate.assert_called_once()


class DividendIntelligenceAlertTests(unittest.TestCase):
    @patch("app.services.dividend_intelligence._alert_opted_in", return_value=False)
    def test_scheduled_alerts_are_opt_in(self, _enabled) -> None:
        result = dispatch_scheduled_dividend_intelligence_alerts(
            "tester", {"trigger": "scheduled", "as_of_date": "2026-09-28"}
        )
        self.assertEqual(result["status"], "disabled")

    @patch("app.services.dividend_intelligence._dispatch_events")
    @patch("app.services.dividend_intelligence._alert_opted_in", return_value=True)
    def test_official_alert_uses_existing_event_identity(self, _enabled, dispatch) -> None:
        dispatch.return_value = {"status": "sent", "sent_count": 1}
        snapshot = {
            "trigger": "scheduled",
            "as_of_date": "2026-09-28",
            "monthly_schedule": [
                {
                    "month": 10,
                    "items": [
                        {
                            "code": "005930",
                            "name": "삼성전자",
                            "payout_krw": 10000,
                            "forecast_source": "opendart_confirmed_disclosure",
                            "event_identity": "dividend:v1:005930:record:2026-09-30",
                            "event_identity_confidence": "official",
                            "record_date": "2026-09-30",
                            "payment_date": "2026-10-20",
                            "receipt_no": "202609270001",
                        }
                    ],
                }
            ],
            "holding_forecasts": [],
        }
        result = dispatch_scheduled_dividend_intelligence_alerts("tester", snapshot)
        self.assertEqual(result["status"], "sent")
        events = dispatch.call_args.args[1]
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0].event_key,
            "dividend_intelligence:confirmed:dividend:v1:005930:record:2026-09-30",
        )
        self.assertFalse(events[0].metadata["entitlement_confirmed"])

    @patch("app.services.dividend_intelligence._dispatch_events")
    @patch("app.services.dividend_intelligence._alert_opted_in", return_value=True)
    def test_family_threshold_alerts_ignore_family_reference_and_aggregate_owner(
        self, _enabled, dispatch
    ) -> None:
        dispatch.return_value = {"status": "sent", "sent_count": 1}
        family_risk = {
            "year": 2026,
            "family_reference": {
                "projected_gross_screening_income_krw": 99000000,
                "statutory_threshold_applied": False,
            },
            "members": [
                {
                    "owner": "아빠",
                    "projected_gross_screening_income_krw": 12000000,
                    "thresholds": {
                        "watch": {"at_or_above": True, "threshold_krw": 10000000},
                        "comprehensive_tax": {
                            "at_or_above": False,
                            "exceeded": False,
                            "threshold_krw": 20000000,
                            "remaining_krw": 8000000,
                        },
                    },
                },
                {
                    "owner": "모두",
                    "projected_gross_screening_income_krw": 99000000,
                    "thresholds": {
                        "watch": {"at_or_above": True, "threshold_krw": 10000000},
                        "comprehensive_tax": {
                            "at_or_above": True,
                            "exceeded": True,
                            "threshold_krw": 20000000,
                            "remaining_krw": 0,
                        },
                    },
                },
            ],
        }
        dispatch_family_financial_income_alerts("tester", family_risk)
        events = dispatch.call_args.args[1]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].metadata["owner"], "아빠")
        self.assertTrue(events[0].metadata["individual_threshold_only"])


class DividendIntelligenceAsyncAlertTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.dividend_intelligence_async._enabled", return_value=True)
    @patch(
        "app.services.tax.family_financial_income.get_family_financial_income_risk_for_user",
        new_callable=AsyncMock,
    )
    @patch("app.services.dividend_intelligence.dispatch_family_financial_income_alerts")
    async def test_async_bridge_reuses_b1_family_risk(
        self, dispatch, get_risk, _enabled
    ) -> None:
        get_risk.return_value = {"year": 2026, "members": []}
        dispatch.return_value = {"status": "no_new_events", "sent_count": 0}

        result = await dispatch_scheduled_family_financial_income_alerts(
            "tester", as_of="2026-09-28"
        )

        self.assertEqual(result["status"], "no_new_events")
        get_risk.assert_awaited_once_with("tester", as_of="2026-09-28")
        dispatch.assert_called_once_with("tester", {"year": 2026, "members": []})


if __name__ == "__main__":
    unittest.main()
