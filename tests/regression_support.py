from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from app.services import ledger, portfolio, user_manager, user_openapi


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def import_main_without_loading_real_env():
    """Import app.main while making its .env loader see no production .env file."""
    if "app.main" in sys.modules:
        module = sys.modules["app.main"]
        module.app.router.on_startup[:] = [
            handler for handler in module.app.router.on_startup
            if handler is not module.ensure_data_dir
        ]
        return module

    original_exists = Path.exists

    def safe_exists(path: Path) -> bool:
        if path == PROJECT_ROOT / ".env":
            return False
        return original_exists(path)

    with patch.object(Path, "exists", safe_exists):
        module = importlib.import_module("app.main")
    # TestClient must not run startup jobs that call external market APIs or
    # write production caches. Endpoint tests invoke only the routes in scope.
    module.app.router.on_startup[:] = [
        handler for handler in module.app.router.on_startup
        if handler is not module.ensure_data_dir
    ]
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
        self.patchers = [
            patch.object(user_manager, "get_user_data_dir", side_effect=self.fixture_user_dir),
            patch.object(ledger, "get_user_data_dir", side_effect=self.fixture_user_dir),
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
