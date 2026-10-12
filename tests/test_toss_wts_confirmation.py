"""Synthetic-only QR confirmation contracts, written for operator execution.

No browser, subprocess, Toss authentication or real user storage is used.
Complete descendant termination remains an explicitly unresolved runtime risk.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import os
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from app.services import toss_wts_login as login


ROOT = Path(__file__).resolve().parents[1]


def qr_data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def helper_module():
    spec = importlib.util.spec_from_file_location(
        "confirmation_helper_fixture", ROOT / "vendor/tossctl-auth-helper/tossctl_auth_helper/cli.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"WEALTH_DATA_DIR": self.temp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.helper = helper_module()

    def seed(self, owner="alice", attempt="synthetic-attempt", letter="A"):
        meta = {"attempt_id": attempt, "owner": owner, "status": "pending", "_pid": 123}
        login._write_meta(attempt, owner, meta)
        png = login._qr_path(attempt, owner)
        ipc = login._confirmation_path(attempt, owner)
        with patch.dict(os.environ, {"TOSSCTL_AUTH_CONFIRMATION_FILE": str(ipc), "TOSSCTL_AUTH_HELPER_QUIET": "1"}):
            state = self.helper.QRState(png)
            state.handle_api_payload({"qrCode": qr_data_uri(b"synthetic QR"), "answerLetter": letter})
        return meta, state, png, ipc

    def pending_status(self, attempt, owner):
        with patch.object(login, "_check_and_finalize", side_effect=lambda meta, *_: meta):
            return login.get_login_attempt(attempt, requesting_username=owner, settings={"synthetic": True})

    def test_owner_scoped_letters_and_owner_denial(self):
        _, _, _, alice = self.seed(letter="A")
        _, _, _, bob = self.seed(owner="bob", letter="B")
        self.assertNotEqual(alice, bob)
        self.assertEqual(self.pending_status("synthetic-attempt", "alice")["answer_letter"], "A")
        self.assertEqual(self.pending_status("synthetic-attempt", "bob")["answer_letter"], "B")
        with self.assertRaises(login.TossLoginNotFoundError):
            self.pending_status("synthetic-attempt", "charlie")
        with patch.object(login, "_read_meta", return_value={"owner": "alice", "status": "pending"}), \
             patch.object(login, "_read_confirmation") as read:
            with self.assertRaises(login.TossLoginNotFoundError):
                self.pending_status("synthetic-attempt", "bob")
            read.assert_not_called()

    def test_qr_letter_rotation_and_revision_are_bound(self):
        _, state, png, ipc = self.seed()
        first = self.pending_status("synthetic-attempt", "alice")
        state.handle_api_payload({"qrCode": qr_data_uri(b"second QR"), "answerLetter": "B"})
        second = self.pending_status("synthetic-attempt", "alice")
        self.assertEqual(second["answer_letter"], "B")
        self.assertNotEqual(first["qr_revision"], second["qr_revision"])
        self.assertIsNone(login.get_login_qr("synthetic-attempt", requesting_username="alice", expected_revision=first["qr_revision"]))
        self.assertEqual(login.get_login_qr("synthetic-attempt", requesting_username="alice", expected_revision=second["qr_revision"]), b"second QR")
        state.handle_api_payload({"qrCode": qr_data_uri(b"third QR")})
        self.assertFalse(ipc.exists())
        self.assertNotIn("answer_letter", self.pending_status("synthetic-attempt", "alice"))
        state.handle_api_payload({"answerLetter": "C"})
        self.assertEqual(self.pending_status("synthetic-attempt", "alice")["answer_letter"], "C")
        if os.name == "posix":
            self.assertEqual(ipc.stat().st_mode & 0o777, 0o600)
            self.assertEqual(ipc.parent.stat().st_mode & 0o777, 0o700)

    def test_invalid_mismatched_and_failed_qr_never_publish_old_letter(self):
        _, state, png, ipc = self.seed()
        state.handle_api_payload({"answerLetter": "<script>"})
        self.assertFalse(ipc.exists())
        state.handle_api_payload({"answerLetter": "B"})
        png.write_bytes(b"different QR")
        self.assertEqual(login._read_confirmation("synthetic-attempt", "alice"), {})
        with patch.object(self.helper, "save_qr_png", return_value=False) as save:
            failed_qr = qr_data_uri(b"failed QR")
            state.handle_api_payload({"qrCode": failed_qr, "answerLetter": "C"})
            save.assert_called_once_with(failed_qr, png)
        state.handle_api_payload({"answerLetter": "C"})
        self.assertFalse(ipc.exists())

    def test_terminal_cleanup_all_statuses_and_no_public_letter(self):
        for status in ("success", "failed", "cancelled", "timeout"):
            with self.subTest(status=status):
                meta, _, png, ipc = self.seed()
                meta.update(status=status, answer_letter="A", qr_sha256="private")
                tmp = ipc.with_name(ipc.name + ".orphan.tmp")
                tmp.write_text("private", encoding="utf-8")
                with patch("app.services.toss_wts_auth_guard.clear_active_op_marker"):
                    login._terminal_cleanup("synthetic-attempt", "alice", meta)
                self.assertFalse(png.exists())
                self.assertFalse(ipc.exists())
                self.assertFalse(tmp.exists())
                self.assertNotIn("answer_letter", login._safe_public(meta))
                self.assertNotIn("answer_letter", self.pending_status("synthetic-attempt", "alice"))

    def test_confirmation_never_printed_even_without_quiet(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), patch.dict(os.environ, {"TOSSCTL_AUTH_HELPER_QUIET": "0"}):
            _, state, _, _ = self.seed(letter="SECRETZ")
            state.handle_api_payload({"answerLetter": "SECRETY"})
        self.assertNotIn("SECRETZ", stdout.getvalue() + stderr.getvalue())
        self.assertNotIn("SECRETY", stdout.getvalue() + stderr.getvalue())

    def test_signal_error_does_not_confirm_exit_or_release_marker(self):
        meta, _, _, ipc = self.seed()
        with patch.object(login, "_IS_WINDOWS", False), \
             patch.object(login, "_is_process_reaped", return_value=False), \
             patch("app.services.toss_wts_auth_guard.pid_alive", return_value=True), \
             patch.object(login.os, "kill", side_effect=PermissionError("synthetic")), \
             patch.object(login, "_write_meta"), \
             patch.object(login, "_terminal_cleanup") as cleanup:
            result = login._handle_timeout("synthetic-attempt", "alice", meta, datetime.now(timezone.utc))
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["error_code"], "AUTH_LOGIN_TERMINATION_PENDING")
        cleanup.assert_not_called()
        self.assertTrue(ipc.exists())

    def test_cancel_uncertainty_retains_attempt_and_private_artifact(self):
        meta, _, _, ipc = self.seed()
        with patch.object(login, "_check_and_finalize", return_value=meta), \
             patch.object(login, "_terminate_and_reap", return_value=False), \
             patch.object(login, "_terminal_cleanup") as cleanup:
            result = login.cancel_login_attempt("synthetic-attempt", requesting_username="alice", settings={"synthetic": True})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["error_code"], "AUTH_LOGIN_CANCEL_TERMINATION_PENDING")
        self.assertNotIn("answer_letter", result)
        cleanup.assert_not_called()
        self.assertTrue(ipc.exists())

    def test_spawn_env_unique_private_path_and_cli_unchanged(self):
        spawn = Mock(return_value=Mock(pid=123))
        with patch("app.services.toss_wts_auth_guard.auth_operation_lock", side_effect=lambda *a, **k: nullcontext()), \
             patch("app.services.toss_wts_auth_guard.check_active_login_operation", return_value=False), \
             patch("app.services.toss_wts_auth_guard.write_active_op_marker"), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time", return_value="synthetic-start"), \
             patch.object(login, "_start_watcher"):
            a = login.start_toss_login({"enabled": True, "executable": "synthetic-tossctl"}, username="alice", reauthenticate=True, _popen=spawn)
            b = login.start_toss_login({"enabled": True, "executable": "synthetic-tossctl"}, username="bob", reauthenticate=True, _popen=spawn)
        calls = spawn.call_args_list
        first, second = calls[0].kwargs["env"], calls[1].kwargs["env"]
        self.assertNotEqual(first["TOSSCTL_AUTH_CONFIRMATION_FILE"], second["TOSSCTL_AUTH_CONFIRMATION_FILE"])
        self.assertEqual(first["TOSSCTL_AUTH_CONFIRMATION_FILE"], str(login._confirmation_path(a, "alice")))
        self.assertEqual(second["TOSSCTL_AUTH_CONFIRMATION_FILE"], str(login._confirmation_path(b, "bob")))
        self.assertEqual(first["TOSSCTL_AUTH_HELPER_QUIET"], "1")
        self.assertEqual(calls[0].args[0], ["synthetic-tossctl", "--config-dir", str(login._user_config_dir("alice")), "auth", "login", "--headless", "--link", "--qr-output", str(login._qr_path(a, "alice"))])
        for call in calls:
            self.assertFalse(call.kwargs["shell"])
            for name in ("stdin", "stdout", "stderr"):
                self.assertEqual(call.kwargs[name], login.subprocess.DEVNULL)

    def test_pid_identity_mismatch_never_signals_reused_pid(self):
        with patch.object(login, "_is_process_reaped", return_value=None), \
             patch("app.services.toss_wts_auth_guard.pid_alive", return_value=False) as alive, \
             patch.object(login.os, "kill") as kill:
            self.assertTrue(login._terminate_and_reap("synthetic", 123, "original-start"))
        alive.assert_called_once_with(123, "original-start")
        kill.assert_not_called()

    def test_ui_letter_uses_text_content_and_matching_image_not_url(self):
        source = (ROOT / "app/static/wealth-settings.js").read_text(encoding="utf-8")
        self.assertIn("box.textContent = value", source)
        self.assertIn("qrImg.onload =", source)
        self.assertIn("ticket === _tossLoginQrTicket", source)
        self.assertIn("encodeURIComponent(result.qr_revision)", source)
        self.assertNotIn("encodeURIComponent(result.answer_letter)", source)
        api = (ROOT / "app/main.py").read_text(encoding="utf-8")
        block = api.split("async def toss_wts_login_status_api", 1)[1].split('@app.get(', 1)[0]
        self.assertIn('"Cache-Control": "no-store"', block)
        self.assertIn("requesting_username=username", block)


if __name__ == "__main__":
    unittest.main()
