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


# Keep presentation/calendar tests honest: they must never rewrite the real
# production snapshot while exercising mocked market data.
_original_testcase_run = unittest.TestCase.run


def _guarded_testcase_run(self, result=None):
    before = _market_store_sha256()
    outcome = _original_testcase_run(self, result)
    after = _market_store_sha256()
    if before != after:
        raise AssertionError(
            "Tests must not mutate data/ipo/market.json "
            f"(before={before}, after={after})"
        )
    return outcome


unittest.TestCase.run = _guarded_testcase_run
