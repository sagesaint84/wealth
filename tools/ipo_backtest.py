#!/usr/bin/env python3
"""Wealth IPO Backtest Engine & CLI (tools/ipo_backtest.py).

Evaluates Wealth IPO Score v1.0 walk-forward on historical Korean IPO listings (post 2021-07-01).
Strictly prevents future data leakage by freezing cohorts as of subscription_start - 1d 23:59:59 KST.

Rigorous Acceptance Criteria for Production Promotion (All required):
  1. Evaluation universe >= 200 eligible IPOs (post 2021-07-01, excluding SPAC/REIT/etc.)
  2. Core feature availability >= 95%
  3. Score coverage >= 85%
  4. Manual validation (50 sample cases): Date/Price accuracy >= 98%
  5. Manual validation (50 sample cases): Score feature accuracy >= 95%
  6. Spearman rank correlation: Score vs Day 1 Close Return (R0) >= 0.20
  7. Spearman rank correlation: Score vs 1 Month Return (R1M) >= 0.12
  8. Top 20% - Bottom 20% R0 median spread >= +20%p
  9. Top 20% - Bottom 20% R1M median spread >= +10%p
  10. Top 20% R0 loss probability reduction >= 25% relative to overall
  11. Top 20% R1M loss probability reduction >= 15% relative to overall
  12. Quarterly consistency: Top 20% median > Bottom 20% median in >= 70% of quarters
  13. Bootstrap 95% CI for (Top 20% - Bottom 20% R0 spread): lower bound > 0
  14. Market regimes (R1/R2/R3): Top 20% - Bottom 20% R0 spread > 0 for all regimes with >= 20 samples
  * Note: R3M return correlation & spread are calculated and reported, but are not an acceptance criterion.

Safety Rule:
  If real historical dataset or manual validation data is missing,
  NEVER claim PRODUCTION. Output 'BACKTEST DATA NOT AVAILABLE' or
  'VALIDATION INCOMPLETE' and keep Score status as 'BETA'.
  Synthetic data is for CLI validation only and cannot promote to PRODUCTION.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import random
import sys
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.ipo.features import CORE_MANDATORY_FEATURES
from app.services.ipo.score import calculate_wealth_ipo_score

EXCLUDED_NAME_KEYWORDS = ["스팩", "SPAC", "리츠", "REIT", "우선주", "합병", "직상장", "재상장", "이전상장"]
EXCLUDED_TRACKS = {"spac", "reit", "transfer", "relisting", "merger", "direct"}


def is_excluded_from_universe(record: dict[str, Any]) -> bool:
    """Universe filter: Excludes SPAC, REIT, transfer, relisting, preferred stock, merger, direct."""
    name = str(record.get("company_name", "")).strip()
    track = str(record.get("listing_track", "")).strip().lower()
    sec_type = str(record.get("security_type", "")).strip()

    if track in EXCLUDED_TRACKS:
        return True
    if any(k in name for k in EXCLUDED_NAME_KEYWORDS):
        return True
    if name.endswith("우") or name.endswith("우B"):
        return True
    if sec_type and not any(valid in sec_type for valid in ["보통주", "주권", "일반", "common"]):
        if any(bad in sec_type for bad in ["우선주", "스팩", "리츠", "채권"]):
            return True
    return False


def spearman_correlation(x: list[float], y: list[float]) -> float:
    """Calculate Spearman rank correlation coefficient between x and y."""
    n = len(x)
    if n < 2 or len(y) != n:
        return 0.0

    def rank_array(arr: list[float]) -> list[float]:
        sorted_indices = sorted(range(n), key=lambda idx: arr[idx])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and arr[sorted_indices[j]] == arr[sorted_indices[j + 1]]:
                j += 1
            avg_rank = 1.0 + (i + j) / 2.0
            for k in range(i, j + 1):
                ranks[sorted_indices[k]] = avg_rank
            i = j + 1
        return ranks

    rx = rank_array(x)
    ry = rank_array(y)

    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n

    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - mean_ry) ** 2 for i in range(n)))

    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def calculate_median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def bootstrap_ci_diff(
    top_vals: list[float],
    bot_vals: list[float],
    n_resamples: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Computes 95% bootstrap confidence interval for (median(top) - median(bottom))."""
    if not top_vals or not bot_vals:
        return 0.0, 0.0
    rng = random.Random(seed)
    diffs: list[float] = []
    n_top = len(top_vals)
    n_bot = len(bot_vals)
    for _ in range(n_resamples):
        s_top = [top_vals[rng.randint(0, n_top - 1)] for _ in range(n_top)]
        s_bot = [bot_vals[rng.randint(0, n_bot - 1)] for _ in range(n_bot)]
        diffs.append(calculate_median(s_top) - calculate_median(s_bot))
    diffs.sort()
    lower_idx = int(0.025 * n_resamples)
    upper_idx = int(0.975 * n_resamples)
    return diffs[lower_idx], diffs[upper_idx]


def evaluate_quarterly_consistency(scored_items: list[dict[str, Any]]) -> tuple[float, int, int]:
    """Evaluate if Top 20% median > Bottom 20% median across quarterly folds."""
    quarters: dict[str, list[dict[str, Any]]] = {}
    for item in scored_items:
        dt_str = item.get("subscription_start") or item.get("listing_date") or ""
        if len(dt_str) >= 7:
            y = dt_str[:4]
            m = int(dt_str[5:7])
            q = (m - 1) // 3 + 1
            key = f"{y}Q{q}"
            quarters.setdefault(key, []).append(item)

    consistent_quarters = 0
    evaluated_quarters = 0

    for q_name, items in sorted(quarters.items()):
        if len(items) < 4:
            continue
        sorted_items = sorted(items, key=lambda it: it["score"])
        k = max(1, math.floor(len(sorted_items) * 0.20))
        bot_group = [it["R0"] for it in sorted_items[:k]]
        top_group = [it["R0"] for it in sorted_items[-k:]]
        if calculate_median(top_group) > calculate_median(bot_group):
            consistent_quarters += 1
        evaluated_quarters += 1

    rate = (consistent_quarters / evaluated_quarters) * 100.0 if evaluated_quarters > 0 else 0.0
    return rate, consistent_quarters, evaluated_quarters


def generate_synthetic_dataset(count: int = 250) -> list[dict[str, Any]]:
    """Generates synthetic IPO records for verification purposes only."""
    rng = random.Random(42)
    records = []
    base_year = 2022
    for i in range(count):
        month = (i % 36) + 1
        y = base_year + (month - 1) // 12
        m = ((month - 1) % 12) + 1
        sub_start = f"{y:04d}-{m:02d}-10"
        listing_date = f"{y:04d}-{m:02d}-22"

        quality = rng.uniform(20.0, 90.0)
        comp = quality * 18.0 + rng.uniform(-50, 50)
        lockup = (quality / 100.0) * 45.0 + rng.uniform(-3, 3)
        high_bid = min(100.0, max(50.0, quality + rng.uniform(-8, 8)))
        tradable = max(10.0, 55.0 - (quality / 2.0) + rng.uniform(-4, 4))
        r0 = (quality - 50.0) * 1.0 + rng.uniform(-10, 10)
        r1m = (quality - 50.0) * 0.6 + rng.uniform(-15, 15)
        r3m = (quality - 50.0) * 0.4 + rng.uniform(-20, 20)

        records.append({
            "ipo_id": f"synth-{i:04d}",
            "company_name": f"Synthetic_{i}",
            "market": "KOSDAQ",
            "listing_track": "general",
            "subscription_start": sub_start,
            "listing_date": listing_date,
            "final_offer_price": 10000.0,
            "offer_band_high": 10000.0,
            "features": {
                "institutional_competition_ratio": {"value": max(1.0, comp), "status": "ok"},
                "lockup_commitment_ratio": {"value": max(0.0, lockup), "status": "ok"},
                "high_bid_ratio": {"value": high_bid, "status": "ok"},
                "tradable_share_ratio": {"value": tradable, "status": "ok"},
                "pricing_discipline": {"value": 100.0, "status": "ok"},
                "secondary_sale_ratio": {"value": 0.0, "status": "ok"},
                "unlock_3m_ratio": {"value": 5.0, "status": "ok"},
                "relative_valuation": {"value": 0.9, "status": "ok"},
                "revenue_cagr": {"value": 25.0, "status": "ok"},
                "operating_margin": {"value": 15.0, "status": "ok"},
                "net_debt_to_assets": {"value": -5.0, "status": "ok"},
                "recent_ipo_market_return": {"value": 25.0, "status": "ok"},
                "market_20d_return": {"value": 3.0, "status": "ok"},
            },
            "returns": {
                "R0": r0,
                "R1M": r1m,
                "R3M": r3m,
            },
        })
    return records


def run_backtest(
    data_path: Path | None = None,
    synthetic_test: bool = False,
    manual_validation_path: Path | None = None,
) -> dict[str, Any]:
    default_data_path = BASE_DIR / "data" / "ipo" / "backtest_dataset.json"
    target_path = data_path or default_data_path

    is_real_data = False
    records: list[dict[str, Any]] = []

    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                records = json.load(f)
            is_real_data = True
        except Exception as e:
            print(f"Error reading dataset at {target_path}: {e}")
            records = []
    elif synthetic_test:
        records = generate_synthetic_dataset(250)
        is_real_data = False
    else:
        print("=" * 70)
        print("BACKTEST DATA NOT AVAILABLE")
        print(f"Target path '{target_path}' not found.")
        print("Wealth IPO Score v1 remains in status: BETA")
        print("External crawling is prohibited. Score remains BETA.")
        print("=" * 70)
        return {
            "status": "BACKTEST DATA NOT AVAILABLE",
            "score_status": "BETA",
            "sample_count": 0,
            "message": "Local historical dataset not found. External crawling prohibited. Score remains BETA.",
        }

    # Filter universe (Exclude SPAC, REIT, relisting, transfer, etc. and post 2021-07-01)
    eligible_records = [
        r for r in records
        if not is_excluded_from_universe(r)
        and (r.get("subscription_start") or r.get("listing_date") or "") >= "2021-07-01"
    ]

    # Strictly sort by subscription_start ascending to prevent any future data leakage
    eligible_records.sort(
        key=lambda r: (
            r.get("subscription_start") or "9999-99-99",
            r.get("listing_date") or "9999-99-99",
            r.get("ipo_id") or "",
        )
    )

    total_eligible = len(eligible_records)
    if total_eligible == 0:
        print("BACKTEST DATA NOT AVAILABLE: 0 eligible records post 2021-07-01.")
        return {
            "status": "BACKTEST DATA NOT AVAILABLE",
            "score_status": "BETA",
            "sample_count": 0,
        }

    scored_items: list[dict[str, Any]] = []
    core_available_count = 0
    scored_count = 0

    for i, r in enumerate(eligible_records):
        feat = r.get("features", {})
        ret = r.get("returns", {})

        # Core availability check using canonical CORE_MANDATORY_FEATURES (4 features)
        has_core = all(feat.get(k, {}).get("value") is not None for k in CORE_MANDATORY_FEATURES)
        if has_core:
            core_available_count += 1

        # Strictly point-in-time past cohort: only records with subscription_start strictly prior to current
        cur_sub_start = r.get("subscription_start") or ""
        past_cohort = [
            c for c in eligible_records
            if (c.get("subscription_start") or "") < cur_sub_start
        ]

        # Score calculation uses operational score engine
        res = calculate_wealth_ipo_score(r, past_cohort)

        if not res.get("is_calculating") and res.get("score") is not None:
            scored_count += 1
            if ret.get("R0") is not None and ret.get("R1M") is not None:
                scored_items.append({
                    "record": r,
                    "score": float(res["score"]),
                    "R0": float(ret["R0"]),
                    "R1M": float(ret["R1M"]),
                    "R3M": float(ret.get("R3M", 0.0)),
                    "subscription_start": cur_sub_start,
                    "listing_date": r.get("listing_date", ""),
                })

    core_rate = (core_available_count / total_eligible) * 100.0 if total_eligible > 0 else 0.0
    score_coverage_rate = (scored_count / total_eligible) * 100.0 if total_eligible > 0 else 0.0

    scores = [it["score"] for it in scored_items]
    r0_list = [it["R0"] for it in scored_items]
    r1m_list = [it["R1M"] for it in scored_items]
    r3m_list = [it["R3M"] for it in scored_items]

    rho_r0 = spearman_correlation(scores, r0_list)
    rho_r1m = spearman_correlation(scores, r1m_list)
    rho_r3m = spearman_correlation(scores, r3m_list)

    # Top 20% vs Bottom 20% evaluation
    n_scored = len(scored_items)
    k_top = max(1, int(n_scored * 0.20)) if n_scored >= 5 else 0

    sorted_by_score = sorted(scored_items, key=lambda it: it["score"])
    bottom_group = sorted_by_score[:k_top]
    top_group = sorted_by_score[-k_top:]

    top_r0 = [it["R0"] for it in top_group]
    bot_r0 = [it["R0"] for it in bottom_group]
    top_r1m = [it["R1M"] for it in top_group]
    bot_r1m = [it["R1M"] for it in bottom_group]

    top_bot_r0_median_diff = calculate_median(top_r0) - calculate_median(bot_r0)
    top_bot_r1m_median_diff = calculate_median(top_r1m) - calculate_median(bot_r1m)

    # Loss probability reduction
    overall_r0_loss_rate = (sum(1 for r in r0_list if r < 0) / n_scored) if n_scored > 0 else 0.0
    top_r0_loss_rate = (sum(1 for r in top_r0 if r < 0) / len(top_r0)) if top_r0 else 0.0
    r0_loss_reduction = ((overall_r0_loss_rate - top_r0_loss_rate) / overall_r0_loss_rate) if overall_r0_loss_rate > 0 else 0.0

    overall_r1m_loss_rate = (sum(1 for r in r1m_list if r < 0) / n_scored) if n_scored > 0 else 0.0
    top_r1m_loss_rate = (sum(1 for r in top_r1m if r < 0) / len(top_r1m)) if top_r1m else 0.0
    r1m_loss_reduction = ((overall_r1m_loss_rate - top_r1m_loss_rate) / overall_r1m_loss_rate) if overall_r1m_loss_rate > 0 else 0.0

    # Quarterly consistency
    q_rate, q_pos, q_total = evaluate_quarterly_consistency(scored_items)

    # Bootstrap 95% CI for R0 Top - Bottom median
    ci_lower, ci_upper = bootstrap_ci_diff(top_r0, bot_r0)

    # Market Regimes (R1: 2021-07-01 ~ 2025-06-30, R2: 2025-07-01 ~ 2025-12-31, R3: 2026-01-01 ~)
    regimes = {
        "R1": [it for it in scored_items if "2021-07-01" <= (it.get("subscription_start") or it.get("listing_date") or "") <= "2025-06-30"],
        "R2": [it for it in scored_items if "2025-07-01" <= (it.get("subscription_start") or it.get("listing_date") or "") <= "2025-12-31"],
        "R3": [it for it in scored_items if (it.get("subscription_start") or it.get("listing_date") or "") >= "2026-01-01"],
    }
    regime_results = {}
    meets_regimes = True
    for r_name, r_items in regimes.items():
        n_r = len(r_items)
        if n_r >= 20:
            s_r = sorted(r_items, key=lambda it: it["score"])
            k_r = max(1, math.floor(n_r * 0.20))
            top_r = [it["R0"] for it in s_r[-k_r:]]
            bot_r = [it["R0"] for it in s_r[:k_r:]]
            spread = calculate_median(top_r) - calculate_median(bot_r)
            pos = spread > 0.0
            if not pos:
                meets_regimes = False
            regime_results[r_name] = {"sample_count": n_r, "spread": round(spread, 2), "status": "PASS" if pos else "FAIL"}
        else:
            regime_results[r_name] = {"sample_count": n_r, "status": "insufficient_sample"}

    # Check and calculate manual validation data
    has_manual_validation = False
    manual_val_stats = {"sample_count": 0, "date_price_accuracy": 0.0, "feature_accuracy": 0.0}
    mv_path = manual_validation_path or (BASE_DIR / "data" / "ipo" / "manual_validation_50.json")
    if mv_path.exists():
        try:
            with open(mv_path, "r", encoding="utf-8") as f:
                mv_data = json.load(f)
            if isinstance(mv_data, list):
                n_mv = len(mv_data)
                date_price_ok = sum(1 for row in mv_data if bool(row.get("date_price_correct", False)))
                feat_ok = sum(1 for row in mv_data if bool(row.get("feature_correct", False)))
                dp_acc = (date_price_ok / n_mv) if n_mv > 0 else 0.0
                f_acc = (feat_ok / n_mv) if n_mv > 0 else 0.0
                manual_val_stats = {
                    "sample_count": n_mv,
                    "date_price_accuracy": round(dp_acc * 100, 2),
                    "feature_accuracy": round(f_acc * 100, 2),
                }
                if n_mv >= 50 and dp_acc >= 0.98 and f_acc >= 0.95:
                    has_manual_validation = True
        except Exception as e:
            print(f"Error parsing manual validation file: {e}")

    # Criteria evaluations
    meets_universe = total_eligible >= 200
    meets_core = core_rate >= 95.0
    meets_coverage = score_coverage_rate >= 85.0
    meets_spearman_r0 = rho_r0 >= 0.20
    meets_spearman_r1m = rho_r1m >= 0.12
    meets_median_r0 = top_bot_r0_median_diff >= 20.0
    meets_median_r1m = top_bot_r1m_median_diff >= 10.0
    meets_loss_r0 = r0_loss_reduction >= 0.25
    meets_loss_r1m = r1m_loss_reduction >= 0.15
    meets_quarterly = q_rate >= 70.0
    meets_ci = ci_lower > 0.0

    all_criteria_passed = all([
        meets_universe,
        meets_core,
        meets_coverage,
        meets_spearman_r0,
        meets_spearman_r1m,
        meets_median_r0,
        meets_median_r1m,
        meets_loss_r0,
        meets_loss_r1m,
        meets_quarterly,
        meets_ci,
        meets_regimes,
        has_manual_validation,
        is_real_data,
    ])

    print("=" * 70)
    print("WEALTH IPO SCORE v1.0 WALK-FORWARD BACKTEST AUDIT")
    print("=" * 70)
    print(f"Dataset: {'REAL HISTORICAL DATA' if is_real_data else 'SYNTHETIC / TEST DATA'}")
    print(f"Total Eligible Sample (post 2021-07-01):  {total_eligible:4d} (Target >= 200: {meets_universe})")
    print(f"Core Feature Availability:              {core_rate:5.1f}% (Target >= 95%: {meets_core})")
    print(f"Score Coverage Rate:                     {score_coverage_rate:5.1f}% (Target >= 85%: {meets_coverage})")
    print(f"Spearman Score <-> R0 (Day 1):          {rho_r0:6.3f} (Target >= 0.20: {meets_spearman_r0})")
    print(f"Spearman Score <-> R1M (1 Month):       {rho_r1m:6.3f} (Target >= 0.12: {meets_spearman_r1m})")
    print(f"Spearman Score <-> R3M (3 Month):       {rho_r3m:6.3f} (Reported)")
    print(f"Top 20% - Bot 20% R0 Median Spread:     +{top_bot_r0_median_diff:5.1f}%p (Target >= +20%p: {meets_median_r0})")
    print(f"Top 20% - Bot 20% R1M Median Spread:    +{top_bot_r1m_median_diff:5.1f}%p (Target >= +10%p: {meets_median_r1m})")
    print(f"Top 20% R0 Loss Rate Reduction:         {r0_loss_reduction*100:5.1f}% (Target >= 25%: {meets_loss_r0})")
    print(f"Top 20% R1M Loss Rate Reduction:        {r1m_loss_reduction*100:5.1f}% (Target >= 15%: {meets_loss_r1m})")
    print(f"Quarterly Consistency (Top > Bot):      {q_rate:5.1f}% ({q_pos}/{q_total}, Target >= 70%: {meets_quarterly})")
    print(f"Bootstrap 95% CI R0 Spread:             [{ci_lower:.1f}%p, {ci_upper:.1f}%p] (Target lower > 0: {meets_ci})")
    print(f"Regime Consistency (R1/R2/R3 >=20):     {meets_regimes} ({regime_results})")
    print(f"Manual Validation (50 samples >=98%/95%): {has_manual_validation} ({manual_val_stats})")
    print("-" * 70)

    if all_criteria_passed:
        final_score_status = "PRODUCTION"
        verdict = "PASS"
    elif is_real_data:
        final_score_status = "BETA"
        verdict = "VALIDATION INCOMPLETE"
    else:
        final_score_status = "BETA"
        verdict = "SYNTHETIC TEST ONLY (VALIDATION INCOMPLETE)"

    print(f"Overall Backtest Verdict:               {verdict}")
    print(f"Final Wealth IPO Score Status:          Wealth IPO Score v1 · {final_score_status}")
    print("=" * 70)

    return {
        "status": verdict,
        "score_status": final_score_status,
        "is_real_data": is_real_data,
        "sample_count": total_eligible,
        "core_feature_rate": round(core_rate, 2),
        "score_coverage_rate": round(score_coverage_rate, 2),
        "spearman_r0": round(rho_r0, 3),
        "spearman_r1m": round(rho_r1m, 3),
        "spearman_r3m": round(rho_r3m, 3),
        "top_bot_r0_median_diff": round(top_bot_r0_median_diff, 2),
        "top_bot_r1m_median_diff": round(top_bot_r1m_median_diff, 2),
        "r0_loss_reduction_pct": round(r0_loss_reduction * 100, 2),
        "r1m_loss_reduction_pct": round(r1m_loss_reduction * 100, 2),
        "quarterly_consistency_pct": round(q_rate, 2),
        "bootstrap_ci_95": [round(ci_lower, 2), round(ci_upper, 2)],
        "regime_results": regime_results,
        "meets_regimes": meets_regimes,
        "manual_validation_passed": has_manual_validation,
        "manual_validation_stats": manual_val_stats,
        "all_criteria_passed": all_criteria_passed,
        "criteria": {
            "universe_200": meets_universe,
            "core_rate_95": meets_core,
            "coverage_85": meets_coverage,
            "spearman_r0_020": meets_spearman_r0,
            "spearman_r1m_012": meets_spearman_r1m,
            "median_r0_20": meets_median_r0,
            "median_r1m_10": meets_median_r1m,
            "loss_r0_25": meets_loss_r0,
            "loss_r1m_15": meets_loss_r1m,
            "quarterly_70": meets_quarterly,
            "bootstrap_ci_positive": meets_ci,
            "has_manual_validation": has_manual_validation,
            "is_real_data": is_real_data,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Wealth IPO Backtest CLI")
    parser.add_argument("--data", type=str, default=None, help="Path to historical backtest dataset JSON")
    parser.add_argument("--synthetic", action="store_true", help="Run with synthetic test dataset for CLI verification")
    parser.add_argument("--manual-val", type=str, default=None, help="Path to manual validation 50-case JSON")
    args = parser.parse_args()

    data_path = Path(args.data) if args.data else None
    manual_path = Path(args.manual_val) if args.manual_val else None
    result = run_backtest(data_path=data_path, synthetic_test=args.synthetic, manual_validation_path=manual_path)
    # CLI exit code: 0 always unless unhandled crash
    sys.exit(0)


if __name__ == "__main__":
    main()
