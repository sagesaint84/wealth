"""Narrow helpers for atomically persisting credential-bearing JSON files."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_private_json(path: Path, value: Any, *, indent: int | None = None) -> None:
    """Atomically write JSON and enforce mode 0600 on POSIX.

    The parent directory is created when absent but its existing permissions are
    never widened. A failed serialization, flush, fsync, or replace leaves the
    previous target intact and removes the temporary file where possible.
    """
    _atomic_write_private(path, lambda stream: json.dump(
        value, stream, ensure_ascii=False, indent=indent, allow_nan=False,
    ))


def atomic_write_private_bytes(path: Path, value: bytes) -> None:
    """Atomically restore exact validated financial bytes, with private permissions."""
    _atomic_write_private(path, lambda stream: stream.write(value), binary=True)


def _atomic_write_private(path: Path, write, *, binary: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp = Path(temporary)
    raw_fd = fd
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        stream = os.fdopen(fd, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"}))
        raw_fd = None  # fdopen owns closing now; the descriptor may be reused.
        with stream:
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        # On Windows, replace can transiently fail with PermissionError/WinError 5
        # if a virus scanner, indexer, or concurrent file access holds a transient handle.
        if os.name == "nt":
            import time
            for attempt in range(10):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:
                    if attempt == 9:
                        raise
                    time.sleep(0.005)
        else:
            os.replace(tmp, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
    except Exception:
        if raw_fd is not None:
            try:
                os.close(raw_fd)
            except OSError:
                pass
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
