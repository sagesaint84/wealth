"""Test-only guards against accidental writes to the repository data root."""

from __future__ import annotations

import os
from pathlib import Path

from app.services.network_policy import is_test_mode


class TestSafetyError(AssertionError):
    pass


def assert_write_allowed(path: Path) -> None:
    if not is_test_mode():
        return
    candidate = path.resolve()
    project_root = Path(__file__).resolve().parents[2]
    repo_production = (project_root / "data").resolve()
    configured_production = os.environ.get("WEALTH_PRODUCTION_DATA_DIR")
    production_roots = [repo_production]
    if configured_production:
        production_roots.append(Path(configured_production).resolve())
    # TEMP validation copies must be writable, while the real repository data
    # remains denied. Production denial takes precedence if paths overlap.
    for prod_dir in production_roots:
        try:
            candidate.relative_to(prod_dir)
        except ValueError:
            pass
        else:
            raise TestSafetyError(
                f"Refusing to write production data path while WEALTH_ENV=test: {candidate}"
            )
    active_data = Path(os.environ.get("DATA_DIR", str(repo_production))).resolve()
    try:
        candidate.relative_to(active_data)
    except ValueError:
        return
