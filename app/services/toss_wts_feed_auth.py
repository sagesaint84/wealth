"""Static deployment authorization layer for Toss WTS feed access.

This module determines whether a given Wealth stable user identity matches
the data-first (or legacy environment) allowed stable user identifier.

It deliberately does not perform runtime session confirmation, provider transport,
user storage lookups, or route guard wiring.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.system_settings import SystemSettingsError, resolve_toss_wts_settings
from app.services.user_identity import validate_user_id

WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID = "WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID"

AUTHORIZED = "AUTHORIZED"
NOT_CONFIGURED = "NOT_CONFIGURED"
INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
NOT_AUTHORIZED = "NOT_AUTHORIZED"
CURRENT_USER_ID_UNAVAILABLE = "CURRENT_USER_ID_UNAVAILABLE"


@dataclass(frozen=True)
class WtsFeedStaticAuthDecision:
    """Privacy-safe static authorization decision.

    Attributes:
        authorized: True if and only if the current user ID matches the
            deployment-configured allowed user ID.
        code: Safe public status code explaining the decision without leaking
            identifiers.
    """

    authorized: bool
    code: str

    def as_dict(self) -> dict[str, object]:
        return {"authorized": self.authorized, "code": self.code}

    def __bool__(self) -> bool:
        return self.authorized

    def __getitem__(self, item: str) -> object:
        if item == "authorized":
            return self.authorized
        if item == "code":
            return self.code
        raise KeyError(item)


def _get_allowed_user_id() -> tuple[str | None, str | None]:
    """Resolve and strictly validate the configured allowed stable user ID.

    Returns a tuple of (allowed_user_id, error_code). Exactly one element is None.
    Does not log or mutate the configured value.
    """
    try:
        raw_allowed = resolve_toss_wts_settings()["allowed_user_id"]
    except SystemSettingsError:
        return None, INVALID_CONFIGURATION
    if raw_allowed is None:
        return None, NOT_CONFIGURED

    try:
        return validate_user_id(raw_allowed), None
    except ValueError:
        return None, INVALID_CONFIGURATION


def check_wts_feed_static_authorization(
    user_id: object = None,
) -> WtsFeedStaticAuthDecision:
    """Check whether *user_id* matches the deployment-configured allowed stable user ID.

    Reads the stored system setting first, then the legacy environment fallback.
    Applies exact string equality against strictly validated canonical UUID4 IDs.
    Returns a privacy-safe WtsFeedStaticAuthDecision.
    """
    allowed_user_id, config_error = _get_allowed_user_id()
    if config_error is not None:
        return WtsFeedStaticAuthDecision(authorized=False, code=config_error)

    if user_id is None:
        return WtsFeedStaticAuthDecision(
            authorized=False, code=CURRENT_USER_ID_UNAVAILABLE
        )

    try:
        current_user_id = validate_user_id(user_id)
    except ValueError:
        return WtsFeedStaticAuthDecision(
            authorized=False, code=CURRENT_USER_ID_UNAVAILABLE
        )

    if current_user_id == allowed_user_id:
        return WtsFeedStaticAuthDecision(authorized=True, code=AUTHORIZED)

    return WtsFeedStaticAuthDecision(authorized=False, code=NOT_AUTHORIZED)
