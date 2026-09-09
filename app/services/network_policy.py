"""Runtime policy for outbound network integrations.

External integrations are disabled when WEALTH_ENV=test.  Localhost remains
available so a real FastAPI server can be exercised by browser integration
tests.  Callers should short-circuit before constructing an HTTP client.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def is_test_mode() -> bool:
    return os.getenv("WEALTH_ENV", "production").strip().lower() == "test"


def external_network_allowed() -> bool:
    return not is_test_mode()


def network_target_allowed(target: str) -> bool:
    """Allow normal production traffic and localhost-only traffic in tests."""
    if external_network_allowed():
        return True
    parsed = urlparse(target if "://" in target else f"//{target}")
    host = (parsed.hostname or target).strip("[]").lower()
    return host in LOCAL_HOSTS


class ExternalNetworkDisabled(RuntimeError):
    """Raised before an external integration can reach an HTTP client."""


def require_external_network(operation: str) -> None:
    if not external_network_allowed():
        raise ExternalNetworkDisabled(
            f"External network disabled in test environment: {operation}"
        )
