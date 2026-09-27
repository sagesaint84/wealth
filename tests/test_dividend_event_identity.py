from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.dividend_event_identity import (
    build_dividend_event_identity,
    normalize_dividend_code,
)
from app.services.dividend_records import (
    create_dividend_record,
    read_dividend_records,
    update_dividend_record,
)
from app.services.tax.financial_income import build_financial_income_projection
from app.services.toss_wts_income import map_toss_wts_income_row


def _actual(*records: dict) -> dict:
    return {
        "year": "2026",
        "total_actual_dividend_krw": sum(
            float(record.get("amount_krw", 0)) for record in records
        ),
        "total_actual_interest_krw": 0,
        "record_count": len(records),
        "interest_record_count": 0,
        "records": list(records),
        "interest_records": [],
    }


def _schedule(*, october_total: float, october_items: list[dict]) -> list[dict]:
    return [
        {
            "month": month,
            "total_krw": october_total if month == 10 else 0,
            "items": october_items if month == 10 else [],
        }
        for month in range(1, 13)
    ]


def _official_item(**overrides: object) -> dict:
    item = {
        "code": "005930",
        "payout_krw": 300_000,
        "event_identity": "dividend:v1:005930:record:2026-08-31",
        "event_identity_confidence": "official",
        "record_date": "2026-08-31",
        "payment_date": "2026-10-05",
        "forecast_source": "opendart_confirmed_disclosure",
        "quantity_basis": "current_holding",
        "entitlement_confirmed": False,
    }
    item.update(overrides)
    return item


class DividendEventIdentityTests(unittest.TestCase):
    def test_broker_prefixed_alphanumeric_krx_short_code_is_normalized(self):
        self.assertEqual(normalize_dividend_code("A0005G0"), "0005G0")
        self.assertEqual(normalize_dividend_code("A005930"), "005930")
        self.assertEqual(normalize_dividend_code("AAPL"), "AAPL")
        self.assertEqual(normalize_dividend_code("AABCDEF"), "AABCDEF")

    def test_alphanumeric_krx_identity_matches_without_broker_prefix(self):
        prefixed = build_dividend_event_identity(
            code="A0005G0",
            record_date="2026-07-31",
            source="kind",
            source_event_id="20260729000913",
        )
        short = build_dividend_event_identity(
            code="0005G0",
            record_date="2026-07-31",
            source="kind",
            source_event_id="20260729000913",
        )
        self.assertEqual(prefixed, "dividend:v1:0005G0:record:2026-07-31")
        self.assertEqual(prefixed, short)

    def test_record_date_identity_is_stable_across_correction_receipts(self):
        first = build_dividend_event_identity(
            code="005930",
            record_date="2026-08-31",
            source="opendart",
            source_event_id="20260915001234",
        )
        corrected = build_dividend_event_identity(
            code="A005930",
            record_date="2026-08-31",
            source="opendart",
            source_event_id="20260920009999",
        )
        self.assertEqual(first, "dividend:v1:005930:record:2026-08-31")
        self.assertEqual(corrected, first)

    def test_different_record_dates_are_different_economic_events(self):
        first = build_dividend_event_identity(
            code="005930", record_date="2026-08-31", source="opendart"
        )
        second = build_dividend_event_identity(
            code="005930", record_date="2026-11-30", source="opendart"
        )
        self.assertNotEqual(first, second)

    def test_receipt_fallback_requires_trusted_parts(self):
        self.assertEqual(
            build_dividend_event_identity(
                code="379800",
                source="kind",
                source_event_id="20260729000913",
            ),
            "dividend:v1:kind:379800:receipt:20260729000913",
        )
        self.assertIsNone(
            build_dividend_event_identity(
                code="379800", source="naver", source_event_id="guessed"
            )
        )


class DividendProjectionDedupTests(unittest.TestCase):
    def test_exact_payment_date_matches_broker_prefixed_alphanumeric_krx_code(self):
        result = build_financial_income_projection(
            _actual(
                {"date": "2026-10-05", "code": "A0005G0", "amount_krw": 250_000}
            ),
            {
                "monthly_schedule": _schedule(
                    october_total=300_000,
                    october_items=[_official_item(code="0005G0")],
                )
            },
            as_of="2026-09-27",
        )
        self.assertEqual(result["forecast_basis"]["dividend_event_dedup_applied_count"], 1)
        self.assertEqual(
            result["components"]["future_months_estimated_dividend_gross_krw"], 0
        )

    def test_exact_identity_dedups_across_actual_and_forecast_months(self):
        item = _official_item()
        result = build_financial_income_projection(
            _actual(
                {
                    "date": "2026-09-20",
                    "code": "005930",
                    "amount_krw": 250_000,
                    "event_identity": item["event_identity"],
                }
            ),
            {"monthly_schedule": _schedule(october_total=300_000, october_items=[item])},
            as_of="2026-09-27",
        )
        self.assertEqual(
            result["components"]["future_months_estimated_dividend_gross_krw"], 0
        )
        self.assertEqual(result["forecast_basis"]["dividend_event_dedup_applied_count"], 1)
        self.assertEqual(
            result["forecast_basis"]["dividend_event_dedup_amount_krw"], 300_000
        )

    def test_exact_official_payment_date_matches_without_actual_identity(self):
        result = build_financial_income_projection(
            _actual(
                {"date": "2026-10-05", "code": "A005930", "amount_krw": 250_000}
            ),
            {
                "monthly_schedule": _schedule(
                    october_total=300_000, october_items=[_official_item()]
                )
            },
            as_of="2026-09-27",
        )
        self.assertEqual(result["forecast_basis"]["dividend_event_dedup_applied_count"], 1)

    def test_heuristic_month_mismatch_is_not_deduped(self):
        heuristic = {"code": "005930", "payout_krw": 300_000}
        result = build_financial_income_projection(
            _actual(
                {"date": "2026-09-20", "code": "005930", "amount_krw": 300_000}
            ),
            {
                "monthly_schedule": _schedule(
                    october_total=300_000, october_items=[heuristic]
                )
            },
            as_of="2026-09-27",
        )
        self.assertEqual(
            result["components"]["future_months_estimated_dividend_gross_krw"],
            300_000,
        )
        self.assertEqual(result["forecast_basis"]["dividend_event_dedup_applied_count"], 0)
        self.assertFalse(result["data_quality"]["heuristic_forecast_event_dedup_applied"])

    def test_one_actual_consumes_only_one_forecast_event(self):
        items = [
            _official_item(payment_date="2026-09-20"),
            _official_item(
                event_identity="dividend:v1:005930:record:2026-09-30",
                record_date="2026-09-30",
                payment_date="2026-09-20",
                payout_krw=200_000,
            ),
        ]
        result = build_financial_income_projection(
            _actual(
                {"date": "2026-09-20", "code": "005930", "amount_krw": 250_000}
            ),
            {"monthly_schedule": _schedule(october_total=500_000, october_items=items)},
            as_of="2026-09-01",
        )
        self.assertEqual(result["forecast_basis"]["dividend_event_dedup_applied_count"], 1)
        self.assertIn(
            result["components"]["future_months_estimated_dividend_gross_krw"],
            {200_000, 300_000},
        )

    def test_bucket_residual_is_preserved(self):
        result = build_financial_income_projection(
            _actual(
                {
                    "date": "2026-09-20",
                    "code": "005930",
                    "amount_krw": 250_000,
                    "event_identity": "dividend:v1:005930:record:2026-08-31",
                }
            ),
            {
                "monthly_schedule": _schedule(
                    october_total=1_000_000, october_items=[_official_item()]
                )
            },
            as_of="2026-09-27",
        )
        self.assertEqual(
            result["components"]["future_months_estimated_dividend_gross_krw"],
            700_000,
        )

    def test_schedule_without_event_metadata_is_unchanged(self):
        result = build_financial_income_projection(
            _actual(),
            {
                "monthly_schedule": _schedule(
                    october_total=1_000_000,
                    october_items=[{"code": "005930", "payout_krw": 300_000}],
                )
            },
            as_of="2026-09-27",
        )
        self.assertEqual(
            result["components"]["future_months_estimated_dividend_gross_krw"],
            1_000_000,
        )


class DividendRecordEventMetadataTests(unittest.TestCase):
    def test_create_update_read_round_trip_optional_event_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "app.services.dividend_records._get_user_dir", return_value=root
            ):
                created = create_dividend_record(
                    {
                        "date": "2026-09-20",
                        "code": "005930",
                        "name": "삼성전자",
                        "amount": 1000,
                        "event_identity": "dividend:v1:005930:record:2026-08-31",
                        "record_date": "2026-08-31",
                        "payment_date": "2026-09-20",
                    }
                )
                updated = update_dividend_record(
                    created["id"], {"payment_date": "2026-09-21"}
                )
                stored = read_dividend_records()

        self.assertEqual(updated["event_identity"], created["event_identity"])
        self.assertEqual(updated["record_date"], "2026-08-31")
        self.assertEqual(updated["payment_date"], "2026-09-21")
        self.assertEqual(stored[0]["event_identity"], created["event_identity"])

    def test_toss_fingerprint_is_not_promoted_to_event_identity(self):
        mapped = map_toss_wts_income_row(
            {
                "market": "kr",
                "currency": "KRW",
                "datetime": "2026-09-20T09:00:00+09:00",
                "adjusted_amount": 8460,
                "source_meta": {
                    "summary_no": "1104",
                    "trade_type_name": "배당금입금",
                    "transaction_type_code": "1",
                    "transaction_type_name": "입금",
                    "stock_code": "005930",
                    "stock_name": "삼성전자",
                    "provider_amount": 10000,
                    "provider_tax_amount": 1540,
                    "composite_key": {"date": "20260920", "no": 7},
                },
            }
        )
        self.assertIsNotNone(mapped)
        self.assertIn("source_fingerprint", mapped)
        self.assertNotIn("event_identity", mapped)


if __name__ == "__main__":
    unittest.main()
