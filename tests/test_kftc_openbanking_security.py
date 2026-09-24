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

        # Mock user directory for token storage
        self.patch_user_dir = patch(
            "app.services.kftc_openbanking_storage.get_user_data_dir",
            side_effect=lambda u: Path(self.tmp.name) / (u or "default"),
        )
        self.patch_user_dir.start()
        self.addCleanup(self.patch_user_dir.stop)

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

    def test_ordinary_user_cannot_access_or_patch_admin_config(self):
        client = self._make_client("sagesaint", role="user")
        res = client.get("/api/settings/kftc-openbanking")
        self.assertEqual(res.status_code, 403)

        patch_res = client.patch(
            "/api/settings/kftc-openbanking",
            json={"enabled": True},
        )
        self.assertEqual(patch_res.status_code, 403)

    def test_admin_can_access_and_patch_config(self):
        client = self._make_client("admin", role="admin")
        res = client.get("/api/settings/kftc-openbanking")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["can_manage"])
        self.assertNotIn("client_secret", data)

    def test_unauthenticated_request_rejected(self):
        client = self._make_client()
        res = client.get("/api/kftc/openbanking/status")
        self.assertEqual(res.status_code, 401)

        res_start = client.post("/api/kftc/openbanking/oauth/start")
        self.assertEqual(res_start.status_code, 401)

    def test_user_isolation(self):
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


if __name__ == "__main__":
    unittest.main()
