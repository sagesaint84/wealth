import json
import unittest
from app.services.kis_feed import sign_kis_feed_row, project_kis_feed_row
from app.services.kis_realized import (
    map_kis_domestic_profit_row,
    build_kis_realized_fingerprint,
    preview_kis_realized_selection,
)
from app.services.kis_openapi import compute_kis_account_key


class TestKISRealizedPreview(unittest.TestCase):
    def setUp(self):
        self.user_id = "test_user"
        self.account_key = compute_kis_account_key("12345678", "01")
        self.masked_label = "1234****-01"
        self.dest_account = {
            "id": "acc-kis-1",
            "account_name": "한투종합",
            "broker": "한국투자증권",
            "owner": "김철수",
        }
        self.row1 = {
            "trad_dt": "20240410",
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "sll_qty": "10",
            "sll_amt": "840000",
            "buy_amt": "700000",
            "pchs_amt": "700000",
            "rlzt_pfls": "140000",
            "pfls_rt": "20.00",
        }
        self.token1 = sign_kis_feed_row(self.row1, user_id=self.user_id, source_account_key=self.account_key)

    def test_preview_all_new(self):
        selected = [{"row": self.row1, "selection_token": self.token1}]
        res = preview_kis_realized_selection(
            selected_items=selected,
            destination_account=self.dest_account,
            existing_records=[],
            user_id=self.user_id,
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            market="kr",
        )
        self.assertEqual(res["counts"]["new"], 1)
        self.assertEqual(res["counts"]["already_imported"], 0)
        self.assertEqual(res["counts"]["possible_duplicate"], 0)
        self.assertEqual(res["counts"]["invalid"], 0)
        self.assertTrue(res["scope_verified"])
        self.assertEqual(res["source_account_key"], self.account_key)
        self.assertEqual(res["source_account_label"], self.masked_label)
        self.assertEqual(res["items"][0]["status"], "NEW")
        self.assertNotIn("12345678", json.dumps(res))

    def test_preview_already_imported_exact_match(self):
        cand1 = map_kis_domestic_profit_row(
            self.row1,
            account_name="한투종합",
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            owner="김철수",
            fetched_at="2024-04-10",
        )
        fp1 = build_kis_realized_fingerprint(cand1)
        existing = [{
            "id": "rec-1",
            "source": "kis",
            "source_fingerprint": fp1,
            "source_account_key": self.account_key,
            "date": "2024-04-10",
            "code": "005930",
            "pnl": 140000.0,
        }]

        selected = [{"row": self.row1, "selection_token": self.token1}]
        res = preview_kis_realized_selection(
            selected_items=selected,
            destination_account=self.dest_account,
            existing_records=existing,
            user_id=self.user_id,
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            market="kr",
        )
        self.assertEqual(res["counts"]["new"], 0)
        self.assertEqual(res["counts"]["already_imported"], 1)
        self.assertEqual(res["items"][0]["status"], "ALREADY_IMPORTED")

    def test_preview_possible_duplicate_manual_match(self):
        # A manual record with same date, code, and PnL
        manual_existing = [{
            "id": "rec-manual-1",
            "source": "manual",
            "date": "2024-04-10",
            "code": "005930",
            "name": "삼성전자",
            "pnl": 140000.0,
            "pnl_krw": 140000.0,
            "account_name": "수동계좌",
        }]

        selected = [{"row": self.row1, "selection_token": self.token1}]
        res = preview_kis_realized_selection(
            selected_items=selected,
            destination_account=self.dest_account,
            existing_records=manual_existing,
            user_id=self.user_id,
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            market="kr",
        )
        self.assertEqual(res["counts"]["new"], 0)
        self.assertEqual(res["counts"]["possible_duplicate"], 1)
        self.assertEqual(res["items"][0]["status"], "POSSIBLE_DUPLICATE")
        self.assertEqual(res["items"][0]["matched_record"]["id"], "rec-manual-1")

    def test_preview_invalid_token(self):
        selected = [{"row": self.row1, "selection_token": "bad_token"}]
        res = preview_kis_realized_selection(
            selected_items=selected,
            destination_account=self.dest_account,
            existing_records=[],
            user_id=self.user_id,
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            market="kr",
        )
        self.assertEqual(res["counts"]["invalid"], 1)
        self.assertEqual(res["items"][0]["status"], "INVALID")

    def test_kis_real_domestic_shape_preview_is_new(self):
        # Authoritative official KIS TTTC8715R domestic shape
        real_kis_row = {
            "trad_dt": "20260312",
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "sll_qty": "10",
            "sll_amt": "840000",
            "buy_amt": "700000",  # Official field: buy_amt is present!
            "rlzt_pfls": "140000",
            "pfls_rt": "20.00",
            "fee": "100",
            "tl_tax": "1500",
        }
        # 1. Project to feed format
        projected = project_kis_feed_row(real_kis_row, market="kr")
        self.assertEqual(projected["buy_amount"], 700000.0)
        self.assertEqual(projected["sell_amount"], 840000.0)
        self.assertEqual(projected["profit_loss"], 140000.0)

        # 2. Sign token
        token = sign_kis_feed_row(projected, user_id=self.user_id, source_account_key=self.account_key)

        # 3. Simulate browser JSON roundtrip (int vs float)
        browser_json = json.dumps([{"row": projected, "selection_token": token}])
        selected_from_browser = json.loads(browser_json)

        # 4. Preview classification
        res = preview_kis_realized_selection(
            selected_items=selected_from_browser,
            destination_account=self.dest_account,
            existing_records=[],
            user_id=self.user_id,
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            market="kr",
        )
        self.assertEqual(res["counts"]["new"], 1)
        self.assertEqual(res["counts"]["invalid"], 0)
        self.assertEqual(res["counts"]["already_imported"], 0)
        self.assertEqual(res["counts"]["possible_duplicate"], 0)
        self.assertEqual(res["items"][0]["status"], "NEW")
        self.assertEqual(res["items"][0]["candidate"]["source_meta"]["buy_amount"], 700000.0)

    def test_kis_domestic_zero_buy_amount_preserved(self):
        zero_cost_row = {
            "trad_dt": "20260312",
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "sll_qty": "5",
            "sll_amt": "350000",
            "buy_amt": "0",  # Genuine zero
            "rlzt_pfls": "350000",
            "pfls_rt": "100.00",
        }
        projected = project_kis_feed_row(zero_cost_row, market="kr")
        self.assertEqual(projected["buy_amount"], 0.0)
        token = sign_kis_feed_row(projected, user_id=self.user_id, source_account_key=self.account_key)

        res = preview_kis_realized_selection(
            selected_items=[{"row": projected, "selection_token": token}],
            destination_account=self.dest_account,
            existing_records=[],
            user_id=self.user_id,
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            market="kr",
        )
        self.assertEqual(res["counts"]["new"], 1)
        self.assertEqual(res["counts"]["invalid"], 0)
        self.assertEqual(res["items"][0]["candidate"]["source_meta"]["buy_amount"], 0.0)

    def test_kis_domestic_missing_buy_amount_invalid(self):
        missing_buy_row = {
            "trad_dt": "20260312",
            "pdno": "005930",
            "prdt_name": "삼성전자",
            "sll_qty": "5",
            "sll_amt": "350000",
            # buy_amt and pchs_amt completely missing
            "rlzt_pfls": "350000",
            "pfls_rt": "100.00",
        }
        projected = project_kis_feed_row(missing_buy_row, market="kr")
        self.assertIsNone(projected["buy_amount"])
        token = sign_kis_feed_row(projected, user_id=self.user_id, source_account_key=self.account_key)

        res = preview_kis_realized_selection(
            selected_items=[{"row": projected, "selection_token": token}],
            destination_account=self.dest_account,
            existing_records=[],
            user_id=self.user_id,
            source_account_key=self.account_key,
            source_account_label=self.masked_label,
            market="kr",
        )
        self.assertEqual(res["counts"]["invalid"], 1)
        self.assertEqual(res["counts"]["new"], 0)
        self.assertEqual(res["items"][0]["status"], "INVALID")
        self.assertEqual(res["items"][0]["reason"], "MISSING_BUY_AMOUNT")


if __name__ == "__main__":
    unittest.main()
