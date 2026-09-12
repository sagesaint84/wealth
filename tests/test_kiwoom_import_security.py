import json
import os
import unittest
from unittest.mock import patch

from app.services.kiwoom_feed import (
    build_kiwoom_realized_feed,
    compute_kiwoom_items_hash,
    sign_kiwoom_import_preview_ticket,
    sign_kiwoom_feed_row,
    verify_kiwoom_feed_row,
    verify_kiwoom_import_preview_ticket,
)
from app.services.kiwoom_realized import classify_kiwoom_rows, preview_kiwoom_realized_selection


class KiwoomImportSecurityTests(unittest.TestCase):
    user_id = "synthetic-user"
    source_key = "synthetic-opaque-source"

    def domestic_raw(self, **updates):
        row = {
            "dt": "20260901", "stk_cd": "A005930", "stk_nm": "Synthetic Domestic",
            "cntr_qty": "2", "buy_uv": "10", "cntr_pric": "20", "tdy_sel_pl": "17",
            "pl_rt": "85", "tdy_trde_cmsn": "1", "tdy_trde_tax": "2",
        }
        row.update(updates)
        return row

    def feed(self, rows=None):
        return build_kiwoom_realized_feed(
            rows or [self.domestic_raw()], market="kr", source_account_key=self.source_key,
            source_account_label="******7890", user_id=self.user_id,
        )

    def test_signed_row_survives_json_roundtrip_and_binds_all_context(self):
        feed = self.feed()
        row = json.loads(json.dumps(feed["rows"][0]))
        token = feed["selection_tokens"][0]
        self.assertEqual(verify_kiwoom_feed_row(row, token, user_id=self.user_id, source_account_key=self.source_key, market="kr"), (True, None))
        self.assertEqual(verify_kiwoom_feed_row(row, token, user_id="other", source_account_key=self.source_key, market="kr")[1], "USER_MISMATCH")
        self.assertEqual(verify_kiwoom_feed_row(row, token, user_id=self.user_id, source_account_key="other", market="kr")[1], "SCOPE_MISMATCH")
        self.assertEqual(verify_kiwoom_feed_row(row, token, user_id=self.user_id, source_account_key=self.source_key, market="us")[1], "MARKET_MISMATCH")
        changed = dict(row); changed["pnl"] = "18"
        self.assertEqual(verify_kiwoom_feed_row(changed, token, user_id=self.user_id, source_account_key=self.source_key, market="kr")[1], "ROW_TAMPERED")

    def test_preview_ticket_binds_user_source_destination_market_and_multiset(self):
        feed = self.feed()
        selected = [{"row": feed["rows"][0], "selection_token": feed["selection_tokens"][0]}]
        items_hash = compute_kiwoom_items_hash(selected)
        ticket = sign_kiwoom_import_preview_ticket(
            account_id="destination", items_hash=items_hash, user_id=self.user_id,
            source_account_key=self.source_key, market="kr",
        )
        args = dict(account_id="destination", items_hash=items_hash, user_id=self.user_id, source_account_key=self.source_key, market="kr")
        self.assertEqual(verify_kiwoom_import_preview_ticket(ticket, **args), (True, None))
        for key, value, reason in (
            ("account_id", "other", "DESTINATION_ACCOUNT_CHANGED"),
            ("items_hash", "other", "ITEMS_TAMPERED"),
            ("user_id", "other", "USER_MISMATCH"),
            ("source_account_key", "other", "SCOPE_MISMATCH"),
            ("market", "us", "MARKET_MISMATCH"),
        ):
            changed = dict(args); changed[key] = value
            self.assertEqual(verify_kiwoom_import_preview_ticket(ticket, **changed)[1], reason)
        self.assertFalse(verify_kiwoom_import_preview_ticket(ticket + "x", **args)[0])
        with patch("app.services.kiwoom_feed.KIWOOM_PREVIEW_TICKET_MAX_AGE_SECONDS", -1):
            self.assertEqual(verify_kiwoom_import_preview_ticket(ticket, **args)[1], "PREVIEW_TICKET_EXPIRED")

    def test_classifier_preserves_occurrences_and_rejects_same_identity(self):
        feed = self.feed([self.domestic_raw(), self.domestic_raw()])
        rows = feed["rows"]
        classified = classify_kiwoom_rows(rows, [], self.source_key)
        self.assertEqual([item["status"] for item in classified], ["NEW", "NEW"])
        self.assertNotEqual(classified[0]["fingerprint"], classified[1]["fingerprint"])
        duplicate = classify_kiwoom_rows([rows[0], rows[0]], [], self.source_key)
        self.assertEqual(duplicate[1], {"status": "INVALID", "reason": "DUPLICATE_SELECTION"})
        existing = [{"source": "kiwoom", "source_fingerprint": classified[0]["fingerprint"]}]
        self.assertEqual(classify_kiwoom_rows([rows[0]], existing, self.source_key)[0]["status"], "ALREADY_IMPORTED")
        other_feed = build_kiwoom_realized_feed(
            [self.domestic_raw()], market="kr", source_account_key="different-opaque-source",
            source_account_label="******4321", user_id=self.user_id,
        )
        other_scope = classify_kiwoom_rows(other_feed["rows"], existing, "different-opaque-source")
        self.assertEqual(other_scope[0]["status"], "NEW")

    def test_production_signing_has_no_fallback_secret(self):
        row = self.feed()["rows"][0]
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}, clear=True):
            with self.assertRaises(RuntimeError):
                sign_kiwoom_feed_row(
                    row, user_id=self.user_id, source_account_key=self.source_key, market="kr",
                )

    def test_preview_is_pure_and_detects_manual_close_match(self):
        feed = self.feed()
        selected = [{"row": feed["rows"][0], "selection_token": feed["selection_tokens"][0]}]
        destination = {"id": "destination", "account_name": "Synthetic", "owner": "Owner", "broker": "Kiwoom"}
        existing = [{"source": "manual", "date": "20260901", "code": "005930", "pnl": 17}]
        original_selected = json.dumps(selected, sort_keys=True)
        original_existing = json.dumps(existing, sort_keys=True)
        result = preview_kiwoom_realized_selection(
            selected, destination, existing, user_id=self.user_id,
            source_account_key=self.source_key, source_account_label="******7890", market="kr",
        )
        self.assertEqual(result["counts"]["possible_duplicate"], 1)
        self.assertFalse(result["scope_verified"])
        self.assertEqual(json.dumps(selected, sort_keys=True), original_selected)
        self.assertEqual(json.dumps(existing, sort_keys=True), original_existing)


if __name__ == "__main__":
    unittest.main()
