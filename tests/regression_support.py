from __future__ import annotations

import importlib
import os
import socket
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from app.services import ledger, portfolio, settings, user_manager, user_openapi
from app.services.kb_openapi import KBOpenAPI
from app.services.kis_openapi import KISOpenAPI

# The package-level guard is intentionally also installed here so tests that
# import this helper directly (outside package discovery) get the same policy.
os.environ.setdefault("WEALTH_ENV", "test")
# Explicit test-only signing secret — mirrors tests/__init__.py.
os.environ.setdefault(
    "WEALTH_TEST_SIGNING_SECRET",
    "wealth-test-suite-signing-secret-not-for-production",
)

_original_socket_connect = socket.socket.connect
_original_socket_connect_ex = socket.socket.connect_ex


def _test_loopback(address: object) -> bool:
    return isinstance(address, tuple) and bool(address) and str(address[0]).strip().lower().strip("[]") in {"127.0.0.1", "localhost", "::1"}


def _blocked_external_connect(sock, address):
    if not _test_loopback(address):
        raise AssertionError(f"External network is blocked in tests: {address!r}")
    return _original_socket_connect(sock, address)


def _blocked_external_connect_ex(sock, address):
    if not _test_loopback(address):
        raise AssertionError(f"External network is blocked in tests: {address!r}")
    return _original_socket_connect_ex(sock, address)


if socket.socket.connect is not _blocked_external_connect:
    socket.socket.connect = _blocked_external_connect
    socket.socket.connect_ex = _blocked_external_connect_ex


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def import_main_without_loading_real_env():
    """Import app.main while making its .env loader see no production .env file."""
    if "app.main" in sys.modules:
        return sys.modules["app.main"]

    original_exists = Path.exists

    def safe_exists(path: Path) -> bool:
        if path == PROJECT_ROOT / ".env":
            return False
        return original_exists(path)

    with patch.object(Path, "exists", safe_exists):
        module = importlib.import_module("app.main")
    return module


def authenticated_request(username: str = "fixture_user") -> Request:
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/fixture",
            "raw_path": b"/fixture",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )
    request.state.username = username
    request.state.role = "user"
    return request


def empty_portfolio(**overrides):
    data = deepcopy(portfolio.EMPTY_PORTFOLIO)
    data.update(overrides)
    data["settings"] = deepcopy(overrides.get("settings", data["settings"]))
    data["settings"].setdefault("fx_rates", {"KRW": 1.0})
    data["settings"].setdefault("fx_info", {})
    data["settings"].setdefault("daily_snapshot", {})
    data["settings"].setdefault("cash_balances", {})
    return data


class IsolatedDataTestCase(unittest.TestCase):
    """Run service persistence against a disposable directory only."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="wealth-regression-")
        self.fixture_root = Path(self.temp_dir.name)
        self.fixture_users = self.fixture_root / "users"
        def _isolated_kis_init(kis_self, username="sagesaint"):
            kis_self.username = username
            cfg = user_openapi.get_user_openapi_config(username).get("kis", {})
            kis_self.base_url = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443").rstrip("/")
            kis_self.app_key = cfg.get("app_key", "")
            kis_self.app_secret = cfg.get("app_secret", "")
            kis_self.account_no = cfg.get("account_no", "").replace("-", "").strip()
            kis_self._validate_url(kis_self.base_url, "KIS_BASE_URL")
            user_dir = self.fixture_user_dir(username)
            kis_self.token_cache_file = user_dir / "kis_token_cache.json"
            kis_self._token = None
            kis_self.last_accounts = []
            kis_self.account_cash = {}

        def _isolated_kb_init(kb_self, username="sagesaint"):
            kb_self.username = username
            cfg = user_openapi.get_user_openapi_config(username).get("kb", {})
            kb_self.base_url = "https://developer.kbsec.com:32484"
            kb_self.app_key = cfg.get("app_key", "")
            kb_self.app_secret = cfg.get("app_secret", "")
            kb_self.gnl_ac_no = cfg.get("gnl_ac_no", "").replace("-", "").strip()
            kb_self.gds_no = cfg.get("gds_no", "").strip()
            kb_self._token = None
            user_dir = self.fixture_user_dir(username)
            kb_self.token_cache_file = user_dir / "kb_token_cache.json"

        self.patchers = [
            patch.object(user_manager, "get_user_data_dir", side_effect=self.fixture_user_dir),
            patch.object(ledger, "get_user_data_dir", side_effect=self.fixture_user_dir),
            patch.object(settings, "get_user_data_dir", side_effect=self.fixture_user_dir),
            patch.object(user_openapi, "USERS_DIR", self.fixture_users),
            patch.object(KISOpenAPI, "__init__", _isolated_kis_init),
            patch.object(KBOpenAPI, "__init__", _isolated_kb_init),
            patch.object(
                user_openapi,
                "get_user_openapi_config",
                side_effect=AssertionError("Regression tests must not access OpenAPI credentials"),
            ),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def fixture_user_dir(self, username: str | None = None) -> Path:
        safe_username = (username or "fixture_default").strip()
        path = self.fixture_users / safe_username
        path.mkdir(parents=True, exist_ok=True)
        return path
