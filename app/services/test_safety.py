"""Test-only guards against accidental writes to the repository data root."""

from __future__ import annotations

import os
from pathlib import Path


class TestSafetyError(AssertionError):
    pass


def assert_write_allowed(path: Path) -> None:
    if os.getenv("WEALTH_ENV", "production").strip().lower() != "test":
        return
    candidate = path.resolve()
    project_root = Path(__file__).resolve().parents[2]
    production_data = (project_root / "data").resolve()
    try:
        candidate.relative_to(production_data)
    except ValueError:
        return
    raise TestSafetyError(
        f"Refusing to write production data path while WEALTH_ENV=test: {candidate}"
    )
