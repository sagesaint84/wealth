import asyncio
import copy
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response

from app.services.user_identity import generate_user_id


def _import_main_without_loading_real_env():
    os.environ.setdefault("WEALTH_ENV", "test")
    if "app.main" in sys.modules:
        return sys.modules["app.main"]
    project_root = Path(__file__).resolve().parents[1]
    original_exists = Path.exists

    def safe_exists(path: Path) -> bool:
        if path == project_root / ".env":
            return False
        return original_exists(path)

    with patch.object(Path, "exists", safe_exists):
        return importlib.import_module("app.main")


def _request(path: str, cookie: str | None = None) -> Request:
    headers = []
    if cookie:
        headers.append((b"cookie", cookie.encode("ascii")))
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    })


class RequestStateUserIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()

    def _cookie(self, username: str = "synthetic-user") -> str:
        token = self.main._serializer.dumps({"user": username, "role": "user"})
        return f"{self.main.COOKIE_NAME}={token}"

    async def _call_middleware(self, request: Request) -> Response:
        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        return await self.main.require_login(request, call_next)

    def test_authenticated_user_id_comes_from_current_persisted_record(self):
        persisted_id = generate_user_id()
        user = {"username": "synthetic-user", "id": persisted_id, "role": "user"}
        request = _request("/api/synthetic", self._cookie())
        with patch("app.services.user_manager.get_user_by_name", return_value=user):
            response = asyncio.run(self._call_middleware(request))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(request.state.username, "synthetic-user")
        self.assertEqual(request.state.user_id, persisted_id)

    def test_legacy_user_gets_none_without_backfill(self):
        legacy_user = {"username": "synthetic-user", "role": "user"}
        before = copy.deepcopy(legacy_user)
        request = _request("/api/synthetic", self._cookie())
        with patch("app.services.user_manager.get_user_by_name", return_value=legacy_user), \
             patch("app.services.user_manager.generate_user_id", side_effect=AssertionError):
            response = asyncio.run(self._call_middleware(request))
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(request.state.user_id)
        self.assertEqual(legacy_user, before)

    def test_deleted_user_and_tampered_cookie_leave_no_user_id(self):
        deleted_request = _request("/api/synthetic", self._cookie())
        with patch("app.services.user_manager.get_user_by_name", return_value=None):
            response = asyncio.run(self._call_middleware(deleted_request))
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(deleted_request.state.user_id)

        tampered_request = _request("/api/synthetic", f"{self.main.COOKIE_NAME}=invalid")
        response = asyncio.run(self._call_middleware(tampered_request))
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(tampered_request.state.user_id)

    def test_same_username_recreation_resolves_current_id_without_cache(self):
        old_id = generate_user_id()
        new_id = generate_user_id()
        current_user = {"username": "synthetic-user", "id": old_id, "role": "user"}

        def lookup(_username: str):
            return current_user

        with patch("app.services.user_manager.get_user_by_name", side_effect=lookup):
            first = _request("/api/synthetic", self._cookie())
            asyncio.run(self._call_middleware(first))
            current_user = {"username": "synthetic-user", "id": new_id, "role": "user"}
            second = _request("/api/synthetic", self._cookie())
            asyncio.run(self._call_middleware(second))

        self.assertEqual(first.state.user_id, old_id)
        self.assertEqual(second.state.user_id, new_id)
        self.assertNotEqual(second.state.user_id, old_id)

    def test_cookie_has_no_user_id_and_auth_me_response_does_not_expose_it(self):
        token = self.main._serializer.dumps({"user": "synthetic-user", "role": "user"})
        self.assertEqual(self.main._serializer.loads(token), {"user": "synthetic-user", "role": "user"})

        request = _request("/api/auth/me")
        request.state.username = "synthetic-user"
        request.state.role = "user"
        request.state.must_change_password = False
        result = asyncio.run(self.main.get_my_info(request))
        self.assertNotIn("id", result)
        self.assertNotIn("user_id", result)


if __name__ == "__main__":
    unittest.main()
