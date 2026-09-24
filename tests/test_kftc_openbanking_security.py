import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, _serializer, COOKIE_NAME
from app.services import kftc_openbanking_config as cfg
from app.services import kftc_openbanking_storage as storage


class KftcOpenBankingSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        # Mock user directory for storage and config
        self.patch_user_dir = patch(
            "app.services.kftc_openbanking_storage.get_user_data_dir",
            side_effect=lambda u: Path(self.tmp.name) / (u or "default"),
        )
        self.patch_user_dir.start()
        self.addCleanup(self.patch_user_dir.stop)

        self.patch_cfg_user_dir = patch(
            "app.services.kftc_openbanking_config.get_user_data_dir",
            side_effect=lambda u: Path(self.tmp.name) / (u or "default"),
        )
        self.patch_cfg_user_dir.start()
        self.addCleanup(self.patch_cfg_user_dir.stop)

    def _make_client(self, username: str | None = None, role: str = "user") -> TestClient:
        client = TestClient(app)
        if username:
            client.cookies.set(COOKIE_NAME, _serializer.dumps({"user": username, "role": role}))
            user_patch = patch(
                "app.services.user_manager.get_user_by_name",
                return_value={"username": username, "id": f"id-{username}", "role": role},
            )
            user_patch.start()
            self.addCleanup(user_patch.stop)
        return client

    def test_sagesaint_and_regular_users_can_manage_own_config(self):
        # Regular user 'sagesaint' can GET & PATCH their own config without admin role
        client = self._make_client("sagesaint", role="user")
        get_res = client.get("/api/user/kftc-openbanking-config")
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertFalse(data["enabled"])
        self.assertNotIn("client_secret", data)

        patch_res = client.patch(
            "/api/user/kftc-openbanking-config",
            json={
                "enabled": True,
                "environment": "test",
                "client_id": "sagesaint-cid",
                "client_secret": "sagesaint-sec",
                "client_use_code": "B123456789",
            },
        )
        self.assertEqual(patch_res.status_code, 200)
        patch_data = patch_res.json()
        self.assertTrue(patch_data["enabled"])
        self.assertTrue(patch_data["client_id_configured"])
        self.assertTrue(patch_data["client_secret_configured"])
        self.assertTrue(patch_data["client_use_code_configured"])
        self.assertNotIn("client_secret", patch_data)
        self.assertNotIn("sagesaint-sec", str(patch_data))

    def test_user_cannot_access_or_modify_other_user_config(self):
        # Alice configures her KFTC
        client_alice = self._make_client("alice", role="user")
        client_alice.patch(
            "/api/user/kftc-openbanking-config",
            json={"enabled": True, "client_id": "alice-id", "client_secret": "alice-secret"},
        )

        # Bob logs in and checks his config
        client_bob = self._make_client("bob", role="user")
        bob_res = client_bob.get("/api/user/kftc-openbanking-config")
        self.assertEqual(bob_res.status_code, 200)
        bob_data = bob_res.json()
        # Bob's config must be completely empty and independent
        self.assertFalse(bob_data["enabled"])
        self.assertFalse(bob_data["client_id_configured"])
        self.assertNotEqual(bob_data.get("client_id"), "alice-id")

        # Bob cannot specify username in request parameter/body to access Alice's config
        patch_attempt = client_bob.patch(
            "/api/user/kftc-openbanking-config",
            json={"username": "alice", "client_id": "hacked-id"},
        )
        self.assertEqual(patch_attempt.status_code, 400)  # rejected because 'username' is an illegal patch key

    def test_client_secret_encrypted_at_rest_in_user_dir(self):
        client = self._make_client("alice", role="user")
        client.patch(
            "/api/user/kftc-openbanking-config",
            json={"enabled": True, "client_id": "alice-id", "client_secret": "super-private-kftc-secret"},
        )

        alice_dir = Path(self.tmp.name) / "alice"
        config_file = alice_dir / "kftc_openbanking_config.json"
        self.assertTrue(config_file.exists())
        content = config_file.read_text(encoding="utf-8")
        self.assertNotIn("super-private-kftc-secret", content)
        self.assertIn("client_secret_encrypted", content)

    def test_old_admin_endpoint_no_longer_exists(self):
        client_admin = self._make_client("admin", role="admin")
        res = client_admin.get("/api/settings/kftc-openbanking")
        self.assertEqual(res.status_code, 404)

    def test_unauthenticated_request_rejected(self):
        client = self._make_client()
        res_cfg = client.get("/api/user/kftc-openbanking-config")
        self.assertEqual(res_cfg.status_code, 401)

        res_patch = client.patch("/api/user/kftc-openbanking-config", json={"enabled": True})
        self.assertEqual(res_patch.status_code, 401)

        res = client.get("/api/kftc/openbanking/status")
        self.assertEqual(res.status_code, 401)

        res_start = client.post("/api/kftc/openbanking/oauth/start")
        self.assertEqual(res_start.status_code, 401)

    def test_user_isolation_tokens(self):
        # Alice connects; Bob checks status
        storage.save_user_tokens(
            "alice",
            access_token="alice-acc",
            refresh_token="alice-ref",
            user_seq_no="seq-alice",
            scope="login inquiry",
            expires_in=7776000,
        )
        with patch.object(cfg, "is_user_allowed_kftc", return_value=True):
            # Alice status
            client_alice = self._make_client("alice")
            alice_status = client_alice.get("/api/kftc/openbanking/status").json()
            self.assertTrue(alice_status["connected"])

            # Bob status
            client_bob = self._make_client("bob")
            bob_status = client_bob.get("/api/kftc/openbanking/status").json()
            self.assertFalse(bob_status["connected"])

    def test_status_endpoint_never_leaks_tokens(self):
        storage.save_user_tokens(
            "alice",
            access_token="super-secret-access-token",
            refresh_token="super-secret-refresh-token",
            user_seq_no="seq-alice",
            scope="login inquiry",
            expires_in=7776000,
        )
        with patch.object(cfg, "is_user_allowed_kftc", return_value=True):
            client = self._make_client("alice")
            status = client.get("/api/kftc/openbanking/status").json()
            status_str = str(status)
            self.assertNotIn("super-secret-access-token", status_str)
            self.assertNotIn("super-secret-refresh-token", status_str)
            self.assertNotIn("encrypted", status_str)

    def test_session_cookie_secure_attribute_in_production_and_testing(self):
        from app import main as app_module

        # When TESTING=False (production mode), secure attribute must be True
        with patch.object(app_module, "TESTING", False):
            with patch("app.services.user_manager.authenticate_user", return_value={"username": "alice", "role": "user"}):
                client = TestClient(app, follow_redirects=False)
                res = client.post("/login", data={"username": "alice", "password": "password123"})
                set_cookie_header = res.headers.get("set-cookie", "")
                self.assertIn("secure", set_cookie_header.lower())
                self.assertIn("httponly", set_cookie_header.lower())
                self.assertIn("samesite=lax", set_cookie_header.lower())

        # When TESTING=True (testing mode), secure attribute is False to support test harness HTTP
        with patch.object(app_module, "TESTING", True):
            with patch("app.services.user_manager.authenticate_user", return_value={"username": "alice", "role": "user"}):
                client = TestClient(app, follow_redirects=False)
                res = client.post("/login", data={"username": "alice", "password": "password123"})
                set_cookie_header = res.headers.get("set-cookie", "")
                self.assertNotIn("secure", set_cookie_header.lower())
                self.assertIn("httponly", set_cookie_header.lower())
                self.assertIn("samesite=lax", set_cookie_header.lower())


if __name__ == "__main__":
    unittest.main()
