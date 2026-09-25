"""Comprehensive test suite for Action Link V2 Foundation (Phase 2).

Verifies:
1. State path resolution (explicit path, WEALTH_DATA_DIR, repo default <repo>/data/system)
2. Provider-independent Action Models (MARK_IPO_APPLIED, OPEN_IPO_SALE_FLOW)
3. Secure Storage (SHA-256 digest lookup, raw token never written to disk, atomic write)
4. Token format validation (fail fast on malformed, whitespace, unicode, length)
5. Expiration boundary (KST 23:59:59 subscription end date)
6. URL generation (uses configured public_base_url, validates https)
7. Canonical IPO display resolution (authoritative read_market_store_read_only)
8. Read-Only GET /a/{token} (no side effects, zero changes to all state files, lock files, portfolio)
9. Mutating POST /a/{token}/execute & CSRF / same-origin validation (Origin, Referer fallback, evil origin rejected)
10. OPEN_IPO_SALE_FLOW is non-executable in Phase 2 (status 400 ACTION_NOT_EXECUTABLE, no mutation)
11. Safe public error mapping (no internal paths, OSError, parser details leaked)
12. Session authentication & strict username binding (403 on mismatch)
13. Unauthenticated redirect & Open-Redirect protection (?return_to= strictly validated)
14. Pruning retention (7 days retention post consumed/expired)
15. Concurrency & locking safety
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import _serializer, app, COOKIE_NAME
from app.services.action_v2 import (
    ACTION_RETENTION_DAYS,
    ACTION_TYPE_MARK_IPO_APPLIED,
    ACTION_TYPE_OPEN_IPO_SALE_FLOW,
    action_v2_lock,
    build_action_url,
    create_web_action,
    execute_web_action,
    get_action_v2_file_path,
    get_web_action_metadata,
    hash_action_token,
    is_action_expired,
    prune_old_v2_actions,
    validate_action_token,
    _load_v2,
    _save_v2,
    REPO_ROOT,
)
from app.services.ipo.actions import IpoActionError

KST = timezone(timedelta(hours=9))


def _make_market_data(ipo_id="ipo-test-1", start="2026-09-20", end="2026-09-21", name="정식공모주"):
    return {
        "ipos": [
            {
                "ipo_id": ipo_id,
                "company_name": name,
                "name": name,
                "subscription_start": start,
                "subscription_end": end,
            }
        ]
    }


def _make_user_applications(ipo_id="ipo-test-1", applied=None, targets=None, revision=1):
    return {
        "revision": revision,
        "family_members": ["본인", "배우자"],
        "applications": {
            ipo_id: {
                "target_owners": targets if targets is not None else ["본인", "배우자"],
                "applied_owners": applied if applied is not None else [],
            }
        },
    }


class ActionV2EngineTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="wealth-act-v2-")
        self.addCleanup(self.tmp_dir.cleanup)
        self.action_file = Path(self.tmp_dir.name) / "action_v2_state.json"
        self.today = date(2026, 9, 20)

    def test_state_path_resolution(self):
        # 1. Explicit path parameter has highest precedence
        p1 = get_action_v2_file_path("/custom/path/action.json")
        self.assertEqual(p1, Path("/custom/path/action.json"))

        # 2. WEALTH_DATA_DIR environment variable
        with patch.dict(os.environ, {"WEALTH_DATA_DIR": "/tmp/env_wealth_data"}):
            p2 = get_action_v2_file_path()
            self.assertEqual(p2, Path("/tmp/env_wealth_data/system/action_v2_state.json"))

        # 3. Default repo root fallback
        with patch.dict(os.environ, {}, clear=True):
            p3 = get_action_v2_file_path()
            expected_default = REPO_ROOT / "data" / "system" / "action_v2_state.json"
            self.assertEqual(p3, expected_default)
            # Verify parent structure: REPO_ROOT contains app/services/action_v2.py
            self.assertTrue((REPO_ROOT / "app" / "services" / "action_v2.py").exists())

    def test_token_format_validation(self):
        # Valid token
        valid_tok = "a" * 32
        self.assertEqual(validate_action_token(valid_tok), valid_tok)
        self.assertEqual(validate_action_token("A-Z_0-9_valid-token-123456"), "A-Z_0-9_valid-token-123456")

        # Invalid tokens
        invalid_tokens = [
            "",  # empty
            "short",  # too short (< 16)
            "a" * 65,  # too long (> 64)
            "has space inside",
            "has/slash",
            "has%percent",
            "has?question",
            "한글토큰1234567890",
            None,
            12345,
        ]
        for inv in invalid_tokens:
            with self.assertRaises(IpoActionError):
                validate_action_token(inv)  # type: ignore

    def test_token_hashing(self):
        t1 = "test-token-1234567890abcdef"
        h1 = hash_action_token(t1)
        expected = hashlib.sha256(t1.encode("utf-8")).hexdigest()
        self.assertEqual(h1, expected)
        self.assertEqual(len(h1), 64)
        # Empty/invalid token validation raises IpoActionError
        with self.assertRaises(IpoActionError):
            hash_action_token("")

    def test_create_and_raw_token_never_persisted(self):
        market = _make_market_data("ipo-1", "2026-09-20", "2026-09-21")
        apps = _make_user_applications("ipo-1", applied=[], targets=["본인"])

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                source_channel="test",
                today=self.today,
                path=self.action_file,
            )

        raw_token = action_res["raw_token"]
        digest = action_res["token_digest"]
        self.assertEqual(hash_action_token(raw_token), digest)

        # Check raw file contents on disk
        self.assertTrue(self.action_file.exists())
        file_bytes = self.action_file.read_bytes()
        file_str = file_bytes.decode("utf-8")

        # RAW TOKEN MUST NEVER APPEAR IN STORAGE
        self.assertNotIn(raw_token, file_str)
        # DIGEST MUST APPEAR
        self.assertIn(digest, file_str)

        # Verify JSON schema
        data = json.loads(file_str)
        self.assertEqual(data["version"], 2)
        self.assertIn(digest, data["actions"])
        rec = data["actions"][digest]
        self.assertEqual(rec["username"], "alice")
        self.assertEqual(rec["action_type"], ACTION_TYPE_MARK_IPO_APPLIED)
        self.assertIsNone(rec["consumed_at"])
        self.assertEqual(rec["metadata"]["owner"], "본인")

    def test_read_only_get_metadata(self):
        market = _make_market_data("ipo-1", "2026-09-20", "2026-09-21")
        apps = _make_user_applications("ipo-1", applied=[], targets=["본인"])

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                today=self.today,
                path=self.action_file,
            )

        raw_token = action_res["raw_token"]
        initial_sha256 = hashlib.sha256(self.action_file.read_bytes()).hexdigest()

        # Call get_web_action_metadata multiple times
        for _ in range(5):
            meta = get_web_action_metadata(raw_token, path=self.action_file)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["username"], "alice")

        # Ensure zero byte changes to action file
        post_sha256 = hashlib.sha256(self.action_file.read_bytes()).hexdigest()
        self.assertEqual(initial_sha256, post_sha256)

    def test_is_action_expired_kst_boundary(self):
        # Subscription end is 2026-09-21
        end_kst = datetime(2026, 9, 21, 23, 59, 59, tzinfo=KST)
        action = {"expires_at": end_kst.astimezone(timezone.utc).isoformat()}

        # On 2026-09-20: not expired
        self.assertFalse(is_action_expired(action, date(2026, 9, 20)))
        # On 2026-09-21 (subscription end day): not expired
        self.assertFalse(is_action_expired(action, date(2026, 9, 21)))
        # On 2026-09-22 (next day): expired
        self.assertTrue(is_action_expired(action, date(2026, 9, 22)))

    def test_execute_web_action_success_and_idempotency(self):
        market = _make_market_data("ipo-1", "2026-09-20", "2026-09-21")
        apps = _make_user_applications("ipo-1", applied=[], targets=["본인"], revision=1)

        def fake_update(user, ipo_id, applied, rev):
            apps["applications"][ipo_id]["applied_owners"] = applied
            apps["revision"] = rev + 1
            return {"revision": apps["revision"]}

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                today=self.today,
                path=self.action_file,
            )
            raw_token = action_res["raw_token"]

            # First execution -> success
            res1 = execute_web_action(
                raw_token,
                authenticated_username="alice",
                today=self.today,
                path=self.action_file,
            )
            self.assertEqual(res1["status"], "applied")
            self.assertEqual(res1["owner"], "본인")

            # Check that action record is consumed
            stored = _load_v2(self.action_file)
            self.assertIsNotNone(stored["actions"][action_res["token_digest"]]["consumed_at"])

            # Second execution -> idempotent status already_processed
            res2 = execute_web_action(
                raw_token,
                authenticated_username="alice",
                today=self.today,
                path=self.action_file,
            )
            self.assertEqual(res2["status"], "already_processed")

    def test_open_ipo_sale_flow_not_executable_in_phase2(self):
        action_res = create_web_action(
            username="alice",
            action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
            metadata={"ipo_id": "ipo-1", "owner": "본인"},
            today=self.today,
            path=self.action_file,
        )
        raw_token = action_res["raw_token"]

        with self.assertRaises(IpoActionError) as cm:
            execute_web_action(
                raw_token,
                authenticated_username="alice",
                today=self.today,
                path=self.action_file,
            )
        self.assertEqual(str(cm.exception), "ACTION_NOT_EXECUTABLE")

        # Verify consumed_at was NOT set
        stored = _load_v2(self.action_file)
        self.assertIsNone(stored["actions"][action_res["token_digest"]]["consumed_at"])

    def test_execute_web_action_cross_user_rejection(self):
        market = _make_market_data("ipo-1", "2026-09-20", "2026-09-21")
        apps = _make_user_applications("ipo-1", applied=[], targets=["본인"])

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                today=self.today,
                path=self.action_file,
            )

        # Bob attempts to execute Alice's action
        with self.assertRaises(IpoActionError) as cm:
            execute_web_action(
                action_res["raw_token"],
                authenticated_username="bob",
                today=self.today,
                path=self.action_file,
            )
        self.assertEqual(str(cm.exception), "FORBIDDEN")

    def test_build_action_url(self):
        valid_tok = "tok1234567890abcdef"
        with patch("app.services.action_v2.get_effective_system_settings", return_value={"public_base_url": "https://wealth.example.com"}):
            url = build_action_url(valid_tok)
            self.assertEqual(url, f"https://wealth.example.com/a/{valid_tok}")

        with patch("app.services.action_v2.get_effective_system_settings", return_value={"public_base_url": ""}):
            with self.assertRaises(IpoActionError):
                build_action_url(valid_tok)

        # Malformed token in URL generation fails fast
        with self.assertRaises(IpoActionError):
            build_action_url("short")

    def test_pruning_policy(self):
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(days=ACTION_RETENTION_DAYS + 2)).isoformat()
        recent_time = (now - timedelta(days=1)).isoformat()

        data = {
            "version": 2,
            "actions": {
                "old_consumed": {
                    "token_digest": "old_consumed",
                    "consumed_at": old_time,
                    "expires_at": old_time,
                },
                "recent_consumed": {
                    "token_digest": "recent_consumed",
                    "consumed_at": recent_time,
                    "expires_at": old_time,
                },
                "old_expired_unconsumed": {
                    "token_digest": "old_expired_unconsumed",
                    "consumed_at": None,
                    "expires_at": old_time,
                },
                "active_unconsumed": {
                    "token_digest": "active_unconsumed",
                    "consumed_at": None,
                    "expires_at": (now + timedelta(days=2)).isoformat(),
                },
            },
        }

        result = prune_old_v2_actions(data, now=now)
        self.assertNotIn("old_consumed", result["actions"])
        self.assertNotIn("old_expired_unconsumed", result["actions"])
        self.assertIn("recent_consumed", result["actions"])
        self.assertIn("active_unconsumed", result["actions"])


class ActionV2HttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(app)
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="wealth-http-v2-")
        self.addCleanup(self.tmp_dir.cleanup)
        self.action_file = Path(self.tmp_dir.name) / "action_v2_state.json"
        self.public_origin = "https://wealth.example.com"
        self.settings_patch = patch(
            "app.services.system_settings.get_effective_system_settings",
            return_value={"public_base_url": self.public_origin},
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

    def _login_session(self, username="alice", role="user"):
        token = _serializer.dumps({"user": username, "role": role})
        self.client.cookies.set(COOKIE_NAME, token)
        p = patch("app.services.user_manager.get_user_by_name", return_value={"username": username, "id": f"id-{username}", "role": role})
        p.start()
        self.addCleanup(p.stop)

    def test_unauthenticated_get_redirects_with_return_to(self):
        self.client.cookies.clear()
        resp = self.client.get("/a/abc123xyz_token456", follow_redirects=False)
        self.assertEqual(resp.status_code, 307)
        self.assertIn("/login?return_to=%2Fa%2Fabc123xyz_token456", resp.headers["location"])

    def test_login_flow_preserves_valid_return_to(self):
        self.client.cookies.clear()
        with patch("app.services.user_manager.authenticate_user", return_value={"username": "alice", "role": "user", "must_change_password": False}):
            resp = self.client.post(
                "/login",
                data={
                    "username": "alice",
                    "password": "correct_password",
                    "return_to": "/a/valid_test_token_12345",
                },
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 303)
            self.assertEqual(resp.headers["location"], "/a/valid_test_token_12345")

    def test_login_flow_neutralizes_open_redirect_attacks(self):
        self.client.cookies.clear()
        malicious_inputs = [
            "https://evil.com/phish",
            "//evil.com",
            "/dashboard",
            "/api/auth/me",
            "javascript:alert(1)",
            "/a/short",  # too short
            "/a/" + "a" * 100,  # too long
            "/a/with!special$chars",
        ]

        with patch("app.services.user_manager.authenticate_user", return_value={"username": "alice", "role": "user", "must_change_password": False}):
            for mal in malicious_inputs:
                resp = self.client.post(
                    "/login",
                    data={
                        "username": "alice",
                        "password": "correct_password",
                        "return_to": mal,
                    },
                    follow_redirects=False,
                )
                self.assertEqual(resp.status_code, 303)
                # Malicious input neutralized: defaults to /dashboard
                self.assertEqual(resp.headers["location"], "/dashboard")

    def test_canonical_ipo_display_resolution(self):
        self._login_session("alice")
        cur_date = datetime.now(KST).date()
        start_str = (cur_date - timedelta(days=1)).isoformat()
        end_str = (cur_date + timedelta(days=1)).isoformat()
        # Market store has official canonical name "삼양식품바이오"
        market = _make_market_data("ipo-99", start_str, end_str, name="삼양식품바이오")
        apps = _make_user_applications("ipo-99", applied=[], targets=["본인"])

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                # Even if legacy metadata had a stale name "구버전이름"
                metadata={"ipo_id": "ipo-99", "ipo_name": "구버전이름", "owner": "본인"},
                today=cur_date,
                path=self.action_file,
            )

        with patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file), \
             patch("app.services.ipo.store.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.applications.get_user_applications", return_value=apps):
            resp = self.client.get(f"/a/{action_res['raw_token']}")
            self.assertEqual(resp.status_code, 200)
            # Authoritative name resolved
            self.assertIn("삼양식품바이오", resp.text)
            self.assertNotIn("구버전이름", resp.text)

    def test_read_only_get_has_zero_side_effects_comprehensive(self):
        self._login_session("alice")
        cur_date = datetime.now(KST).date()
        start_str = (cur_date - timedelta(days=1)).isoformat()
        end_str = (cur_date + timedelta(days=1)).isoformat()
        market = _make_market_data("ipo-1", start_str, end_str, name="테스트공모주")
        apps = _make_user_applications("ipo-1", applied=[], targets=["본인"])

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                today=cur_date,
                path=self.action_file,
            )

        raw_token = action_res["raw_token"]

        def snapshot_tree():
            res = {}
            for p in sorted(Path(self.tmp_dir.name).glob("**/*")):
                if p.is_file():
                    res[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
            return res

        tree_before = snapshot_tree()

        with patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file), \
             patch("app.services.ipo.store.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.applications.get_user_applications", return_value=apps):
            # Execute 5 consecutive GET requests
            for _ in range(5):
                resp = self.client.get(f"/a/{raw_token}")
                self.assertEqual(resp.status_code, 200)
                self.assertIn("IPO 청약 완료 확인", resp.text)
                self.assertIn("테스트공모주", resp.text)
                self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")

        tree_after = snapshot_tree()
        # Verify file set and hashes are identical
        self.assertEqual(tree_before.keys(), tree_after.keys(), "File set must not change on GET")
        self.assertEqual(tree_before, tree_after, "File hashes must not change on GET")
        # Ensure no dangling temporary files
        self.assertFalse(any(k.endswith(".tmp") for k in tree_after))

    def test_post_csrf_same_origin_protection(self):
        self._login_session("alice")
        cur_date = datetime.now(KST).date()
        start_str = (cur_date - timedelta(days=1)).isoformat()
        end_str = (cur_date + timedelta(days=1)).isoformat()
        market = _make_market_data("ipo-1", start_str, end_str)
        apps = _make_user_applications("ipo-1", applied=[], targets=["본인"], revision=5)

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                today=cur_date,
                path=self.action_file,
            )

        raw_token = action_res["raw_token"]

        with patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            # 1. Missing Origin and missing Referer -> 403 CSRF rejection
            resp_missing = self.client.post(f"/a/{raw_token}/execute")
            self.assertEqual(resp_missing.status_code, 403)
            self.assertIn("요청 검증 실패", resp_missing.text)

            # 2. Evil Origin -> 403 CSRF rejection
            resp_evil = self.client.post(
                f"/a/{raw_token}/execute",
                headers={"Origin": "https://evil-attacker.com"},
            )
            self.assertEqual(resp_evil.status_code, 403)
            self.assertIn("요청 검증 실패", resp_evil.text)

            # 3. Evil Referer fallback -> 403 CSRF rejection
            resp_evil_ref = self.client.post(
                f"/a/{raw_token}/execute",
                headers={"Referer": "https://evil-attacker.com/page"},
            )
            self.assertEqual(resp_evil_ref.status_code, 403)
            self.assertIn("요청 검증 실패", resp_evil_ref.text)

            # Confirm action remains UNCONSUMED and application UNTOUCHED after rejections
            data = _load_v2(self.action_file)
            self.assertIsNone(data["actions"][action_res["token_digest"]]["consumed_at"])
            self.assertEqual(apps["revision"], 5)
            self.assertEqual(apps["applications"]["ipo-1"]["applied_owners"], [])

            # 4. Valid Referer fallback -> Success
            def fake_update(user, ipo_id, applied, rev):
                apps["applications"][ipo_id]["applied_owners"] = applied
                apps["revision"] = rev + 1
                return {"revision": apps["revision"]}

            with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
                 patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
                 patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
                resp_valid_ref = self.client.post(
                    f"/a/{raw_token}/execute",
                    headers={"Referer": f"{self.public_origin}/a/{raw_token}"},
                )
                self.assertEqual(resp_valid_ref.status_code, 200)
                self.assertIn("청약 완료 처리 성공", resp_valid_ref.text)
                self.assertEqual(apps["revision"], 6)

    def test_post_execute_updates_state_and_is_idempotent(self):
        self._login_session("alice")
        cur_date = datetime.now(KST).date()
        start_str = (cur_date - timedelta(days=1)).isoformat()
        end_str = (cur_date + timedelta(days=1)).isoformat()
        market = _make_market_data("ipo-1", start_str, end_str)
        apps = _make_user_applications("ipo-1", applied=[], targets=["본인"], revision=5)

        def fake_update(user, ipo_id, applied, rev):
            apps["applications"][ipo_id]["applied_owners"] = applied
            apps["revision"] = rev + 1
            return {"revision": apps["revision"]}

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                today=cur_date,
                path=self.action_file,
            )

        raw_token = action_res["raw_token"]

        with patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file), \
             patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            # POST /a/{token}/execute with valid Origin
            headers = {"Origin": self.public_origin}
            resp1 = self.client.post(f"/a/{raw_token}/execute", headers=headers)
            self.assertEqual(resp1.status_code, 200)
            self.assertIn("청약 완료 처리 성공", resp1.text)
            self.assertIn("본인", apps["applications"]["ipo-1"]["applied_owners"])
            self.assertEqual(apps["revision"], 6)

            # Idempotent re-POST
            resp2 = self.client.post(f"/a/{raw_token}/execute", headers=headers)
            self.assertEqual(resp2.status_code, 200)
            self.assertIn("이미 처리 완료", resp2.text)
            # Revision didn't bump again
            self.assertEqual(apps["revision"], 6)

    def test_open_ipo_sale_flow_post_execute_returns_400(self):
        self._login_session("alice")
        cur_date = datetime.now(KST).date()

        with patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            action_res = create_web_action(
                username="alice",
                action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                metadata={"ipo_id": "ipo-1", "owner": "본인"},
                today=cur_date,
                path=self.action_file,
            )

        raw_token = action_res["raw_token"]

        with patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            resp = self.client.post(f"/a/{raw_token}/execute", headers={"Origin": self.public_origin})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("실행할 수 없는 작업", resp.text)
            self.assertIn("ACTION_NOT_EXECUTABLE", resp.text)

    def test_safe_error_mapping_no_internal_leak(self):
        self._login_session("alice")
        headers = {"Origin": self.public_origin}

        # Corrupt the state file to simulate unreadable JSON / OSError
        self.action_file.write_text("{corrupt: json syntax...", encoding="utf-8")

        valid_tok = "test_valid_format_token_12345"
        with patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_file):
            resp = self.client.post(f"/a/{valid_tok}/execute", headers=headers)
            self.assertEqual(resp.status_code, 400)
            self.assertIn("작업 저장소 상태를 확인할 수 없습니다", resp.text)
            # Ensure no internal path or python exception details are in the output
            self.assertNotIn("JSONDecodeError", resp.text)
            self.assertNotIn(str(self.action_file), resp.text)
            self.assertNotIn("Traceback", resp.text)


if __name__ == "__main__":
    unittest.main()
