import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services import dart_secrets
from app.services.ipo.dart_client import DartClient


class DartSecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "system" / "secrets" / "dart.json"

    def test_save_load_precedence_delete_and_environment_fallback(self):
        with patch.dict(os.environ, {"DART_API_KEY": "ENV_DART_KEY"}, clear=False):
            self.assertEqual(dart_secrets.resolve_dart_api_key(path=self.path), ("ENV_DART_KEY", "environment"))
            dart_secrets.save_dart_api_key("STORED_DART_KEY", path=self.path)
            self.assertEqual(dart_secrets.load_stored_dart_api_key(path=self.path), "STORED_DART_KEY")
            self.assertEqual(dart_secrets.resolve_dart_api_key(path=self.path), ("STORED_DART_KEY", "stored"))
            dart_secrets.delete_stored_dart_api_key(path=self.path)
            self.assertEqual(dart_secrets.resolve_dart_api_key(path=self.path), ("ENV_DART_KEY", "environment"))
        with patch.dict(os.environ, {"DART_API_KEY": ""}, clear=False):
            self.assertEqual(dart_secrets.resolve_dart_api_key(path=self.path), ("", "unconfigured"))

    def test_invalid_value_atomic_write_and_posix_permissions(self):
        with self.assertRaises(dart_secrets.DartSecretError):
            dart_secrets.save_dart_api_key("\x00bad", path=self.path)
        dart_secrets.save_dart_api_key("SAFE_DART_KEY", path=self.path)
        before = self.path.read_bytes()
        with patch("app.services.dart_secrets.atomic_write_private_json", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                dart_secrets.save_dart_api_key("REPLACEMENT_DART_KEY", path=self.path)
        self.assertEqual(self.path.read_bytes(), before)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_dart_client_uses_resolver_without_leaking_key(self):
        with patch("app.services.dart_secrets.resolve_dart_api_key", return_value=("RESOLVED_DART_KEY", "stored")):
            client = DartClient()
            legacy_blank_client = DartClient(api_key="")
        self.assertTrue(client.is_configured())
        self.assertEqual(client.credential_source, "stored")
        self.assertEqual(legacy_blank_client.credential_source, "stored")
        self.assertNotIn("RESOLVED_DART_KEY", client._safe_log_url("company.json", {"crtfc_key": client.api_key}))


class DartSettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "system" / "secrets" / "dart.json"
        self.client = TestClient(app)
        self.client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({"user": "admin"}))
        self.user = patch("app.services.user_manager.get_user_by_name", return_value={"username": "admin", "id": "admin", "role": "admin"})
        self.secret_path = patch("app.services.dart_secrets.dart_secret_path", return_value=self.path)
        self.user.start(); self.secret_path.start()
        self.addCleanup(self.user.stop); self.addCleanup(self.secret_path.stop)

    def test_admin_api_is_safe_and_delete_falls_back_to_environment(self):
        secret = "DART_API_KEY_MUST_NOT_APPEAR"
        with patch.dict(os.environ, {"DART_API_KEY": "ENV_DART_FALLBACK"}, clear=False):
            response = self.client.patch("/api/settings/dart", json={"api_key": secret})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"configured": True, "source": "stored"})
            self.assertNotIn(secret, response.text)
            self.assertNotIn(secret, self.client.get("/api/settings/dart").text)
            deleted = self.client.delete("/api/settings/dart")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(deleted.json(), {"configured": True, "source": "environment"})

    def test_admin_validation_test_endpoint_and_non_admin_forbidden(self):
        invalid = self.client.patch("/api/settings/dart", json={"api_key": "DART_RAW_INVALID_SECRET", "extra": True})
        self.assertEqual(invalid.status_code, 400)
        self.assertNotIn("api_key", invalid.text)
        self.assertNotIn("DART_RAW_INVALID_SECRET", invalid.text)
        with patch("app.services.ipo.dart_client.DartClient.verify_credentials") as verify:
            self.client.patch("/api/settings/dart", json={"api_key": "DART_TEST_KEY"})
            result = self.client.post("/api/settings/dart/test")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"configured": True, "valid": True, "source": "stored"})
        verify.assert_called_once()
        self.user.stop()
        non_admin = patch("app.services.user_manager.get_user_by_name", return_value={"username": "alice", "id": "alice", "role": "user"})
        non_admin.start()
        self.addCleanup(non_admin.stop)
        self.client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({"user": "alice"}))
        for method, url in ((self.client.get, "/api/settings/dart"), (self.client.delete, "/api/settings/dart"), (self.client.post, "/api/settings/dart/test")):
            self.assertEqual(method(url).status_code, 403)
