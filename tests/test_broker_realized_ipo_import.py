from __future__ import annotations

import copy
import unittest

from app.services.broker_realized_import import (
    BrokerRealizedImportError,
    apply_wealth_import_preferences,
    compute_wealth_import_items_hash,
    ipo_fee_memo_annotation,
    normalize_wealth_import_preference,
)
from app.services.kiwoom_feed import canonical_kiwoom_row_hash
from app.services.kiwoom_realized import classify_kiwoom_rows, kiwoom_fingerprint
from app.services import pnl_records
from tests.regression_support import IsolatedDataTestCase


class BrokerRealizedIpoImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = {
            "date": "20260901", "code": "SYN", "name": "Synthetic",
            "quantity": "1", "buy_amount": "10000", "sell_amount": "15000",
            "pnl": "5000", "pnl_krw": "5000", "currency": "KRW",
            "fee": "100", "tax": "50", "expenses_total": None, "memo": "",
            "source_occurrence": 1,
        }

    def apply(self, preferences, candidates=None):
        rows = candidates or [copy.deepcopy(self.candidate) for _ in preferences]
        result = {"items": [
            {"index": index, "status": "NEW", "fingerprint": f"synthetic-{index}", "candidate": row}
            for index, row in enumerate(rows)
        ]}
        selected = [
            {"row": copy.deepcopy(row), "selection_token": f"token-{index}", "wealth_import": preference}
            for index, (row, preference) in enumerate(zip(rows, preferences))
        ]
        return apply_wealth_import_preferences(result, selected), selected

    def test_general_default_has_zero_fee_effect_and_no_annotation(self):
        result, _ = self.apply([{"stock_type": "general", "ipo_subscription_fee_krw": "9999"}])
        candidate = result["items"][0]["candidate"]
        self.assertFalse(candidate["is_ipo"])
        self.assertEqual(candidate["asset_type"], "stock")
        self.assertEqual(candidate["ipo_subscription_fee_krw"], 0)
        self.assertEqual(candidate["pnl"], "5000")
        self.assertEqual(candidate["memo"], "")

    def test_ipo_default_fee_is_deducted_once_and_annotated(self):
        result, _ = self.apply([{"stock_type": "ipo"}])
        item = result["items"][0]
        candidate = item["candidate"]
        self.assertTrue(candidate["is_ipo"])
        self.assertEqual(candidate["asset_type"], "ipo")
        self.assertEqual(candidate["provider_realized_pnl"], "5000")
        self.assertEqual(candidate["ipo_subscription_fee_krw"], 2000)
        self.assertEqual(candidate["pnl"], "3000")
        self.assertEqual(candidate["pnl_krw"], "3000")
        self.assertEqual(candidate["fee"], "100")
        self.assertEqual(candidate["tax"], "50")
        self.assertEqual(candidate["memo"], "공모수수료 2천원 차감")
        self.assertEqual(item["wealth_import"]["final_wealth_pnl"], "3000")

    def test_custom_and_zero_fee_memo_and_existing_memo_append(self):
        rows = [copy.deepcopy(self.candidate), copy.deepcopy(self.candidate)]
        rows[0]["memo"] = "기존 메모"
        result, _ = self.apply([
            {"stock_type": "ipo", "ipo_subscription_fee_krw": 3500},
            {"stock_type": "ipo", "ipo_subscription_fee_krw": 0},
        ], rows)
        first, second = [item["candidate"] for item in result["items"]]
        self.assertEqual(first["pnl"], "1500")
        self.assertEqual(first["memo"], "기존 메모 · 공모수수료 3500원 차감")
        self.assertEqual(second["pnl"], "5000")
        self.assertEqual(second["memo"], "공모수수료 0원 차감")
        self.assertEqual(ipo_fee_memo_annotation(2000), "공모수수료 2천원 차감")

    def test_memo_annotation_is_not_duplicated(self):
        row = copy.deepcopy(self.candidate)
        row["memo"] = "기존 메모 · 공모수수료 2천원 차감"
        result, _ = self.apply([{"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}], [row])
        self.assertEqual(result["items"][0]["candidate"]["memo"].count("공모수수료 2천원 차감"), 1)

    def test_invalid_ipo_fees_are_rejected(self):
        for value in ("", -1, "bad", "NaN", "Infinity", "-Infinity", 1.5):
            with self.subTest(value=value), self.assertRaises(BrokerRealizedImportError):
                normalize_wealth_import_preference({
                    "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": value}
                })

    def test_mixed_batch_keeps_per_row_choices(self):
        result, _ = self.apply([
            {"stock_type": "general"},
            {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000},
            {"stock_type": "general"},
        ])
        candidates = [item["candidate"] for item in result["items"]]
        self.assertEqual([candidate["asset_type"] for candidate in candidates], ["stock", "ipo", "stock"])
        self.assertEqual([candidate["pnl"] for candidate in candidates], ["5000", "3000", "5000"])

    def test_preference_hash_binds_type_and_fee_to_each_token(self):
        base = "provider-items-hash"
        general = [{"selection_token": "token-a", "wealth_import": {"stock_type": "general"}}]
        ipo_2000 = [{"selection_token": "token-a", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}}]
        ipo_3000 = [{"selection_token": "token-a", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 3000}}]
        self.assertNotEqual(compute_wealth_import_items_hash(base, general), compute_wealth_import_items_hash(base, ipo_2000))
        self.assertNotEqual(compute_wealth_import_items_hash(base, ipo_2000), compute_wealth_import_items_hash(base, ipo_3000))

    def test_provider_hash_and_fingerprint_do_not_include_wealth_adjustment(self):
        provider_row = copy.deepcopy(self.candidate)
        row_hash = canonical_kiwoom_row_hash(provider_row)
        fingerprint = kiwoom_fingerprint(provider_row, "synthetic-source", 1)
        adjusted, _ = self.apply([{"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}], [provider_row])
        self.assertEqual(canonical_kiwoom_row_hash(provider_row), row_hash)
        self.assertEqual(kiwoom_fingerprint(provider_row, "synthetic-source", 1), fingerprint)
        self.assertNotEqual(adjusted["items"][0]["candidate"]["pnl"], provider_row["pnl"])

    def test_type_or_fee_change_cannot_bypass_provider_duplicate(self):
        row = copy.deepcopy(self.candidate)
        fingerprint = kiwoom_fingerprint(row, "synthetic-source", 1)
        existing = [{"source": "kiwoom", "source_fingerprint": fingerprint}]
        self.assertEqual(classify_kiwoom_rows([row], existing, "synthetic-source")[0]["status"], "ALREADY_IMPORTED")

    def test_foreign_currency_ipo_fee_fails_closed(self):
        row = copy.deepcopy(self.candidate)
        row.update({"currency": "USD", "pnl_krw": None})
        with self.assertRaisesRegex(BrokerRealizedImportError, "IPO_FEE_REQUIRES_KRW_PNL"):
            self.apply([{"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}], [row])


class BrokerRealizedIpoStorageRegressionTests(IsolatedDataTestCase):
    def test_new_fields_persist_and_summary_uses_final_net_once(self) -> None:
        username = "synthetic-ipo-storage"
        record = pnl_records.create_pnl_record({
            "date": "2026-09-01",
            "code": "SYNIPO",
            "name": "Synthetic IPO",
            "currency": "KRW",
            "pnl": 3000,
            "pnl_krw": 3000,
            "is_ipo": True,
            "asset_type": "ipo",
            "memo": "기존 메모 · 공모수수료 2천원 차감",
            "provider_realized_pnl": "5000",
            "ipo_subscription_fee_krw": 2000,
            "fee": "100",
            "tax": "50",
            "source": "kiwoom",
        }, username)

        self.assertEqual(record["provider_realized_pnl"], "5000")
        self.assertEqual(record["ipo_subscription_fee_krw"], 2000)
        self.assertEqual(record["memo"], "기존 메모 · 공모수수료 2천원 차감")
        self.assertEqual(record["fee"], "100")
        self.assertEqual(record["tax"], "50")

        summary = pnl_records.get_pnl_summary(year=2026, trade_type="ipo", username=username)
        self.assertEqual(summary["total_pnl_krw"], 3000)
        yearly = next(item for item in summary["yearly_schedule"] if item["year"] == "2026")
        self.assertEqual(yearly["total_krw"], 3000)

    def test_existing_manual_ipo_shape_remains_unchanged(self) -> None:
        username = "synthetic-manual-ipo"
        before = {
            "id": "manual-ipo",
            "date": "2026-08-01",
            "code": "SYNMANUAL",
            "name": "Synthetic Manual IPO",
            "asset_type": "ipo",
            "currency": "KRW",
            "pnl": 7000,
            "pnl_krw": 7000,
            "is_ipo": True,
            "memo": "기존 수동 메모",
        }
        pnl_records.write_pnl_records([copy.deepcopy(before)], username)

        summary = pnl_records.get_pnl_summary(year=2026, trade_type="ipo", username=username)
        stored = pnl_records.read_pnl_records(username)[0]
        self.assertEqual(stored, before)
        self.assertEqual(summary["total_pnl_krw"], 7000)
        self.assertEqual(summary["records"][0]["memo"], "기존 수동 메모")


class BrokerRealizedSecondChanceModalContractTests(IsolatedDataTestCase):
    """Verifies Cases A through K for the confirmation modal second-chance editing."""

    def setUp(self) -> None:
        super().setUp()
        self.candidate = {
            "date": "20260901", "code": "SYN", "name": "Synthetic",
            "quantity": "1", "buy_amount": "10000", "sell_amount": "15000",
            "pnl": "5000", "pnl_krw": "5000", "currency": "KRW",
            "fee": "100", "tax": "50", "expenses_total": None, "memo": "",
            "source_occurrence": 1,
        }

    def test_case_a_initial_general_opens_as_general(self):
        # Case A: previous screen general -> modal opens general, 0 fee effect, no annotation
        result = {"items": [{"index": 0, "status": "NEW", "fingerprint": "f1", "candidate": copy.deepcopy(self.candidate)}]}
        selected = [{"row": copy.deepcopy(self.candidate), "selection_token": "tok-1", "wealth_import": {"stock_type": "general"}}]
        applied = apply_wealth_import_preferences(result, selected)
        cand = applied["items"][0]["candidate"]
        self.assertFalse(cand["is_ipo"])
        self.assertEqual(cand["asset_type"], "stock")
        self.assertEqual(cand["ipo_subscription_fee_krw"], 0)
        self.assertEqual(cand["pnl"], "5000")
        self.assertEqual(cand["memo"], "")

    def test_case_b_initial_ipo_default_fee_opens_as_ipo_2000(self):
        # Case B: previous screen ipo/2000 -> modal opens ipo/2000, 2000 deduction, memo annotated
        result = {"items": [{"index": 0, "status": "NEW", "fingerprint": "f1", "candidate": copy.deepcopy(self.candidate)}]}
        selected = [{"row": copy.deepcopy(self.candidate), "selection_token": "tok-1", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}}]
        applied = apply_wealth_import_preferences(result, selected)
        cand = applied["items"][0]["candidate"]
        self.assertTrue(cand["is_ipo"])
        self.assertEqual(cand["asset_type"], "ipo")
        self.assertEqual(cand["ipo_subscription_fee_krw"], 2000)
        self.assertEqual(cand["pnl"], "3000")
        self.assertEqual(cand["memo"], "공모수수료 2천원 차감")

    def test_case_c_initial_ipo_custom_fee_preserves_fee(self):
        # Case C: previous screen ipo/custom -> modal preserves custom fee
        result = {"items": [{"index": 0, "status": "NEW", "fingerprint": "f1", "candidate": copy.deepcopy(self.candidate)}]}
        selected = [{"row": copy.deepcopy(self.candidate), "selection_token": "tok-1", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 3500}}]
        applied = apply_wealth_import_preferences(result, selected)
        cand = applied["items"][0]["candidate"]
        self.assertEqual(cand["ipo_subscription_fee_krw"], 3500)
        self.assertEqual(cand["pnl"], "1500")
        self.assertEqual(cand["memo"], "공모수수료 3500원 차감")

    def test_case_d_second_chance_general_to_ipo_applies_deduction(self):
        # Case D: user changes modal from general to ipo -> preview refreshed with ipo deduction
        row = copy.deepcopy(self.candidate)
        result = {"items": [{"index": 0, "status": "NEW", "fingerprint": "f1", "candidate": copy.deepcopy(row)}]}
        # First preview: general
        sel_general = [{"row": copy.deepcopy(row), "selection_token": "tok-1", "wealth_import": {"stock_type": "general"}}]
        prev1 = apply_wealth_import_preferences(copy.deepcopy(result), sel_general)
        self.assertEqual(prev1["items"][0]["candidate"]["pnl"], "5000")

        # Second preview after modal change: ipo with default 2000
        sel_ipo = [{"row": copy.deepcopy(row), "selection_token": "tok-1", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}}]
        prev2 = apply_wealth_import_preferences(copy.deepcopy(result), sel_ipo)
        self.assertEqual(prev2["items"][0]["candidate"]["pnl"], "3000")
        self.assertEqual(prev2["items"][0]["candidate"]["memo"], "공모수수료 2천원 차감")

    def test_case_e_second_chance_ipo_to_general_clears_deduction(self):
        # Case E: user changes modal from ipo to general -> preview refreshed with zero fee effect and memo cleared
        row = copy.deepcopy(self.candidate)
        result = {"items": [{"index": 0, "status": "NEW", "fingerprint": "f1", "candidate": copy.deepcopy(row)}]}
        # First preview: ipo
        sel_ipo = [{"row": copy.deepcopy(row), "selection_token": "tok-1", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}}]
        prev1 = apply_wealth_import_preferences(copy.deepcopy(result), sel_ipo)
        self.assertEqual(prev1["items"][0]["candidate"]["pnl"], "3000")

        # Second preview after modal change: general
        sel_general = [{"row": copy.deepcopy(row), "selection_token": "tok-1", "wealth_import": {"stock_type": "general"}}]
        prev2 = apply_wealth_import_preferences(copy.deepcopy(result), sel_general)
        self.assertEqual(prev2["items"][0]["candidate"]["pnl"], "5000")
        self.assertEqual(prev2["items"][0]["candidate"]["memo"], "")

    def test_case_f_and_g_modal_fee_or_type_change_invalidates_ticket_hash(self):
        # Case F & G: changing fee or type alters computed items hash, invalidating any existing ticket
        base_hash = "base-items-hash-12345"
        items_general = [{"selection_token": "tok-1", "wealth_import": {"stock_type": "general"}}]
        items_ipo_2000 = [{"selection_token": "tok-1", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}}]
        items_ipo_3000 = [{"selection_token": "tok-1", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 3000}}]

        hash_gen = compute_wealth_import_items_hash(base_hash, items_general)
        hash_2000 = compute_wealth_import_items_hash(base_hash, items_ipo_2000)
        hash_3000 = compute_wealth_import_items_hash(base_hash, items_ipo_3000)

        self.assertNotEqual(hash_gen, hash_2000)
        self.assertNotEqual(hash_2000, hash_3000)
        self.assertNotEqual(hash_gen, hash_3000)

    def test_case_h_and_i_stale_ticket_rejected_on_commit(self):
        # Case H & I: stale ticket generated for general is rejected if committed with ipo
        from unittest.mock import AsyncMock, patch
        from starlette.testclient import TestClient
        from app.services import portfolio, user_openapi
        from app.services.kiwoom_feed import build_kiwoom_realized_feed
        from tests.test_request_state_user_id import _import_main_without_loading_real_env

        main = _import_main_without_loading_real_env()
        client = TestClient(main.app)
        username = "synthetic-second-chance-user"
        user_id = "uid-sc-123"
        dest_account = {"id": "acc-sc-1", "broker": "키움증권", "name": "SC Dest", "account_name": "SC Dest", "owner": "본인"}
        portfolio.write_portfolio({"accounts": [dest_account], "holdings": [], "settings": {"fx_rates": {"KRW": 1.0}}}, username)

        token = main._serializer.dumps({"user": username, "role": "user"})
        headers = {"Cookie": f"{main.COOKIE_NAME}={token}"}
        source_key = "k" * 64

        import os
        with patch.dict(os.environ, {"WEALTH_ENV": "test", "WEALTH_TEST_SIGNING_SECRET": "synthetic-second-chance-secret", "DASHBOARD_SECRET_KEY": "synthetic-second-chance-secret"}, clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value={"username": username, "id": user_id, "role": "user", "must_change_password": False}), \
             patch.object(user_openapi, "get_user_openapi_config", return_value={"kiwoom": {"app_key": "SYN", "app_secret": "SYN"}}), \
             patch("app.services.kiwoom_openapi.KiwoomOpenAPI.get_realized_source_account_state", new_callable=AsyncMock, return_value=(source_key, "******1234")):


            raw_row = {
                "dt": "20260901", "stk_cd": "A005930", "stk_nm": "Samsung",
                "cntr_qty": "1", "buy_uv": "50000", "cntr_pric": "60000", "tdy_sel_pl": "10000",
                "pl_rt": "20", "tdy_trde_cmsn": "50", "tdy_trde_tax": "150",
            }
            feed = build_kiwoom_realized_feed([raw_row], market="kr", source_account_key=source_key, source_account_label="******1234", user_id=user_id)
            tok = feed["selection_tokens"][0]

            # 1. Preview with general stock type
            sel_general = [{"row": feed["rows"][0], "selection_token": tok, "wealth_import": {"stock_type": "general"}}]
            preview_res1 = client.post("/api/kiwoom/realized-feed/import-preview", headers=headers, json={
                "market": "kr", "source_account_key": source_key, "account_id": dest_account["id"], "selected_items": sel_general,
            })
            self.assertEqual(preview_res1.status_code, 200)
            ticket_general = preview_res1.json()["preview_ticket"]

            # 2. Try to commit with ipo using ticket_general -> MUST FAIL with 400 (ITEMS_HASH_MISMATCH / PREVIEW_TICKET_INVALID)
            sel_ipo = [{"row": feed["rows"][0], "selection_token": tok, "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}}]
            bad_commit = client.post("/api/kiwoom/realized-feed/import", headers=headers, json={
                "market": "kr", "source_account_key": source_key, "account_id": dest_account["id"],
                "selected_items": sel_ipo, "preview_ticket": ticket_general,
            })
            self.assertEqual(bad_commit.status_code, 400)
            self.assertIn(bad_commit.json()["detail"]["code"], ("ITEMS_TAMPERED", "PREVIEW_TICKET_INVALID"))

            # 3. Fresh preview with ipo -> receives new valid ticket -> commit succeeds
            preview_res2 = client.post("/api/kiwoom/realized-feed/import-preview", headers=headers, json={
                "market": "kr", "source_account_key": source_key, "account_id": dest_account["id"], "selected_items": sel_ipo,
            })
            self.assertEqual(preview_res2.status_code, 200)
            ticket_ipo = preview_res2.json()["preview_ticket"]
            self.assertNotEqual(ticket_general, ticket_ipo)

            good_commit = client.post("/api/kiwoom/realized-feed/import", headers=headers, json={
                "market": "kr", "source_account_key": source_key, "account_id": dest_account["id"],
                "selected_items": sel_ipo, "preview_ticket": ticket_ipo,
            })
            self.assertEqual(good_commit.status_code, 200)
            self.assertEqual(good_commit.json()["imported"], 1)

            # Verify persisted record has net P/L adjusted by 2000 KRW
            records = pnl_records.read_pnl_records(username)
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["is_ipo"])
            self.assertEqual(records[0]["ipo_subscription_fee_krw"], 2000)
            self.assertEqual(records[0]["pnl"], 8000.0)  # 10000 - 2000
            self.assertEqual(records[0]["memo"], "공모수수료 2천원 차감")

        client.close()

    def test_case_j_multi_row_settings_independent(self):
        # Case J: multi-row selections remain independently editable
        row1 = copy.deepcopy(self.candidate)
        row1["name"] = "Stock A"
        row1["pnl"] = "10000"
        row2 = copy.deepcopy(self.candidate)
        row2["name"] = "Stock B"
        row2["pnl"] = "20000"

        result = {"items": [
            {"index": 0, "status": "NEW", "fingerprint": "f1", "candidate": copy.deepcopy(row1)},
            {"index": 1, "status": "NEW", "fingerprint": "f2", "candidate": copy.deepcopy(row2)},
        ]}
        selected = [
            {"row": row1, "selection_token": "tok-1", "wealth_import": {"stock_type": "general"}},
            {"row": row2, "selection_token": "tok-2", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 3000}},
        ]
        applied = apply_wealth_import_preferences(result, selected)
        cand1 = applied["items"][0]["candidate"]
        cand2 = applied["items"][1]["candidate"]

        self.assertFalse(cand1["is_ipo"])
        self.assertEqual(cand1["pnl"], "10000")
        self.assertEqual(cand1["memo"], "")

        self.assertTrue(cand2["is_ipo"])
        self.assertEqual(cand2["pnl"], "17000")  # 20000 - 3000
        self.assertEqual(cand2["memo"], "공모수수료 3000원 차감")

    def test_case_k_duplicate_classification_untouched(self):
        # Case K: duplicate classification remains untouched regardless of IPO preference
        row = copy.deepcopy(self.candidate)
        fingerprint = kiwoom_fingerprint(row, "source-sc", 1)
        existing = [{"source": "kiwoom", "source_fingerprint": fingerprint}]

        # classify_kiwoom_rows must return ALREADY_IMPORTED
        classified = classify_kiwoom_rows([row], existing, "source-sc")
        self.assertEqual(classified[0]["status"], "ALREADY_IMPORTED")

        # applying IPO preference does NOT alter status
        result = {"items": [{"index": 0, "status": classified[0]["status"], "fingerprint": fingerprint, "candidate": copy.deepcopy(row)}]}
        selected = [{"row": row, "selection_token": "tok-1", "wealth_import": {"stock_type": "ipo", "ipo_subscription_fee_krw": 2000}}]
        applied = apply_wealth_import_preferences(result, selected)
        self.assertEqual(applied["items"][0]["status"], "ALREADY_IMPORTED")


if __name__ == "__main__":
    unittest.main()
