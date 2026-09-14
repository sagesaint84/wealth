from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from app.services import historical_fx, pnl_records
from tests.regression_support import IsolatedDataTestCase


class StrictHistoricalFxTests(unittest.TestCase):
    def strict_lookup(self, rates: dict[str, float], target: str):
        with patch.object(historical_fx, "load_cached_fx", return_value=rates):
            return historical_fx.lookup_historical_fx_strict(target)

    def test_exact_compact_and_previous_business_day_rates(self) -> None:
        rates = {"2026-01-02": 1300.0, "2026-01-05": 1310.0}
        self.assertEqual(self.strict_lookup(rates, "20260105"), (1310.0, "2026-01-05"))
        self.assertEqual(self.strict_lookup(rates, "2026-01-04"), (1300.0, "2026-01-02"))

    def test_no_future_or_hard_coded_fallback(self) -> None:
        rates = {"2026-01-05": 1310.0}
        self.assertIsNone(self.strict_lookup(rates, "2026-01-04"))
        self.assertIsNone(self.strict_lookup({}, "2026-01-04"))
        self.assertIsNone(self.strict_lookup(rates, "not-a-date"))


class ForeignRealizedPnlFxTests(IsolatedDataTestCase):
    username = "foreign-fx-fixture"

    def setUp(self) -> None:
        super().setUp()
        self.stock_patch = patch.object(
            pnl_records,
            "resolve_stock_info",
            side_effect=lambda code, name, currency: (code, name, currency),
        )
        self.stock_patch.start()

    def tearDown(self) -> None:
        self.stock_patch.stop()
        super().tearDown()

    @staticmethod
    def broker_payload(source: str, **overrides) -> dict:
        payload = {
            "date": "20260102",
            "code": "SYN-US",
            "name": "Synthetic US",
            "currency": "USD",
            "pnl": 10,
            "pnl_krw": None,
            "fx_rate": None,
            "fx_pnl_krw": None,
            "source": source,
            "source_meta": {},
        }
        payload.update(overrides)
        return payload

    def test_kiwoom_missing_krw_is_derived_strictly_without_mutating_native_pnl(self) -> None:
        payload = self.broker_payload("kiwoom", source_meta={"api_id": "ust21530"})
        with patch.object(pnl_records, "lookup_historical_fx_strict", return_value=(1300.0, "2026-01-02")):
            record = pnl_records.create_pnl_record(payload, username=self.username)

        self.assertEqual(record["pnl"], 10)
        self.assertEqual(record["pnl_krw"], 13000)
        self.assertEqual(record["fx_rate"], 1300.0)
        self.assertIsNone(record["fx_pnl_krw"])
        self.assertEqual(record["source_meta"]["pnl_krw_semantics"], "historical_fx_derived")
        self.assertEqual(record["source_meta"]["fx_date"], "2026-01-02")

    def test_kiwoom_without_strict_rate_stays_unconverted(self) -> None:
        payload = self.broker_payload("kiwoom", source_meta={"api_id": "ust21530"})
        with patch.object(pnl_records, "lookup_historical_fx_strict", return_value=None):
            record = pnl_records.create_pnl_record(payload, username=self.username)
        self.assertIsNone(record["pnl_krw"])
        self.assertIsNone(record["fx_rate"])
        self.assertEqual(record["source_meta"]["pnl_krw_semantics"], "unavailable")

    def test_nh_query_date_context_is_not_used_for_conversion(self) -> None:
        payload = self.broker_payload(
            "nh",
            date="2026-01-02",
            source_meta={"market": "overseas", "country": "US"},
        )
        with patch.object(pnl_records, "lookup_historical_fx_strict", return_value=(1300.0, "2026-01-02")) as lookup:
            record = pnl_records.create_pnl_record(payload, username=self.username)
        lookup.assert_not_called()
        self.assertIsNone(record["pnl_krw"])
        self.assertEqual(record["source_meta"]["pnl_krw_semantics"], "unavailable")

    def test_provider_authoritative_and_toss_krw_values_are_not_overwritten(self) -> None:
        records = [
            self.broker_payload(
                "kiwoom",
                id="kiwoom-provider",
                pnl_krw=12000,
                fx_rate=None,
                source_meta={"api_id": "ust21530", "pnl_krw_semantics": "provider"},
            ),
            self.broker_payload("toss_wts", id="toss-provider", pnl_krw=12500),
        ]
        original = copy.deepcopy(records)
        with (
            patch.object(pnl_records, "read_pnl_records", return_value=records),
            patch.object(pnl_records, "write_pnl_records") as write,
            patch.object(pnl_records, "lookup_historical_fx_strict", return_value=(1300.0, "2026-01-02")) as lookup,
        ):
            updated = pnl_records.recalculate_pnl_historical_fx(self.username)
        self.assertEqual(updated, 0)
        write.assert_not_called()
        lookup.assert_not_called()
        self.assertEqual(records, original)

    def test_recalculation_handles_none_fields_and_only_updates_eligible_kiwoom(self) -> None:
        kiwoom = self.broker_payload(
            "kiwoom",
            id="kiwoom",
            source_meta={"api_id": "ust21530", "pnl_krw_semantics": "unavailable"},
        )
        nh = self.broker_payload("nh", id="nh")
        with (
            patch.object(pnl_records, "read_pnl_records", return_value=[kiwoom, nh]),
            patch.object(pnl_records, "write_pnl_records") as write,
            patch.object(pnl_records, "lookup_historical_fx_strict", return_value=(1300.0, "2026-01-02")),
        ):
            updated = pnl_records.recalculate_pnl_historical_fx(self.username)
        self.assertEqual(updated, 1)
        self.assertEqual(kiwoom["pnl_krw"], 13000)
        self.assertIsNone(kiwoom["fx_pnl_krw"])
        self.assertIsNone(nh["pnl_krw"])
        write.assert_called_once()

    def test_recalculation_does_not_write_when_strict_rate_is_unavailable(self) -> None:
        record = self.broker_payload(
            "kiwoom",
            id="kiwoom",
            source_meta={"api_id": "ust21530", "pnl_krw_semantics": "unavailable"},
        )
        with (
            patch.object(pnl_records, "read_pnl_records", return_value=[record]),
            patch.object(pnl_records, "write_pnl_records") as write,
            patch.object(pnl_records, "lookup_historical_fx_strict", return_value=None),
        ):
            updated = pnl_records.recalculate_pnl_historical_fx(self.username)
        self.assertEqual(updated, 0)
        self.assertIsNone(record["pnl_krw"])
        write.assert_not_called()

    def test_summary_uses_native_sign_but_marks_krw_total_incomplete(self) -> None:
        records = [
            {"id": "positive-usd", "date": "2026-01-02", "currency": "USD", "pnl": 10, "pnl_krw": None},
            {"id": "negative-usd", "date": "2026-01-03", "currency": "USD", "pnl": -4, "pnl_krw": None},
            {"id": "domestic", "date": "2026-01-04", "currency": "KRW", "pnl": 500, "pnl_krw": 500},
        ]
        pnl_records.write_pnl_records(records, self.username)
        summary = pnl_records.get_pnl_summary(year=2026, username=self.username)
        january = summary["monthly_schedule"][0]
        yearly = summary["yearly_schedule"][0]

        self.assertEqual(summary["total_pnl_krw"], 500)
        self.assertEqual(summary["win_count"], 2)
        self.assertEqual(summary["loss_count"], 1)
        self.assertEqual(summary["win_rate"], 66.7)
        self.assertEqual(summary["converted_record_count"], 1)
        self.assertEqual(summary["unconverted_record_count"], 2)
        self.assertEqual(summary["win_loss_record_count"], 3)
        self.assertFalse(summary["summary_complete"])
        self.assertEqual(january["unconverted_record_count"], 2)
        self.assertFalse(january["summary_complete"])
        self.assertEqual(yearly["unconverted_record_count"], 2)
        self.assertFalse(yearly["summary_complete"])

    def test_update_none_fields_is_safe_and_keeps_broker_value_unavailable(self) -> None:
        with patch.object(pnl_records, "lookup_historical_fx_strict", return_value=None):
            created = pnl_records.create_pnl_record(
                self.broker_payload("nh", date="2026-01-02"),
                username=self.username,
            )
        updated = pnl_records.update_pnl_record(created["id"], {"memo": "synthetic"}, self.username)
        self.assertIsNotNone(updated)
        self.assertIsNone(updated["fx_rate"])
        self.assertIsNone(updated["fx_pnl_krw"])
        self.assertIsNone(updated["pnl_krw"])

    def test_domestic_record_and_manual_file_fx_behavior_remain_compatible(self) -> None:
        domestic = pnl_records.create_pnl_record(
            {"date": "2026-01-02", "code": "SYN-KR", "name": "Synthetic KR", "currency": "KRW", "pnl": 75},
            username=self.username,
        )
        self.assertEqual(domestic["pnl"], 75)
        self.assertEqual(domestic["pnl_krw"], 75)
        manual = {
            "id": "manual-usd",
            "date": "2026-01-02",
            "currency": "USD",
            "pnl": 2,
            "fx_rate": None,
            "fx_pnl_krw": None,
            "pnl_krw": None,
            "source": "spreadsheet",
        }
        with (
            patch.object(pnl_records, "read_pnl_records", return_value=[manual]),
            patch.object(pnl_records, "write_pnl_records") as write,
            patch.object(pnl_records, "lookup_historical_fx_strict", return_value=(1300.0, "2026-01-02")),
        ):
            updated = pnl_records.recalculate_pnl_historical_fx(self.username)
        self.assertEqual(updated, 1)
        self.assertEqual(manual["pnl_krw"], 2600)
        write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
