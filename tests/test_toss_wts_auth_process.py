"""Mock boundary tests plus Linux-only synthetic descendants (no Toss/network).

Written for user execution. Existing Windows login mocks remain unchanged.
"""
from __future__ import annotations

import json
import errno
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.services import toss_wts_auth_guard as guard
from app.services import toss_wts_auth_process as process
from app.services import toss_wts_login as login


class ProcessBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Linux supervisor mocks also need the POSIX wait option on Windows.
        # Preserve the host's real value when present; remove a created
        # attribute again when this test ends, including assertion failures.
        wait_option = patch.object(process.os, "WNOHANG", getattr(process.os, "WNOHANG", 1), create=True)
        wait_option.start()
        self.addCleanup(wait_option.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"WEALTH_DATA_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        self.boundary = {"kind": process.BOUNDARY_KIND, "token": "synthetic-token", "boot_id": "synthetic-boot"}
        self.meta = {"attempt_id": "fixture-attempt", "owner": "alice", "status": "pending",
                     "started_at": "2020-01-01T00:00:00+09:00", "_pid": 123,
                     "_pid_start_time": "100", "_process_boundary": self.boundary}

    def marker(self):
        guard.write_active_op_marker("alice", "fixture-attempt", 123,
                                     self.meta["started_at"], process_boundary=self.boundary,
                                     process_start="100")

    def test_definite_popen_failure_releases_only_reservation_and_allows_retry(self):
        real_lock = guard.auth_operation_lock
        entered = False
        lock_entries = []
        observed = []
        @contextmanager
        def single_lock(username, **options):
            nonlocal entered
            self.assertFalse(entered, "reservation recovery must not re-acquire auth lock")
            entered = True
            lock_entries.append(username)
            try:
                with real_lock(username, **options):
                    yield
            finally:
                entered = False
        def spawn(_argv, **options):
            marker = guard._get_active_op_data("alice")
            self.assertEqual(marker["pid"], 0)
            self.assertTrue(guard._get_thread_lock("alice").locked())
            observed.append(marker)
            if len(observed) == 1:
                raise FileNotFoundError(errno.ENOENT, "SYNTHETIC_SECRET executable")
            return Mock(pid=123)
        guard.write_active_op_marker("bob", "bob-attempt", 456, self.meta["started_at"],
                                     process_boundary=self.boundary, process_start="200")
        bob_bytes = guard._active_op_path("bob").read_bytes()
        with patch.object(login, "_IS_LINUX", True), \
             patch.object(process, "boot_id", return_value="synthetic-boot"), \
             patch.object(guard, "get_pid_start_time", return_value="100"), \
             patch.object(guard, "auth_operation_lock", side_effect=single_lock), \
             patch.object(login, "_start_watcher"):
            with self.assertRaises(login.TossLoginError) as error:
                login.start_toss_login({"enabled": True, "executable": "synthetic"}, username="alice", reauthenticate=True, _popen=spawn)
            self.assertEqual(str(error.exception), "AUTH_LOGIN_SPAWN_FAILED")
            self.assertTrue(error.exception.__suppress_context__)
            self.assertFalse(guard.check_active_login_operation("alice"))
            self.assertFalse(guard._active_op_path("alice").exists())
            self.assertEqual(guard._active_op_path("bob").read_bytes(), bob_bytes)
            next_attempt = login.start_toss_login({"enabled": True, "executable": "synthetic"}, username="alice", reauthenticate=True, _popen=spawn)
        self.assertEqual(lock_entries, ["alice", "alice"])
        self.assertEqual(len(observed), 2)
        self.assertNotEqual(observed[0]["attempt_id"], next_attempt)
        self.assertEqual(guard._get_active_op_data("alice")["attempt_id"], next_attempt)
        self.assertTrue(guard.check_active_login_operation("alice"))

    def test_reservation_recovery_rejects_mismatch_started_and_corrupt_markers(self):
        alterations = (
            {"attempt_id": "other-attempt"}, {"owner": "bob"},
            {"process_boundary": {**self.boundary, "token": "other-token"}},
            {"process_boundary": {**self.boundary, "boot_id": "other-boot"}},
            {"process_boundary": {**self.boundary, "kind": "unknown-boundary"}},
            {"pid": 123, "pid_start_time": "100"}, {"pid": False},
            {"pid": 0, "pid_start_time": "unknown"}, {"type": "unknown"},
        )
        with guard.auth_operation_lock("alice"):
            # Any nested attempt to acquire this non-reentrant lock must fail.
            with patch.object(guard, "auth_operation_lock", side_effect=AssertionError("nested lock")):
                for alteration in alterations:
                    with self.subTest(alteration=alteration):
                        guard.write_active_op_marker("alice", "fixture-attempt", 0, self.meta["started_at"], process_boundary=self.boundary)
                        path = guard._active_op_path("alice")
                        data = json.loads(path.read_text(encoding="utf-8"))
                        data.update(alteration)
                        path.write_text(json.dumps(data), encoding="utf-8")
                        before = path.read_bytes()
                        self.assertFalse(guard._release_unspawned_reservation_locked("alice", "fixture-attempt", token=self.boundary["token"], boot_id=self.boundary["boot_id"]))
                        self.assertEqual(path.read_bytes(), before)
                for corrupt in ("{broken", "[]", "null"):
                    path.write_text(corrupt, encoding="utf-8")
                    self.assertFalse(guard._release_unspawned_reservation_locked("alice", "fixture-attempt", token=self.boundary["token"], boot_id=self.boundary["boot_id"]))
                    self.assertEqual(path.read_text(encoding="utf-8"), corrupt)
        self.assertTrue(guard.check_active_login_operation("alice"))

    def test_unlocked_reservation_recovery_is_refused(self):
        guard.write_active_op_marker("alice", "fixture-attempt", 0, self.meta["started_at"], process_boundary=self.boundary)
        self.assertFalse(guard._release_unspawned_reservation_locked("alice", "fixture-attempt", token=self.boundary["token"], boot_id=self.boundary["boot_id"]))
        self.assertTrue(guard.check_active_login_operation("alice"))

    def test_unknown_popen_failure_retains_guard_and_blocks_retry(self):
        spawn = Mock(side_effect=OSError(errno.EIO, "synthetic uncertain execution"))
        with patch.object(login, "_IS_LINUX", True), \
             patch.object(process, "boot_id", return_value="synthetic-boot"):
            with self.assertRaises(login.TossLoginError) as error:
                login.start_toss_login({"enabled": True, "executable": "synthetic"}, username="alice", reauthenticate=True, _popen=spawn)
            self.assertEqual(str(error.exception), "AUTH_LOGIN_SPAWN_FAILED")
            self.assertTrue(guard.check_active_login_operation("alice"))
            with self.assertRaises(login.TossLoginLockError):
                login.start_toss_login({"enabled": True, "executable": "synthetic"}, username="alice", reauthenticate=True, _popen=spawn)
        self.assertEqual(spawn.call_count, 1)

    def test_running_supervisor_setup_failure_never_uses_unspawned_recovery(self):
        proc = Mock(pid=123)
        with patch.object(login, "_IS_LINUX", True), \
             patch.object(process, "boot_id", return_value="synthetic-boot"), \
             patch.object(guard, "get_pid_start_time", return_value="100"), \
             patch.object(login, "_write_meta", side_effect=OSError(errno.ENOSPC, "synthetic setup failure")), \
             patch.object(login, "_rollback_spawn") as rollback, \
             patch.object(guard, "_release_unspawned_reservation_locked") as release:
            with self.assertRaises(login.TossLoginError) as error:
                login.start_toss_login({"enabled": True, "executable": "synthetic"}, username="alice", reauthenticate=True, _popen=Mock(return_value=proc))
        self.assertEqual(str(error.exception), "AUTH_LOGIN_SETUP_FAILED")
        release.assert_not_called()
        self.assertEqual(rollback.call_count, 1)
        self.assertEqual(rollback.call_args.kwargs["expected_start_time"], "100")
        self.assertEqual(guard._get_active_op_data("alice")["pid"], 123)
        self.assertTrue(guard.check_active_login_operation("alice"))

    def test_parent_exit_without_receipt_keeps_marker_and_skips_verification(self):
        self.marker()
        with patch.object(login, "_boundary_complete", return_value=False), \
             patch.object(login, "_is_process_reaped", return_value=True), \
             patch.object(login, "_verify_post_login") as verify, \
             patch.object(login, "_terminal_cleanup") as cleanup:
            result = login._check_and_finalize(self.meta, {})
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["error_code"], "AUTH_LOGIN_TERMINATION_PENDING")
        verify.assert_not_called()
        cleanup.assert_not_called()
        self.assertTrue(guard.check_active_login_operation("alice"))

    def test_verified_whole_tree_exit_then_active_valid_and_artifact_cleanup(self):
        for valid, expected in ((True, "success"), (False, "failed")):
            with self.subTest(valid=valid):
                self.marker()
                meta = self.meta.copy()
                login._write_meta("fixture-attempt", "alice", meta)
                qr = login._qr_path("fixture-attempt", "alice")
                ipc = login._confirmation_path("fixture-attempt", "alice")
                qr.write_bytes(b"synthetic")
                ipc.write_text("synthetic", encoding="utf-8")
                with patch.object(login, "_boundary_complete", return_value=True), \
                     patch.object(process, "boundary_complete", return_value=True), \
                     patch.object(login, "_verify_post_login", return_value=valid) as verify:
                    result = login._check_and_finalize(meta, {})
                self.assertEqual(result["status"], expected)
                verify.assert_called_once_with({}, "alice")
                self.assertFalse(qr.exists())
                self.assertFalse(ipc.exists())
                self.assertFalse(guard.check_active_login_operation("alice"))

    def test_restart_unknown_cleanup_keeps_marker_beyond_360_seconds(self):
        self.marker()
        with patch.object(guard, "pid_alive", return_value=False), \
             patch.object(login, "_is_process_reaped", return_value=None), \
             patch.object(login, "_boundary_complete", return_value=False):
            self.assertTrue(guard.check_active_login_operation("alice"))
            self.assertEqual(login._check_and_finalize(self.meta, {})["status"], "pending")
        self.assertTrue(guard._active_op_path("alice").exists())
        self.assertFalse(guard.check_active_login_operation("bob"))

    def test_corrupt_marker_is_busy_and_not_silently_deleted(self):
        self.marker()
        path = guard._active_op_path("alice")
        path.write_text("{broken", encoding="utf-8")
        self.assertTrue(guard.check_active_login_operation("alice"))
        self.assertFalse(guard.clear_active_op_marker("alice", "fixture-attempt"))
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_incomplete_cancel_and_timeout_block_relogin_and_extend_guard(self):
        self.marker()
        with patch.object(login, "_check_and_finalize", side_effect=lambda meta, *_: meta), \
             patch.object(login, "_terminate_attempt", return_value=False), \
             patch.object(login, "_terminal_cleanup") as cleanup:
            login._write_meta("fixture-attempt", "alice", self.meta)
            cancelled = login.cancel_login_attempt("fixture-attempt", requesting_username="alice", settings={"synthetic": True})
            timed = login._handle_timeout("fixture-attempt", "alice", self.meta.copy(), datetime.now(timezone.utc))
        self.assertEqual(cancelled["status"], "pending")
        self.assertEqual(timed["status"], "pending")
        cleanup.assert_not_called()
        self.assertTrue(guard.check_active_login_operation("alice"))
        spawn = Mock()
        with self.assertRaises(login.TossLoginLockError):
            login.start_toss_login({"enabled": True, "executable": "synthetic"}, username="alice", reauthenticate=True, _popen=spawn)
        spawn.assert_not_called()
        # Session extend uses exactly this same per-user durable guard.
        source = (Path(__file__).resolve().parents[1] / "app/services/toss_wts_session.py").read_text(encoding="utf-8")
        self.assertIn("check_active_login_operation(owner_username)", source)

    def test_receipt_identity_owner_nonce_boot_and_exit_all_required(self):
        proof = {**self.boundary, "owner": "alice", "attempt_id": "fixture-attempt",
                 "supervisor_pid": 123, "supervisor_start": "100", "cleanup_complete": True}
        def complete():
            return process.boundary_complete(Path(self.temp.name), "fixture-attempt", "alice", self.boundary, 123, "100")
        with patch.object(process, "private_receipt", return_value=proof), \
             patch.object(process, "boot_id", return_value="synthetic-boot"), \
             patch.object(process, "process_identity", side_effect=FileNotFoundError()):
            self.assertTrue(complete())
            for key, value in (("owner", "bob"), ("attempt_id", "other-attempt"),
                               ("token", "other-token"), ("boot_id", "other-boot"),
                               ("supervisor_pid", 456), ("supervisor_start", "new"),
                               ("cleanup_complete", False)):
                original = proof[key]
                proof[key] = value
                self.assertFalse(complete(), key)
                proof[key] = original
        with patch.object(process, "private_receipt", return_value=proof), \
             patch.object(process, "boot_id", return_value="synthetic-boot"), \
             patch.object(process, "process_identity", return_value=(1, "100")):
            self.assertFalse(complete())  # Supervisor still alive.
        with patch.object(process, "private_receipt", side_effect=PermissionError()):
            self.assertFalse(complete())

    def test_termination_requests_only_supervisor_and_missing_proof_stays_pending(self):
        with patch.object(login, "_boundary_complete", return_value=False), \
             patch.object(process, "signal_supervisor", return_value=True) as request, \
             patch.object(login.time, "monotonic", side_effect=[0, 16]), \
             patch.object(login.os, "kill") as raw_kill:
            self.assertFalse(login._terminate_attempt(self.meta))
        request.assert_called_once_with(123, "100", "synthetic-boot")
        raw_kill.assert_not_called()

    def test_other_attempt_and_owner_do_not_release_marker(self):
        self.marker()
        with patch.object(process, "boundary_complete", return_value=True):
            self.assertFalse(guard.clear_active_op_marker("alice", "other-attempt"))
        self.assertTrue(guard.check_active_login_operation("alice"))
        self.assertFalse(guard.check_active_login_operation("bob"))

    def test_relogin_during_cancel_wait_is_blocked(self):
        self.marker()
        login._write_meta("fixture-attempt", "alice", self.meta)
        waiting, release = threading.Event(), threading.Event()
        results = []
        def uncertain(_meta):
            waiting.set()
            if not release.wait(timeout=3):
                raise RuntimeError("synthetic synchronization timeout")
            return False
        def cancel():
            results.append(login.cancel_login_attempt("fixture-attempt", requesting_username="alice", settings={"synthetic": True}))
        with patch.object(login, "_check_and_finalize", side_effect=lambda meta, *_: meta), \
             patch.object(login, "_terminate_attempt", side_effect=uncertain):
            worker = threading.Thread(target=cancel)
            worker.start()
            try:
                self.assertTrue(waiting.wait(timeout=3))
                spawn = Mock()
                with self.assertRaises(login.TossLoginLockError):
                    login.start_toss_login({"enabled": True, "executable": "synthetic"}, username="alice", reauthenticate=True, _popen=spawn)
                spawn.assert_not_called()
            finally:
                release.set()
                worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0]["status"], "pending")
        self.assertTrue(guard.check_active_login_operation("alice"))

    def test_pid_reuse_never_signals_supervisor(self):
        with patch.object(process, "boot_id", return_value="synthetic-boot"), \
             patch.object(process, "process_identity", return_value=(1, "reused")), \
             patch.object(process.os, "pidfd_open", create=True) as fd:
            self.assertFalse(process.signal_supervisor(123, "100", "synthetic-boot"))
        fd.assert_not_called()

    def test_owned_child_check_excludes_other_users_and_attempts(self):
        with patch.object(process.os, "getpid", return_value=10), \
             patch.object(process, "process_identity", return_value=(999, "start")), \
             patch.object(process.os, "pidfd_open", create=True) as fd:
            process.signal_owned_child(123, signal.SIGTERM)
        fd.assert_not_called()

    def test_pinned_child_identity_rechecked_after_pidfd_open(self):
        with patch.object(process.os, "getpid", return_value=10), \
             patch.object(process, "process_identity", side_effect=[(10, "old"), (10, "new")]), \
             patch.object(process.os, "pidfd_open", return_value=50, create=True), \
             patch.object(process.os, "close") as close, \
             patch.object(process.signal, "pidfd_send_signal", create=True) as send:
            process.signal_owned_child(123, signal.SIGTERM)
        send.assert_not_called()
        close.assert_called_once_with(50)

    def test_parent_then_adopted_child_reaped_before_receipt(self):
        # CLI exit -> one live adopted child -> child exit -> kernel ECHILD.
        cli = Mock(pid=123)
        path = Path(self.temp.name) / "receipt.json"
        with patch.object(process, "enable_subreaper"), \
             patch.object(process.signal, "signal"), \
             patch.object(process.subprocess, "Popen", return_value=cli), \
             patch.object(process.os, "waitpid", side_effect=[(123, 0), (0, 0), (456, 0), ChildProcessError()]), \
             patch.object(process, "direct_children", return_value=[456]), \
             patch.object(process, "signal_owned_child") as stop, \
             patch.object(process, "atomic_private_json") as receipt, \
             patch.object(process.time, "sleep"):
            self.assertEqual(process.supervise(["synthetic-cli"], {"owner": "alice"}, path), 0)
        stop.assert_called_once_with(456, signal.SIGTERM)
        self.assertTrue(receipt.call_args.args[1]["cleanup_complete"])
        self.assertEqual(receipt.call_args.args[1]["cli_exit_code"], 0)

    def test_failed_child_signal_never_emits_completion_receipt(self):
        cli = Mock(pid=123)
        with patch.object(process, "enable_subreaper"), \
             patch.object(process.signal, "signal"), \
             patch.object(process.subprocess, "Popen", return_value=cli), \
             patch.object(process.os, "waitpid", side_effect=[(123, 0), (0, 0), (0, 0)]), \
             patch.object(process, "direct_children", return_value=[456]), \
             patch.object(process, "signal_owned_child", side_effect=PermissionError()), \
             patch.object(process, "atomic_private_json") as receipt, \
             patch.object(process.time, "sleep", side_effect=[None, RuntimeError("stop synthetic loop")]):
            with self.assertRaisesRegex(RuntimeError, "stop synthetic loop"):
                process.supervise(["synthetic-cli"], {}, Path(self.temp.name) / "receipt.json")
        receipt.assert_not_called()

    def test_capability_denied_never_starts_cli(self):
        with patch.object(process, "enable_subreaper", side_effect=PermissionError()), \
             patch.object(process.signal, "signal"), \
             patch.object(process.subprocess, "Popen") as spawn, \
             patch.object(process.os, "waitpid", side_effect=ChildProcessError()), \
             patch.object(process, "atomic_private_json") as receipt:
            self.assertEqual(process.supervise(["synthetic-cli"], {}, Path(self.temp.name) / "receipt.json"), 0)
        spawn.assert_not_called()
        self.assertEqual(receipt.call_args.args[1]["cli_exit_code"], -1)

    def test_rollback_only_requests_owned_supervisor_and_keeps_reservation(self):
        self.marker()
        proc = Mock(pid=123)
        with patch.object(process, "signal_supervisor", return_value=False) as request, \
             patch.object(guard, "get_pid_start_time", return_value="100"), \
             patch.object(login, "_start_watcher") as watcher, \
             patch.object(guard, "clear_active_op_marker") as clear:
            login._rollback_spawn("fixture-attempt", "alice", proc, process_boundary=self.boundary,
                                  expected_start_time="100")
        watcher.assert_called_once_with("fixture-attempt", proc)
        request.assert_called_once_with(123, "100", "synthetic-boot")
        clear.assert_not_called()
        self.assertTrue(guard.check_active_login_operation("alice"))

    def test_linux_spawn_reserves_guard_before_launch_and_keeps_cli_argv(self):
        observed = []
        def spawn(argv, **options):
            marker = guard._get_active_op_data("alice")
            self.assertEqual(marker["pid"], 0)
            self.assertEqual(marker["owner"], "alice")
            self.assertEqual(marker["process_boundary"]["kind"], process.BOUNDARY_KIND)
            self.assertEqual(argv[0], sys.executable)
            self.assertEqual(Path(argv[1]).name, "toss_wts_auth_process.py")
            self.assertEqual(argv[2:6], ["synthetic-cli", "--config-dir", str(login._user_config_dir("alice")), "auth"])
            self.assertEqual(argv[6:9], ["login", "--headless", "--link"])
            self.assertEqual(argv[9], "--qr-output")
            self.assertFalse(options["shell"])
            for key in ("stdin", "stdout", "stderr"):
                self.assertEqual(options[key], subprocess.DEVNULL)
            context = json.loads(options["env"]["TOSSCTL_AUTH_PROCESS_CONTEXT"])
            self.assertEqual(context["token"], marker["process_boundary"]["token"])
            observed.append(marker)
            return Mock(pid=123)
        with patch.object(login, "_IS_LINUX", True), \
             patch.object(process, "boot_id", return_value="synthetic-boot"), \
             patch.object(guard, "get_pid_start_time", return_value="100"), \
             patch.object(login, "_start_watcher"):
            attempt = login.start_toss_login({"enabled": True, "executable": "synthetic-cli"}, username="alice", reauthenticate=True, _popen=spawn)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["attempt_id"], attempt)
        stored = login._read_meta(attempt, "alice")
        self.assertEqual(stored["_pid_start_time"], "100")
        self.assertNotIn("_process_boundary", login._safe_public(stored))


@unittest.skipUnless(sys.platform == "linux", "Linux kernel subreaper/pidfd integration")
class LinuxSyntheticProcessTests(unittest.TestCase):
    def test_detached_descendants_are_reaped_after_cli_exit(self):
        self.run_synthetic(cancel=False)

    def test_cancel_reaps_detached_descendants(self):
        self.run_synthetic(cancel=True)

    def run_synthetic(self, *, cancel):
        """No network or browser: detached Python descendants model Chromium."""
        with TemporaryDirectory() as temp:
            root = Path(temp)
            pids = root / "synthetic-pids.json"
            script = root / "synthetic-cli.py"
            # Descendant lifespan is deliberate; supervisor must terminate it.
            descendant = (
                "import os,json,subprocess,sys,time; "
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True); "
                f"open({str(pids)!r},'w').write(json.dumps([os.getpid(),child.pid])); "
                "time.sleep(60)"
            )
            script.write_text(
                "import subprocess,sys,time\nfrom pathlib import Path\n"
                f"subprocess.Popen([sys.executable,'-c',{descendant!r}],start_new_session=True)\n"
                "deadline=time.monotonic()+10\n"
                f"while not Path({str(pids)!r}).exists():\n"
                "    if time.monotonic()>deadline: raise RuntimeError('synthetic readiness')\n"
                "    time.sleep(0.01)\n"
                + ("time.sleep(60)\n" if cancel else ""), encoding="utf-8"
            )
            boundary = {"kind": process.BOUNDARY_KIND, "token": "native-fixture", "boot_id": process.boot_id()}
            receipt = process.receipt_path(root, "native-attempt")
            env = {**os.environ, "TOSSCTL_AUTH_PROCESS_CONTEXT": json.dumps({**boundary, "attempt_id": "native-attempt", "owner": "synthetic"}),
                   "TOSSCTL_AUTH_PROCESS_RECEIPT": str(receipt)}
            proc = subprocess.Popen([sys.executable, str(Path(process.__file__)), sys.executable, str(script)],
                                    env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            start = guard.get_pid_start_time(proc.pid)
            try:
                if cancel:
                    ready_deadline = time.monotonic() + 10
                    while not pids.exists() and proc.poll() is None:
                        if time.monotonic() >= ready_deadline:
                            self.fail("synthetic descendants did not become ready")
                        time.sleep(0.01)
                    self.assertTrue(pids.exists())
                    self.assertTrue(process.signal_supervisor(proc.pid, start, boundary["boot_id"]))
                self.assertEqual(proc.wait(timeout=15), 0)
                self.assertTrue(process.boundary_complete(root, "native-attempt", "synthetic", boundary, proc.pid, start))
                for pid in json.loads(pids.read_text(encoding="utf-8")):
                    with self.assertRaises(FileNotFoundError):
                        process.process_identity(pid)
            finally:
                if proc.poll() is None:
                    process.signal_supervisor(proc.pid, start, boundary["boot_id"])
                    proc.wait(timeout=15)


if __name__ == "__main__":
    unittest.main()
