import json, os, unittest
from decimal import Decimal
os.environ.setdefault("WEALTH_ENV", "test")
from app.services.nh_feed import canonical_nh_row_hash, project_nh_row, sign_nh_feed_row, verify_nh_feed_row, sign_nh_import_preview_ticket, verify_nh_import_preview_ticket, build_nh_realized_feed

class NhFeedTests(unittest.TestCase):
    def test_domestic_projection_and_numeric_roundtrip(self):
        raw = {"_wealth_date_context":"20260102","iem_cd":"SYN","iem_nm":"Synthetic","sll_qty":"10.0","byn_amt":"0","sll_amt":"100","pls_amt":"10","pft_rt":"1","fee_sum":"2","tax_sum":"3"}
        row = project_nh_row(raw, "kr")
        self.assertEqual(row["buy_amount"], "0"); self.assertEqual(row["pnl_krw"], "10")
        copy = json.loads(json.dumps(row)); self.assertEqual(canonical_nh_row_hash(row), canonical_nh_row_hash(copy))
        token=sign_nh_feed_row(row,user_id="u",source_account_key="k",market="kr")
        self.assertEqual(verify_nh_feed_row(copy,token,user_id="u",source_account_key="k",market="kr"),(True,None))
        copy["pnl"] = 11; self.assertEqual(verify_nh_feed_row(copy,token,user_id="u",source_account_key="k",market="kr")[1],"ROW_TAMPERED")
    def test_overseas_expense_and_null_fx(self):
        row=project_nh_row({"_wealth_date_context":"20260102","_wealth_country_context":"200","_wealth_currency_context":"USD","iem_cd":"SYN","iem_nm":"Synthetic","fc_sdr_xps":"4","fc_rzt_pls":"5"},"us")
        self.assertEqual(row["expenses_total"],"4"); self.assertIsNone(row["fee"]); self.assertIsNone(row["tax"]); self.assertIsNone(row["pnl_krw"]); self.assertIsNone(row["fx_rate"])
    def test_lossless_decimal_canonicalization(self):
        hashes = {
            canonical_nh_row_hash({"pnl": value})
            for value in (10, 10.0, "10", "10.0", "10.000", Decimal("10.000"))
        }
        self.assertEqual(len(hashes), 1)
        self.assertNotEqual(canonical_nh_row_hash({"pnl": 1000000000001}), canonical_nh_row_hash({"pnl": 1000000000002}))
        self.assertNotEqual(canonical_nh_row_hash({"pnl": "1.0000000000000000001"}), canonical_nh_row_hash({"pnl": "1.0000000000000000002"}))
        for value in ("NaN", "Infinity", "-Infinity", Decimal("NaN")):
            with self.subTest(value=str(value)):
                with self.assertRaises(ValueError):
                    canonical_nh_row_hash({"pnl": value})
    def test_preview_ticket_binds_all_authorization_context(self):
        token=sign_nh_import_preview_ticket(account_id="a",items_hash="h",user_id="u",source_account_key="k",market="kr")
        self.assertEqual(verify_nh_import_preview_ticket(token,account_id="a",items_hash="h",user_id="u",source_account_key="k",market="kr"),(True,None))
        self.assertEqual(verify_nh_import_preview_ticket(token,account_id="b",items_hash="h",user_id="u",source_account_key="k",market="kr")[1],"DESTINATION_ACCOUNT_CHANGED")
        self.assertEqual(verify_nh_import_preview_ticket(token,account_id="a",items_hash="h",user_id="u",source_account_key="k",market="us")[1],"MARKET_MISMATCH")
    def test_identical_feed_rows_get_stable_distinct_signed_occurrences(self):
        raw={"_wealth_date_context":"20260102","iem_cd":"SYN","iem_nm":"Synthetic","sll_qty":"1","byn_uit_pr":"10","byn_amt":"10","sll_uit_pr":"20","sll_amt":"20","pls_amt":"10"}
        feed=build_nh_realized_feed([raw,dict(raw)],market="kr",source_account_key="k",source_account_label="masked",user_id="u")
        self.assertEqual([r["source_occurrence"] for r in feed["rows"]],[0,1])
        self.assertNotEqual(feed["selection_tokens"][0],feed["selection_tokens"][1])
