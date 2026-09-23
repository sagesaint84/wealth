from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from typing import Any

from app.services.ipo.features import (
    FEATURE_WEIGHTS,
    CORE_MANDATORY_FEATURES,
    calculate_pricing_discipline_score,
    calculate_relative_valuation_score,
    compute_derived_features,
)
from app.services.ipo.normalize import select_cohort, normalize_feature_value
from app.services.ipo.identity import is_spac_ipo


def normalize_observation_date(value: object) -> date | None:
    """Parse only recognized source-date encodings for point-in-time checks.

    DART commonly returns ``YYYYMMDD`` while canonical IPO records use ISO
    dates.  Comparing those encodings lexicographically incorrectly treats a
    same-day observation as future information.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    candidates = (raw, raw[:10], raw[:8])
    for candidate in candidates:
        try:
            if re.fullmatch(r"\d{8}", candidate):
                return datetime.strptime(candidate, "%Y%m%d").date()
            if re.fullmatch(r"\d{8}\d{6}", candidate):
                return datetime.strptime(candidate, "%Y%m%d%H%M%S").date()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
                return date.fromisoformat(candidate)
            if "T" in candidate:
                return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def determine_grade(score: float | None) -> str | None:
    if score is None:
        return None
    s = round(score, 1)
    if s >= 80.0:
        return "A"
    elif s >= 65.0:
        return "B"
    elif s >= 50.0:
        return "C"
    elif s >= 35.0:
        return "D"
    else:
        return "E"


def calculate_wealth_ipo_score(
    current_ipo: dict[str, Any],
    all_ipos: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate Wealth IPO Score v1.0.

    Strict rules:
    - Core mandatory features must all be present; otherwise status = '산정중' (calculating).
    - Missing optional features receive neutral score = 50.0 (no weight redistribution).
    - Coverage must be >= 75% for formal score; otherwise '산정중'.
    - Output status remains 'BETA' until backtest dataset proves PASS.
    """
    ipo_copy = dict(current_ipo)

    # SPACs require a separate evaluation framework.
    # Legacy snapshots can lack listing_track, so retain the domain's safe
    # company-name fallback as well.
    if is_spac_ipo(ipo_copy):
        return {
            "score": None,
            "grade": None,
            "coverage": None,
            "confidence_level": "not_applicable",
            "status": "NOT_APPLICABLE",
            "is_calculating": False,
            "reason": "SPAC requires a separate evaluation framework",
            "core_missing": [],
            "component_scores": {},
            "feature_scores": {},
            "score_label": "별도평가",
            "score_as_of": None,
            "score_version": "v1.0",
        }

    features = dict(ipo_copy.get("features", {}) or {})

    # Compute derived features (pricing_discipline, tradable_market_cap_krw)
    derived = compute_derived_features(ipo_copy)
    for k, v in derived.items():
        if k not in features or features[k].get("status") != "ok":
            features[k] = v

    # Determine score_as_of (day before subscription_start at 23:59:59 KST)
    sub_date = str(ipo_copy.get("subscription_start") or "")[:10]
    as_of_date = ""
    score_as_of = None
    if sub_date:
        try:
            dt = datetime.strptime(sub_date, "%Y-%m-%d").date()
            as_of_date = (dt - timedelta(days=1)).isoformat()
            score_as_of = f"{as_of_date}T23:59:59+09:00"
        except ValueError:
            pass

    # Helper to check if a feature is validly observed prior to score_as_of
    def _is_feature_observed(feat_name: str) -> tuple[bool, float | None]:
        feat_item = features.get(feat_name)
        if not isinstance(feat_item, dict) or feat_item.get("status") != "ok" or feat_item.get("value") is None:
            return False, None

        # Provenance date check: prevent future data leakage (e.g. securities reports filed after subscription)
        src_date = feat_item.get("source_date")
        if src_date and as_of_date:
            src_day = normalize_observation_date(src_date)
            as_of_day = normalize_observation_date(as_of_date)
            # A supplied but malformed provenance date is not trustworthy.
            if src_day is None or as_of_day is None or src_day > as_of_day:
                return False, None

        try:
            return True, float(feat_item["value"])
        except (ValueError, TypeError):
            return False, None

    # 1. Check Core Mandatory Features
    core_missing = []
    for core_feat in CORE_MANDATORY_FEATURES:
        valid, _ = _is_feature_observed(core_feat)
        if not valid:
            core_missing.append(core_feat)

    # 2. Check Observed Features & Coverage
    observed_weight = 0
    feature_scores: dict[str, float] = {}

    # Select point-in-time cohort
    cohort = select_cohort(ipo_copy, all_ipos)
    cohort_inst = select_cohort(ipo_copy, all_ipos, for_institutional_regime=True)

    for feat_name, weight in FEATURE_WEIGHTS.items():
        is_observed, raw_val = _is_feature_observed(feat_name)
        if is_observed and raw_val is not None:
            observed_weight += weight

            # Direct formula features
            if feat_name == "pricing_discipline":
                score_0_100 = raw_val
            elif feat_name == "relative_valuation":
                # Critical bug fix: 0.0 is a valid score! Never use 'or 50.0'
                val_score = calculate_relative_valuation_score(raw_val)
                score_0_100 = 50.0 if val_score is None else val_score
            # Institutional regime cohort
            elif feat_name in ("lockup_commitment_ratio", "institutional_competition_ratio", "high_bid_ratio"):
                score_0_100 = normalize_feature_value(feat_name, raw_val, cohort_inst)
            # General cohort
            else:
                score_0_100 = normalize_feature_value(feat_name, raw_val, cohort)
        else:
            # Missing optional features receive neutral 50.0
            score_0_100 = 50.0

        feature_scores[feat_name] = round(score_0_100, 2)

    coverage = round((observed_weight / 100.0) * 100.0, 1)

    # Confidence level based on coverage
    if coverage >= 90.0:
        confidence_level = "high"
    elif coverage >= 75.0:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    # If any core feature missing or coverage < 75%: calculating ('산정중')
    if core_missing or coverage < 75.0:
        return {
            "score": None,
            "grade": None,
            "coverage": coverage,
            "confidence_level": confidence_level,
            "status": "BETA",
            "is_calculating": True,
            "reason": f"Core features missing: {', '.join(core_missing)}" if core_missing else "Insufficient coverage (<75%)",
            "core_missing": core_missing,
            "component_scores": {},
            "feature_scores": feature_scores,
            "score_label": "산정중",
            "score_as_of": score_as_of,
            "score_version": "v1.0",
        }

    # Calculate weighted total score
    total_score = 0.0
    for feat_name, weight in FEATURE_WEIGHTS.items():
        total_score += (feature_scores[feat_name] / 100.0) * weight

    final_score = round(min(100.0, max(0.0, total_score)), 1)
    grade = determine_grade(final_score)

    # Component scores
    comp_scores = {
        "institutional_demand": round(
            (feature_scores["lockup_commitment_ratio"] * 15 +
             feature_scores["institutional_competition_ratio"] * 10 +
             feature_scores["high_bid_ratio"] * 10) / 100.0, 1
        ),
        "supply_structure": round(
            (feature_scores["tradable_share_ratio"] * 15 +
             feature_scores["tradable_market_cap_krw"] * 7 +
             feature_scores["secondary_sale_ratio"] * 5 +
             feature_scores["unlock_3m_ratio"] * 3) / 100.0, 1
        ),
        "valuation": round(
            (feature_scores["pricing_discipline"] * 8 +
             feature_scores["relative_valuation"] * 7) / 100.0, 1
        ),
        "fundamentals": round(
            (feature_scores["revenue_cagr"] * 4 +
             feature_scores["operating_margin"] * 3 +
             feature_scores["net_debt_to_assets"] * 3) / 100.0, 1
        ),
        "market_environment": round(
            (feature_scores["recent_ipo_market_return"] * 6 +
             feature_scores["market_20d_return"] * 4) / 100.0, 1
        ),
    }

    return {
        "score": final_score,
        "grade": grade,
        "coverage": coverage,
        "confidence_level": confidence_level,
        "status": "BETA",
        "is_calculating": False,
        "component_scores": comp_scores,
        "feature_scores": feature_scores,
        "core_missing": [],
        "score_label": f"{final_score}점 · {grade}",
        "score_as_of": score_as_of,
        "score_version": "v1.0",
    }
