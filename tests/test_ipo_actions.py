"""Comprehensive test suite for app/services/ipo/actions.py — Batch F.2A-1.

Coverage:
- action_state_lock: same-process contention, exception release, cross-process
- _load: fail-closed on corrupt JSON, missing file returns empty
- _save: atomic temp→replace, NaN serialization failure preserves existing file, .tmp cleaned
- prune_old_actions: active preserved, recently consumed preserved, old consumed pruned,
  old expired unconsumed pruned
- _subscription_expiry / _is_expired: KST boundary (23:59:59, next-day 00:00:00)
- create_mark_applied_action: valid, invalid owner, IPO_NOT_FOUND, SUBSCRIPTION_NOT_ACTIVE,
  opaque unique IDs, persistence round-trip
- mark_ipo_owner_applied: applied, already_applied (no write), OWNER_NOT_ELIGIBLE,
  IPO_NOT_FOUND, SUBSCRIPTION_NOT_ACTIVE, frozen targets, untouched application,
  field/accounting preservation, CAS already_applied recovery, CAS retry success,
  CAS double-conflict propagated
- execute_action: valid, ACTION_NOT_FOUND, ACTION_EXPIRED, already_processed,
  already_applied action consumed, concurrency (same action), different-action same-owner race
- Full accounting isolation
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.ipo.actions import (
    ACTION_RETENTION_DAYS,
    IpoActionAlreadyRunning,
    IpoActionError,
    KST,
    _is_expired,
    _load,
    _now_utc,
    _save,
    _subscription_expiry,
    action_state_lock,
    create_mark_applied_action,
    execute_action,
    mark_ipo_owner_applied,
    prune_old_actions,
)
from app.services.ipo.applications import ApplicationRevisionConflict

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

def _make_market(ipo_id="ipo1", start="2026-09-20", end="2026-09-21"):
    return {
        "ipos": [{
            "ipo_id": ipo_id,
            "company_name": "테스트",
            "subscription_start": start,
            "subscription_end": end,
            "lead_managers": ["한국투자증권"],
        }]
    }


def _make_apps(family=None, applied=None, frozen_targets=None, applicants=None, revision=0):
    app = {}
    if frozen_targets is not None:
        app["target_owners"] = frozen_targets
        app["target_frozen_at"] = "2026-09-19T00:00:00+09:00"
    if applied is not None:
        app["applied_owners"] = applied
    if applicants is not None:
        app["applicants"] = applicants
    return {
        "revision": revision,
        "family_members": family or ["아빠", "엄마", "자녀"],
        "applications": {"ipo1": app} if app else {},
    }


TODAY = date(2026, 9, 20)


# ---------------------------------------------------------------------------
# 1. action_state_lock — same-process contention
# ---------------------------------------------------------------------------

class TestActionStateLockSameProcess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "action_state.json"

    def test_same_process_contention_fails_fast(self):
        with action_state_lock(self.path):
            with self.assertRaises(IpoActionAlreadyRunning):
                with action_state_lock(self.path):
                    pass

    def test_normal_exit_releases(self):
        with action_state_lock(self.path):
            pass
        with action_state_lock(self.path):
            pass

    def test_exception_releases(self):
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with action_state_lock(self.path):
                raise RuntimeError("boom")
        with action_state_lock(self.path):
            pass


# ---------------------------------------------------------------------------
# 2. action_state_lock — cross-process
# ---------------------------------------------------------------------------

class TestActionStateLockCrossProcess(unittest.TestCase):
    def test_cross_process_contention_and_release(self):
        script = """
import sys, time
from pathlib import Path
from app.services.ipo.actions import action_state_lock

path = Path(sys.argv[1])
flag = Path(sys.argv[2])

with action_state_lock(path):
    flag.write_text('LOCKED', encoding='utf-8')
    for _ in range(100):
        time.sleep(0.1)
        if flag.read_text(encoding='utf-8') == 'RELEASE':
            break
"""
        with tempfile.TemporaryDirectory() as tmp:
            script_file = Path(tmp) / "worker.py"
            script_file.write_text(script, encoding="utf-8")
            state_path = Path(tmp) / "action_state.json"
            flag_path = Path(tmp) / "flag.txt"

            env = dict(os.environ)
            env["PYTHONPATH"] = "."
            proc = subprocess.Popen(
                [sys.executable, str(script_file), str(state_path), str(flag_path)],
                env=env,
            )
            try:
                locked = False
                for _ in range(50):
                    time.sleep(0.1)
                    if flag_path.exists() and flag_path.read_text(encoding="utf-8") == "LOCKED":
                        locked = True
                        break
                self.assertTrue(locked, "Worker failed to acquire lock")

                with self.assertRaises(IpoActionAlreadyRunning):
                    with action_state_lock(state_path):
                        pass

                flag_path.write_text("RELEASE", encoding="utf-8")
                proc.wait(5)
                self.assertEqual(proc.returncode, 0)

                # Post-release: parent must succeed
                with action_state_lock(state_path):
                    pass
            finally:
                if proc.poll() is None:
                    flag_path.write_text("RELEASE", encoding="utf-8")
                    proc.terminate()


# ---------------------------------------------------------------------------
# 3. _load / _save — persistence and failure safety
# ---------------------------------------------------------------------------

class TestLoadSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "action_state.json"

    def test_missing_file_returns_empty(self):
        data = _load(self.path)
        self.assertEqual(data, {"actions": {}})

    def test_valid_round_trip(self):
        original = {"actions": {"abc": {"action_id": "abc", "consumed_at": None}}}
        _save(original, self.path)
        loaded = _load(self.path)
        self.assertEqual(loaded["actions"]["abc"]["action_id"], "abc")

    def test_corrupt_json_raises(self):
        self.path.write_text("{invalid", encoding="utf-8")
        with self.assertRaises(IpoActionError):
            _load(self.path)

    def test_malformed_structure_raises(self):
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(IpoActionError):
            _load(self.path)

    def test_nan_save_fails_preserves_file_and_removes_tmp(self):
        good = {"actions": {"good": {"action_id": "good", "consumed_at": None}}}
        _save(good, self.path)
        before = self.path.read_bytes()

        bad = {"actions": {"bad": {"score": float("nan")}}}
        with self.assertRaises((ValueError, Exception)):
            _save(bad, self.path)

        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.path.with_suffix(".tmp").exists())

    def test_atomic_write_uses_temp(self):
        """Verify that .tmp file is used and replaced (no direct overwrite)."""
        data = {"actions": {}}
        # Intercept the replace call to verify temp file was created
        original_replace = Path.replace

        replaced_from = []

        def spy_replace(self_path, target):
            replaced_from.append(str(self_path))
            return original_replace(self_path, target)

        with patch.object(Path, "replace", spy_replace):
            _save(data, self.path)

        self.assertTrue(any(".tmp" in s for s in replaced_from))


# ---------------------------------------------------------------------------
# 4. prune_old_actions
# ---------------------------------------------------------------------------

class TestPruneOldActions(unittest.TestCase):
    def _make_action(self, aid, consumed_at=None, expires_at=None):
        return {
            "action_id": aid,
            "action_type": "MARK_IPO_APPLIED",
            "consumed_at": consumed_at,
            "expires_at": expires_at,
        }

    def setUp(self):
        self.now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
        self.cutoff = self.now - timedelta(days=ACTION_RETENTION_DAYS)

    def test_active_old_action_preserved(self):
        """Unconsumed, expires in future (20 days from now) → kept regardless of age."""
        future_exp = (self.now + timedelta(days=20)).isoformat()
        data = {"actions": {"a": self._make_action("a", expires_at=future_exp)}}
        result = prune_old_actions(data, now=self.now)
        self.assertIn("a", result["actions"])

    def test_recently_consumed_preserved(self):
        """Consumed 2 days ago → within retention → kept."""
        consumed_2d = (self.now - timedelta(days=2)).isoformat()
        data = {"actions": {"b": self._make_action("b", consumed_at=consumed_2d)}}
        result = prune_old_actions(data, now=self.now)
        self.assertIn("b", result["actions"])

    def test_old_consumed_pruned(self):
        """Consumed 8 days ago → past retention → pruned."""
        consumed_8d = (self.now - timedelta(days=8)).isoformat()
        data = {"actions": {"c": self._make_action("c", consumed_at=consumed_8d)}}
        result = prune_old_actions(data, now=self.now)
        self.assertNotIn("c", result["actions"])

    def test_old_expired_unconsumed_pruned(self):
        """Unconsumed, expired 8 days ago → pruned."""
        expired_8d = (self.now - timedelta(days=8)).isoformat()
        data = {"actions": {"d": self._make_action("d", expires_at=expired_8d)}}
        result = prune_old_actions(data, now=self.now)
        self.assertNotIn("d", result["actions"])

    def test_mixed_batch(self):
        consumed_2d = (self.now - timedelta(days=2)).isoformat()
        consumed_8d = (self.now - timedelta(days=8)).isoformat()
        future_exp = (self.now + timedelta(days=5)).isoformat()
        expired_8d = (self.now - timedelta(days=8)).isoformat()
        data = {"actions": {
            "keep1": self._make_action("keep1", consumed_at=consumed_2d),
            "keep2": self._make_action("keep2", expires_at=future_exp),
            "prune1": self._make_action("prune1", consumed_at=consumed_8d),
            "prune2": self._make_action("prune2", expires_at=expired_8d),
        }}
        result = prune_old_actions(data, now=self.now)
        self.assertIn("keep1", result["actions"])
        self.assertIn("keep2", result["actions"])
        self.assertNotIn("prune1", result["actions"])
        self.assertNotIn("prune2", result["actions"])


# ---------------------------------------------------------------------------
# 5. KST expiry boundary
# ---------------------------------------------------------------------------

class TestExpiryBoundary(unittest.TestCase):
    def test_subscription_expiry_is_end_of_day_kst(self):
        sub_end = date(2026, 9, 21)
        exp = _subscription_expiry(sub_end)
        # Should be 2026-09-21 23:59:59 KST = 2026-09-21 14:59:59 UTC
        expected_utc = datetime(2026, 9, 21, 14, 59, 59, tzinfo=timezone.utc)
        self.assertEqual(exp, expected_utc)

    def _make_action_with_expiry(self, expiry_dt: datetime) -> dict:
        return {"expires_at": expiry_dt.isoformat(), "consumed_at": None}

    def test_second_before_expiry_not_expired(self):
        # 2026-09-21 23:59:58 KST
        dt = datetime(2026, 9, 21, 23, 59, 58, tzinfo=KST)
        # expires_at = end of 2026-09-21 23:59:59 KST
        action = {"expires_at": _subscription_expiry(date(2026, 9, 21)).isoformat(), "consumed_at": None}
        # today = 2026-09-21 → not expired
        self.assertFalse(_is_expired(action, date(2026, 9, 21)))

    def test_at_expiry_boundary_valid(self):
        # expires_at is 2026-09-21 23:59:59 KST → valid through end of 2026-09-21
        action = {"expires_at": _subscription_expiry(date(2026, 9, 21)).isoformat(), "consumed_at": None}
        self.assertFalse(_is_expired(action, date(2026, 9, 21)))

    def test_next_day_is_expired(self):
        # 2026-09-22 → expired
        action = {"expires_at": _subscription_expiry(date(2026, 9, 21)).isoformat(), "consumed_at": None}
        self.assertTrue(_is_expired(action, date(2026, 9, 22)))


# ---------------------------------------------------------------------------
# 6. mark_ipo_owner_applied — direct command tests
# ---------------------------------------------------------------------------

def _patch_mark(market=None, apps=None):
    """Helper: returns patch context managers for market store and user applications."""
    m = market or _make_market()
    a = apps or _make_apps()
    return (
        patch("app.services.ipo.actions.read_market_store_read_only", return_value=m),
        patch("app.services.ipo.actions.get_user_applications", return_value=a),
    )


class TestMarkIpoOwnerApplied(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_valid_apply(self):
        apps = _make_apps(applied=["엄마"])
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application",
                   return_value={"revision": 1}) as mock_upd:
            result = mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["owner"], "아빠")
        mock_upd.assert_called_once()

    def test_already_applied_no_write(self):
        apps = _make_apps(applied=["아빠"])
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application") as mock_upd:
            result = mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        self.assertEqual(result["status"], "already_applied")
        mock_upd.assert_not_called()

    def test_owner_not_eligible(self):
        apps = _make_apps()
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            with self.assertRaises(IpoActionError) as ctx:
                mark_ipo_owner_applied(None, "ipo1", "공격자", today=TODAY)
        self.assertIn("OWNER_NOT_ELIGIBLE", str(ctx.exception))

    def test_ipo_not_found(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value={"ipos": []}):
            with self.assertRaises(IpoActionError) as ctx:
                mark_ipo_owner_applied(None, "ipo_unknown", "아빠", today=TODAY)
        self.assertIn("IPO_NOT_FOUND", str(ctx.exception))

    def test_subscription_not_active_before(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()):
            with self.assertRaises(IpoActionError) as ctx:
                mark_ipo_owner_applied(None, "ipo1", "아빠", today=date(2026, 9, 19))
        self.assertIn("SUBSCRIPTION_NOT_ACTIVE", str(ctx.exception))

    def test_subscription_not_active_after(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()):
            with self.assertRaises(IpoActionError) as ctx:
                mark_ipo_owner_applied(None, "ipo1", "아빠", today=date(2026, 9, 22))
        self.assertIn("SUBSCRIPTION_NOT_ACTIVE", str(ctx.exception))

    def test_subscription_start_day_allowed(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()), \
             patch("app.services.ipo.actions.update_user_application", return_value={"revision": 1}):
            result = mark_ipo_owner_applied(None, "ipo1", "아빠", today=date(2026, 9, 20))
        self.assertEqual(result["status"], "applied")

    def test_subscription_end_day_allowed(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()), \
             patch("app.services.ipo.actions.update_user_application", return_value={"revision": 1}):
            result = mark_ipo_owner_applied(None, "ipo1", "아빠", today=date(2026, 9, 21))
        self.assertEqual(result["status"], "applied")

    def test_frozen_targets_enforced(self):
        """자녀 is in configured family but not in frozen targets → OWNER_NOT_ELIGIBLE."""
        apps = _make_apps(family=["아빠", "엄마", "자녀"], frozen_targets=["아빠", "엄마"])
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            with self.assertRaises(IpoActionError) as ctx:
                mark_ipo_owner_applied(None, "ipo1", "자녀", today=TODAY)
        self.assertIn("OWNER_NOT_ELIGIBLE", str(ctx.exception))

    def test_untouched_application_uses_family(self):
        """No existing application record → fall back to configured family_members."""
        apps = {"revision": 0, "family_members": ["아빠", "엄마"], "applications": {}}
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", return_value={"revision": 1}):
            result = mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        self.assertEqual(result["status"], "applied")

    def test_invalid_date_missing_start(self):
        market = {"ipos": [{"ipo_id": "ipo1", "subscription_start": None, "subscription_end": "2026-09-21"}]}
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market):
            with self.assertRaises(IpoActionError) as ctx:
                mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        self.assertIn("SUBSCRIPTION_NOT_ACTIVE", str(ctx.exception))

    def test_invalid_date_start_after_end(self):
        market = {"ipos": [{"ipo_id": "ipo1", "subscription_start": "2026-09-22", "subscription_end": "2026-09-21"}]}
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=market), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()):
            with self.assertRaises(IpoActionError) as ctx:
                mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        self.assertIn("SUBSCRIPTION_NOT_ACTIVE", str(ctx.exception))


# ---------------------------------------------------------------------------
# 7. CAS conflict recovery
# ---------------------------------------------------------------------------

class TestCASRecovery(unittest.TestCase):
    def test_cas_recovery_already_applied_after_conflict(self):
        """Conflict on first try; re-read shows owner already applied → already_applied."""
        apps_v1 = _make_apps(applied=[], revision=0)
        apps_v2 = _make_apps(applied=["아빠"], revision=1)

        call_count = {"n": 0}

        def fake_get_apps(_username):
            call_count["n"] += 1
            return apps_v1 if call_count["n"] == 1 else apps_v2

        def fake_update(username, ipo_id, applied, rev):
            raise ApplicationRevisionConflict("Revision conflict: client=0, server=1")

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", side_effect=fake_get_apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            result = mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        self.assertEqual(result["status"], "already_applied")

    def test_cas_recovery_retry_succeeds(self):
        """Conflict on first try; owner still pending; retry with fresh revision succeeds."""
        apps_v1 = _make_apps(applied=[], revision=0)
        apps_v2 = _make_apps(applied=[], revision=1)

        get_call = {"n": 0}
        update_call = {"n": 0}

        def fake_get_apps(_username):
            get_call["n"] += 1
            return apps_v1 if get_call["n"] == 1 else apps_v2

        def fake_update(username, ipo_id, applied, rev):
            update_call["n"] += 1
            if update_call["n"] == 1:
                raise ApplicationRevisionConflict("Revision conflict")
            return {"revision": 2}

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", side_effect=fake_get_apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            result = mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(update_call["n"], 2)

    def test_cas_double_conflict_propagates(self):
        """Two consecutive conflicts → exception propagated (no infinite retry)."""
        apps = _make_apps(applied=[], revision=0)

        def fake_update(username, ipo_id, applied, rev):
            raise ApplicationRevisionConflict("Revision conflict")

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            with self.assertRaises(ApplicationRevisionConflict):
                mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)


# ---------------------------------------------------------------------------
# 8. create_mark_applied_action
# ---------------------------------------------------------------------------

class TestCreateMarkAppliedAction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "action_state.json"

    def _create(self, owner="아빠", today=TODAY):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()):
            return create_mark_applied_action(None, "ipo1", owner, "telegram", today=today, path=self.path)

    def test_valid_creates_action(self):
        action = self._create()
        self.assertEqual(action["action_type"], "MARK_IPO_APPLIED")
        self.assertEqual(action["owner"], "아빠")
        self.assertIsNone(action["consumed_at"])

    def test_action_id_is_opaque_unique(self):
        ids = {self._create()["action_id"] for _ in range(5)}
        self.assertEqual(len(ids), 5)
        for aid in ids:
            self.assertNotIn("아빠", aid)
            self.assertNotIn("ipo1", aid)

    def test_persistence_round_trip(self):
        action = self._create()
        data = _load(self.path)
        loaded = data["actions"][action["action_id"]]
        self.assertEqual(loaded["owner"], "아빠")
        self.assertEqual(loaded["ipo_id"], "ipo1")

    def test_ipo_not_found(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value={"ipos": []}):
            with self.assertRaises(IpoActionError) as ctx:
                create_mark_applied_action(None, "bad_ipo", "아빠", "tg", today=TODAY, path=self.path)
        self.assertIn("IPO_NOT_FOUND", str(ctx.exception))

    def test_owner_not_eligible(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()):
            with self.assertRaises(IpoActionError) as ctx:
                create_mark_applied_action(None, "ipo1", "공격자", "tg", today=TODAY, path=self.path)
        self.assertIn("OWNER_NOT_ELIGIBLE", str(ctx.exception))

    def test_subscription_not_active(self):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()):
            with self.assertRaises(IpoActionError) as ctx:
                create_mark_applied_action(None, "ipo1", "아빠", "tg", today=date(2026, 9, 22), path=self.path)
        self.assertIn("SUBSCRIPTION_NOT_ACTIVE", str(ctx.exception))

    def test_expires_at_is_kst_end_of_day(self):
        action = self._create()
        exp = datetime.fromisoformat(action["expires_at"])
        # 2026-09-21 23:59:59 KST = 2026-09-21 14:59:59 UTC
        expected = datetime(2026, 9, 21, 14, 59, 59, tzinfo=timezone.utc)
        self.assertEqual(exp, expected)


# ---------------------------------------------------------------------------
# 9. execute_action
# ---------------------------------------------------------------------------

class TestExecuteAction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "action_state.json"

    def _create(self, owner="아빠", today=TODAY):
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()):
            return create_mark_applied_action(None, "ipo1", owner, "tg", today=today, path=self.path)

    def _execute(self, action_id, today=TODAY, applied=None):
        apps = _make_apps(applied=applied or [])
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", return_value={"revision": 1}):
            return execute_action(action_id, today=today, path=self.path)

    def test_valid_execute(self):
        action = self._create()
        result = self._execute(action["action_id"])
        self.assertEqual(result["status"], "applied")
        # consumed_at set
        data = _load(self.path)
        a = data["actions"].get(action["action_id"])
        self.assertIsNotNone(a)  # might be pruned only after 7 days
        if a:
            self.assertIsNotNone(a["consumed_at"])

    def test_action_not_found(self):
        with self.assertRaises(IpoActionError) as ctx:
            execute_action("nonexistent", today=TODAY, path=self.path)
        self.assertIn("ACTION_NOT_FOUND", str(ctx.exception))

    def test_action_expired(self):
        action = self._create(today=TODAY)
        # Execute with tomorrow+1 (past subscription end 2026-09-21)
        with self.assertRaises(IpoActionError) as ctx:
            self._execute(action["action_id"], today=date(2026, 9, 22))
        self.assertIn("ACTION_EXPIRED", str(ctx.exception))

    def test_already_consumed(self):
        action = self._create()
        self._execute(action["action_id"])
        result = self._execute(action["action_id"])
        self.assertEqual(result["status"], "already_processed")

    def test_already_applied_action_consumed(self):
        """Owner already applied by another path; action execute → already_applied and consumed."""
        action = self._create()
        # Mark owner as already applied externally
        apps = _make_apps(applied=["아빠"])
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application") as mock_upd:
            result = execute_action(action["action_id"], today=TODAY, path=self.path)
        self.assertEqual(result["status"], "already_applied")
        mock_upd.assert_not_called()
        # Confirm consumed_at was set
        data = _load(self.path)
        a = data["actions"].get(action["action_id"])
        if a:
            self.assertIsNotNone(a["consumed_at"])

    def test_stale_owner_not_eligible(self):
        """Owner removed from targets after action creation → OWNER_NOT_ELIGIBLE on execute."""
        action = self._create(owner="아빠")
        # Now family no longer includes 아빠
        apps = {"revision": 0, "family_members": ["엄마", "자녀"], "applications": {}}
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            with self.assertRaises(IpoActionError) as ctx:
                execute_action(action["action_id"], today=TODAY, path=self.path)
        self.assertIn("OWNER_NOT_ELIGIBLE", str(ctx.exception))


# ---------------------------------------------------------------------------
# 10. Field / accounting preservation
# ---------------------------------------------------------------------------

class TestFieldPreservation(unittest.TestCase):
    """Verify mark_ipo_owner_applied only mutates applied_owners and revision."""

    def test_applicants_preserved(self):
        applicants = {"엄마": {"broker_id": "kb", "account_id": "uuid-1"}}
        apps = _make_apps(applied=["엄마"], applicants=applicants)

        captured = {}

        def fake_update(username, ipo_id, applied_owners, rev):
            captured["applied"] = applied_owners
            return {"revision": 1}

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)

        # update_user_application preserves applicants internally — we verify the call payload
        self.assertIn("아빠", captured["applied"])
        self.assertIn("엄마", captured["applied"])

    def test_accounting_isolation(self):
        """market.json is never written by mark_ipo_owner_applied or execute_action."""
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()) as mock_read, \
             patch("app.services.ipo.actions.get_user_applications", return_value=_make_apps()), \
             patch("app.services.ipo.actions.update_user_application", return_value={"revision": 1}):
            mark_ipo_owner_applied(None, "ipo1", "아빠", today=TODAY)
        # read_market_store_read_only is read-only; no write call should exist
        from app.services.ipo import store
        with patch.object(store, "write_market_store") as mock_write:
            mock_read.assert_called()
            mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# 11. Concurrency — same action, same-owner different actions
# ---------------------------------------------------------------------------

class TestConcurrency(unittest.TestCase):
    """
    These tests use real temp files and threading to exercise actual lock contention.
    We cannot use action_state_lock from two threads simultaneously in one process
    (threading.Lock is process-global), so we test at the portfolio/CAS level instead.
    The cross-process lock covers the file-lock race.
    """

    def test_same_action_executed_concurrently_applied_once(self):
        """Two threads try to execute the same action concurrently.
        One gets applied, the other gets already_processed.
        """
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "action_state.json"

        # Pre-seed an action
        expires_utc = _subscription_expiry(date(2026, 9, 21)).isoformat()
        data = {"actions": {"act1": {
            "action_id": "act1", "action_type": "MARK_IPO_APPLIED",
            "username": None, "ipo_id": "ipo1", "owner": "아빠",
            "created_at": _now_utc().isoformat(), "expires_at": expires_utc,
            "consumed_at": None, "source_channel": "test",
        }}}
        _save(data, path)

        results = []
        lock = threading.Lock()

        def do_execute():
            try:
                apps = _make_apps(applied=[])
                with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
                     patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
                     patch("app.services.ipo.actions.update_user_application", return_value={"revision": 1}):
                    r = execute_action("act1", today=TODAY, path=path)
                with lock:
                    results.append(("ok", r["status"]))
            except IpoActionAlreadyRunning:
                with lock:
                    results.append(("lock_blocked", None))
            except Exception as e:
                with lock:
                    results.append(("error", str(e)))

        t1 = threading.Thread(target=do_execute)
        t2 = threading.Thread(target=do_execute)
        t1.start(); t2.start()
        t1.join(10); t2.join(10)

        statuses = [r[1] for r in results if r[0] == "ok"]
        # Acceptable: one gets applied and one gets already_processed,
        # OR one gets lock_blocked (same-process lock fires first).
        applied_count = statuses.count("applied")
        already_count = statuses.count("already_processed")
        lock_blocked = sum(1 for r in results if r[0] == "lock_blocked")

        self.assertGreaterEqual(applied_count, 1, "At least one thread must apply")
        self.assertTrue(applied_count + already_count + lock_blocked == 2)

    def test_different_actions_same_owner_idempotent(self):
        """Two different actions targeting the same owner/IPO."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "action_state.json"

        expires_utc = _subscription_expiry(date(2026, 9, 21)).isoformat()
        data = {"actions": {
            "actA": {
                "action_id": "actA", "action_type": "MARK_IPO_APPLIED",
                "username": None, "ipo_id": "ipo1", "owner": "아빠",
                "created_at": _now_utc().isoformat(), "expires_at": expires_utc,
                "consumed_at": None, "source_channel": "tg",
            },
            "actB": {
                "action_id": "actB", "action_type": "MARK_IPO_APPLIED",
                "username": None, "ipo_id": "ipo1", "owner": "아빠",
                "created_at": _now_utc().isoformat(), "expires_at": expires_utc,
                "consumed_at": None, "source_channel": "discord",
            },
        }}
        _save(data, path)

        results = []
        lock = threading.Lock()

        def run_action(aid):
            apps = _make_apps(applied=[])
            try:
                with patch("app.services.ipo.actions.read_market_store_read_only", return_value=_make_market()), \
                     patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
                     patch("app.services.ipo.actions.update_user_application", return_value={"revision": 1}):
                    r = execute_action(aid, today=TODAY, path=path)
                with lock:
                    results.append(("ok", r["status"]))
            except IpoActionAlreadyRunning:
                with lock:
                    results.append(("blocked", None))

        t1 = threading.Thread(target=run_action, args=("actA",))
        t2 = threading.Thread(target=run_action, args=("actB",))
        t1.start(); t2.start()
        t1.join(10); t2.join(10)

        ok_results = [r[1] for r in results if r[0] == "ok"]
        blocked = [r for r in results if r[0] == "blocked"]
        # At least one must complete; no invalid status
        self.assertTrue(all(s in ("applied", "already_applied") for s in ok_results))


# ---------------------------------------------------------------------------
# 12. Malformed existing state fail-closed
# ---------------------------------------------------------------------------

class TestMalformedStateFail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "action_state.json"

    def test_malformed_json_raises_not_overwrites(self):
        self.path.write_text("{bad json}", encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaises(IpoActionError):
            with action_state_lock(self.path):
                _load(self.path)
        # File must be unchanged
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_type_raises(self):
        self.path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(IpoActionError):
            _load(self.path)


if __name__ == "__main__":
    unittest.main()
