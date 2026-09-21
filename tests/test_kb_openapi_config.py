"""Tests for KB OpenAPI configuration resolution and safety."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from app.services import user_openapi
from app.services.kb_openapi import KBOpenAPI
from app.services.user_identity import generate_user_id
from app.services.user_openapi import (
    _validate_and_derive_kb_account,
    get_masked_user_openapi_config,
    save_user_openapi_config,
)
from tests.test_request_state_user_id import _import_main_without_loading_real_env

_ORIGINAL_GET_USER_OPENAPI_CONFIG = user_openapi.get_user_openapi_config



class TestKBOpenAPIConfig(unittest.TestCase):
    def test_validation_and_derivation_helpers(self):
        # A. 11 digits accepted
        acc11, gnl, gds = _validate_and_derive_kb_account("12345678901")
        self.assertEqual(acc11, "12345678901")
        self.assertEqual(gnl, "123678901")  # acc[:3] + acc[5:]
        self.assertEqual(gds, "45")         # acc[3:5]

        # B. 11 digits with hyphens normalized (e.g. AAA-BB-CCCCCC)
        acc11, gnl, gds = _validate_and_derive_kb_account("123-45-678901")
        self.assertEqual(acc11, "12345678901")
        self.assertEqual(gnl, "123678901")
        self.assertEqual(gds, "45")

        # C. Leading zero preserved
        acc11, gnl, gds = _validate_and_derive_kb_account("01234567890")
        self.assertEqual(acc11, "01234567890")
        self.assertEqual(gnl, "012567890")  # preserves '012' and '567890'
        self.assertEqual(gds, "34")

        # Empty string returns empty tuple
        self.assertEqual(_validate_and_derive_kb_account(""), ("", "", ""))

        # D. 10 digits rejected
        with self.assertRaises(ValueError) as cm:
            _validate_and_derive_kb_account("1234567890")
        self.assertEqual(str(cm.exception), "KB증권 계좌번호 11자리를 확인하세요.")

        # E. 12 digits rejected
        with self.assertRaises(ValueError) as cm:
            _validate_and_derive_kb_account("123456789012")
        self.assertEqual(str(cm.exception), "KB증권 계좌번호 11자리를 확인하세요.")

        # F. Non-digit rejected
        with self.assertRaises(ValueError) as cm:
            _validate_and_derive_kb_account("12345abcd01")
        self.assertEqual(str(cm.exception), "KB증권 계좌번호 11자리를 확인하세요.")

        # Error does not leak account input
        with self.assertRaises(ValueError) as cm:
            _validate_and_derive_kb_account("999-88-77777")
        self.assertNotIn("999", str(cm.exception))

        # G. Derivation: AAA BB CCCCCC => gnl_ac_no = AAA + CCCCCC, gds_no = BB
        acc11, gnl, gds = _validate_and_derive_kb_account("00191123456")
        self.assertEqual(acc11, "00191123456")
        self.assertEqual(gnl, "001123456")
        self.assertEqual(len(gnl), 9)
        self.assertEqual(gds, "91")
        self.assertEqual(len(gds), 2)

        # H. Derived gds_no is NOT hardcoded (e.g. test multiple distinct values)
        _, _, gds1 = _validate_and_derive_kb_account("11102222222")
        _, _, gds2 = _validate_and_derive_kb_account("11177222222")
        self.assertEqual(gds1, "02")
        self.assertEqual(gds2, "77")
        self.assertNotEqual(gds1, gds2)


class TestKBOpenAPIFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wealth-kb-openapi-test-")
        self.fixture_users = Path(self.temp_dir.name) / "users"
        self.username = "synthetic-kb-cfg-user"
        self.user_id = generate_user_id()
        def _fixture_user_dir(u=None):
            p = self.fixture_users / (u or "fixture_default").strip()
            p.mkdir(parents=True, exist_ok=True)
            return p
        self.patchers = [
            patch.dict("os.environ", {"DASHBOARD_SECRET_KEY": "synthetic-kb-test-secret", "WEALTH_TEST_SIGNING_SECRET": "synthetic-kb-test-secret"}, clear=False),
            patch.object(user_openapi, "USERS_DIR", self.fixture_users),
            patch.object(user_openapi, "get_user_openapi_config", side_effect=_ORIGINAL_GET_USER_OPENAPI_CONFIG),
            patch("app.services.user_manager.get_user_by_name", return_value={
                "username": self.username, "id": self.user_id, "role": "user", "must_change_password": False,
            }),
            patch("app.services.user_manager.get_user_data_dir", side_effect=_fixture_user_dir),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def headers(self):
        token = self.main._serializer.dumps({"user": self.username, "role": "user"})
        return {"Cookie": f"{self.main.COOKIE_NAME}={token}"}

    def test_save_and_mask_kb_config_11digits(self):
        # 1. Save valid synthetic keys and 11-digit account (with hyphen)
        save_user_openapi_config(
            self.username,
            {
                "kb": {
                    "app_key": "mock-app-key-123",
                    "app_secret": "mock-secret-456",
                    "account_no": "012-34-567890",
                }
            },
        )

        # I, J, K. Verify masked retrieval: does not expose raw 11-digit, gnl_ac_no, or gds_no
        masked = get_masked_user_openapi_config(self.username)
        kb_masked = masked["kb"]

        self.assertNotIn("account11", kb_masked)
        self.assertNotIn("gnl_ac_no", kb_masked)
        self.assertNotIn("gds_no", kb_masked)
        self.assertEqual(kb_masked["app_key"], "mock****")
        self.assertEqual(kb_masked["app_secret"], "********")
        self.assertEqual(kb_masked["account_no"], "****7890-**")
        self.assertTrue(kb_masked["has_provider_account"])
        self.assertTrue(kb_masked["has_product_number"])
        self.assertTrue(kb_masked["has_account_no"])
        self.assertTrue(kb_masked["configured"])
        self.assertTrue(kb_masked["realized_configured"])

        # Verify persistent storage preserved leading zero and derived fields
        raw_cfg = user_openapi.get_user_openapi_config(self.username)
        self.assertEqual(raw_cfg["kb"]["account11"], "01234567890")
        self.assertEqual(raw_cfg["kb"]["gnl_ac_no"], "012567890")
        self.assertEqual(raw_cfg["kb"]["gds_no"], "34")

        # L. realized_configured becomes true when credentials + valid account11 exist
        kb_client = KBOpenAPI(self.username)
        self.assertTrue(kb_client.configured)
        self.assertTrue(kb_client.realized_configured)
        key, label = kb_client.get_realized_source_account_state()
        self.assertTrue(len(key) == 64)
        self.assertEqual(label, "****7890-**")

    def test_mask_preservation_on_subsequent_save(self):
        save_user_openapi_config(
            self.username,
            {
                "kb": {
                    "app_key": "initial-key",
                    "app_secret": "initial-secret",
                    "account_no": "999-88-777777",
                }
            },
        )

        save_user_openapi_config(
            self.username,
            {
                "kb": {
                    "app_key": "init****",
                    "app_secret": "********",
                    "account_no": "****7777-**",
                }
            },
        )

        raw_cfg = user_openapi.get_user_openapi_config(self.username)
        self.assertEqual(raw_cfg["kb"]["app_key"], "initial-key")
        self.assertEqual(raw_cfg["kb"]["app_secret"], "initial-secret")
        self.assertEqual(raw_cfg["kb"]["account11"], "99988777777")
        self.assertEqual(raw_cfg["kb"]["gnl_ac_no"], "999777777")
        self.assertEqual(raw_cfg["kb"]["gds_no"], "88")

    def test_post_openapi_config_validation_rejection(self):
        # 10 digits returns 400
        res = self.client.post(
            "/api/user/openapi-config",
            headers=self.headers(),
            json={
                "kb": {
                    "app_key": "testkey",
                    "app_secret": "testsecret",
                    "account_no": "1234567890",
                }
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("KB증권 계좌번호 11자리를 확인하세요.", res.text)
        self.assertNotIn("1234567890", res.text)

        # 12 digits returns 400
        res = self.client.post(
            "/api/user/openapi-config",
            headers=self.headers(),
            json={
                "kb": {
                    "app_key": "testkey",
                    "app_secret": "testsecret",
                    "account_no": "123456789012",
                }
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("KB증권 계좌번호 11자리를 확인하세요.", res.text)

        # Letters return 400
        res = self.client.post(
            "/api/user/openapi-config",
            headers=self.headers(),
            json={
                "kb": {
                    "app_key": "testkey",
                    "app_secret": "testsecret",
                    "account_no": "12345abcde1",
                }
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("KB증권 계좌번호 11자리를 확인하세요.", res.text)

    def test_post_and_get_openapi_config_success(self):
        # Valid 11-digit payload
        res = self.client.post(
            "/api/user/openapi-config",
            headers=self.headers(),
            json={
                "kb": {
                    "app_key": "validkbkey",
                    "app_secret": "validkbsecret",
                    "account_no": "001-91-123456",
                }
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("message", data)
        self.assertNotIn("00191123456", json.dumps(data))
        self.assertNotIn("001123456", json.dumps(data))
        self.assertNotIn("91", json.dumps(data))

        # GET config returns masked data without secrets
        res_get = self.client.get("/api/user/openapi-config", headers=self.headers())
        self.assertEqual(res_get.status_code, 200)
        get_data = res_get.json()
        kb = get_data["kb"]
        self.assertTrue(kb["has_provider_account"])
        self.assertTrue(kb["has_product_number"])
        self.assertTrue(kb["realized_configured"])
        self.assertEqual(kb["account_no"], "****3456-**")
        self.assertNotIn("account11", kb)
        self.assertNotIn("gnl_ac_no", kb)
        self.assertNotIn("gds_no", kb)

        # GET /api/kb/status returns readiness without leaking credentials
        status_res = self.client.get("/api/kb/status", headers=self.headers())
        self.assertEqual(status_res.status_code, 200)
        st = status_res.json()
        self.assertTrue(st["configured"])
        self.assertEqual(len(st["accounts"]), 1)
        self.assertFalse(st["source_scope_verified"])
        self.assertFalse(st["accounts"][0]["source_scope_verified"])
        self.assertEqual(st["accounts"][0]["source_account_label"], "****3456-**")
        self.assertNotIn("00191123456", status_res.text)
        self.assertNotIn("001123456", status_res.text)
        self.assertNotIn("gnl_ac_no", status_res.text)
        self.assertNotIn("gds_no", status_res.text)


if __name__ == "__main__":
    unittest.main()
