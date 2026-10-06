"""User-specific display metadata; never reorder financial source arrays."""
from __future__ import annotations

import unicodedata
from typing import Any

from app.services import portfolio
from app.services.broker_registry import normalize_broker, get_aliases, get_display_name

KINDS = {"securities": ("accounts",),
         "banking": ("bank_accounts", "savings_accounts", "loan_accounts")}
MAX_ORDER = 2000


def institution_key(value: str, scope: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if scope == "securities":
        return normalize_broker(text) or text.casefold() or "기타"
    return " ".join(text.split()).casefold() or "기타"


def ordered(preference: Any, natural: list[str]) -> list[str]:
    if not isinstance(preference, list) or any(not isinstance(x, str) for x in preference):
        return list(natural)
    valid = set(natural)
    result = list(dict.fromkeys(x for x in preference if x in valid))
    known = set(result)
    return result + [x for x in natural if x not in known]


def effective_order(data: dict) -> dict:
    stored = data.get("settings", {}).get("account_display_order")
    if not isinstance(stored, dict) or type(stored.get("version")) is not int or stored.get("version") != 1:
        stored = {}
    result = {"version": 1}
    for scope, kinds in KINDS.items():
        saved = stored.get(scope)
        saved = saved if isinstance(saved, dict) else {}
        section = {"institutions": [], "labels": {}, "aliases": {}}
        for kind in kinds:
            groups = {}
            for row in data.get(kind, []):
                if not isinstance(row, dict):
                    continue
                label = str(row.get("broker" if scope == "securities" else "bank_name") or "기타").strip()
                key = institution_key(label, scope)
                section["labels"].setdefault(key, label)
                section["aliases"][label] = key
                if scope == "securities" and normalize_broker(label):
                    for alias in [key, get_display_name(key), *get_aliases(key)]:
                        section["aliases"][alias] = key
                if key not in section["institutions"]:
                    section["institutions"].append(key)
                identity = row.get("id")
                if isinstance(identity, str) and identity and identity not in groups.setdefault(key, []):
                    groups[key].append(identity)
            saved_groups = saved.get(kind)
            saved_groups = saved_groups if isinstance(saved_groups, dict) else {}
            section[kind] = {key: ordered(saved_groups.get(key), ids) for key, ids in groups.items()}
        section["institutions"] = ordered(saved.get("institutions"), section["institutions"])
        result[scope] = section
    return result


def merge_subset(full: list[str], subset: list[str]) -> list[str]:
    visible = set(subset)
    replacements = iter(subset)
    return [next(replacements) if item in visible else item for item in full]


def apply_operation(data: dict, payload: Any) -> dict:
    if not isinstance(payload, dict) or set(payload) - {"scope", "level", "kind", "institution", "order"}:
        raise ValueError("잘못된 순서 요청입니다.")
    scope, level = payload.get("scope"), payload.get("level")
    if not isinstance(scope, str) or scope not in KINDS or level not in ("institutions", "accounts"):
        raise ValueError("지원하지 않는 순서 범위입니다.")
    requested = payload.get("order")
    if (not isinstance(requested, list) or not 1 <= len(requested) <= MAX_ORDER
            or any(not isinstance(x, str) or not x.strip() or len(x) > 200 for x in requested)):
        raise ValueError("순서 항목이 올바르지 않습니다.")
    result = effective_order(data)
    section = result[scope]
    if level == "institutions":
        if "kind" in payload or "institution" in payload:
            raise ValueError("기관 순서 요청에 계좌 범위를 사용할 수 없습니다.")
        subset = [institution_key(x, scope) for x in requested]
        full = section["institutions"]
    else:
        kind = payload.get("kind", "accounts" if scope == "securities" else None)
        institution = payload.get("institution")
        if not isinstance(kind, str) or kind not in KINDS[scope] or not isinstance(institution, str) or not institution.strip() or len(institution) > 200:
            raise ValueError("계좌 범위가 올바르지 않습니다.")
        key = institution_key(institution, scope)
        if key not in section["institutions"]:
            raise ValueError("등록되지 않은 기관입니다.")
        subset = requested
        full = section[kind].get(key, [])
        other_ids = {identity for group, identities in section[kind].items() if group != key for identity in identities}
        if set(subset) & other_ids:
            raise ValueError("다른 기관에도 속한 계좌는 이동할 수 없습니다.")
    if len(set(subset)) != len(subset) or not set(subset) <= set(full):
        raise ValueError("중복 또는 다른 기관의 계좌/기관입니다.")
    merged = merge_subset(full, subset)
    if level == "institutions":
        section["institutions"] = merged
    else:
        section[kind][key] = merged
    # Labels/aliases are derived from current records, not persisted identities.
    return {"version": 1, **{s: {k: v for k, v in result[s].items() if k not in ("labels", "aliases")}
                              for s in KINDS}}


def get_account_display_order(username: str) -> dict:
    return effective_order(portfolio.read_portfolio(username))


def patch_account_display_order(username: str, payload: Any) -> dict:
    saved = portfolio.mutate_account_display_order(lambda data: apply_operation(data, payload), username)
    # Compute labels from the latest current records under a fresh read.
    data = portfolio.read_portfolio(username)
    data["settings"]["account_display_order"] = saved
    return effective_order(data)
