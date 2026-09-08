"""Set test safety policy before pytest imports any test module."""

from __future__ import annotations

import os
import socket

os.environ.setdefault("WEALTH_ENV", "test")

_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def _loopback(address: object) -> bool:
    return isinstance(address, tuple) and bool(address) and str(address[0]).strip().lower().strip("[]") in {"localhost", "127.0.0.1", "::1"}


def _guard_connect(sock, address):
    if not _loopback(address):
        raise AssertionError(f"External network is blocked in tests: {address!r}")
    return _connect(sock, address)


def _guard_connect_ex(sock, address):
    if not _loopback(address):
        raise AssertionError(f"External network is blocked in tests: {address!r}")
    return _connect_ex(sock, address)


if socket.socket.connect.__name__ != "_guard_connect":
    socket.socket.connect = _guard_connect
    socket.socket.connect_ex = _guard_connect_ex
