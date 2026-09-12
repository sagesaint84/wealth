"""Integration unit tests for POST /api/toss-wts/feed/confirm endpoint."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from starlette.testclient import TestClient

from app.services.toss_wts_feed_auth import WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID
from app.services.toss_wts_feed_runtime import (
    check_wts_feed_runtime_confirmation,
    clear_wts_feed_runtime_confirmation,
)
from app.services.user_identity import generate_user_id
from tests.test_request_state_user_id import _import_main_without_loading_real_env


class TossWtsFeedConfirmationEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        clear_wts_feed_runtime_confirmation()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(clear_wts_feed_runtime_confirmation)

        root = Path(self.temp_dir.name)
        self.exe_path = root / "tossctl"
        self.exe_path.write_text("synthetic_tossctl_binary", encoding="utf-8")

        self.config_dir = root / "config"
        self.config_dir.mkdir()
        self.session_path = self.config_dir / "session.json"
        self.session_path.write_text('{"token": "SYNTHETIC_WTS_SESSION_TOKEN_123"}', encoding="utf-8")

    def _cookie_header(self, username: str, role: str = "user") -> dict[str, str]:
        token = self.main._serializer.dumps({"user": username, "role": role})
        return {"Cookie": f"{self.main.COOKIE_NAME}={token}"}

    def _env_for(self, user_id: str) -> dict[str, str]:
        return {
            WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: user_id,
            "WEALTH_TOSS_WTS_ENABLED": "1",
            "WEALTH_TOSSCTL_PATH": str(self.exe_path),
            "WEALTH_TOSSCTL_CONFIG_DIR": str(self.config_dir),
        }

    def test_allowed_normal_user_can_confirm(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        payload = response.json()
        self.assertEqual(payload, {"confirmed": True, "code": "CONFIRMED"})

        # Verify process memory confirmation was stored
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertTrue(check_res.confirmed)
            self.assertEqual(check_res.code, "CONFIRMED")

    def test_allowed_admin_can_confirm(self):
        admin_id = generate_user_id()
        admin_record = {"username": "admin-user", "id": admin_id, "role": "admin", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(admin_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=admin_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("admin-user", "admin"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"confirmed": True, "code": "CONFIRMED"})

    def test_non_allowed_admin_is_denied_with_403(self):
        allowed_id = generate_user_id()
        admin_id = generate_user_id()
        self.assertNotEqual(allowed_id, admin_id)
        admin_record = {"username": "admin-b", "id": admin_id, "role": "admin", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=admin_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("admin-b", "admin"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

        # Verify no confirmation was stored
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False):
            check_res = check_wts_feed_runtime_confirmation(allowed_id)
            self.assertFalse(check_res.confirmed)

    def test_non_allowed_normal_user_is_denied_with_403(self):
        allowed_id = generate_user_id()
        other_id = generate_user_id()
        other_record = {"username": "user-other", "id": other_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=other_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-other", "user"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

    def test_unauthenticated_request_is_denied(self):
        allowed_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.main.confirm_wts_feed_runtime_session", side_effect=AssertionError("helper called on unauthenticated")):
            response = self.client.post("/api/toss-wts/feed/confirm")

        self.assertEqual(response.status_code, 401)

    def test_tampered_cookie_is_denied(self):
        allowed_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.main.confirm_wts_feed_runtime_session", side_effect=AssertionError("helper called on tampered")):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers={"Cookie": f"{self.main.COOKIE_NAME}=invalid_tampered_token"},
            )

        self.assertEqual(response.status_code, 401)

    def test_body_supplied_user_id_is_ignored(self):
        allowed_id = generate_user_id()
        spoofed_id = generate_user_id()
        user_record = {"username": "user-a", "id": allowed_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            # Send spoofed ID in JSON body
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                json={"user_id": spoofed_id},
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"confirmed": True, "code": "CONFIRMED"})

        # Process-local confirmation was stored for user-a's allowed_id, NOT spoofed_id
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False):
            check_allowed = check_wts_feed_runtime_confirmation(allowed_id)
            self.assertTrue(check_allowed.confirmed)

    def test_query_supplied_user_id_is_ignored(self):
        allowed_id = generate_user_id()
        spoofed_id = generate_user_id()
        user_record = {"username": "user-a", "id": allowed_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.post(
                f"/api/toss-wts/feed/confirm?user_id={spoofed_id}",
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"confirmed": True, "code": "CONFIRMED"})

    def test_legacy_missing_user_id_fails_closed(self):
        allowed_id = generate_user_id()
        # Legacy user record without 'id'
        legacy_record = {"username": "legacy-user", "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=legacy_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("legacy-user", "user"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

    def test_runtime_material_unavailable_yields_503(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        # Remove session file
        self.session_path.unlink()

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "RUNTIME_MATERIAL_UNAVAILABLE"}})

    def test_success_response_privacy(self):
        sentinel_uuid = "00000000-0000-4000-8000-000000000001"
        user_record = {"username": "sentinel-user", "id": sentinel_uuid, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(sentinel_uuid), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("sentinel-user", "user"),
            )

        self.assertEqual(response.status_code, 200)
        body = response.text
        for sensitive in (
            sentinel_uuid,
            "sentinel-user",
            str(self.exe_path),
            str(self.config_dir),
            str(self.session_path),
            "marker",
            "mtime",
            "st_size",
        ):
            self.assertNotIn(sensitive, body)

    def test_failure_response_privacy(self):
        sentinel_uuid = "00000000-0000-4000-8000-000000000002"
        other_uuid = "00000000-0000-4000-8000-000000000003"
        user_record = {"username": "sentinel-denied", "id": other_uuid, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(sentinel_uuid), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("sentinel-denied", "user"),
            )

        self.assertEqual(response.status_code, 403)
        body = response.text
        for sensitive in (sentinel_uuid, other_uuid, "sentinel-denied", str(self.config_dir)):
            self.assertNotIn(sensitive, body)

    def test_no_store_headers_on_success_and_failure(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            success_res = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-a", "user"),
            )
        self.assertEqual(success_res.headers.get("cache-control"), "no-store")

        with patch.dict(os.environ, self._env_for(generate_user_id()), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            fail_res = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-a", "user"),
            )
        self.assertEqual(fail_res.headers.get("cache-control"), "no-store")

    def test_confirm_function_called_exactly_once(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record), \
             patch("app.main.confirm_wts_feed_runtime_session", wraps=self.main.confirm_wts_feed_runtime_session) as mock_confirm:
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-a", "user"),
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(mock_confirm.call_count, 1)
            mock_confirm.assert_called_once_with(user_id)

    def test_unauthorized_user_does_not_stat_runtime_material(self):
        allowed_id = generate_user_id()
        unauthorized_id = generate_user_id()
        user_record = {"username": "user-unauth", "id": unauthorized_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record), \
             patch("pathlib.Path.stat", side_effect=AssertionError("stat called for unauthorized caller")):
            response = self.client.post(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-unauth", "user"),
            )
        self.assertEqual(response.status_code, 403)

    def test_wrong_user_does_not_revoke_owner_confirmation(self):
        owner_id = generate_user_id()
        attacker_id = generate_user_id()
        owner_record = {"username": "user-owner", "id": owner_id, "role": "user", "must_change_password": False}
        attacker_record = {"username": "user-attacker", "id": attacker_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(owner_id), clear=False):
            # 1. Owner confirms successfully
            with patch("app.services.user_manager.get_user_by_name", return_value=owner_record):
                res1 = self.client.post("/api/toss-wts/feed/confirm", headers=self._cookie_header("user-owner", "user"))
            self.assertEqual(res1.status_code, 200)

            # 2. Attacker calls endpoint and is denied
            with patch("app.services.user_manager.get_user_by_name", return_value=attacker_record):
                res2 = self.client.post("/api/toss-wts/feed/confirm", headers=self._cookie_header("user-attacker", "user"))
            self.assertEqual(res2.status_code, 403)

            # 3. Existing runtime confirmation for owner remains valid
            owner_check = check_wts_feed_runtime_confirmation(owner_id)
            self.assertTrue(owner_check.confirmed)
            self.assertEqual(owner_check.code, "CONFIRMED")

    def test_explicit_reconfirmation_after_generation_change(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            # 1. Confirm G1
            res1 = self.client.post("/api/toss-wts/feed/confirm", headers=self._cookie_header("user-a", "user"))
            self.assertEqual(res1.status_code, 200)

            # 2. Synthetic session generation changes (rewrite session file)
            time.sleep(0.01)
            self.session_path.write_text('{"token": "NEW_SESSION_G2_TOKEN"}', encoding="utf-8")

            # 3. Runtime check detects invalidation
            check1 = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check1.confirmed)
            self.assertEqual(check1.code, "RUNTIME_GENERATION_CHANGED")

            # 4. Explicit reconfirmation via POST
            res2 = self.client.post("/api/toss-wts/feed/confirm", headers=self._cookie_header("user-a", "user"))
            self.assertEqual(res2.status_code, 200)

            # 5. G2 is now confirmed
            check2 = check_wts_feed_runtime_confirmation(user_id)
            self.assertTrue(check2.confirmed)
            self.assertEqual(check2.code, "CONFIRMED")

    def test_get_on_confirm_endpoint_is_rejected(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record), \
             patch("app.main.confirm_wts_feed_runtime_session", side_effect=AssertionError("helper called on GET")):
            response = self.client.get(
                "/api/toss-wts/feed/confirm",
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 405)

    def test_status_endpoint_does_not_auto_confirm(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.get(
                "/api/toss-wts/status",
                headers=self._cookie_header("user-a", "user"),
            )
        self.assertEqual(response.status_code, 200)

        # Runtime confirmation remains unconfirmed
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, "NOT_CONFIRMED")

    def test_login_does_not_auto_confirm(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.authenticate_user", return_value=user_record):
            response = self.client.post(
                "/login",
                data={"username": "user-a", "password": "valid_password"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)

        # Runtime confirmation remains empty
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, "NOT_CONFIRMED")

    def test_ordinary_routes_do_not_auto_confirm(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.get(
                "/api/auth/me",
                headers=self._cookie_header("user-a", "user"),
            )
        self.assertEqual(response.status_code, 200)

        # Runtime confirmation remains empty
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, "NOT_CONFIRMED")


if __name__ == "__main__":
    unittest.main()
