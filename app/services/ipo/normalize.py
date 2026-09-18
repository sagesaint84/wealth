from __future__ import annotations

import math
from typing import Any


def calculate_percentile(val: float, cohort_vals: list[float]) -> float:
    """Calculate point-in-time percentile rank 0~100."""
    if not cohort_vals:
        return 50.0
    strictly_less = sum(1 for v in cohort_vals if v < val)
    equals = sum(1 for v in cohort_vals if v == val)
    pct = (strictly_less + 0.5 * equals) / len(cohort_vals) * 100.0
    return round(min(100.0, max(0.0, pct)), 2)


def get_institutional_demand_regime(date_str: str) -> str:
    """Determine institutional demand regime."""
    d = date_str[:10] if date_str else ""
    if not d or d < "2025-07-01":
        return "R1"
    elif d <= "2025-12-31":
        return "R2"
    else:
        return "R3"


def select_cohort(
    current_ipo: dict[str, Any],
    all_ipos: list[dict[str, Any]],
    for_institutional_regime: bool = False,
) -> list[dict[str, Any]]:
    """Select point-in-time cohort strictly prior to current IPO's subscription start date.

    Never includes current IPO, same-day IPOs, or future IPOs.
    """
    sub_date = str(current_ipo.get("subscription_start") or "")[:10]
    market = current_ipo.get("market")
    track = current_ipo.get("listing_track", "general")
    current_id = current_ipo.get("ipo_id")

    if not sub_date:
        return []

    # Calculate 36-month cutoff date (T - 3 years)
    try:
        from datetime import datetime
        sub_dt = datetime.strptime(sub_date, "%Y-%m-%d").date()
        try:
            cutoff_36m = sub_dt.replace(year=sub_dt.year - 3).isoformat()
        except ValueError:
            cutoff_36m = sub_dt.replace(year=sub_dt.year - 3, day=28).isoformat()
    except Exception:
        cutoff_36m = "2021-07-01"

    # Base candidate pool: strictly prior to sub_date (< sub_date), post 2021-07-01
    candidates = [
        ipo for ipo in all_ipos
        if ipo.get("ipo_id") != current_id
        and str(ipo.get("subscription_start") or "")[:10] < sub_date
        and str(ipo.get("subscription_start") or "")[:10] >= "2021-07-01"
    ]

    if for_institutional_regime:
        current_regime = get_institutional_demand_regime(sub_date)
        regime_candidates = [
            ipo for ipo in candidates
            if get_institutional_demand_regime(str(ipo.get("subscription_start") or "")) == current_regime
        ]
        if len(regime_candidates) >= 30:
            return regime_candidates
        # Fallback to general cohort selection below if regime sample < 30

    # 1. 36 months + same market + same listing_track
    strict_36m = [
        ipo for ipo in candidates
        if str(ipo.get("subscription_start") or "")[:10] >= cutoff_36m
        and (market is None or ipo.get("market") == market)
        and ipo.get("listing_track", "general") == track
    ]
    if len(strict_36m) >= 30:
        return strict_36m

    # 2. 36 months + listing_track maintained, market relaxed
    relaxed_market_36m = [
        ipo for ipo in candidates
        if str(ipo.get("subscription_start") or "")[:10] >= cutoff_36m
        and ipo.get("listing_track", "general") == track
    ]
    if len(relaxed_market_36m) >= 30:
        return relaxed_market_36m

    # 3. Fallback: all qualified candidates since 2021-07-01 strictly < sub_date
    return candidates


def normalize_feature_value(
    feature_name: str,
    raw_val: float | None,
    cohort_ipos: list[dict[str, Any]],
) -> float:
    """Normalize a feature value to a 0~100 score using point-in-time percentile rank."""
    if raw_val is None:
        return 50.0  # Optional missing neutral 50

    # Extract cohort values for this feature
    cohort_vals: list[float] = []
    for ipo in cohort_ipos:
        feats = ipo.get("features", {}) or {}
        item = feats.get(feature_name)
        if isinstance(item, dict) and item.get("status") == "ok":
            v = item.get("value")
            if v is not None and isinstance(v, (int, float)):
                cohort_vals.append(float(v))

    if not cohort_vals:
        return 50.0

    # Log1p transforms
    if feature_name == "institutional_competition_ratio":
        t_val = math.log1p(max(0.0, raw_val))
        t_cohort = [math.log1p(max(0.0, v)) for v in cohort_vals]
        return calculate_percentile(t_val, t_cohort)

    elif feature_name == "tradable_market_cap_krw":
        t_val = math.log1p(max(0.0, raw_val))
        t_cohort = [math.log1p(max(0.0, v)) for v in cohort_vals]
        pct = calculate_percentile(t_val, t_cohort)
        # P- (lower market cap is better float structure)
        return round(100.0 - pct, 2)

    # Direction P- (lower is better: 100 - P+)
    elif feature_name in ("tradable_share_ratio", "secondary_sale_ratio", "unlock_3m_ratio", "net_debt_to_assets"):
        pct = calculate_percentile(raw_val, cohort_vals)
        return round(100.0 - pct, 2)

    # Direction P+ (higher is better: P+)
    else:
        return calculate_percentile(raw_val, cohort_vals)


def normalize_equity_registration_response(raw: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Normalize OpenDART estkRs grouped response into canonical categories.

    Categories:
    - general: 일반사항
    - security_classes: 증권의 종류
    - underwriters: 인수인 정보
    - use_of_funds: 자금의 사용목적
    - sellers: 매출인에 관한 사항
    - redemption_rights: 일반청약자 환매청구권
    - unknown_groups: Any other unrecognized groups (preserved without loss)
    """
    normalized: dict[str, Any] = {
        "general": [],
        "security_classes": [],
        "underwriters": [],
        "use_of_funds": [],
        "sellers": [],
        "redemption_rights": [],
        "unknown_groups": [],
    }

    if not raw:
        return normalized

    # Raw may be a list of groups, or a dict containing group/groups/list
    groups_to_process: list[Any] = []
    if isinstance(raw, list):
        groups_to_process = raw
    elif isinstance(raw, dict):
        if "group" in raw and isinstance(raw["group"], list):
            groups_to_process = raw["group"]
        elif "groups" in raw and isinstance(raw["groups"], list):
            groups_to_process = raw["groups"]
        elif "group" in raw and isinstance(raw["group"], dict):
            groups_to_process = [raw["group"]]
        elif "list" in raw and isinstance(raw["list"], list):
            # Check if items in "list" are group objects or data row objects
            first_item = raw["list"][0] if raw["list"] else None
            if isinstance(first_item, dict) and ("title" in first_item or "group_name" in first_item or "list" in first_item):
                groups_to_process = raw["list"]
            else:
                # Flat row list fallback: inspect row fields to determine category
                for row in raw["list"]:
                    if not isinstance(row, dict):
                        continue
                    if any(k in row for k in ("sbd", "pymd", "sband", "asand")):
                        normalized["general"].append(row)
                    elif any(k in row for k in ("stksen", "stkcnt", "fv", "slprc", "slta", "slmthn")):
                        normalized["security_classes"].append(row)
                    elif any(k in row for k in ("actsen", "actnmn", "udtcnt", "udtamt", "udtprc", "udtmth")):
                        normalized["underwriters"].append(row)
                    elif any(k in row for k in ("hdr", "rl_cmp", "bfsl_hdstk", "slstk", "atsl_hdstk")):
                        normalized["sellers"].append(row)
                    else:
                        normalized["unknown_groups"].append(row)
                return normalized
        else:
            # Dict itself might be a single group or unknown
            groups_to_process = [raw]

    # Process each group item
    for grp in groups_to_process:
        if not isinstance(grp, dict):
            continue

        title = str(grp.get("title") or grp.get("group_name") or grp.get("name") or "").strip()
        items = grp.get("list")
        if items is None and "items" in grp:
            items = grp.get("items")
        if items is None:
            # The group might directly be a row or contain rows
            items = [grp]
        elif not isinstance(items, list):
            items = [items]

        # Categorize by title keywords (check specific multi-word groups before general)
        if any(k in title for k in ("환매청구권", "환매", "풋백옵션")):
            normalized["redemption_rights"].extend(items)
        elif any(k in title for k in ("자금의 사용목적", "자금의사용목적", "자금사용", "자금의 목적")):
            normalized["use_of_funds"].extend(items)
        elif any(k in title for k in ("매출인", "구주매출")):
            normalized["sellers"].extend(items)
        elif any(k in title for k in ("인수인", "주간사", "인수단", "인수회사")):
            normalized["underwriters"].extend(items)
        elif any(k in title for k in ("증권의 종류", "증권의종류", "모집매출", "모집/매출")):
            normalized["security_classes"].extend(items)
        elif any(k in title for k in ("일반사항", "공모개요", "발행개요")) or title == "일반":
            normalized["general"].extend(items)
        else:
            # Fallback by examining row keys
            matched_by_keys = False
            for row in items:
                if not isinstance(row, dict):
                    continue
                if any(k in row for k in ("sbd", "pymd", "sband", "asand")):
                    normalized["general"].append(row)
                    matched_by_keys = True
                elif any(k in row for k in ("actsen", "actnmn", "udtcnt", "udtamt")):
                    normalized["underwriters"].append(row)
                    matched_by_keys = True
                elif any(k in row for k in ("hdr", "rl_cmp", "bfsl_hdstk", "slstk")):
                    normalized["sellers"].append(row)
                    matched_by_keys = True
                elif any(k in row for k in ("stksen", "stkcnt", "slprc", "slta")):
                    normalized["security_classes"].append(row)
                    matched_by_keys = True

            if not matched_by_keys:
                normalized["unknown_groups"].append(grp)

    return normalized
