"""One-time conservative migration for legacy Toss WTS realized-P/L codes.

Only the Wealth-facing code is rewritten. Provider product identity and source
fingerprints remain untouched so exact Toss WTS duplicate detection is stable.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from app.services.user_manager import DATA_DIR, USERS_DIR
from app.services.financial_json import financial_lock, write_financial_json


_LEGACY_KR_CODE_RE = re.compile(r"^A([0-9A-Z]{6})$")


def _normalize_record(record: dict[str, Any]) -> bool:
    if str(record.get("source") or "").strip() != "toss_wts":
        return False
    if str(record.get("currency") or "").strip().upper() != "KRW":
        return False
    source_meta = record.get("source_meta")
    if not isinstance(source_meta, dict):
        return False
    if str(source_meta.get("market_type") or "").strip().lower() != "kr":
        return False

    code = str(record.get("code") or "").strip()
    matched = _LEGACY_KR_CODE_RE.fullmatch(code)
    if not matched:
        return False

    provider_code = str(source_meta.get("product_code") or "").strip()
    if provider_code != code:
        return False

    record["code"] = matched.group(1)
    return True


def migrate_realized_records_file(path: Path, *, apply: bool = False) -> dict[str, Any]:
    path = Path(path)
    with financial_lock(path):
        with open(path, "r", encoding="utf-8") as fp:
            payload = json.load(fp)
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise ValueError(f"invalid realized P/L record structure: {path}")
        records = payload["records"]
        if not all(isinstance(record, dict) for record in records):
            raise ValueError(f"invalid realized P/L record entry: {path}")

        changed = sum(1 for record in records if _normalize_record(record))
        if apply and changed:
            payload["updated_at"] = datetime.now().astimezone().isoformat()
            write_financial_json(path, payload)

        return {
            "path": str(path),
            "matched": changed,
            "applied": changed if apply else 0,
        }


def candidate_files() -> list[Path]:
    paths: list[Path] = []
    legacy = DATA_DIR / "realized_pnl_records.json"
    if legacy.is_file():
        paths.append(legacy)
    if USERS_DIR.is_dir():
        paths.extend(sorted(USERS_DIR.glob("*/realized_pnl_records.json")))
    return paths


def migrate_all(*, apply: bool = False) -> dict[str, Any]:
    results = [migrate_realized_records_file(path, apply=apply) for path in candidate_files()]
    return {
        "mode": "apply" if apply else "dry-run",
        "files": len(results),
        "matched": sum(item["matched"] for item in results),
        "applied": sum(item["applied"] for item in results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize legacy Toss WTS Korean realized-P/L stock codes"
    )
    parser.add_argument("--apply", action="store_true", help="write changes; default is dry-run")
    args = parser.parse_args()
    print(json.dumps(migrate_all(apply=args.apply), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
