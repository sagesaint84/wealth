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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    tmp = Path(temporary)
    try:
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=False,
                indent=indent,
                allow_nan=False,
            )
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
        try:
            os.close(fd)
        except OSError:
            pass
        tmp.unlink(missing_ok=True)
        raise
