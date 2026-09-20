"""Canonical, explicit broker identity registry for Wealth.

``broker_id`` is a Wealth-only identifier.  It deliberately does not represent
MyData, CODEF, OpenAPI, or any other external provider code.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any


_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "broker_registry.json"


def _key(value: object) -> str:
    return str(value or "").strip().casefold()


@lru_cache(maxsize=1)
def _load_registry() -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Load and validate the bundled registry once per process."""
    try:
        payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Wealth broker registry is unavailable") from exc

    rows = payload.get("brokers") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("Wealth broker registry has no broker list")

    by_id: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    display_names: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("Wealth broker registry contains an invalid broker")
        broker_id = _key(row.get("broker_id"))
        display_name = str(row.get("display_name") or "").strip()
        raw_aliases = row.get("aliases")
        if not broker_id or not display_name or not isinstance(raw_aliases, list):
            raise RuntimeError("Wealth broker registry contains an incomplete broker")
        if broker_id in by_id:
            raise RuntimeError(f"Wealth broker registry duplicates broker_id: {broker_id}")

        display_key = _key(display_name)
        if display_key in display_names:
            raise RuntimeError(f"Wealth broker registry duplicates display_name: {display_name}")
        display_names.add(display_key)

        normalized_aliases: list[str] = []
        for alias in raw_aliases:
            if not isinstance(alias, str):
                raise RuntimeError("Wealth broker registry aliases must be strings")
            alias = alias.strip()
            # Preserve the prior behavior: empty string aliases are ignored.
            if alias:
                normalized_aliases.append(alias)

        canonical = {
            "broker_id": broker_id,
            "display_name": display_name,
            "aliases": normalized_aliases,
        }
        by_id[broker_id] = canonical
        for value in [broker_id, display_name, *canonical["aliases"]]:
            alias_key = _key(value)
            if not alias_key:
                continue
            previous = aliases.get(alias_key)
            if previous and previous != broker_id:
                raise RuntimeError(f"Wealth broker registry aliases collide: {value}")
            aliases[alias_key] = broker_id

    return by_id, aliases


def normalize_broker(value: str | None) -> str | None:
    """Return the exact canonical broker_id, without fuzzy matching."""
    _, aliases = _load_registry()
    return aliases.get(_key(value))


def get_broker(broker_id: str) -> dict[str, Any] | None:
    """Return a defensive copy of the registry record for a canonical ID."""
    brokers, _ = _load_registry()
    broker = brokers.get(_key(broker_id))
    if broker is None:
        return None
    return {**broker, "aliases": list(broker["aliases"])}


def get_display_name(broker_id: str) -> str | None:
    broker = get_broker(broker_id)
    return str(broker["display_name"]) if broker else None


def get_aliases(broker_id: str) -> list[str]:
    broker = get_broker(broker_id)
    return list(broker["aliases"]) if broker else []


def is_known_broker(value: str | None) -> bool:
    return normalize_broker(value) is not None
