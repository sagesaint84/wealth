"""One-time, conservative migration for legacy Toss WTS Korean income codes.

The Toss provider may return Korean security short codes with an ``A`` prefix,
while wealth stores the six-character short code without that provider prefix.
This migration only rewrites records already identified as Toss WTS Korean
dividend or distribution income. Provider identity and the existing source
fingerprint are preserved.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from app.services.user_manager import DATA_DIR, USERS_DIR

_LEGACY_KR_CODE_RE = re.compile(r"^A([0-9A-Z]{6})$")
_SUPPORTED_TYPES = frozenset({"dividend", "distribution"})


def _normalize_record(record: dict[str, Any]) -> bool:
    if str(record.get("source") or "").strip() != "toss_wts":
        return False
    if str(record.get("currency") or "").strip().upper() != "KRW":
        return False
    if str(record.get("income_type") or "").strip() not in _SUPPORTED_TYPES:
        return False
    source_meta = record.get("source_meta")
    if not isinstance(source_meta, dict):
        return False
    if str(source_meta.get("market") or "").strip().lower() != "kr":
        return False
    code = str(record.get("code") or "").strip()
    matched = _LEGACY_KR_CODE_RE.fullmatch(code)
    if not matched:
        return False

    source_meta.setdefault("provider_stock_code", code)
    record["code"] = matched.group(1)
    return True


def migrate_dividend_records_file(path: Path, *, apply: bool = False) -> dict[str, Any]:
    path = Path(path)
    with open(path, "r", encoding="utf-8") as fp:
        payload = json.load(fp)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError(f"invalid dividend record structure: {path}")
    records = payload["records"]
    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"invalid dividend record entry: {path}")

    changed = sum(1 for record in records if _normalize_record(record))
    if apply and changed:
        payload["updated_at"] = datetime.now().astimezone().isoformat()
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
        tmp.replace(path)

    return {
        "path": str(path),
        "matched": changed,
        "applied": changed if apply else 0,
    }


def candidate_files() -> list[Path]:
    paths: list[Path] = []
    legacy = DATA_DIR / "dividend_records.json"
    if legacy.is_file():
        paths.append(legacy)
    if USERS_DIR.is_dir():
        paths.extend(sorted(USERS_DIR.glob("*/dividend_records.json")))
    return paths


def migrate_all(*, apply: bool = False) -> dict[str, Any]:
    results = [migrate_dividend_records_file(path, apply=apply) for path in candidate_files()]
    return {
        "mode": "apply" if apply else "dry-run",
        "files": len(results),
        "matched": sum(item["matched"] for item in results),
        "applied": sum(item["applied"] for item in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize legacy Toss WTS Korean dividend stock codes")
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    args = parser.parse_args()
    print(json.dumps(migrate_all(apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())