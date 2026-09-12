"""Unit tests for Toss WTS runtime session confirmation guard."""

from __future__ import annotations

import importlib
import inspect
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from app.services import toss_wts_feed_runtime
from app.services.toss_wts_feed_auth import WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID
from app.services.toss_wts_feed_runtime import (
    CONFIRMATION_IDENTITY_CHANGED,
    CONFIRMED,
    NOT_CONFIRMED,
    PROCESS_LOCAL_CONFIRMATION_ONLY,
    MULTI_PROCESS_SHARED_CONFIRMATION,
    RUNTIME_GENERATION_CHANGED,
    RUNTIME_MATERIAL_UNAVAILABLE,
    STATIC_AUTHORIZATION_FAILED,
    WtsFeedRuntimeDecision,
    check_wts_feed_runtime_confirmation,
    clear_wts_feed_runtime_confirmation,
    confirm_wts_feed_runtime_session,
)
from app.services.user_identity import generate_user_id


class TossWtsFeedRuntimeTests(unittest.TestCase):
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

    def _env_for(self, user_id: str) -> dict[str, str]:
        return {
            WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: user_id,
            "WEALTH_TOSS_WTS_ENABLED": "1",
            "WEALTH_TOSSCTL_PATH": str(self.exe_path),
            "WEALTH_TOSSCTL_CONFIG_DIR": str(self.config_dir),
        }

    def test_multi_process_contract_constants(self):
        self.assertTrue(PROCESS_LOCAL_CONFIRMATION_ONLY)
        self.assertFalse(MULTI_PROCESS_SHARED_CONFIRMATION)

    def test_confirm_success_and_immediate_check(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertIsInstance(confirm_res, WtsFeedRuntimeDecision)
            self.assertTrue(confirm_res.confirmed)
            self.assertTrue(bool(confirm_res))
            self.assertEqual(confirm_res.code, CONFIRMED)
            self.assertEqual(confirm_res["confirmed"], True)
            self.assertEqual(confirm_res["code"], CONFIRMED)

            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertTrue(check_res.confirmed)
            self.assertEqual(check_res.code, CONFIRMED)

    def test_pre_confirm_check_returns_not_confirmed(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            # Prior to confirmation, no session metadata access needed
            with patch("pathlib.Path.stat", side_effect=AssertionError("stat called before confirm")):
                check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, NOT_CONFIRMED)

    def test_static_auth_failure_blocks_confirm_without_material_inspection(self):
        allowed_id = generate_user_id()
        unauthorized_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False):
            with patch("pathlib.Path.stat", side_effect=AssertionError("stat called on unauthorized")):
                confirm_res = confirm_wts_feed_runtime_session(unauthorized_id)
            self.assertFalse(confirm_res.confirmed)
            self.assertEqual(confirm_res.code, STATIC_AUTHORIZATION_FAILED)

            # Ensure no confirmation was stored
            check_res = check_wts_feed_runtime_confirmation(allowed_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, NOT_CONFIRMED)

    def test_unconfigured_static_auth_fails_closed(self):
        user_id = generate_user_id()
        env = self._env_for(user_id)
        env.pop(WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID, None)
        with patch.dict(os.environ, env, clear=True):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertFalse(confirm_res.confirmed)
            self.assertEqual(confirm_res.code, STATIC_AUTHORIZATION_FAILED)

    def test_wrong_user_does_not_revoke_owner_confirmation(self):
        owner_id = generate_user_id()
        attacker_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(owner_id), clear=False):
            # Owner confirms
            confirm_res = confirm_wts_feed_runtime_session(owner_id)
            self.assertTrue(confirm_res.confirmed)

            # Attacker checks - should be denied
            attacker_res = check_wts_feed_runtime_confirmation(attacker_id)
            self.assertFalse(attacker_res.confirmed)
            self.assertEqual(attacker_res.code, STATIC_AUTHORIZATION_FAILED)

            # Owner check remains confirmed
            owner_res = check_wts_feed_runtime_confirmation(owner_id)
            self.assertTrue(owner_res.confirmed)
            self.assertEqual(owner_res.code, CONFIRMED)

    def test_session_mtime_or_size_change_invalidates_confirmation(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Modify synthetic session file content (changes size and mtime)
            # without letting runtime guard read it
            self.session_path.write_text('{"token": "NEW_DIFFERENT_TOKEN_456789"}', encoding="utf-8")

            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, RUNTIME_GENERATION_CHANGED)

            # Subsequent check finds confirmation cleared
            subsequent = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(subsequent.confirmed)
            self.assertEqual(subsequent.code, NOT_CONFIRMED)

    def test_session_replacement_at_same_path_invalidates_confirmation(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Replace file: unlink and recreate with new file identity / mtime
            self.session_path.unlink()
            time.sleep(0.01)
            self.session_path.write_text('{"token": "REPLACED_SESSION_TOKEN"}', encoding="utf-8")

            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, RUNTIME_GENERATION_CHANGED)

    def test_session_disappearance_invalidates_confirmation(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Delete session file
            self.session_path.unlink()

            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, RUNTIME_MATERIAL_UNAVAILABLE)

    def test_reappearance_does_not_auto_restore_confirmation(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Session disappears -> invalidates
            self.session_path.unlink()
            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)

            # Session reappears
            self.session_path.write_text('{"token": "REAPPEARED_TOKEN"}', encoding="utf-8")

            # Check without explicit reconfirmation must return NOT_CONFIRMED
            restore_check = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(restore_check.confirmed)
            self.assertEqual(restore_check.code, NOT_CONFIRMED)

    def test_executable_change_invalidates_confirmation(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Replace executable
            self.exe_path.write_text("updated_tossctl_binary_v2", encoding="utf-8")

            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, RUNTIME_GENERATION_CHANGED)

    def test_executable_target_change_invalidates_confirmation(self):
        user_id = generate_user_id()
        other_exe = Path(self.temp_dir.name) / "tossctl_alt"
        other_exe.write_text("alt_exe", encoding="utf-8")

        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Change executable path env
            with patch.dict(os.environ, {"WEALTH_TOSSCTL_PATH": str(other_exe)}, clear=False):
                check_res = check_wts_feed_runtime_confirmation(user_id)
                self.assertFalse(check_res.confirmed)
                self.assertEqual(check_res.code, RUNTIME_GENERATION_CHANGED)

    def test_config_target_change_invalidates_confirmation(self):
        user_id = generate_user_id()
        other_config = Path(self.temp_dir.name) / "config_alt"
        other_config.mkdir()
        (other_config / "session.json").write_text('{"token": "ALT"}', encoding="utf-8")

        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Change config dir env
            with patch.dict(os.environ, {"WEALTH_TOSSCTL_CONFIG_DIR": str(other_config)}, clear=False):
                check_res = check_wts_feed_runtime_confirmation(user_id)
                self.assertFalse(check_res.confirmed)
                self.assertEqual(check_res.code, RUNTIME_GENERATION_CHANGED)

    def test_runtime_material_missing_at_confirm(self):
        user_id = generate_user_id()
        # Missing executable
        missing_exe_env = self._env_for(user_id)
        missing_exe_env["WEALTH_TOSSCTL_PATH"] = str(Path(self.temp_dir.name) / "nonexistent_exe")
        with patch.dict(os.environ, missing_exe_env, clear=False):
            res = confirm_wts_feed_runtime_session(user_id)
            self.assertFalse(res.confirmed)
            self.assertEqual(res.code, RUNTIME_MATERIAL_UNAVAILABLE)

        # Missing config dir
        missing_dir_env = self._env_for(user_id)
        missing_dir_env["WEALTH_TOSSCTL_CONFIG_DIR"] = str(Path(self.temp_dir.name) / "nonexistent_dir")
        with patch.dict(os.environ, missing_dir_env, clear=False):
            res = confirm_wts_feed_runtime_session(user_id)
            self.assertFalse(res.confirmed)
            self.assertEqual(res.code, RUNTIME_MATERIAL_UNAVAILABLE)

        # Missing session
        self.session_path.unlink()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            res = confirm_wts_feed_runtime_session(user_id)
            self.assertFalse(res.confirmed)
            self.assertEqual(res.code, RUNTIME_MATERIAL_UNAVAILABLE)

    def test_allowed_user_config_change_and_away_and_back_no_auto_restore(self):
        user_a = generate_user_id()
        user_b = generate_user_id()

        # Confirm user A
        with patch.dict(os.environ, self._env_for(user_a), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_a)
            self.assertTrue(confirm_res.confirmed)

        # Change env to user B
        with patch.dict(os.environ, self._env_for(user_b), clear=False):
            # Check with user B detects identity change and invalidates
            check_b = check_wts_feed_runtime_confirmation(user_b)
            self.assertFalse(check_b.confirmed)
            self.assertEqual(check_b.code, CONFIRMATION_IDENTITY_CHANGED)

        # Change env back to user A without reconfirming
        with patch.dict(os.environ, self._env_for(user_a), clear=False):
            check_a = check_wts_feed_runtime_confirmation(user_a)
            self.assertFalse(check_a.confirmed)
            self.assertEqual(check_a.code, NOT_CONFIRMED)

    def test_same_username_recreation_has_different_id_and_cannot_inherit(self):
        old_id_a = generate_user_id()
        recreated_id_b = generate_user_id()

        sig = inspect.signature(confirm_wts_feed_runtime_session)
        self.assertEqual(list(sig.parameters.keys()), ["user_id"])
        self.assertNotIn("username", sig.parameters)

        with patch.dict(os.environ, self._env_for(old_id_a), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(old_id_a)
            self.assertTrue(confirm_res.confirmed)

            check_res = check_wts_feed_runtime_confirmation(recreated_id_b)
            self.assertFalse(check_res.confirmed)

    def test_process_restart_semantics_yields_not_confirmed(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Simulate process restart by reloading the module
            importlib.reload(toss_wts_feed_runtime)

            check_res = toss_wts_feed_runtime.check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, NOT_CONFIRMED)

    def test_explicit_clear_invalidates_confirmation(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            clear_wts_feed_runtime_confirmation()

            check_res = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_res.confirmed)
            self.assertEqual(check_res.code, NOT_CONFIRMED)

    def test_session_content_is_never_read_or_parsed_or_hashed(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            # Guard session content reads
            with patch("pathlib.Path.read_text", side_effect=AssertionError("read_text called")), \
                 patch("pathlib.Path.read_bytes", side_effect=AssertionError("read_bytes called")), \
                 patch("json.load", side_effect=AssertionError("json.load called")), \
                 patch("json.loads", side_effect=AssertionError("json.loads called")):
                confirm_res = confirm_wts_feed_runtime_session(user_id)
                self.assertTrue(confirm_res.confirmed)

                check_res = check_wts_feed_runtime_confirmation(user_id)
                self.assertTrue(check_res.confirmed)

    def test_decision_privacy_and_marker_not_exposed(self):
        user_id = "00000000-0000-4000-8000-000000000001"
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            decision = confirm_wts_feed_runtime_session(user_id)

            rep = repr(decision)
            st = str(decision)
            d = decision.as_dict()

            for sensitive in (
                user_id,
                str(self.exe_path),
                str(self.config_dir),
                str(self.session_path),
                "st_size",
                "st_mtime",
                "st_ino",
                "marker",
                "token",
            ):
                self.assertNotIn(sensitive, rep)
                self.assertNotIn(sensitive, st)
                self.assertNotIn(sensitive, str(d))

            self.assertEqual(set(d.keys()), {"confirmed", "code"})

    def test_no_persistence_or_sidecar_files_created(self):
        user_id = generate_user_id()
        files_before = set(Path(self.temp_dir.name).rglob("*"))
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            confirm_wts_feed_runtime_session(user_id)
            check_wts_feed_runtime_confirmation(user_id)
        files_after = set(Path(self.temp_dir.name).rglob("*"))
        self.assertEqual(files_before, files_after)

    def test_no_environment_mutation(self):
        user_id = generate_user_id()
        env = self._env_for(user_id)
        with patch.dict(os.environ, env, clear=False):
            before = dict(os.environ)
            confirm_wts_feed_runtime_session(user_id)
            check_wts_feed_runtime_confirmation(user_id)
            after = dict(os.environ)
        self.assertEqual(before, after)

    def test_no_network_or_subprocess_executed(self):
        user_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(user_id), clear=False):
            with patch("subprocess.run", side_effect=AssertionError("subprocess called")), \
                 patch("subprocess.Popen", side_effect=AssertionError("subprocess called")), \
                 patch("urllib.request.urlopen", side_effect=AssertionError("network called")):
                confirm_res = confirm_wts_feed_runtime_session(user_id)
                self.assertTrue(confirm_res.confirmed)
                check_res = check_wts_feed_runtime_confirmation(user_id)
                self.assertTrue(check_res.confirmed)


if __name__ == "__main__":
    unittest.main()
