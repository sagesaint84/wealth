from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from app.services import pnl_records


class TossWtsFxRecalculationGuardTests(unittest.TestCase):
    @staticmethod
    def usd_record(*, source: str | None = None, broker: str = "가상증권") -> dict:
        record = {
            "id": "synthetic-id",
            "date": "2026-01-02",
            "currency": "USD",
            "pnl": 2.5,
            "pnl_krw": 3000,
            "fx_rate": 1200.0,
            "fx_pnl_krw": 40.0,
            "created_at": "2026-01-02T00:00:00+09:00",
            "updated_at": "2026-01-02T00:00:00+09:00",
            "broker": broker,
        }
        if source is not None:
            record["source"] = source
        return record

    def run_recalculation(self, records: list[dict]):
        with (
            patch.object(pnl_records, "read_pnl_records", return_value=records),
            patch.object(pnl_records, "write_pnl_records") as write,
            patch.object(pnl_records, "get_historical_fx_rate", return_value=1300.0) as historical_fx,
        ):
            updated = pnl_records.recalculate_pnl_historical_fx(username="synthetic-user")
        return updated, historical_fx, write

    def test_toss_wts_usd_record_is_completely_untouched_without_fx_lookup(self):
        record = self.usd_record(source="toss_wts")
        record["fx_rate"] = None
        record["fx_pnl_krw"] = None
        record["source_meta"] = {
            "market_type": "us",
            "quantity": 1.5,
            "profit_loss": {"krw": 3000, "usd": 2.5},
            "buy_amount": {"krw": 1, "usd": 1},
            "sell_amount": {"krw": 2, "usd": 2},
            "fetched_at": "synthetic-fetch-time",
        }
        original = copy.deepcopy(record)
        updated, historical_fx, write = self.run_recalculation([record])
        self.assertEqual(updated, 0)
        historical_fx.assert_not_called()
        write.assert_not_called()
        self.assertEqual(record, original)

    def test_toss_wts_guard_is_source_based_for_all_currencies_and_populated_fx(self):
        usd = self.usd_record(source="toss_wts")
        krw = {
            "id": "synthetic-krw",
            "currency": "KRW",
            "pnl": 100,
            "pnl_krw": 100,
            "fx_rate": 1.0,
            "fx_pnl_krw": 0.0,
            "updated_at": "synthetic-time",
            "source": "toss_wts",
        }
        original = copy.deepcopy([usd, krw])
        updated, historical_fx, write = self.run_recalculation([usd, krw])
        self.assertEqual(updated, 0)
        historical_fx.assert_not_called()
        write.assert_not_called()
        self.assertEqual([usd, krw], original)

    def test_legacy_manual_spreadsheet_and_toss_broker_records_keep_existing_behavior(self):
        legacy = self.usd_record()
        manual = self.usd_record(source="manual")
        spreadsheet = self.usd_record(source="spreadsheet")
        manual_toss_broker = self.usd_record(source="manual", broker="토스증권")
        legacy_toss_broker = self.usd_record(broker="토스증권")
        wts = self.usd_record(source="toss_wts")
        wts["source_meta"] = {"profit_loss": {"krw": 3000, "usd": 2.5}}
        krw = {"id": "krw", "currency": "KRW", "pnl": 8, "pnl_krw": 8, "updated_at": "old"}
        records = [legacy, manual, spreadsheet, manual_toss_broker, legacy_toss_broker, wts, krw]
        wts_before = copy.deepcopy(wts)
        order_before = [r["id"] for r in records]

        updated, historical_fx, write = self.run_recalculation(records)

        self.assertEqual(updated, 5)
        self.assertEqual(historical_fx.call_count, 5)
        write.assert_called_once_with(records, "synthetic-user")
        self.assertEqual([r["id"] for r in records], order_before)
        self.assertEqual(wts, wts_before)
        for record in (legacy, manual, spreadsheet, manual_toss_broker, legacy_toss_broker):
            self.assertEqual(record["fx_rate"], 1300.0)
            self.assertEqual(record["pnl_krw"], 3290.0)
        self.assertEqual(krw["pnl_krw"], 8)


if __name__ == "__main__":
    unittest.main()
