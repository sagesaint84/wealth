"""Auth image contracts only: all browser/auth behavior below uses mocks.

Written for later user execution; no real browser, Docker, or Toss request.
"""
from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import sys
from types import ModuleType
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "vendor/tossctl-auth-helper/tossctl_auth_helper/cli.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DockerAuthRuntimeContractTests(unittest.TestCase):
    def test_bookworm_isolated_python_pins_and_full_chromium_install(self):
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.11-slim-bookworm", docker)
        self.assertIn("python -m venv /opt/toss-auth/venv", docker)
        self.assertIn("--only-binary=:all: -r /opt/toss-auth/requirements.txt", docker)
        self.assertIn("playwright install --with-deps --no-shell chromium", docker)
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH=/opt/toss-auth/ms-playwright", docker)
        pins = (ROOT / "ops/toss-auth/requirements.txt").read_text(encoding="utf-8")
        self.assertEqual([line for line in pins.splitlines() if line and not line.startswith("#")], [
            "playwright==1.58.0", "pyee==13.0.0", "greenlet==3.3.1", "typing_extensions==4.15.0",
        ])
        app_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("playwright", app_requirements.lower())

    def test_helper_python_directory_channel_and_mount_are_separate(self):
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        for contract in (
            "TOSSCTL_AUTH_HELPER_PYTHON=/opt/toss-auth/venv/bin/python",
            "TOSSCTL_AUTH_HELPER_DIR=/opt/toss-auth/helper",
            "TOSSCTL_AUTH_HELPER_BROWSER_CHANNEL=chromium",
            "TOSSCTL_AUTH_HELPER_QUIET=1",
            "COPY vendor/tossctl-auth-helper/ /opt/toss-auth/helper/",
        ):
            self.assertIn(contract, docker)
        compose = (ROOT / "docker-compose.ghcr.yml").read_text(encoding="utf-8")
        self.assertIn("./toss-wts/bin/tossctl:/opt/toss-wts/tossctl:ro", compose)
        for name in ("__init__.py", "__main__.py", "cli.py"):
            self.assertTrue((HELPER.parent / name).is_file())
        self.assertIn("from tossctl_auth_helper.cli import main", (HELPER.parent / "__main__.py").read_text(encoding="utf-8"))

    def test_multiplatform_build_and_offline_fail_closed_smoke(self):
        workflow = (ROOT / ".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
        self.assertIn("platforms: linux/amd64,linux/arm64", workflow)
        self.assertIn("docker/setup-qemu-action@", workflow)
        self.assertIn("docker/setup-buildx-action@", workflow)
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertNotIn("--platform=linux/amd64", docker)
        self.assertIn("RUN --network=none /opt/toss-auth/venv/bin/python /opt/toss-auth/browser_smoke.py", docker)
        self.assertIn("Copyright (c) 2026 JungHoon Ghae and contributors", (HELPER.parents[1] / "LICENSE").read_text(encoding="utf-8"))
        provenance = (HELPER.parents[1] / "WEALTH-PATCHES.md").read_text(encoding="utf-8")
        self.assertIn("152d6a5242b9e05ea975991df68a93c1d040bec7", provenance)


class HelperChannelAndPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.helper = load_module(HELPER, "wealth_vendored_auth_helper")

    def test_default_chrome_and_image_chromium_use_same_options(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.helper.browser_launch_options(headless=False), {"headless": False, "channel": "chrome"})
        with patch.dict(os.environ, {"TOSSCTL_AUTH_HELPER_BROWSER_CHANNEL": "chromium"}, clear=True):
            self.assertEqual(self.helper.browser_launch_options(headless=True), {"headless": True, "channel": "chromium"})

    def test_persistent_cookie_requirement_is_not_relaxed(self):
        with patch.object(self.helper.time, "time", return_value=1000):
            for expiry in (-1, 1001):
                self.assertFalse(self.helper.has_persistent_session_cookie({"cookies": [{"name": "SESSION", "expires": expiry}]}))
            self.assertTrue(self.helper.has_persistent_session_cookie({"cookies": [{"name": "SESSION", "expires": 1000 + self.helper.PERSISTENT_SESSION_MIN_TTL_SECONDS}]}))
        self.assertEqual(self.helper.build_parser().parse_args(["login", "--storage-state", "synthetic.json", "--headless"]).timeout_seconds, 300)

    def test_image_quiet_mode_never_emits_raw_auth_diagnostics(self):
        sentinel = "SYNTHETIC_QR_SESSION_XSRF_SECRET"
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"TOSSCTL_AUTH_HELPER_QUIET": "1"}), redirect_stdout(stdout), redirect_stderr(stderr):
            self.helper.log("QR URL: https://invalid.example/" + sentinel)
            self.helper.emit({"status": "error", "message": sentinel})
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn(sentinel, stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["status"], "error")

    def test_success_protocol_retains_go_cli_fields_without_cookie_contents(self):
        payload = {"status": "ok", "storage_state_path": "synthetic-state.json", "cookie_count": 6, "origin_count": 1, "user_agent": "synthetic-UA"}
        stdout = io.StringIO()
        with patch.dict(os.environ, {"TOSSCTL_AUTH_HELPER_QUIET": "1"}), redirect_stdout(stdout):
            self.helper.emit(payload)
        self.assertEqual(json.loads(stdout.getvalue()), payload)


class OfflineBrowserSmokeTests(unittest.TestCase):
    def test_launch_close_and_failure_are_mocked_without_navigation(self):
        smoke = load_module(ROOT / "ops/toss-auth/browser_smoke.py", "wealth_auth_smoke")
        playwright = Mock()
        fake_api = ModuleType("playwright.sync_api")
        manager = MagicMock(); manager.__enter__.return_value = playwright
        fake_api.sync_playwright = Mock(return_value=manager)
        fake_package = ModuleType("playwright"); fake_package.__path__ = []
        helper_package = ModuleType("tossctl_auth_helper"); helper_package.__path__ = []
        fake_cli = Mock(); fake_cli.browser_launch_options.return_value = {"channel": "chromium", "headless": True}
        saved_path = list(sys.path)
        try:
            with patch.dict(os.environ, {"TOSSCTL_AUTH_HELPER_DIR": str(HELPER.parents[1])}), \
                 patch.dict(sys.modules, {"playwright": fake_package, "playwright.sync_api": fake_api, "tossctl_auth_helper": helper_package, "tossctl_auth_helper.cli": fake_cli}), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(smoke.main(), 0)
                playwright.chromium.launch.assert_called_once_with(channel="chromium", headless=True)
                playwright.chromium.launch.return_value.close.assert_called_once()
                playwright.chromium.launch.return_value.new_page.assert_not_called()
                playwright.chromium.launch.side_effect = RuntimeError("SYNTHETIC_SECRET")
                error = io.StringIO()
                with redirect_stderr(error):
                    self.assertEqual(smoke.main(), 1)
                self.assertIn("RuntimeError", error.getvalue())
                self.assertNotIn("SYNTHETIC_SECRET", error.getvalue())
        finally:
            sys.path[:] = saved_path


class ExistingWealthAuthBoundariesTests(unittest.TestCase):
    def test_per_user_locks_remain_independent(self):
        from app.services import toss_wts_auth_guard as guard
        with TemporaryDirectory() as temp, patch.dict(os.environ, {"WEALTH_DATA_DIR": temp}):
            self.assertNotEqual(guard._lock_path("alice"), guard._lock_path("bob"))
            self.assertIs(guard._get_thread_lock("alice"), guard._get_thread_lock("alice"))
            self.assertIsNot(guard._get_thread_lock("alice"), guard._get_thread_lock("bob"))

    def test_login_process_argv_and_private_streams_remain_canonical(self):
        source = (ROOT / "app/services/toss_wts_login.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        start = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "start_toss_login")
        argv = next(n.value for n in ast.walk(start) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "argv" for t in n.targets))
        literals = [n.value for n in argv.elts if isinstance(n, ast.Constant)]
        self.assertEqual(literals, ["--config-dir", "auth", "login", "--headless", "--link"])
        spawn = next(n for n in ast.walk(start) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_popen")
        keywords = {n.arg: ast.unparse(n.value) for n in spawn.keywords}
        self.assertEqual(keywords["shell"], "False")
        for key in ("stdin", "stdout", "stderr"):
            self.assertEqual(keywords[key], "subprocess.DEVNULL")
        self.assertIn('_AUTH_LOGIN_QR_FLAG: str = "--qr-output"', source)

    def test_user_config_session_paths_and_active_valid_are_preserved(self):
        from app.services import toss_wts_login as login
        with TemporaryDirectory() as temp, patch.dict(os.environ, {"WEALTH_DATA_DIR": temp}):
            alice, bob = login._user_config_dir("alice"), login._user_config_dir("bob")
            self.assertEqual(alice, Path(temp) / "toss-wts/users/alice/config")
            self.assertEqual(bob, Path(temp) / "toss-wts/users/bob/config")
            self.assertNotEqual(alice / "session.json", bob / "session.json")
            for active, valid in ((False, False), (True, False), (False, True), (True, True)):
                with patch("app.services.toss_wts_session.get_toss_session_status", return_value={"active": active, "valid": valid}) as status:
                    self.assertEqual(login._verify_post_login({}, "alice"), active and valid)
                    status.assert_called_once_with(username="alice", settings={})

    def test_public_failed_attempt_does_not_expose_raw_streams_or_storage_state(self):
        from app.services import toss_wts_login as login
        sentinel = "SYNTHETIC_QR_COOKIE_STATE_SECRET"
        result = login._safe_public({"attempt_id": "fake", "owner": "alice", "status": login.STATUS_FAILED, "error_code": "AUTH_LOGIN_VERIFY_FAILED", "stdout": sentinel, "stderr": sentinel, "storage_state": sentinel, "qr_url": sentinel, "_pid": 123})
        self.assertNotIn(sentinel, json.dumps(result))
        self.assertEqual(result["error_code"], "AUTH_LOGIN_VERIFY_FAILED")

    def test_exit_zero_without_verified_session_is_failed_and_cleaned_up(self):
        from datetime import datetime, timezone
        from app.services import toss_wts_login as login
        meta = {"attempt_id": "synthetic", "owner": "alice", "status": login.STATUS_PENDING, "_pid": 123, "error_code": None}
        with patch.dict(login._watcher_registry, {"synthetic": {"reaped": True, "exit_code": 0}}), \
             patch.object(login, "_verify_post_login", return_value=False), \
             patch.object(login, "_terminal_cleanup") as cleanup:
            result = login._check_and_finalize(meta, {}, now_provider=lambda: datetime(2026, 10, 12, tzinfo=timezone.utc))
        self.assertEqual(result["status"], login.STATUS_FAILED)
        self.assertEqual(result["error_code"], "AUTH_LOGIN_VERIFY_FAILED")
        cleanup.assert_called_once_with("synthetic", "alice", meta)

    def test_timeout_cannot_release_marker_until_exit_confirmed(self):
        from datetime import datetime, timezone
        from app.services import toss_wts_login as login
        meta = {"attempt_id": "synthetic", "owner": "alice", "status": login.STATUS_PENDING, "_pid": 123}
        with patch.object(login, "_terminate_and_reap", return_value=False), \
             patch.object(login, "_write_meta"), \
             patch.object(login, "_terminal_cleanup") as cleanup:
            result = login._handle_timeout("synthetic", "alice", meta, datetime(2026, 10, 12, tzinfo=timezone.utc))
        self.assertEqual(result["status"], login.STATUS_PENDING)
        self.assertEqual(result["error_code"], "AUTH_LOGIN_TERMINATION_PENDING")
        cleanup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
