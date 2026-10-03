from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from app.services.ipo.metalogos_reference_refresh import (
    refresh_missing_metalogos_references,
)
from app.services.ipo.store import read_market_store


class _CalendarReferenceClient:
    def __init__(self) -> None:
        self.calls = []

    def fetch_calendar_items(self, *, target_date_str: str, max_items: int):
        self.calls.append((target_date_str, max_items))
        return [
            {
                "company_name": "진코스텍",
                "final_offer_price": 1.0,
                "market": "KONEX",
                "features": {"lockup_commitment_ratio": 99.0},
                "sources": {
                    "metalogos160": {
                        "url": "https://metalogos.ai/160ipo/stock/B202605999",
                        "attractiveness_score": 88,
                        "demand_participant_count_reference": 2405,
                        "lockup_participant_count_reference": 797,
                        "tradable_share_ratio_reference": 34.5,
                    }
                },
            },
            {
                "company_name": "다른회사",
                "sources": {
                    "metalogos160": {
                        "url": "https://metalogos.ai/160ipo/stock/OTHER",
                        "attractiveness_score": 99,
                    }
                },
            },
        ]


def test_calendar_fallback_copies_only_reference_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        market_file = Path(tmp) / "market.json"
        market_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "ipos": [
                        {
                            "ipo_id": "jinco",
                            "company_name": "진코스텍",
                            "subscription_start": "2026-10-02",
                            "subscription_end": "2026-10-06",
                            "final_offer_price": 23500.0,
                            "market": "KOSDAQ",
                            "features": {
                                "institutional_competition_ratio": 1100.0,
                            },
                            "sources": {},
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        client = _CalendarReferenceClient()
        with patch("app.services.ipo.store.get_market_file", return_value=market_file):
            result = refresh_missing_metalogos_references(
                target_date_str="2026-10-03",
                client=client,
                max_items=24,
            )
            saved = read_market_store()["ipos"][0]

    assert result == {
        "status": "ok",
        "candidates": 1,
        "matched": 1,
        "unmatched": 0,
        "scan_limit": 24,
    }
    assert client.calls == [("2026-10-03", 24)]
    assert saved["final_offer_price"] == 23500.0
    assert saved["market"] == "KOSDAQ"
    assert saved["features"] == {"institutional_competition_ratio": 1100.0}
    reference = saved["sources"]["metalogos160"]
    assert reference["attractiveness_score"] == 88
    assert reference["lockup_participant_count_reference"] == 797
    assert "lockup_commitment_ratio" not in reference


def test_existing_metalogos_reference_skips_fallback_network():
    with tempfile.TemporaryDirectory() as tmp:
        market_file = Path(tmp) / "market.json"
        market_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "ipos": [
                        {
                            "ipo_id": "jinco",
                            "company_name": "진코스텍",
                            "subscription_start": "2026-10-02",
                            "sources": {
                                "metalogos160": {
                                    "url": "https://metalogos.ai/160ipo/stock/B202605999"
                                }
                            },
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        client = _CalendarReferenceClient()
        with patch("app.services.ipo.store.get_market_file", return_value=market_file):
            result = refresh_missing_metalogos_references(
                target_date_str="2026-10-03",
                client=client,
            )

    assert result == {"status": "not_needed", "candidates": 0, "matched": 0}
    assert client.calls == []
