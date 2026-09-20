from copy import deepcopy
from datetime import datetime
import json
from typing import Any

from app.services import portfolio
from app.services.ipo.account_resolution import (
    IpoAccountResolution,
    resolve_ipo_account_candidates,
    validate_ipo_account_selection,
)


class ApplicationRevisionConflict(RuntimeError):
    """Raised when application revision does not match the current portfolio revision."""


class InvalidApplicationError(ValueError):
    """Raised when an application payload contains invalid owners or data."""


class ApplicationAccountMappingConflict(InvalidApplicationError):
    """Raised when a persisted applicant account mapping cannot be remapped safely."""


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
            "applicants": _public_applicants(app.get("applicants")),
        }

    return {
        "revision": revision,
        "applications": result_apps,
        "family_members": family,
    }


def _public_applicants(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for owner, item in value.items():
        if not isinstance(item, dict):
            continue
        broker_id = str(item.get("broker_id") or "").strip()
        account_id = str(item.get("account_id") or "").strip()
        if broker_id and account_id:
            result[str(owner)] = {"broker_id": broker_id, "account_id": account_id}
    return result


def _application_targets(app: dict[str, Any], portfolio_data: dict[str, Any]) -> list[str]:
    return list(app.get("target_owners") or get_configured_family_members(portfolio_data))


def resolve_user_application_account(
    username: str | None,
    ipo_id: str,
    owner: str,
    broker_value: str | None,
    *,
    ignore_existing_mapping: bool = False,
) -> IpoAccountResolution:
    """Return sanitized same-broker candidates for one IPO applicant."""
    data = portfolio.read_portfolio(username)
    app = ((data.get("settings", {}) or {}).get("ipo", {}).get("applications", {}) or {}).get(ipo_id, {})
    targets = _application_targets(app if isinstance(app, dict) else {}, data)
    if owner not in targets or owner == "모두":
        raise InvalidApplicationError("owner is not eligible for this IPO application")
    existing = (app.get("applicants") or {}).get(owner) if isinstance(app, dict) else None
    return resolve_ipo_account_candidates(
        broker_value,
        data.get("accounts", []),
        existing_mapping=None if ignore_existing_mapping else (existing if isinstance(existing, dict) else None),
    )


def set_user_application_account(
    username: str | None,
    ipo_id: str,
    owner: str,
    broker_value: str | None,
    account_id: object,
    client_revision: int,
) -> dict[str, Any]:
    """Persist a broker-validated Wealth UUID for one applied IPO applicant."""
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        pf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        settings = pf.setdefault("settings", {})
        ipo_settings = settings.setdefault("ipo", {"revision": 0, "applications": {}})
        current_rev = int(ipo_settings.get("revision", 0))
        if client_revision != current_rev:
            raise ApplicationRevisionConflict(f"Revision conflict: client={client_revision}, server={current_rev}")

        app = (ipo_settings.setdefault("applications", {})).get(ipo_id)
        if not isinstance(app, dict):
            raise InvalidApplicationError("IPO application must be saved before assigning an account")
        targets = _application_targets(app, pf)
        if owner not in targets or owner == "모두":
            raise InvalidApplicationError("owner is not eligible for this IPO application")
        if owner not in list(app.get("applied_owners") or []):
            raise InvalidApplicationError("owner has not applied for this IPO")

        applicants = app.setdefault("applicants", {})
        existing = applicants.get(owner)
        try:
            selected, resolution = validate_ipo_account_selection(
                broker_value,
                pf.get("accounts", []),
                account_id,
                existing_mapping=existing if isinstance(existing, dict) else None,
            )
        except ValueError as exc:
            if str(exc) == "MAPPING_CONFLICT":
                raise ApplicationAccountMappingConflict("MAPPING_CONFLICT") from exc
            raise InvalidApplicationError(str(exc)) from exc

        if resolution.broker_id is None:
            raise InvalidApplicationError("BROKER_UNKNOWN")
        if isinstance(existing, dict):
            # The matching branch is intentionally a no-op: no silent remap.
            return {
                "revision": current_rev,
                "ipo_id": ipo_id,
                "owner": owner,
                "broker_id": resolution.broker_id,
                "account_id": selected["account_id"],
                "resolution_status": resolution.resolution_status,
            }

        applicants[owner] = {
            "broker_id": resolution.broker_id,
            "account_id": selected["account_id"],
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        ipo_settings["revision"] = current_rev + 1
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(pf, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)
        return {
            "revision": current_rev + 1,
            "ipo_id": ipo_id,
            "owner": owner,
            "broker_id": resolution.broker_id,
            "account_id": selected["account_id"],
            "resolution_status": resolution.resolution_status,
        }


def remap_user_application_account(
    username: str | None,
    ipo_id: str,
    owner: str,
    broker_value: str | None,
    account_id: object,
    expected_current_account_id: object,
    client_revision: int,
) -> dict[str, Any]:
    """Explicitly replace one applicant's account UUID after concurrency checks."""
    expected_id = str(expected_current_account_id or "").strip()
    if not expected_id:
        raise ApplicationAccountMappingConflict("MAPPING_CONFLICT")
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        pf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        ipo_settings = pf.setdefault("settings", {}).setdefault("ipo", {"revision": 0, "applications": {}})
        current_rev = int(ipo_settings.get("revision", 0))
        if client_revision != current_rev:
            raise ApplicationRevisionConflict(f"Revision conflict: client={client_revision}, server={current_rev}")
        app = (ipo_settings.setdefault("applications", {})).get(ipo_id)
        if not isinstance(app, dict):
            raise InvalidApplicationError("IPO application must be saved before remapping an account")
        if owner not in _application_targets(app, pf) or owner == "모두":
            raise InvalidApplicationError("owner is not eligible for this IPO application")
        if owner not in list(app.get("applied_owners") or []):
            raise InvalidApplicationError("owner has not applied for this IPO")
        applicants = app.get("applicants")
        existing = applicants.get(owner) if isinstance(applicants, dict) else None
        if not isinstance(existing, dict) or str(existing.get("account_id") or "").strip() != expected_id:
            raise ApplicationAccountMappingConflict("MAPPING_CONFLICT")
        allocation = existing.get("allocation")
        if isinstance(allocation, dict) and allocation.get("links"):
            # Links reference authoritative P/L records scoped to this account;
            # moving the applicant would make those links misleading.
            raise ApplicationAccountMappingConflict("IPO_ACCOUNT_REMAP_HAS_LINKED_SALES")

        try:
            selected, resolution = validate_ipo_account_selection(
                broker_value, pf.get("accounts", []), account_id,
                # Explicit remap is the only path that intentionally ignores
                # the previous mapping while validating the new destination.
                existing_mapping=None,
            )
        except ValueError as exc:
            raise InvalidApplicationError(str(exc)) from exc
        if resolution.broker_id is None:
            raise InvalidApplicationError("BROKER_UNKNOWN")
        if str(selected["account_id"]) == expected_id and resolution.broker_id == str(existing.get("broker_id") or ""):
            return {"revision": current_rev, "ipo_id": ipo_id, "owner": owner,
                    "broker_id": resolution.broker_id, "account_id": expected_id,
                    "resolution_status": "MAPPED"}

        replacement = dict(existing)
        replacement.update({"broker_id": resolution.broker_id, "account_id": selected["account_id"],
                            "updated_at": datetime.now().astimezone().isoformat()})
        applicants[owner] = replacement
        ipo_settings["revision"] = current_rev + 1
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(pf, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)
        return {"revision": current_rev + 1, "ipo_id": ipo_id, "owner": owner,
                "broker_id": resolution.broker_id, "account_id": selected["account_id"],
                "resolution_status": "REMAPPED"}


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
        if isinstance(existing_app.get("applicants"), dict):
            # Application toggles must not silently erase a future allocation's
            # stable account relationship.
            updated_app["applicants"] = existing_app["applicants"]
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
