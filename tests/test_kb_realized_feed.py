import json
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("WEALTH_ENV", "test")
os.environ.setdefault("WEALTH_TEST_SIGNING_SECRET", "synthetic-kb-test-secret")

from app.services.kb_feed import (
    KBFeedError,
    build_kb_realized_feed,
    canonical_kb_number,
    canonical_kb_row_hash,
    is_realized_sale_row,
    project_kb_domestic_row,
    sign_kb_feed_row,
    sign_kb_import_preview_ticket,
    verify_kb_feed_row,
    verify_kb_import_preview_ticket,
)


class KBRealizedFeedTests(unittest.TestCase):
    def domestic_raw(self, **updates):
        """Official KB SSQM2442 Record1 structure for a valid realized sale."""
        row = {
            "trd_dt": "20260901",
            "stnd_is_cd": "KR7005930003",
            "shrt_is_cd": "A005930",
            "is_nm": "삼성전자",
            "trd_dl_ccd": "01",
            "crdt_typ_cd": "00",
            "ccls_q": "2",
            "dtls_ccls_q": "2.5",  # fractional shares
            "dcml_dl_f": "1",
            "ccls_uprc": "70000",
            "b_uprc": "60000",
            "s_amt": "175000",  # 2.5 * 70000
            "b_amt": "150000",  # 2.5 * 60000
            "fee": "100",
            "svrl_tx": "350",
            "rlztn_pl": "24550",
            "yld": "16.36",
        }
        row.update(updates)
        return row

    def test_canonical_mapping_and_direct_fields(self):
        raw = self.domestic_raw()
        projected = project_kb_domestic_row(raw)

        # Exact canonical mappings verified
        self.assertEqual(projected["date"], "20260901")
        self.assertEqual(projected["code"], "005930")  # 'A' stripped
        self.assertEqual(projected["name"], "삼성전자")
        self.assertEqual(projected["quantity"], "2.5")  # lossless from dtls_ccls_q
        self.assertEqual(projected["buy_unit_price"], "60000")
        self.assertEqual(projected["buy_amount"], "150000")
        self.assertEqual(projected["sell_unit_price"], "70000")
        self.assertEqual(projected["sell_amount"], "175000")
        self.assertEqual(projected["pnl"], "24550")
        self.assertEqual(projected["profit_rate"], "16.36")  # authoritative from yld
        self.assertEqual(projected["fee"], "100")
        self.assertEqual(projected["tax"], "350")
        self.assertEqual(projected["currency"], "KRW")
        self.assertEqual(projected["pnl_krw"], "24550")
        self.assertIsNone(projected["fx_rate"])
        self.assertEqual(projected["market_type"], "kr")
        self.assertEqual(projected["country"], "KR")
        self.assertIsNone(projected["exchange"])
        self.assertIsNone(projected["expenses_total"])

        # No double subtraction: fee and tax are informational only
        self.assertEqual(projected["pnl"], raw["rlztn_pl"])
        self.assertEqual(projected["pnl_krw"], raw["rlztn_pl"])

        # Metadata records provider netness status
        self.assertEqual(projected["source_meta"]["api_id"], "SSQM2442")
        self.assertEqual(projected["source_meta"]["pnl_netness"], "PROVIDER_AUTHORITATIVE_UNVERIFIED")

    def test_decimal_normalization_and_lossless_parsing(self):
        values = (10, 10.0, "10", "10.0", "+10.000", "00010.000", " 10 ", "0,010.000", Decimal("10.000"))
        self.assertEqual({canonical_kb_number(value) for value in values}, {"10"})
        self.assertEqual(canonical_kb_number("-0.0"), "0")
        self.assertEqual(canonical_kb_number("-00000000048352"), "-48352")

        # Fractional quantity formatting
        self.assertEqual(canonical_kb_number("0.123450000"), "0.12345")
        self.assertEqual(canonical_kb_number("2.5"), "2.5")

        # Rejection of invalid / non-finite
        for value in (None, "", "NaN", "Infinity", "-Infinity", True, False):
            with self.subTest(value=value), self.assertRaises(KBFeedError):
                canonical_kb_number(value)

    def test_negative_and_zero_pnl_supported(self):
        # Negative P/L
        neg_raw = self.domestic_raw(rlztn_pl="-5000", yld="-3.33")
        neg_proj = project_kb_domestic_row(neg_raw)
        self.assertEqual(neg_proj["pnl"], "-5000")
        self.assertEqual(neg_proj["pnl_krw"], "-5000")
        self.assertEqual(neg_proj["profit_rate"], "-3.33")

        # Zero P/L (must not be lost or rejected)
        zero_raw = self.domestic_raw(rlztn_pl="0", yld="0.00")
        zero_proj = project_kb_domestic_row(zero_raw)
        self.assertEqual(zero_proj["pnl"], "0")
        self.assertEqual(zero_proj["pnl_krw"], "0")
        self.assertEqual(zero_proj["profit_rate"], "0")

    def test_missing_required_financial_field_fails_closed(self):
        # Missing quantity does NOT become zero
        missing_qty = self.domestic_raw()
        del missing_qty["dtls_ccls_q"]
        with self.assertRaises(KBFeedError):
            project_kb_domestic_row(missing_qty)

        # Missing pnl does NOT become zero
        missing_pnl = self.domestic_raw()
        del missing_pnl["rlztn_pl"]
        with self.assertRaises(KBFeedError):
            project_kb_domestic_row(missing_pnl)

        # Missing buy amount does NOT become zero
        missing_bamt = self.domestic_raw()
        del missing_bamt["b_amt"]
        with self.assertRaises(KBFeedError):
            project_kb_domestic_row(missing_bamt)

        # Official fee/tax breakdown fields are informational, but missing or
        # blank values must not be silently fabricated as numeric zero.
        for field in ("fee", "svrl_tx"):
            for mode in ("missing", "blank"):
                with self.subTest(field=field, mode=mode):
                    row = self.domestic_raw()
                    if mode == "missing":
                        del row[field]
                    else:
                        row[field] = ""
                    with self.assertRaises(KBFeedError):
                        project_kb_domestic_row(row)

    def test_realization_row_classification_rules(self):
        # Case A: clearly importable realized sale row
        raw_sale = self.domestic_raw(s_amt="175000", b_amt="150000", dtls_ccls_q="2.5")
        valid, reason = is_realized_sale_row(raw_sale)
        self.assertTrue(valid)
        self.assertIsNone(reason)

        # Case B: obvious buy / non-realization row (e.g. s_amt == 0, b_amt > 0)
        raw_buy = self.domestic_raw(s_amt="0", b_amt="360000", rlztn_pl="0", trd_dl_ccd="02")
        valid, reason = is_realized_sale_row(raw_buy)
        self.assertFalse(valid)
        self.assertEqual(reason, "NON_REALIZATION_BUY_ROW")

        # Case C: zero realized P/L but valid sale proceeds
        zero_pnl_sale = self.domestic_raw(s_amt="100000", b_amt="100000", rlztn_pl="0", yld="0")
        valid, reason = is_realized_sale_row(zero_pnl_sale)
        self.assertTrue(valid)
        self.assertIsNone(reason)

        # Case D: ambiguous row (both s_amt == 0 and b_amt == 0)
        ambiguous = self.domestic_raw(s_amt="0", b_amt="0", rlztn_pl="0")
        valid, reason = is_realized_sale_row(ambiguous)
        self.assertFalse(valid)
        self.assertEqual(reason, "AMBIGUOUS_REALIZATION_ROW")

        # Case E: non-positive quantity
        zero_qty = self.domestic_raw(dtls_ccls_q="0")
        valid, reason = is_realized_sale_row(zero_qty)
        self.assertFalse(valid)
        self.assertEqual(reason, "NON_POSITIVE_QUANTITY")

        # Case F: official buy direction never becomes a realization merely
        # because a contradictory amount field is positive.
        contradictory_buy = self.domestic_raw(trd_dl_ccd="02", s_amt="100000")
        valid, reason = is_realized_sale_row(contradictory_buy)
        self.assertFalse(valid)
        self.assertEqual(reason, "NON_REALIZATION_BUY_ROW")

        # Case G: missing or unsupported direction is ambiguous and fails closed.
        for direction in (None, "", "99"):
            with self.subTest(direction=direction):
                ambiguous_direction = self.domestic_raw(trd_dl_ccd=direction)
                valid, reason = is_realized_sale_row(ambiguous_direction)
                self.assertFalse(valid)
                self.assertEqual(reason, "AMBIGUOUS_TRADE_DIRECTION")

    def test_realization_filter_rejects_non_finite_values_without_raising(self):
        for field in ("s_amt", "b_amt", "dtls_ccls_q"):
            for value in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(field=field, value=value):
                    raw = self.domestic_raw(**{field: value})
                    valid, reason = is_realized_sale_row(raw)
                    self.assertFalse(valid)
                    self.assertEqual(reason, "NON_FINITE_NUMERIC_VALUE")

    def test_build_feed_excludes_non_realization_and_ambiguous_rows(self):
        sale1 = self.domestic_raw(s_amt="100000", b_amt="80000", rlztn_pl="20000")
        buy_row = self.domestic_raw(s_amt="0", b_amt="360000", rlztn_pl="0", trd_dl_ccd="02")
        ambiguous_row = self.domestic_raw(s_amt="0", b_amt="0", rlztn_pl="0")
        zero_pnl_sale = self.domestic_raw(shrt_is_cd="A000660", s_amt="50000", b_amt="50000", rlztn_pl="0")

        feed = build_kb_realized_feed(
            [sale1, buy_row, ambiguous_row, zero_pnl_sale],
            market="kr",
            source_account_key="opaque-kb-key",
            source_account_label="400****078-01",
            user_id="synthetic-user",
        )

        # Only the 2 valid realization sales must be in feed rows
        self.assertEqual(len(feed["rows"]), 2)
        self.assertEqual(feed["excluded_rows_count"], 2)
        self.assertEqual(feed["source"], "kb")
        self.assertFalse(feed["source_scope_verified"])
        codes = [r["code"] for r in feed["rows"]]
        self.assertIn("005930", codes)
        self.assertIn("000660", codes)

    def test_canonical_hash_and_identity_multiset_stability(self):
        row_a = self.domestic_raw(trd_dt="20260901", rlztn_pl="1000")
        row_b = dict(row_a)
        row_distinct = self.domestic_raw(trd_dt="20260902", rlztn_pl="2000")

        feed_forward = build_kb_realized_feed(
            [row_a, row_distinct, row_b],
            market="kr",
            source_account_key="opaque-source",
            source_account_label="400****078-01",
            user_id="user-1",
        )
        feed_reversed = build_kb_realized_feed(
            [row_b, row_distinct, row_a],
            market="kr",
            source_account_key="opaque-source",
            source_account_label="400****078-01",
            user_id="user-1",
        )

        # Order invariance
        identities_forward = [r["future_identity"] for r in feed_forward["rows"]]
        identities_reversed = [r["future_identity"] for r in feed_reversed["rows"]]
        self.assertEqual(identities_forward, identities_reversed)

        # Occurrence ordinal 1 and 2 for genuinely identical rows
        identical_items = [r for r in feed_forward["rows"] if r["date"] == "20260901"]
        self.assertEqual(len(identical_items), 2)
        self.assertEqual([r["source_occurrence"] for r in identical_items], [1, 2])
        self.assertNotEqual(identical_items[0]["future_identity"], identical_items[1]["future_identity"])

    def test_full_hash_distinguishes_every_financial_field(self):
        base = project_kb_domestic_row(self.domestic_raw())
        diff_tax = project_kb_domestic_row(self.domestic_raw(svrl_tx="351"))
        diff_fee = project_kb_domestic_row(self.domestic_raw(fee="101"))
        diff_buy = project_kb_domestic_row(self.domestic_raw(b_amt="150001"))
        diff_sell = project_kb_domestic_row(self.domestic_raw(s_amt="175001"))

        base_hash = canonical_kb_row_hash(base)
        self.assertNotEqual(base_hash, canonical_kb_row_hash(diff_tax))
        self.assertNotEqual(base_hash, canonical_kb_row_hash(diff_fee))
        self.assertNotEqual(base_hash, canonical_kb_row_hash(diff_buy))
        self.assertNotEqual(base_hash, canonical_kb_row_hash(diff_sell))

        # Equivalent numeric representation produces identical hash
        equivalent = project_kb_domestic_row(self.domestic_raw(dtls_ccls_q="2.5000"))
        self.assertEqual(base_hash, canonical_kb_row_hash(equivalent))

    def test_token_signing_and_tamper_detection(self):
        row = project_kb_domestic_row(self.domestic_raw())
        row["canonical_hash"] = canonical_kb_row_hash(row)
        row["source_occurrence"] = 1
        from app.services.kb_feed import _future_identity
        row["future_identity"] = _future_identity("opaque-key", row["canonical_hash"], 1)

        token = sign_kb_feed_row(row, user_id="user-1", source_account_key="opaque-key", market="kr")
        valid, reason = verify_kb_feed_row(row, token, user_id="user-1", source_account_key="opaque-key", market="kr")
        self.assertTrue(valid)
        self.assertIsNone(reason)

        # Tampered financial field
        tampered = dict(row)
        tampered["pnl"] = "999999"
        valid, reason = verify_kb_feed_row(tampered, token, user_id="user-1", source_account_key="opaque-key", market="kr")
        self.assertFalse(valid)
        self.assertEqual(reason, "ROW_TAMPERED")

        # User mismatch
        valid, reason = verify_kb_feed_row(row, token, user_id="wrong-user", source_account_key="opaque-key", market="kr")
        self.assertFalse(valid)
        self.assertEqual(reason, "USER_MISMATCH")

        # Scope mismatch
        valid, reason = verify_kb_feed_row(row, token, user_id="user-1", source_account_key="wrong-scope", market="kr")
        self.assertFalse(valid)
        self.assertEqual(reason, "SCOPE_MISMATCH")

    def test_preview_ticket_binds_all_authorization_context(self):
        values = {
            "account_id": "destination", "items_hash": "items", "user_id": "user-1",
            "source_account_key": "opaque-key", "market": "kr",
        }
        ticket = sign_kb_import_preview_ticket(**values)
        self.assertEqual(verify_kb_import_preview_ticket(ticket, **values), (True, None))
        expected = {
            "account_id": "DESTINATION_ACCOUNT_CHANGED", "items_hash": "ITEMS_TAMPERED",
            "user_id": "USER_MISMATCH", "source_account_key": "SCOPE_MISMATCH",
            "market": "MARKET_MISMATCH",
        }
        for key, reason in expected.items():
            changed = dict(values)
            changed[key] += "-changed"
            self.assertEqual(verify_kb_import_preview_ticket(ticket, **changed)[1], reason)
        self.assertFalse(verify_kb_import_preview_ticket(ticket + "x", **values)[0])
        with patch("app.services.kb_feed.KB_PREVIEW_TICKET_MAX_AGE_SECONDS", -1):
            self.assertEqual(verify_kb_import_preview_ticket(ticket, **values)[1], "PREVIEW_TICKET_EXPIRED")

    def test_production_signing_uses_persistent_secret(self):
        row = project_kb_domestic_row(self.domestic_raw())
        row["canonical_hash"] = canonical_kb_row_hash(row)
        row["source_occurrence"] = 1
        from app.services.kb_feed import _future_identity
        row["future_identity"] = _future_identity("opaque-key", row["canonical_hash"], 1)
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}, clear=True):
            self.assertTrue(sign_kb_feed_row(row, user_id="user-1", source_account_key="opaque-key", market="kr"))

    def test_provider_fingerprint_is_source_scoped_and_preserves_occurrences(self):
        from app.services.kb_realized import classify_kb_rows
        feed = build_kb_realized_feed(
            [self.domestic_raw(), self.domestic_raw()], market="kr",
            source_account_key="opaque-a", source_account_label="****1111-**", user_id="user-1",
        )
        classified = classify_kb_rows(feed["rows"], [], "opaque-a")
        self.assertEqual([item["status"] for item in classified], ["NEW", "NEW"])
        self.assertNotEqual(classified[0]["fingerprint"], classified[1]["fingerprint"])
        existing = [{"source": "kb", "source_fingerprint": classified[0]["fingerprint"]}]
        self.assertEqual(classify_kb_rows([feed["rows"][0]], existing, "opaque-a")[0]["status"], "ALREADY_IMPORTED")
        other_feed = build_kb_realized_feed(
            [self.domestic_raw()], market="kr", source_account_key="opaque-b",
            source_account_label="****2222-**", user_id="user-1",
        )
        self.assertEqual(classify_kb_rows(other_feed["rows"], existing, "opaque-b")[0]["status"], "NEW")
