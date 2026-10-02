from __future__ import annotations

from unittest.mock import patch

from app.services import pnl_records
from app.services.toss_wts_realized import map_toss_wts_profit_row
from tests.regression_support import IsolatedDataTestCase


class TossWtsFxImportPersistenceTests(IsolatedDataTestCase):
    username = "toss-wts-fx-persistence"

    def test_derived_us_fx_values_survive_pnl_record_creation(self) -> None:
        row = {
            "date": "2026-09-26",
            "market_type": "us",
            "symbol": "QQQM",
            "product_code": "US02010I3005",
            "name": "QQQM",
            "quantity": 0.72,
            "profit_loss": {"krw": 41207, "usd": 42.18},
            "profit_rate": 15.88,
            "buy_amount": {"krw": 259464, "usd": 187.40},
            "sell_amount": {"krw": 300994, "usd": 217.60},
        }
        candidate = map_toss_wts_profit_row(
            row,
            account_name="토스 일반 계좌",
            source_account_scope="unverified",
            owner="아빠",
            profit_rate_basis="KRW",
            fetched_at="2026-10-02T00:00:00Z",
        )

        with patch.object(
            pnl_records,
            "resolve_stock_info",
            side_effect=lambda code, name, currency: (code, name, currency),
        ):
            record = pnl_records.create_pnl_record(candidate, username=self.username)

        expected_rate = round(300994 / 217.60, 6)
        expected_fx_pnl = round(41207 - 42.18 * expected_rate, 0)
        self.assertEqual(record["currency"], "USD")
        self.assertEqual(record["pnl"], 42.18)
        self.assertEqual(record["pnl_krw"], 41207.0)
        self.assertEqual(record["fx_rate"], expected_rate)
        self.assertEqual(record["fx_pnl_krw"], expected_fx_pnl)
        self.assertEqual(record["source"], "toss_wts")
        self.assertEqual(record["source_meta"]["sell_amount"], row["sell_amount"])


if __name__ == "__main__":
    import unittest

    unittest.main()
