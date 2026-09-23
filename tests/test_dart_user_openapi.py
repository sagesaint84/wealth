import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.ipo.dart_client import (
    DartAuthError,
    DartClient,
    DartClientError,
    DartRateLimitError,
    DartSourceError,
)
from app.services.ipo.orchestrator import _run_ipo_daily_pipeline
from app.services.user_openapi import (
    delete_user_broker_openapi,
    get_masked_user_openapi_config,
    get_user_openapi_config,
    save_user_openapi_config,
)


class UserOpenApiDartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.users_dir = Path(self.tmp.name) / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.patch_dir = patch("app.services.user_openapi.USERS_DIR", self.users_dir)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)

    def test_default_config_includes_empty_dart(self):
        cfg = get_user_openapi_config("user_a")
        self.assertIn("dart", cfg)
        self.assertEqual(cfg["dart"], {"api_key": ""})

    def test_legacy_broker_fallback_does_not_synthesize_a_user_dart_key(self):
        with patch.dict(os.environ, {"DART_API_KEY": "sagesaint_env_key"}):
            cfg = get_user_openapi_config("sagesaint")
            self.assertEqual(cfg["dart"]["api_key"], "")

    def test_save_and_get_masked_dart_key(self):
        save_user_openapi_config("user_a", {"dart": {"api_key": "0123456789abcdef0123456789abcdef01234567"}})
        raw_cfg = get_user_openapi_config("user_a")
        self.assertEqual(raw_cfg["dart"]["api_key"], "0123456789abcdef0123456789abcdef01234567")

        masked = get_masked_user_openapi_config("user_a")
        self.assertIn("dart", masked)
        self.assertTrue(masked["dart"]["configured"])
        self.assertTrue(masked["dart"]["has_api_key"])
        self.assertEqual(masked["dart"]["api_key"], "********")
        self.assertNotIn("0123", json.dumps(masked))

    def test_masked_input_preserves_existing_key(self):
        save_user_openapi_config("user_a", {"dart": {"api_key": "ORIGINAL_SECRET_KEY_1234"}})
        # Saving with masked asterisks or without dart should preserve the original key
        save_user_openapi_config("user_a", {"dart": {"api_key": "ORIG****"}})
        raw_cfg = get_user_openapi_config("user_a")
        self.assertEqual(raw_cfg["dart"]["api_key"], "ORIGINAL_SECRET_KEY_1234")
        save_user_openapi_config("user_a", {"dart": {"api_key": ""}})
        self.assertEqual(get_user_openapi_config("user_a")["dart"]["api_key"], "ORIGINAL_SECRET_KEY_1234")

    def test_delete_user_dart_openapi(self):
        save_user_openapi_config("user_a", {"dart": {"api_key": "KEY_TO_DELETE"}})
        self.assertTrue(get_masked_user_openapi_config("user_a")["dart"]["configured"])

        delete_user_broker_openapi("user_a", "dart")
        raw_cfg = get_user_openapi_config("user_a")
        self.assertEqual(raw_cfg["dart"]["api_key"], "")
        masked = get_masked_user_openapi_config("user_a")
        self.assertFalse(masked["dart"]["configured"])
        self.assertFalse(masked["dart"]["has_api_key"])


class DartClientResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.users_dir = Path(self.tmp.name) / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.patch_dir = patch("app.services.user_openapi.USERS_DIR", self.users_dir)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)

    def test_explicit_api_key_takes_precedence(self):
        with patch.dict(os.environ, {"DART_API_KEY": "ENV_KEY"}):
            save_user_openapi_config("user_a", {"dart": {"api_key": "USER_KEY"}})
            client = DartClient(username="user_a", api_key="EXPLICIT_KEY")
            self.assertEqual(client.api_key, "EXPLICIT_KEY")
            self.assertEqual(client.credential_source, "explicit")
            self.assertTrue(client.is_configured())

    def test_user_openapi_config_takes_precedence_over_env(self):
        with patch.dict(os.environ, {"DART_API_KEY": "ENV_KEY"}):
            save_user_openapi_config("user_a", {"dart": {"api_key": "USER_KEY"}})
            client = DartClient(username="user_a")
            self.assertEqual(client.api_key, "USER_KEY")
            self.assertEqual(client.credential_source, "user_config")
            self.assertTrue(client.is_configured())

    def test_user_isolation(self):
        save_user_openapi_config("user_a", {"dart": {"api_key": "USER_A_KEY"}})
        save_user_openapi_config("user_b", {"dart": {"api_key": "USER_B_KEY"}})

        client_a = DartClient(username="user_a")
        client_b = DartClient(username="user_b")
        self.assertEqual(client_a.api_key, "USER_A_KEY")
        self.assertEqual(client_b.api_key, "USER_B_KEY")
        self.assertNotEqual(client_a.api_key, client_b.api_key)

    def test_fallback_to_environment_when_user_key_empty(self):
        with patch.dict(os.environ, {"DART_API_KEY": "ENV_FALLBACK_KEY"}):
            client = DartClient(username="user_empty")
            self.assertEqual(client.api_key, "ENV_FALLBACK_KEY")
            self.assertEqual(client.credential_source, "environment")
            self.assertTrue(client.is_configured())

    def test_unconfigured_when_no_user_key_and_no_env(self):
        with patch.dict(os.environ, {"DART_API_KEY": ""}):
            client = DartClient(username="user_none")
            self.assertEqual(client.api_key, "")
            self.assertEqual(client.credential_source, "unconfigured")
            self.assertFalse(client.is_configured())


class UserOpenApiEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.users_dir = Path(self.tmp.name) / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.patch_dir = patch("app.services.user_openapi.USERS_DIR", self.users_dir)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)

        self.client = TestClient(app)

    def test_user_dart_endpoints_flow(self):
        self.client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({"user": "user_a"}))
        user_mock = patch("app.services.user_manager.get_user_by_name", return_value={"username": "user_a", "id": "user_a", "role": "user"})
        user_mock.start()
        self.addCleanup(user_mock.stop)

        # 1. Test when not configured
        with patch.dict(os.environ, {"DART_API_KEY": ""}):
            res = self.client.post("/api/user/openapi-config/dart/test")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data["configured"])
            self.assertEqual(data["error_code"], "NOT_CONFIGURED")

        # 2. Save DART key via POST /api/user/openapi-config
        res = self.client.post(
            "/api/user/openapi-config",
            json={"dart": {"api_key": "TEST_DART_API_KEY_VAL_1234"}},
        )
        self.assertEqual(res.status_code, 200)

        # Check masked config
        res = self.client.get("/api/user/openapi-config")
        self.assertEqual(res.status_code, 200)
        masked = res.json()
        self.assertTrue(masked["dart"]["configured"])
        self.assertEqual(masked["dart"]["api_key"], "********")
        self.assertNotIn("TEST_DART_API_KEY_VAL_1234", res.text)

        # 3. Test verification endpoint with mock
        with patch("app.services.ipo.dart_client.DartClient.verify_credentials") as mock_verify:
            res = self.client.post("/api/user/openapi-config/dart/test")
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["valid"])
            mock_verify.assert_called_once()

        # 4. Each transport outcome is stable and does not disclose the key.
        for exc, expected in (
            (DartAuthError("Invalid key"), "AUTH_ERROR"),
            (DartRateLimitError("limit"), "RATE_LIMIT"),
            (DartSourceError("https://example.invalid/?crtfc_key=TEST_DART_API_KEY_VAL_1234"), "NETWORK_ERROR"),
        ):
            with patch("app.services.ipo.dart_client.DartClient.verify_credentials", side_effect=exc):
                res = self.client.post("/api/user/openapi-config/dart/test")
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()["valid"])
            self.assertEqual(res.json()["error_code"], expected)
            self.assertNotIn("TEST_DART_API_KEY_VAL_1234", res.text)

        # 5. Delete DART key via DELETE /api/user/openapi-config/dart
        with patch.dict(os.environ, {"DART_API_KEY": ""}):
            res = self.client.delete("/api/user/openapi-config/dart")
            self.assertEqual(res.status_code, 200)
            res = self.client.get("/api/user/openapi-config")
            self.assertFalse(res.json()["dart"]["configured"])

    def test_admin_cannot_access_user_dart_test_endpoint(self):
        self.client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({"user": "admin"}))
        admin_mock = patch("app.services.user_manager.get_user_by_name", return_value={"username": "admin", "id": "admin", "role": "admin"})
        admin_mock.start()
        self.addCleanup(admin_mock.stop)

        res = self.client.post("/api/user/openapi-config/dart/test")
        self.assertEqual(res.status_code, 403)

    def test_legacy_settings_dart_endpoints_removed(self):
        self.client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({"user": "admin"}))
        admin_mock = patch("app.services.user_manager.get_user_by_name", return_value={"username": "admin", "id": "admin", "role": "admin"})
        admin_mock.start()
        self.addCleanup(admin_mock.stop)

        legacy_dart = "/api/settings" + "/dart"
        for method, path in (
            (self.client.get, legacy_dart),
            (self.client.patch, legacy_dart),
            (self.client.delete, legacy_dart),
            (self.client.post, legacy_dart + "/test"),
        ):
            res = method(path)
            self.assertEqual(res.status_code, 404)


class IpoPipelineDartResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.users_dir = Path(self.tmp.name) / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.patch_dir = patch("app.services.user_openapi.USERS_DIR", self.users_dir)
        self.patch_dir.start()
        self.addCleanup(self.patch_dir.stop)

    @patch("app.services.ipo.orchestrator.read_market_store", return_value={"schema_version": 1, "ipos": []})
    @patch("app.services.ipo.orchestrator.write_market_store")
    def test_orchestrator_passes_automation_owner_to_dart_client(self, mock_write, mock_read):
        save_user_openapi_config("automation_owner", {"dart": {"api_key": "OWNER_DART_KEY"}})

        mock_kis = MagicMock()
        mock_kis.configured = False
        dart = MagicMock()
        dart.is_configured.return_value = False
        with patch("app.services.ipo.orchestrator.DartClient", return_value=dart) as client_class:
            result = _run_ipo_daily_pipeline(
                username="automation_owner",
                kis_client=mock_kis,
                dry_run=True,
                market_only=True,
            )
        client_class.assert_called_once_with(username="automation_owner")
        self.assertEqual(result["sources"]["dart"], "not_requested (market_only)")

    @patch("app.services.ipo.orchestrator.read_market_store", return_value={"schema_version": 1, "ipos": []})
    @patch("app.services.ipo.orchestrator.write_market_store")
    def test_orchestrator_graceful_when_dart_missing(self, mock_write, mock_read):
        mock_kis = MagicMock()
        mock_kis.configured = False
        mock_kind = MagicMock()
        mock_kind.fetch_pubofr_schedule_items.return_value = []
        mock_krx = MagicMock()
        mock_krx.fetch_listed_master.return_value = []
        mock_naver = MagicMock()
        mock_naver.fetch_completed_listings.return_value = []
        with patch.dict(os.environ, {"DART_API_KEY": ""}):
            result = _run_ipo_daily_pipeline(
                username="owner_no_dart",
                kis_client=mock_kis,
                kind_client=mock_kind,
                krx_client=mock_krx,
                naver_client=mock_naver,
                dry_run=True,
                market_only=False,
                user_side_effects=False,
            )
            self.assertIn("dart", result["sources"])
            self.assertEqual(result["sources"]["dart"], "source_unavailable (api_key_missing)")
            self.assertEqual(result["sources"]["kind"].split(" ")[0], "sync_ok")
            self.assertFalse(result["user_side_effects"])


if __name__ == "__main__":
    unittest.main()
