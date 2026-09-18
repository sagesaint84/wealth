from copy import deepcopy
from datetime import datetime
import json
from typing import Any

from app.services import portfolio


class ApplicationRevisionConflict(RuntimeError):
    """Raised when application revision does not match the current portfolio revision."""


class InvalidApplicationError(ValueError):
    """Raised when an application payload contains invalid owners or data."""


def get_configured_family_members(portfolio_data: dict[str, Any]) -> list[str]:
    settings = portfolio_data.get("settings", {}) or {}
    members = settings.get("family_members")
    if isinstance(members, list) and members:
        # Filter out "모두" if present in legacy configs
        cleaned = [str(m).strip() for m in members if str(m).strip() and str(m).strip() != "모두"]
        if cleaned:
            return cleaned
    return ["아빠", "엄마", "자녀"]


def derive_application_state(target_owners: list[str], applied_owners: list[str]) -> str:
    """Derive tri-state: 'none', 'some', or 'all'."""
    if not applied_owners:
        return "none"
    if not target_owners:
        return "some"
    targets = set(target_owners)
    applied = set(applied_owners)
    if targets.issubset(applied):
        return "all"
    return "some"


def get_user_applications(username: str | None = None) -> dict[str, Any]:
    data = portfolio.read_portfolio(username)
    ipo_settings = (data.get("settings", {}) or {}).get("ipo", {})
    revision = int(ipo_settings.get("revision", 0))
    apps = dict(ipo_settings.get("applications", {}))

    result_apps: dict[str, Any] = {}
    family = get_configured_family_members(data)

    for ipo_id, app in apps.items():
        targets = list(app.get("target_owners") or family)
        applied = list(app.get("applied_owners") or [])
        state = derive_application_state(targets, applied)
        result_apps[ipo_id] = {
            "ipo_id": ipo_id,
            "target_owners": targets,
            "applied_owners": applied,
            "target_frozen_at": app.get("target_frozen_at"),
            "updated_at": app.get("updated_at"),
            "state": state,
            "all_applied": state == "all",
        }

    return {
        "revision": revision,
        "applications": result_apps,
        "family_members": family,
    }


def update_user_application(
    username: str | None,
    ipo_id: str,
    applied_owners: list[str],
    client_revision: int,
) -> dict[str, Any]:
    if not ipo_id or not str(ipo_id).strip():
        raise InvalidApplicationError("ipo_id is required")

    if not isinstance(applied_owners, list):
        raise InvalidApplicationError("applied_owners must be a list")

    # '모두' is strictly forbidden in applied_owners
    if any(str(o).strip() == "모두" for o in applied_owners):
        raise InvalidApplicationError("Invalid owner: '모두' cannot be saved as an applicant.")

    cleaned_applied = [str(o).strip() for o in applied_owners if str(o).strip()]

    # Share the portfolio write lock and read within it directly to prevent deadlock and lost updates
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        pf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        settings = pf.setdefault("settings", {})
        ipo_settings = settings.setdefault("ipo", {"revision": 0, "applications": {}})

        current_rev = int(ipo_settings.get("revision", 0))
        if client_revision != current_rev:
            raise ApplicationRevisionConflict(
                f"Revision conflict: client={client_revision}, server={current_rev}"
            )

        apps = ipo_settings.setdefault("applications", {})
        existing_app = apps.get(ipo_id, {})
        family_members = get_configured_family_members(pf)

        now_iso = datetime.now().astimezone().isoformat()

        # Target freezing rule:
        # If already frozen, target_owners is strictly frozen.
        # Only existing target_owners may be applied; newly configured family members are rejected.
        if existing_app.get("target_frozen_at") and existing_app.get("target_owners"):
            target_owners = list(existing_app["target_owners"])
            target_frozen_at = existing_app["target_frozen_at"]
            for owner in cleaned_applied:
                if owner not in target_owners:
                    raise InvalidApplicationError(
                        f"Frozen application cannot add new family member: '{owner}'. Allowed: {target_owners}"
                    )
        else:
            target_owners = list(family_members)
            target_frozen_at = now_iso
            for owner in cleaned_applied:
                if owner not in target_owners:
                    raise InvalidApplicationError(
                        f"Unknown owner: '{owner}' is not a recognized family member. Allowed: {target_owners}"
                    )

        updated_app = {
            "target_owners": target_owners,
            "applied_owners": sorted(list(set(cleaned_applied))),
            "target_frozen_at": target_frozen_at,
            "updated_at": now_iso,
        }
        apps[ipo_id] = updated_app

        next_rev = current_rev + 1
        ipo_settings["revision"] = next_rev

        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(pf, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)

        state = derive_application_state(target_owners, updated_app["applied_owners"])
        return {
            "revision": next_rev,
            "ipo_id": ipo_id,
            "target_owners": target_owners,
            "applied_owners": updated_app["applied_owners"],
            "state": state,
            "all_applied": state == "all",
            "target_frozen_at": target_frozen_at,
            "updated_at": now_iso,
        }


def freeze_untouched_ipo_application(
    username: str | None,
    ipo_id: str,
) -> dict[str, Any] | None:
    """Helper to freeze target_owners for an IPO when subscription closes if never modified."""
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        pf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        settings = pf.setdefault("settings", {})
        ipo_settings = settings.setdefault("ipo", {"revision": 0, "applications": {}})
        apps = ipo_settings.setdefault("applications", {})

        if ipo_id in apps and apps[ipo_id].get("target_frozen_at"):
            return apps[ipo_id]

        family_members = get_configured_family_members(pf)
        now_iso = datetime.now().astimezone().isoformat()

        app = {
            "target_owners": list(family_members),
            "applied_owners": [],
            "target_frozen_at": now_iso,
            "updated_at": now_iso,
        }
        apps[ipo_id] = app
        ipo_settings["revision"] = int(ipo_settings.get("revision", 0)) + 1

        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(pf, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)
        return app
