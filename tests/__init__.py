"""Process-wide safety defaults for the unittest suite.

Tests explicitly opt into the application's test environment and reject all
non-loopback socket connections. ASGI TestClient traffic remains in-process.
"""

from __future__ import annotations

import os
import socket
import hashlib
from pathlib import Path
import unittest

os.environ.setdefault("WEALTH_ENV", "test")
# Explicit test-only signing secret.  Only used when DASHBOARD_SECRET_KEY is
# absent and WEALTH_ENV=test.  Never used by production runtime.
os.environ.setdefault(
    "WEALTH_TEST_SIGNING_SECRET",
    "wealth-test-suite-signing-secret-not-for-production",
)

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex


def _is_loopback(address: object) -> bool:
    if not isinstance(address, tuple) or not address:
        return False
    host = str(address[0]).strip().lower().strip("[]")
    return host in {"127.0.0.1", "localhost", "::1"}


def _guarded_connect(self, address):
    if not _is_loopback(address):
        raise AssertionError(f"External network is blocked in tests: {address!r}")
    return _original_connect(self, address)


def _guarded_connect_ex(self, address):
    if not _is_loopback(address):
        raise AssertionError(f"External network is blocked in tests: {address!r}")
    return _original_connect_ex(self, address)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex


def _market_store_sha256() -> str | None:
    path = Path(__file__).resolve().parents[1] / "data" / "ipo" / "market.json"
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _users_tree_signature() -> tuple[tuple[str, bool, int], ...]:
    path = Path(__file__).resolve().parents[1] / "data" / "users"
    if not path.exists():
        return ()
    items = []
    for p in path.rglob("*"):
        rel = p.relative_to(path).as_posix()
        is_d = p.is_dir()
        sz = 0 if is_d else p.stat().st_size
        items.append((rel, is_d, sz))
    return tuple(sorted(items))


# Keep presentation/calendar/all tests honest: they must never rewrite the real
# production snapshot or repository data/users while exercising test cases.
_original_testcase_run = unittest.TestCase.run


def _guarded_testcase_run(self, result=None):
    before_market = _market_store_sha256()
    before_users = _users_tree_signature()
    outcome = _original_testcase_run(self, result)
    after_market = _market_store_sha256()
    after_users = _users_tree_signature()
    if before_market != after_market:
        raise AssertionError(
            "Tests must not mutate data/ipo/market.json "
            f"(before={before_market}, after={after_market})"
        )
    if before_users != after_users:
        added = set(after_users) - set(before_users)
        removed = set(before_users) - set(after_users)
        raise AssertionError(
            f"Tests must not mutate repository data/users/ "
            f"(added={sorted(list(added))}, removed={sorted(list(removed))})"
        )
    return outcome


unittest.TestCase.run = _guarded_testcase_run
