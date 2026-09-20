"""Atomic family display-name changes, including IPO applicant references."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.services import portfolio


class FamilyMemberRenameError(ValueError):
    pass


class IpoApplicantRenameCollision(FamilyMemberRenameError):
    pass


def _members(data: dict[str, Any]) -> list[str]:
    value = (data.get("settings", {}) or {}).get("family_members")
    return list(value) if isinstance(value, list) else ["아빠", "엄마", "자녀"]


def _renamed_owner_list(value: object, old_name: str, new_name: str, *, ipo_id: str, field: str) -> object:
    if not isinstance(value, list):
        return value
    items = list(value)
    if old_name in items and new_name in items:
        raise IpoApplicantRenameCollision(f"IPO applicant collision: {ipo_id}.{field}")
    return [new_name if item == old_name else item for item in items]


def rename_family_member_references(username: str | None, old_name: str, new_name: str) -> dict[str, Any]:
    """Rename a family display name and all IPO owner references in one write."""
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        portfolio.assert_write_allowed(path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = deepcopy(portfolio.EMPTY_PORTFOLIO)

        members = _members(data)
        if old_name not in members:
            raise FamilyMemberRenameError("FAMILY_MEMBER_NOT_FOUND")
        if new_name in members and new_name != old_name:
            raise FamilyMemberRenameError("FAMILY_MEMBER_EXISTS")

        ipo_settings = ((data.get("settings", {}) or {}).get("ipo", {}) or {})
        apps = ipo_settings.get("applications", {})
        if not isinstance(apps, dict):
            apps = {}

        # Validate every collision before mutating any object.
        for ipo_id, app in apps.items():
            if not isinstance(app, dict):
                continue
            applicants = app.get("applicants")
            if isinstance(applicants, dict) and old_name in applicants and new_name in applicants:
                raise IpoApplicantRenameCollision(f"IPO applicant collision: {ipo_id}.applicants")
            _renamed_owner_list(app.get("applied_owners"), old_name, new_name, ipo_id=str(ipo_id), field="applied_owners")
            _renamed_owner_list(app.get("target_owners"), old_name, new_name, ipo_id=str(ipo_id), field="target_owners")

        data.setdefault("settings", {})["family_members"] = [new_name if item == old_name else item for item in members]
        for account in data.get("accounts", []) or []:
            if isinstance(account, dict) and account.get("owner") == old_name:
                account["owner"] = new_name

        ipo_changed = False
        for app in apps.values():
            if not isinstance(app, dict):
                continue
            for field in ("applied_owners", "target_owners"):
                original = app.get(field)
                renamed = _renamed_owner_list(original, old_name, new_name, ipo_id="application", field=field)
                if renamed != original:
                    app[field] = renamed
                    ipo_changed = True
            applicants = app.get("applicants")
            if isinstance(applicants, dict) and old_name in applicants:
                # Move the existing object intact for forward compatibility.
                applicants[new_name] = applicants.pop(old_name)
                ipo_changed = True

        if ipo_changed:
            normalized_ipo = data.setdefault("settings", {}).setdefault("ipo", {"revision": 0, "applications": apps})
            normalized_ipo["revision"] = int(normalized_ipo.get("revision", 0)) + 1

        path.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = portfolio.now_iso()
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)
        return {"members": data["settings"]["family_members"], "ipo_changed": ipo_changed,
                "ipo_revision": int((data["settings"].get("ipo") or {}).get("revision", 0))}
