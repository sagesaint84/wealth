from __future__ import annotations

import math
from typing import Any

FEATURE_WEIGHTS: dict[str, int] = {
    # 1. Institutional Demand (35)
    "lockup_commitment_ratio": 15,
    "institutional_competition_ratio": 10,
    "high_bid_ratio": 10,
    # 2. Supply / Float Structure (30)
    "tradable_share_ratio": 15,
    "tradable_market_cap_krw": 7,
    "secondary_sale_ratio": 5,
    "unlock_3m_ratio": 3,
    # 3. Valuation & Pricing (15)
    "pricing_discipline": 8,
    "relative_valuation": 7,
    # 4. Fundamentals (10)
    "revenue_cagr": 4,
    "operating_margin": 3,
    "net_debt_to_assets": 3,
    # 5. Market Environment (10)
    "recent_ipo_market_return": 6,
    "market_20d_return": 4,
}

CORE_MANDATORY_FEATURES = [
    "institutional_competition_ratio",
    "lockup_commitment_ratio",
    "tradable_share_ratio",
    "pricing_discipline",
]


def calculate_pricing_discipline_score(
    final_offer_price: float | None,
    offer_band_high: float | None,
) -> float | None:
    """Pricing discipline score (0~100 points):

    premium = max(0, (final_offer_price - offer_band_high) / offer_band_high)
    score = clamp(100 - 500 * premium, 0, 100)
    - At or below band high: 100
    - +5%: 75
    - +10%: 50
    - +15%: 25
    - +20% or higher: 0
    """
    if final_offer_price is None or offer_band_high is None or offer_band_high <= 0:
        return None

    premium = max(0.0, (final_offer_price - offer_band_high) / offer_band_high)
    raw_score = 100.0 - 500.0 * premium
    return max(0.0, min(100.0, round(raw_score, 2)))


def calculate_relative_valuation_score(valuation_ratio: float | None) -> float | None:
    """Relative valuation score mapping (0~100 points):

    valuation_ratio = issuer_multiple / peer_median_multiple
    - <= 0.80 -> 100
    - 1.00 -> 70
    - 1.20 -> 30
    - >= 1.40 -> 0
    Linear interpolation between breakpoints.
    """
    if valuation_ratio is None or valuation_ratio <= 0:
        return None

    r = float(valuation_ratio)
    if r <= 0.80:
        return 100.0
    elif r <= 1.00:
        # 0.80 to 1.00 maps from 100 down to 70
        return round(100.0 - (r - 0.80) / 0.20 * 30.0, 2)
    elif r <= 1.20:
        # 1.00 to 1.20 maps from 70 down to 30
        return round(70.0 - (r - 1.00) / 0.20 * 40.0, 2)
    elif r <= 1.40:
        # 1.20 to 1.40 maps from 30 down to 0
        return round(30.0 - (r - 1.20) / 0.20 * 30.0, 2)
    else:
        return 0.0


def compute_derived_features(ipo_dict: dict[str, Any]) -> dict[str, Any]:
    """Calculate derived features like tradable_market_cap_krw and pricing_discipline."""
    derived: dict[str, Any] = {}

    offer_price = ipo_dict.get("final_offer_price")
    band_high = ipo_dict.get("offer_band_high")

    # 1. pricing_discipline
    p_disc_score = calculate_pricing_discipline_score(offer_price, band_high)
    # Provenance: later of final_offer_price source_date and offer_band_high source_date
    sources_dict = ipo_dict.get("sources", {}) or {}
    f_price_src = sources_dict.get("final_offer_price", {}).get("source_date") or ipo_dict.get("final_offer_price_source_date")
    b_high_src = sources_dict.get("offer_band_high", {}).get("source_date") or ipo_dict.get("offer_band_high_source_date")
    p_disc_src_dates = [str(d)[:10] for d in [f_price_src, b_high_src] if d]
    p_disc_source_date = max(p_disc_src_dates) if p_disc_src_dates else None

    if p_disc_score is not None:
        derived["pricing_discipline"] = {
            "value": p_disc_score,
            "status": "ok",
            "source": "derived",
            "confidence": "high",
            "source_date": p_disc_source_date,
        }
    else:
        derived["pricing_discipline"] = {
            "value": None,
            "status": "missing",
            "source": "derived",
            "confidence": "none",
            "source_date": p_disc_source_date,
        }

    # 2. tradable_market_cap_krw
    features = ipo_dict.get("features", {}) or {}
    tradable_ratio_item = features.get("tradable_share_ratio", {})
    tradable_ratio_val = tradable_ratio_item.get("value") if isinstance(tradable_ratio_item, dict) else None
    tradable_ratio_src = tradable_ratio_item.get("source_date") if isinstance(tradable_ratio_item, dict) else None
    post_offer_shares = ipo_dict.get("post_offer_shares")
    post_shares_src = sources_dict.get("post_offer_shares", {}).get("source_date") or ipo_dict.get("post_offer_shares_source_date")

    cap_src_dates = [str(d)[:10] for d in [tradable_ratio_src, f_price_src, post_shares_src] if d]
    cap_source_date = max(cap_src_dates) if cap_src_dates else None

    if tradable_ratio_val is not None and post_offer_shares and offer_price:
        tradable_shares = (tradable_ratio_val / 100.0) * float(post_offer_shares)
        tradable_cap = tradable_shares * float(offer_price)
        derived["tradable_market_cap_krw"] = {
            "value": round(tradable_cap, 0),
            "status": "ok",
            "source": "derived",
            "confidence": "high",
            "source_date": cap_source_date,
        }
    else:
        derived["tradable_market_cap_krw"] = {
            "value": None,
            "status": "missing",
            "source": "derived",
            "confidence": "none",
            "source_date": cap_source_date,
        }

    return derived
