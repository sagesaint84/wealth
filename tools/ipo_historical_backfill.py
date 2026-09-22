#!/usr/bin/env python3
"""CLI operator tool for historical IPO backfill (2020~present).

Usage:
    python tools/ipo_historical_backfill.py --from-year 2020 --preview
    python tools/ipo_historical_backfill.py --from-year 2020 --commit
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.ipo.historical_backfill import (
    Classification,
    HistoricalBackfillEngine,
    HistoricalBackfillError,
    get_current_kst_date,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wealth IPO Historical Backfill Operator Tool (2020~present)",
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=2020,
        help="Starting year to backfill (default: 2020, minimum: 2020)",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        help="Ending year to backfill (default: current KST year)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        default=True,
        help="Generate read-only preview without modifying canonical store (default)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        default=False,
        help="Explicitly commit eligible backfill records to canonical store",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional path to output preview report as JSON",
    )

    args = parser.parse_args()

    engine = HistoricalBackfillEngine()
    current_year = get_current_kst_date().year
    to_year = args.to_year or current_year

    print("=" * 70)
    print("WEALTH IPO HISTORICAL BACKFILL OPERATOR")
    print(f"Target Period: {args.from_year} ~ {to_year}")
    print(f"Mode: {'COMMIT' if args.commit else 'PREVIEW-ONLY'}")
    print("=" * 70)

    try:
        preview = engine.generate_preview(from_year=args.from_year, to_year=to_year)
    except HistoricalBackfillError as exc:
        print(f"[ERROR] Backfill preview failed: {exc}", file=sys.stderr)
        return 1

    print("\n--- YEARLY BREAKDOWN ---")
    header = f"{'Year':<6} | {'Fetched':<8} | {'Verified':<9} | {'NEW':<6} | {'ENRICH':<7} | {'PRESENT':<8} | {'CONFLICT':<9} | {'REVIEW':<7} | {'EXCLUDED':<9}"
    print(header)
    print("-" * len(header))
    for y in sorted(preview.by_year.keys()):
        stats = preview.by_year[y]
        print(
            f"{y:<6} | "
            f"{stats.get('fetched', 0):<8} | "
            f"{stats.get('listing_verified', 0):<9} | "
            f"{stats.get('NEW', 0):<6} | "
            f"{stats.get('ENRICHABLE', 0):<7} | "
            f"{stats.get('ALREADY_PRESENT', 0):<8} | "
            f"{stats.get('CONFLICT', 0):<9} | "
            f"{stats.get('REVIEW_REQUIRED', 0):<7} | "
            f"{stats.get('EXCLUDED', 0):<9}"
        )

    print("\n--- TOTALS ---")
    for k, v in preview.totals.items():
        print(f"  {k:<18}: {v}")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(preview.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n[INFO] Preview JSON saved to {out_path}")

    if args.commit:
        print("\n[WARNING] Attempting to commit eligible records to canonical store...")
        try:
            commit_res = engine.commit_backfill(preview)
            print(f"[SUCCESS] Commit complete: {commit_res}")
        except HistoricalBackfillError as exc:
            print(f"[ERROR] Commit aborted: {exc}", file=sys.stderr)
            return 2
    else:
        print("\n[NOTICE] Preview complete. No changes were made to market.json.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
