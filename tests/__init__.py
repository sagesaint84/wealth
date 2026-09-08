"""Process-wide safety defaults for the unittest suite.

Tests explicitly opt into the application's test environment and reject all
non-loopback socket connections. ASGI TestClient traffic remains in-process.
"""

from __future__ import annotations

import os
import socket

os.environ.setdefault("WEALTH_ENV", "test")

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
