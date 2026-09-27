from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.services.dividend_forecast_snapshots import (
    DividendForecastSnapshotStorageError,
    build_dividend_forecast_snapshot,
    evaluate_dividend_forecast_snapshot,
    list_dividend_forecast_snapshots,
    upsert_dividend_forecast_snapshot,
)


def _forecast() -> dict:
    return {
        "total_annual_dividend_krw": 1_200_000,
        "monthly_avg_dividend_krw": 100_000,
        "portfolio_yield": 3.5,
        "dividend_paying_count": 1,
        "forecast_source_policy": {"status": "ok"},
        "holding_dividends": [
            {
                "code": "005930",
                "name": "삼성전자",
                "currency": "KRW",
                "quantity": 10,
                "annual_div_per_share": 120_000,
                "annual_payout_orig": 1_200_000,
                "annual_payout_krw": 1_200_000,
                "payout_months": [10],
                "is_etf": False,
                "forecast_source": {
                    "numeric_source": "opendart_confirmed_disclosure",
                    "confirmed_amount": True,
                },
            }
        ],
        "monthly_schedule": [
            {
                "month": month,
                "total_krw": 1_200_000 if month == 10 else 0,
                "items": (
                    [
                        {
                            "code": "005930",
                            "name": "삼성전자",
                            "quantity": 10,
                            "currency": "KRW",
                            "payout_orig": 1_200_000,
                            "payout_krw": 1_200_000,
                            "forecast_source": "opendart_confirmed_disclosure",
                            "event_identity": "dividend:v1:005930:record:2026-08-31",
                            "event_identity_confidence": "official",
                            "record_date": "2026-08-31",
                            "payment_date": "2026-10-05",
                            "quantity_basis": "current_holding",
                            "entitlement_confirmed": False,
                        },
                        {
                            "code": "AAPL",
                            "name": "Apple",
                            "quantity": 2,
                            "currency": "USD",
                            "payout_orig": 10,
                            "payout_krw": 14_000,
                        },
                    ]
                    if month == 10
                    else []
                ),
            }
            for month in range(1, 13)
        ],
    }


def _snapshot() -> dict:
    return build_dividend_forecast_snapshot(
        _forecast(),
        [
            {
                "code": "005930",
                "name": "삼성전자",
                "currency": "KRW",
                "quantity": 10,
                "account_id": "secret-account",
            }
        ],
        as_of_date="2026-09-27",
        captured_at="2026-09-27T21:00:00+09:00",
        owner="모두",
        source="daily_close",
        trigger="scheduled",
        capture_fx_rate_usd_krw=1400,
    )


class DividendForecastSnapshotStorageTests(unittest.TestCase):
    def test_storage_round_trip_and_sensitive_portfolio_fields_are_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "app.services.dividend_forecast_snapshots._get_user_dir",
                return_value=root,
            ):
                stored = upsert_dividend_forecast_snapshot(_snapshot(), username="alice")
                records = list_dividend_forecast_snapshots(username="alice")
                raw = json.loads((root / "dividend_forecast_snapshots.json").read_text("utf-8"))

        self.assertEqual(stored["schema_version"], 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], stored)
        self.assertEqual(raw["schema_version"], 1)
        self.assertNotIn("account_id", records[0]["portfolio_basis"][0])
        self.assertEqual(
            records[0]["monthly_schedule"][9]["items"][0]["event_identity"],
            "dividend:v1:005930:record:2026-08-31",
        )
        self.assertNotIn("event_identity", records[0]["monthly_schedule"][9]["items"][1])

    def test_same_day_owner_upserts_and_next_day_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "app.services.dividend_forecast_snapshots._get_user_dir",
                return_value=root,
            ):
                first = _snapshot()
                upsert_dividend_forecast_snapshot(first)
                replacement = {
                    **first,
                    "id": "replacement-id",
                    "captured_at": "2026-09-27T22:00:00+09:00",
                }
                stored = upsert_dividend_forecast_snapshot(replacement)
                next_day = {**first, "id": "next-day", "as_of_date": "2026-09-28"}
                upsert_dividend_forecast_snapshot(next_day)
                records = list_dividend_forecast_snapshots()

        self.assertEqual(len(records), 2)
        day_one = next(item for item in records if item["as_of_date"] == "2026-09-27")
        self.assertEqual(day_one["id"], first["id"])
        self.assertEqual(day_one["captured_at"], stored["captured_at"])

    def test_write_guard_and_atomic_temp_replace_are_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch(
                    "app.services.dividend_forecast_snapshots._get_user_dir",
                    return_value=root,
                ),
                patch(
                    "app.services.dividend_forecast_snapshots.assert_write_allowed"
                ) as guard,
            ):
                upsert_dividend_forecast_snapshot(_snapshot())

        guard.assert_called_once_with(root / "dividend_forecast_snapshots.json")
        self.assertFalse((root / "dividend_forecast_snapshots.json.tmp").exists())

    def test_malformed_storage_fails_closed_instead_of_becoming_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dividend_forecast_snapshots.json").write_text("{broken", "utf-8")
            with patch(
                "app.services.dividend_forecast_snapshots._get_user_dir",
                return_value=root,
            ):
                with self.assertRaises(DividendForecastSnapshotStorageError):
                    list_dividend_forecast_snapshots()
                with self.assertRaises(DividendForecastSnapshotStorageError):
                    upsert_dividend_forecast_snapshot(_snapshot())


class DividendForecastSnapshotEvaluatorTests(unittest.TestCase):
    def test_current_incomplete_month_is_excluded_then_completed_month_is_evaluated(self):
        snapshot = _snapshot()
        actual = [{"date": "2026-10-05", "code": "005930", "amount_krw": 900_000}]

        incomplete = evaluate_dividend_forecast_snapshot(
            snapshot, actual, through_date="2026-10-15"
        )
        complete = evaluate_dividend_forecast_snapshot(
            snapshot, actual, through_date="2026-11-01"
        )

        self.assertEqual(incomplete["evaluated_months"], [])
        self.assertEqual(incomplete["status"], "evaluation_horizon_unavailable")
        self.assertEqual(complete["evaluated_months"], ["2026-10"])
        self.assertTrue(complete["monthly_results"][0]["payment_month_hit"])

    def test_cash_only_actual_supports_timing_but_not_gross_accuracy(self):
        result = evaluate_dividend_forecast_snapshot(
            _snapshot(),
            [{"date": "2026-10-05", "code": "005930", "amount_krw": 900_000}],
            through_date="2026-11-01",
        )
        self.assertEqual(result["gross_comparable_record_count"], 0)
        self.assertEqual(result["cash_only_record_count"], 1)
        self.assertFalse(result["amount_accuracy_complete"])
        self.assertIsNone(result["absolute_error_krw"])
        self.assertIsNone(result["mae_krw"])
        self.assertIsNone(result["wape_percent"])
        self.assertTrue(result["monthly_results"][0]["payment_month_hit"])

    def test_explicit_gross_actual_is_included_in_amount_accuracy(self):
        result = evaluate_dividend_forecast_snapshot(
            _snapshot(),
            [
                {
                    "date": "2026-10-05",
                    "code": "005930",
                    "currency": "KRW",
                    "gross_amount": 1_000_000,
                    "amount_krw": 850_000,
                    "event_identity": "dividend:v1:005930:record:2026-08-31",
                }
            ],
            through_date="2026-11-01",
        )
        self.assertEqual(result["gross_comparable_record_count"], 1)
        self.assertEqual(result["cash_only_record_count"], 0)
        self.assertTrue(result["amount_accuracy_complete"])
        self.assertEqual(result["predicted_remaining_krw"], 1_214_000)
        self.assertEqual(result["actual_comparable_gross_krw"], 1_000_000)
        self.assertEqual(result["absolute_error_krw"], 214_000)
        self.assertEqual(result["official_event_identity_match_count"], 1)

    def test_usd_cash_only_is_not_compared_to_gross_forecast(self):
        result = evaluate_dividend_forecast_snapshot(
            _snapshot(),
            [
                {
                    "date": "2026-10-10",
                    "code": "AAPL",
                    "currency": "USD",
                    "amount": 8,
                    "amount_krw": 11_200,
                }
            ],
            through_date="2026-11-01",
        )
        self.assertEqual(result["cash_only_record_count"], 1)
        self.assertIsNone(result["mae_krw"])

    def test_evaluator_uses_only_snapshot_metadata_without_look_ahead(self):
        snapshot = _snapshot()
        result = evaluate_dividend_forecast_snapshot(
            snapshot,
            [
                {
                    "date": "2026-10-05",
                    "code": "005930",
                    "currency": "KRW",
                    "gross_amount": 1_000_000,
                    "forecast_source": "kind_etf_distribution",
                    "later_official_metadata": True,
                }
            ],
            through_date="2026-11-01",
        )
        sources = {item["source_class"] for item in result["monthly_results"]}
        self.assertEqual(sources, {"opendart_confirmed", "unknown"})
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("later_official_metadata", serialized)
        self.assertNotIn("kind_confirmed", sources)
        self.assertEqual(
            result["monthly_results"][0]["event_identity"],
            "dividend:v1:005930:record:2026-08-31",
        )

    def test_missing_historical_snapshot_is_explicitly_unavailable(self):
        result = evaluate_dividend_forecast_snapshot(
            None, [], through_date="2026-11-01"
        )
        self.assertEqual(result["status"], "historical_point_in_time_accuracy_unavailable")


if __name__ == "__main__":
    unittest.main()
