import json
import unittest
from decimal import Decimal

from app.services.kiwoom_feed import (
    KiwoomFeedError,
    build_kiwoom_realized_feed,
    canonical_kiwoom_number,
    canonical_kiwoom_row_hash,
    project_kiwoom_row,
)


class KiwoomRealizedFeedTests(unittest.TestCase):
    def domestic(self, **updates):
        row = {
            "dt": "20260901", "stk_cd": "A005930", "stk_nm": "Synthetic Domestic",
            "cntr_qty": "000000000002", "buy_uv": "+10.125", "cntr_pric": "20.25",
            "tdy_sel_pl": "+19.75", "pl_rt": "97.530864", "tdy_trde_cmsn": "0.25",
            "tdy_trde_tax": "0.50", "tdy_htssel_cmsn": "not-a-financial-value",
        }
        row.update(updates)
        return row

    def overseas(self, **updates):
        row = {
            "sell_dt": "20260902", "stk_cd": "SYNUS", "frgn_stk_nm": "Synthetic Overseas",
            "sell_qty": "2", "avg_buy_uv": "10.125", "buy_amt": "20.25",
            "avg_sell_uv": "20.25", "sell_amt": "40.5", "pl_amt": "19.75",
            "pl_rt": "97.530864", "cmsn_tax": "0.75", "natn_nm": "United States",
            "stex_nm": "Official Synthetic Exchange", "sell_exrt": "1400",
            "krw_chg_pl_amt": "999999",
        }
        row.update(updates)
        return row

    def test_domestic_official_projection_and_net_pnl(self):
        row = project_kiwoom_row(self.domestic(), "kr")
        self.assertEqual(row["date"], "20260901"); self.assertEqual(row["code"], "005930")
        self.assertEqual(row["quantity"], "2"); self.assertEqual(row["buy_amount"], "20.25")
        self.assertEqual(row["sell_amount"], "40.5"); self.assertEqual(row["pnl"], "19.75")
        self.assertEqual(row["pnl_krw"], "19.75"); self.assertEqual(row["fee"], "0.25"); self.assertEqual(row["tax"], "0.5")
        self.assertEqual(row["currency"], "KRW"); self.assertIsNone(row["exchange"]); self.assertIsNone(row["expenses_total"])
        self.assertEqual(Decimal(row["pnl"]), Decimal("19.75"))
        self.assertEqual(row["source_meta"]["buy_amount_semantics"], "DERIVED")
        self.assertNotIn("tdy_htssel_cmsn", json.dumps(row))

    def test_overseas_official_projection_and_foreign_semantics(self):
        row = project_kiwoom_row(self.overseas(), "us")
        self.assertEqual(row["date"], "20260902"); self.assertEqual(row["code"], "SYNUS")
        self.assertEqual(row["buy_amount"], "20.25"); self.assertEqual(row["sell_amount"], "40.5")
        self.assertEqual(row["pnl"], "19.75"); self.assertEqual(row["expenses_total"], "0.75")
        self.assertIsNone(row["fee"]); self.assertIsNone(row["tax"])
        self.assertEqual(row["currency"], "USD"); self.assertIsNone(row["pnl_krw"]); self.assertIsNone(row["fx_rate"])
        self.assertEqual(row["country"], "United States"); self.assertEqual(row["exchange"], "Official Synthetic Exchange")
        self.assertEqual(Decimal(row["pnl"]), Decimal("19.75"))
        self.assertNotIn("sell_exrt", json.dumps(row)); self.assertNotIn("krw_chg_pl_amt", json.dumps(row))

    def test_decimal_normalization_missing_zero_and_nonfinite(self):
        values = (10, 10.0, "10", "10.0", "+10.000", "00010.000", " 10 ", "0,010.000", Decimal("10.000"))
        self.assertEqual({canonical_kiwoom_number(value) for value in values}, {"10"})
        self.assertEqual(canonical_kiwoom_number("-0.0"), "0")
        self.assertEqual(canonical_kiwoom_number("-00000000048352"), "-48352")
        self.assertNotEqual(canonical_kiwoom_number("1000000000001"), canonical_kiwoom_number("1000000000002"))
        for value in (None, "", "NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(KiwoomFeedError):
                canonical_kiwoom_number(value)
        missing = self.domestic(); missing.pop("cntr_qty")
        with self.assertRaises(KiwoomFeedError):
            project_kiwoom_row(missing, "kr")
        self.assertEqual(project_kiwoom_row(self.domestic(cntr_qty="0"), "kr")["quantity"], "0")

    def test_full_hash_distinguishes_financial_fields(self):
        first = project_kiwoom_row(self.domestic(), "kr")
        second = project_kiwoom_row(self.domestic(tdy_trde_tax="0.51"), "kr")
        self.assertNotEqual(canonical_kiwoom_row_hash(first), canonical_kiwoom_row_hash(second))
        equivalent = dict(first); equivalent["quantity"] = "2.000"
        self.assertEqual(canonical_kiwoom_row_hash(first), canonical_kiwoom_row_hash(equivalent))

    def test_occurrence_identity_is_multiset_stable_and_scope_unverified(self):
        identical_a = self.domestic()
        identical_b = dict(identical_a)
        distinct = self.domestic(tdy_sel_pl="19.76")
        feed = build_kiwoom_realized_feed(
            [identical_a, distinct, identical_b], market="kr",
            source_account_key="opaque-source", source_account_label="******7890", user_id="synthetic-user",
        )
        reversed_feed = build_kiwoom_realized_feed(
            [identical_b, distinct, identical_a], market="kr",
            source_account_key="opaque-source", source_account_label="******7890", user_id="synthetic-user",
        )
        self.assertFalse(feed["source_scope_verified"]); self.assertEqual(feed["source"], "kiwoom")
        identities = [row["future_identity"] for row in feed["rows"]]
        self.assertEqual(identities, [row["future_identity"] for row in reversed_feed["rows"]])
        duplicate_hashes = [row for row in feed["rows"] if row["canonical_hash"] == canonical_kiwoom_row_hash(project_kiwoom_row(identical_a, "kr"))]
        self.assertEqual([row["source_occurrence"] for row in duplicate_hashes], [1, 2])
        self.assertEqual(len(set(identities)), 3)

    def test_three_identical_rows_receive_three_occurrences_and_no_raw_account(self):
        raw = self.overseas()
        feed = build_kiwoom_realized_feed(
            [raw, dict(raw), dict(raw)], market="us",
            source_account_key="opaque-source", source_account_label="******7890", user_id="synthetic-user",
        )
        self.assertEqual([row["source_occurrence"] for row in feed["rows"]], [1, 2, 3])
        serialized = json.dumps(feed)
        self.assertNotIn("1234567890", serialized)
        self.assertFalse(feed["persisted"]); self.assertFalse(feed["included_in_accounting_totals"])

    def test_chunk_aggregation_does_not_change_identity_or_multiset(self):
        identical = self.domestic()
        distinct = self.domestic(dt="20261201", tdy_sel_pl="21.25")
        logical_rows = [identical, dict(identical), distinct]
        one_request = build_kiwoom_realized_feed(
            logical_rows, market="kr", source_account_key="opaque-source",
            source_account_label="******7890", user_id="synthetic-user",
        )
        combined_chunks = []
        for chunk_rows in ([identical], [], [dict(identical), distinct]):
            combined_chunks.extend(chunk_rows)
        chunked = build_kiwoom_realized_feed(
            combined_chunks, market="kr", source_account_key="opaque-source",
            source_account_label="******7890", user_id="synthetic-user",
        )
        identity = lambda feed: [
            (row["canonical_hash"], row["source_occurrence"], row["future_identity"])
            for row in feed["rows"]
        ]
        self.assertEqual(identity(one_request), identity(chunked))
        self.assertEqual(len(chunked["rows"]), 3)
        duplicate_hash = canonical_kiwoom_row_hash(project_kiwoom_row(identical, "kr"))
        self.assertEqual([row["source_occurrence"] for row in chunked["rows"] if row["canonical_hash"] == duplicate_hash], [1, 2])
        self.assertNotIn("chunk", json.dumps(chunked).lower())


if __name__ == "__main__":
    unittest.main()
