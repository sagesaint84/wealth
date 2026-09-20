from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class IpoRecord:
    ipo_id: str
    company_name: str = ""
    corp_code: str | None = None
    stock_code: str | None = None
    market: str | None = None
    listing_track: str = "general"

    demand_forecast_start: str | None = None
    demand_forecast_end: str | None = None

    subscription_start: str | None = None
    subscription_end: str | None = None

    payment_date: str | None = None
    refund_date: str | None = None

    expected_listing_date: str | None = None
    actual_listing_date: str | None = None

    offer_band_low: float | None = None
    offer_band_high: float | None = None
    final_offer_price: float | None = None

    offer_shares: int | float | None = None
    secondary_shares: int | float | None = None
    post_offer_shares: int | float | None = None

    lead_managers: list[str] = field(default_factory=list)

    features: dict[str, Any] = field(default_factory=dict)
    score: dict[str, Any] = field(default_factory=dict)

    sources: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IpoRecord:
        valid_keys = {
            "ipo_id", "company_name", "corp_code", "stock_code", "market", "listing_track",
            "demand_forecast_start", "demand_forecast_end", "subscription_start", "subscription_end",
            "payment_date", "refund_date", "expected_listing_date", "actual_listing_date",
            "offer_band_low", "offer_band_high", "final_offer_price",
            "offer_shares", "secondary_shares", "post_offer_shares",
            "lead_managers", "features", "score", "sources", "updated_at",
        }
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        if "lead_managers" in filtered and not isinstance(filtered["lead_managers"], list):
            filtered["lead_managers"] = []
        if "features" in filtered and not isinstance(filtered["features"], dict):
            filtered["features"] = {}
        if "score" in filtered and not isinstance(filtered["score"], dict):
            filtered["score"] = {}
        if "sources" in filtered and not isinstance(filtered["sources"], dict):
            filtered["sources"] = {}
        return cls(**filtered)


@dataclass
class FamilyIpoApplication:
    target_owners: list[str] = field(default_factory=list)
    applied_owners: list[str] = field(default_factory=list)
    applicants: dict[str, dict[str, Any]] = field(default_factory=dict)
    target_frozen_at: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FamilyIpoApplication:
        return cls(
            target_owners=list(data.get("target_owners") or []),
            applied_owners=list(data.get("applied_owners") or []),
            applicants=dict(data.get("applicants") or {}),
            target_frozen_at=data.get("target_frozen_at"),
            updated_at=str(data.get("updated_at") or datetime.now().astimezone().isoformat()),
        )
