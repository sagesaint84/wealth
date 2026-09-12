from __future__ import annotations

import copy
import math
import unittest

from app.services.toss_wts_realized import map_toss_wts_profit_row


class TossWtsRealizedMapperTests(unittest.TestCase):
    @staticmethod
    def row(*, market_type: str = "us") -> dict:
        return {
            "date": "2026-01-02",
            "market_type": market_type,
            "symbol": "FAKE",
            "product_code": "FAKE123",
            "name": "가상종목",
            "quantity": 1,
            "profit_loss": {"krw": 321, "usd": 0.25},
            "profit_rate": -1.5,
            "buy_amount": {"krw": 1000, "usd": 1.0},
            "sell_amount": {"krw": 1321, "usd": 1.25},
        }

    def map(self, row: dict | None = None, **overrides):
        context = {
            "account_name": "가상 토스계좌",
            "source_account_scope": "synthetic-account-scope",
            "owner": "모두",
            "profit_rate_basis": "KRW",
            "fetched_at": "2026-09-11T00:00:00Z",
        }
        context.update(overrides)
        return map_toss_wts_profit_row(row or self.row(), **context)

    def test_kr_mapping_has_no_derived_fx(self):
        candidate = self.map(self.row(market_type="kr"))
        self.assertEqual(candidate["currency"], "KRW")
        self.assertEqual(candidate["pnl"], 321)
        self.assertEqual(candidate["pnl_krw"], 321)
        self.assertIsNone(candidate["fx_rate"])
        self.assertIsNone(candidate["fx_pnl_krw"])
        self.assertEqual(candidate["broker"], "토스증권")
        self.assertEqual(candidate["asset_type"], "stock")
        self.assertFalse(candidate["is_ipo"])

    def test_us_mapping_preserves_wts_krw_without_fx_ratio(self):
        row = self.row()
        row["profit_loss"] = {"krw": 991, "usd": 0.37}
        candidate = self.map(row)
        self.assertEqual(candidate["currency"], "USD")
        self.assertEqual(candidate["pnl"], 0.37)
        self.assertEqual(candidate["pnl_krw"], 991)
        self.assertIsNone(candidate["fx_rate"])
        self.assertIsNone(candidate["fx_pnl_krw"])

    def test_exact_candidate_shape_and_metadata_allowlist(self):
        row = self.row()
        row["unexpected_private_field"] = "SHOULD_NOT_COPY"
        candidate = self.map(row)
        self.assertEqual(set(candidate), {
            "date", "code", "name", "asset_type", "currency", "pnl", "fx_rate",
            "fx_pnl_krw", "pnl_krw", "is_ipo", "owner", "broker", "account_name",
            "memo", "source", "source_account_scope", "source_meta",
        })
        self.assertNotIn("id", candidate)
        self.assertNotIn("created_at", candidate)
        self.assertNotIn("updated_at", candidate)
        self.assertNotIn("source_fingerprint", candidate)
        self.assertEqual(set(candidate["source_meta"]), {
            "market_type", "symbol", "product_code", "quantity", "profit_rate",
            "profit_rate_basis", "profit_loss", "buy_amount", "sell_amount", "fetched_at",
        })
        self.assertNotIn("unexpected_private_field", candidate)

    def test_metadata_is_isolated_and_input_is_not_mutated(self):
        row = self.row()
        original = copy.deepcopy(row)
        candidate = self.map(row)
        self.assertEqual(row, original)
        row["profit_loss"]["krw"] = 999
        row["buy_amount"]["usd"] = 999
        self.assertEqual(candidate["source_meta"]["profit_loss"]["krw"], 321)
        self.assertEqual(candidate["source_meta"]["buy_amount"]["usd"], 1.0)
        self.assertEqual(original["profit_loss"]["krw"], 321)
        self.assertEqual(candidate["name"], "가상종목")

    def test_quantity_int_and_float_are_preserved(self):
        self.assertIsInstance(self.map()["source_meta"]["quantity"], int)
        row = self.row()
        row["quantity"] = 1.5
        self.assertEqual(self.map(row)["source_meta"]["quantity"], 1.5)

    def test_optional_usd_money_value_is_preserved_as_none(self):
        row = self.row(market_type="kr")
        row["buy_amount"] = {"krw": 1000, "usd": None}
        candidate = self.map(row)
        self.assertIsNone(candidate["source_meta"]["buy_amount"]["usd"])

    def test_invalid_contract_values_are_rejected(self):
        cases = [
            (self.row(market_type="unknown-market"), {}, "unsupported market_type"),
            (dict(self.row(), quantity=True), {}, "quantity"),
            (dict(self.row(), profit_rate=False), {}, "profit_rate"),
            (dict(self.row(), profit_loss={"krw": True, "usd": 0.25}), {}, "profit_loss.krw"),
            (dict(self.row(), quantity=float("nan")), {}, "quantity"),
            (dict(self.row(), quantity=math.inf), {}, "quantity"),
            (dict(self.row(market_type="kr"), profit_loss={"krw": None, "usd": 0.25}), {}, "profit_loss.krw"),
            (dict(self.row(), profit_loss={"krw": 321, "usd": None}), {}, "profit_loss.usd"),
            (dict(self.row(), profit_loss={"krw": None, "usd": 0.25}), {}, "profit_loss.krw"),
            (self.row(), {"source_account_scope": "   "}, "source_account_scope"),
            (self.row(), {"profit_rate_basis": "EUR"}, "unsupported profit_rate_basis"),
            (self.row(), {"profit_rate_basis": "KRW; buy"}, "unsupported profit_rate_basis"),
        ]
        for row, context, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(ValueError, expected):
                    self.map(row, **context)

    def test_numeric_strings_are_rejected_and_mapping_is_deterministic(self):
        row = self.row()
        row["quantity"] = "1"
        with self.assertRaisesRegex(ValueError, "quantity"):
            self.map(row)
        source = self.row()
        self.assertEqual(self.map(source), self.map(source))

    def test_both_supported_rate_bases_are_metadata_not_row_currency(self):
        us_candidate = self.map(profit_rate_basis="USD")
        self.assertEqual(us_candidate["currency"], "USD")
        self.assertEqual(us_candidate["source_meta"]["profit_rate_basis"], "USD")
        kr_candidate = self.map(self.row(market_type="kr"), profit_rate_basis="KRW")
        self.assertEqual(kr_candidate["currency"], "KRW")


if __name__ == "__main__":
    unittest.main()
