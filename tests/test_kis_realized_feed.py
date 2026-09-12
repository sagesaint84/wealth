import json
import os
import unittest
from unittest.mock import patch
from app.services.kis_feed import (
    canonical_kis_row_hash,
    sign_kis_feed_row,
    verify_kis_feed_row_token,
    validate_kis_feed_request,
    project_kis_feed_row,
    build_kis_realized_feed_response,
    compute_kis_items_hash,
    sign_kis_import_preview_ticket,
    verify_kis_import_preview_ticket,
    get_kis_signing_secret,
    _get_serializer,
    KIS_ROW_SELECTION_SALT,
)
from app.services.kis_openapi import compute_kis_account_key


class TestKISRealizedFeed(unittest.TestCase):
    def setUp(self):
        self.sample_row = {
            "trad_dt": "20240415",
            "pdno": "000660",
            "prdt_name": "SK하이닉스",
            "sll_qty": "15",
            "sll_amt": "2700000",
            "buy_amt": "2400000",
            "pchs_amt": "2400000",
            "rlzt_pfls": "300000",
            "pfls_rt": "12.50",
            "fee": "300",
            "tl_tax": "5400",
        }
        self.user_id = "test_user"
        self.account_key = compute_kis_account_key("12345678", "01")

    def test_row_hash_determinism(self):
        h1 = canonical_kis_row_hash(self.sample_row)
        h2 = canonical_kis_row_hash(dict(self.sample_row))
        self.assertEqual(h1, h2)
        # Modifying field changes hash
        h_diff = canonical_kis_row_hash(dict(self.sample_row, sll_qty="20"))
        self.assertNotEqual(h1, h_diff)

    def test_token_json_roundtrip_float_int_invariance(self):
        # Python projected row with floats
        projected = project_kis_feed_row(self.sample_row, market="kr")
        token = sign_kis_feed_row(projected, user_id=self.user_id, source_account_key=self.account_key)

        # Simulate browser JSON roundtrip: floats like 15.0 become 15, 2700000.0 become 2700000
        json_str = json.dumps(projected)
        roundtripped = json.loads(json_str)

        # Verification must pass despite JS/JSON int vs float serialization
        valid, err = verify_kis_feed_row_token(roundtripped, token, user_id=self.user_id, expected_account_key=self.account_key)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_row_token_sign_and_verify(self):
        token = sign_kis_feed_row(self.sample_row, user_id=self.user_id, source_account_key=self.account_key)
        self.assertIsInstance(token, str)

        valid, err = verify_kis_feed_row_token(self.sample_row, token, user_id=self.user_id, expected_account_key=self.account_key)
        self.assertTrue(valid)
        self.assertIsNone(err)

        # User mismatch
        valid, err = verify_kis_feed_row_token(self.sample_row, token, user_id="other_user", expected_account_key=self.account_key)
        self.assertFalse(valid)
        self.assertEqual(err, "USER_MISMATCH")

        # Scope / account mismatch
        other_key = compute_kis_account_key("99999999", "01")
        valid, err = verify_kis_feed_row_token(self.sample_row, token, user_id=self.user_id, expected_account_key=other_key)
        self.assertFalse(valid)
        self.assertEqual(err, "SCOPE_MISMATCH")

        # Tampered row content
        tampered_row = dict(self.sample_row, sll_qty="99")
        valid, err = verify_kis_feed_row_token(tampered_row, token, user_id=self.user_id, expected_account_key=self.account_key)
        self.assertFalse(valid)
        self.assertEqual(err, "ROW_TAMPERED")

        # Invalid token
        valid, err = verify_kis_feed_row_token(self.sample_row, "invalid.token.signature", user_id=self.user_id, expected_account_key=self.account_key)
        self.assertFalse(valid)
        self.assertEqual(err, "TOKEN_INVALID")

    def test_signing_fails_closed_in_production_without_secret(self):
        with patch.dict(os.environ, {"WEALTH_ENV": "production", "DASHBOARD_SECRET_KEY": ""}):
            with self.assertRaises(RuntimeError) as ctx:
                get_kis_signing_secret()
            self.assertIn("DASHBOARD_SECRET_KEY", str(ctx.exception))

            with self.assertRaises(RuntimeError):
                sign_kis_feed_row(self.sample_row, user_id=self.user_id, source_account_key=self.account_key)

    def test_no_raw_cano_in_token_payload(self):
        token = sign_kis_feed_row(self.sample_row, user_id=self.user_id, source_account_key=self.account_key)
        s = _get_serializer()
        payload = s.loads(token, salt=KIS_ROW_SELECTION_SALT)
        self.assertNotIn("12345678", str(payload))
        self.assertEqual(payload["source_account_key"], self.account_key)

    def test_overseas_missing_fx_semantics(self):
        row_no_fx = {
            "trad_day": "20240320",
            "ovrs_pdno": "NVDA",
            "ovrs_item_name": "엔비디아",
            "slcl_qty": "5",
            "frcr_sll_amt_smtl1": "1000.0",
            "frcr_pchs_amt1": "800.0",
            "ovrs_rlzt_pfls_amt": "200.0",
            "pftrt": "25.0",
            "crcy_cd": "USD",
        }
        proj = project_kis_feed_row(row_no_fx, market="us")
        self.assertEqual(proj["profit_loss"], 200.0)
        self.assertIsNone(proj["fx_rate"])
        self.assertIsNone(proj["profit_loss_krw"])  # MUST BE None, never 200.0
        self.assertNotIn("raw", proj)

    def test_overseas_with_fx_semantics(self):
        row_with_fx = {
            "trad_day": "20240320",
            "ovrs_pdno": "NVDA",
            "ovrs_item_name": "엔비디아",
            "slcl_qty": "5",
            "frcr_sll_amt_smtl1": "1000.0",
            "frcr_pchs_amt1": "800.0",
            "ovrs_rlzt_pfls_amt": "200.0",
            "pftrt": "25.0",
            "bass_exrt": "1350.0",
            "crcy_cd": "USD",
        }
        proj = project_kis_feed_row(row_with_fx, market="us")
        self.assertEqual(proj["profit_loss"], 200.0)
        self.assertEqual(proj["fx_rate"], 1350.0)
        self.assertEqual(proj["profit_loss_krw"], 270000.0)
        self.assertNotIn("raw", proj)

    def test_validate_kis_feed_request(self):
        m, f, t = validate_kis_feed_request("kr", "2024-01-01", "2024-03-31")
        self.assertEqual(m, "kr")
        self.assertEqual(f, "2024-01-01")
        self.assertEqual(t, "2024-03-31")

        m, f, t = validate_kis_feed_request("overseas", "2024-01-01", "2024-03-31")
        self.assertEqual(m, "us")

        with self.assertRaises(ValueError):
            validate_kis_feed_request("crypto", "2024-01-01", "2024-03-31")

        with self.assertRaises(ValueError):
            validate_kis_feed_request("kr", "2024-05-01", "2024-01-01")  # from > to

    def test_build_feed_response(self):
        resp = build_kis_realized_feed_response(
            market="kr",
            from_date="2024-04-01",
            to_date="2024-04-30",
            rows_raw=[self.sample_row],
            source_account_key=self.account_key,
            source_account_label="1234****-01",
            user_id=self.user_id,
        )
        self.assertEqual(resp["source"], "kis")
        self.assertEqual(resp["kind"], "realized_pnl_feed")
        self.assertTrue(resp["scope_verified"])
        self.assertEqual(resp["source_account_key"], self.account_key)
        self.assertEqual(resp["source_account_label"], "1234****-01")
        self.assertTrue(resp["read_only"])
        self.assertFalse(resp["persisted"])
        self.assertEqual(len(resp["rows"]), 1)
        self.assertEqual(len(resp["selection_tokens"]), 1)
        self.assertNotIn("raw", resp["rows"][0])

    def test_preview_ticket_sign_and_verify(self):
        items_hash = compute_kis_items_hash([{"row": self.sample_row, "selection_token": "tok"}])
        ticket = sign_kis_import_preview_ticket(
            account_id="acc-123",
            items_hash=items_hash,
            user_id=self.user_id,
            source_account_key=self.account_key,
        )
        valid, err = verify_kis_import_preview_ticket(
            ticket,
            account_id="acc-123",
            items_hash=items_hash,
            user_id=self.user_id,
            expected_account_key=self.account_key,
        )
        self.assertTrue(valid)
        self.assertIsNone(err)

        # Tampered items hash
        valid, err = verify_kis_import_preview_ticket(
            ticket,
            account_id="acc-123",
            items_hash="tampered_hash",
            user_id=self.user_id,
            expected_account_key=self.account_key,
        )
        self.assertFalse(valid)
        self.assertEqual(err, "ITEMS_TAMPERED")

        # Destination account changed
        valid, err = verify_kis_import_preview_ticket(
            ticket,
            account_id="other-account",
            items_hash=items_hash,
            user_id=self.user_id,
            expected_account_key=self.account_key,
        )
        self.assertFalse(valid)
        self.assertEqual(err, "DESTINATION_ACCOUNT_CHANGED")


if __name__ == "__main__":
    unittest.main()
