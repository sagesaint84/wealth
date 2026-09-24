from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.toss_wts_income import map_toss_wts_income_row
from app.services.toss_wts_income_feed import (
    compute_income_items_hash,
    sign_income_feed_row,
    sign_income_preview_ticket,
    verify_income_feed_row_token,
    verify_income_preview_ticket,
)
from app.services.toss_wts_income_import import preview_toss_wts_income_selection
from app.services.dividend_records import create_dividend_record, read_dividend_records


def row(*, no=7, adjusted=8460):
    return {
        "market": "kr", "category": "cash", "currency": "KRW",
        "datetime": "2026-09-01T12:00:00+09:00", "display_type": "13",
        "stock_name": "테스트주식", "amount": 10000, "adjusted_amount": adjusted,
        "income_type": "dividend", "display_code": "005930", "display_name": "테스트주식",
        "net_amount": adjusted, "gross_amount": 10000, "tax": 1540,
        "source_meta": {
            "summary_no": "1104", "trade_type_name": "배당금입금",
            "transaction_type_code": "1", "transaction_type_name": "입금",
            "display_type": "13", "stock_code": "005930", "stock_name": "테스트주식",
            "product_name": "테스트주식", "quantity": 0,
            "provider_amount": 10000, "provider_adjusted_amount": adjusted,
            "provider_tax_amount": 1540, "composite_key": {"date": "20260901", "no": no},
        },
    }


def account():
    return {"id": "acct-1", "broker": "토스증권", "account_name": "토스", "owner": "아빠"}


class IncomeFeedSecurityTests(unittest.TestCase):
    def secret_env(self):
        return patch.dict(os.environ, {"WEALTH_APP_SECRET": "test-income-secret-abcdefghijklmnopqrstuvwxyz"}, clear=False)

    def test_row_token_binds_user_generation_and_content(self):
        with self.secret_env():
            token = sign_income_feed_row(row(), user_id="u1", generation_id="g1")
            self.assertEqual(verify_income_feed_row_token(row(), token, user_id="u1", current_generation_id="g1"), (True, None))
            self.assertEqual(verify_income_feed_row_token(row(), token, user_id="u2", current_generation_id="g1")[1], "USER_MISMATCH")
            self.assertEqual(verify_income_feed_row_token(row(), token, user_id="u1", current_generation_id="g2")[1], "RUNTIME_GENERATION_CHANGED")
            tampered = row(adjusted=9999)
            self.assertEqual(verify_income_feed_row_token(tampered, token, user_id="u1", current_generation_id="g1")[1], "ROW_TAMPERED")

    def test_preview_ticket_binds_account_and_items(self):
        with self.secret_env():
            token = sign_income_feed_row(row(), user_id="u1", generation_id="g1")
            selected = [{"row": row(), "selection_token": token}]
            items_hash = compute_income_items_hash(selected)
            ticket = sign_income_preview_ticket(account_id="acct-1", items_hash=items_hash, user_id="u1", generation_id="g1")
            self.assertEqual(verify_income_preview_ticket(ticket, account_id="acct-1", items_hash=items_hash, user_id="u1", current_generation_id="g1"), (True, None))
            self.assertEqual(verify_income_preview_ticket(ticket, account_id="acct-2", items_hash=items_hash, user_id="u1", current_generation_id="g1")[1], "DESTINATION_ACCOUNT_CHANGED")


class IncomePreviewTests(unittest.TestCase):
    def secret_env(self):
        return patch.dict(os.environ, {"WEALTH_APP_SECRET": "test-income-secret-abcdefghijklmnopqrstuvwxyz"}, clear=False)

    def selected(self):
        token = sign_income_feed_row(row(), user_id="u1", generation_id="g1")
        return [{"row": row(), "selection_token": token}]

    def test_new_exact_and_manual_duplicate_classification(self):
        with self.secret_env():
            selected = self.selected()
            fresh = preview_toss_wts_income_selection(selected, account(), [], user_id="u1", current_generation_id="g1")
            self.assertEqual(fresh["counts"]["new"], 1)
            candidate = fresh["items"][0]["candidate"]
            existing_wts = [{**candidate, "source": "toss_wts"}]
            exact = preview_toss_wts_income_selection(selected, account(), existing_wts, user_id="u1", current_generation_id="g1")
            self.assertEqual(exact["counts"]["already_imported"], 1)
            manual = [{"date": candidate["date"], "code": candidate["code"], "name": candidate["name"], "currency": candidate["currency"], "amount": candidate["amount"]}]
            possible = preview_toss_wts_income_selection(selected, account(), manual, user_id="u1", current_generation_id="g1")
            self.assertEqual(possible["counts"]["possible_duplicate"], 1)

    def test_bad_token_is_invalid(self):
        with self.secret_env():
            selected = [{"row": row(), "selection_token": "bad"}]
            result = preview_toss_wts_income_selection(selected, account(), [], user_id="u1", current_generation_id="g1")
            self.assertEqual(result["counts"]["invalid"], 1)


class DividendRecordMetadataTests(unittest.TestCase):
    def test_create_preserves_income_source_metadata(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "app.services.dividend_records._get_user_dir",
            side_effect=lambda username=None: Path(temp) / (username or "sagesaint"),
        ), patch(
            "app.services.dividend_records.resolve_stock_info",
            side_effect=lambda code, name, curr: (code, name, curr),
        ), patch(
            "app.services.dividend_records.get_historical_fx_rate",
            return_value=1300.0,
        ):
            candidate = map_toss_wts_income_row(row())
            candidate.update({
                "owner": "아빠", "account_name": "토스", "source_scope_verified": False,
                "imported_by_user_action": True, "imported_at": "2026-09-24T12:00:00+09:00",
            })
            created = create_dividend_record(candidate, username="alice")
            records = read_dividend_records("alice")
        self.assertEqual(len(records), 1)
        self.assertEqual(created["income_type"], "dividend")
        self.assertEqual(created["gross_amount"], 10000)
        self.assertEqual(created["tax"], 1540)
        self.assertTrue(created["source_fingerprint"].startswith("toss-wts-income:v1:"))
        self.assertFalse(created["source_scope_verified"])
        self.assertEqual(created["source_meta"]["summary_no"], "1104")


if __name__ == "__main__":
    unittest.main()
