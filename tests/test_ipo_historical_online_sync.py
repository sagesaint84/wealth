from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.ipo.historical_online_sync import (
    HistoricalOnlineSyncError,
    commit_online_historical_preview,
    create_online_historical_preview,
)
from app.services.ipo.store import read_market_store, write_market_store


class FakeKrx:
    def __init__(self, rows_by_year: dict[int, list[dict]]):
        self.rows_by_year = rows_by_year
        self.calls: list[tuple[str, str]] = []

    def fetch_new_listings(self, from_date: str, to_date: str):
        self.calls.append((from_date, to_date))
        return deepcopy(self.rows_by_year[int(from_date[:4])])


def existing_record(**overrides):
    row = {
        "ipo_id": "ipo-250030",
        "company_name": "진코스텍",
        "stock_code": "250030",
        "listing_track": "general",
        "actual_listing_date": "2026-10-13",
        "final_offer_price": 12000.0,
        "market": "KOSDAQ",
        "lead_managers": ["기존증권"],
        "features": {},
        "score": {"old": True},
        "sources": {},
    }
    row.update(overrides)
    return row


def krx_row(**overrides):
    row = {
        "stock_code": "250030",
        "company_name": "진코스텍",
        "actual_listing_date": "2026-10-14",
        "final_offer_price": 13500.0,
        "market": "유가증권시장",
        "lead_managers": ["하나증권"],
    }
    row.update(overrides)
    return row


@pytest.fixture
def market_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "market.json"
        with patch("app.services.ipo.store.get_market_file", return_value=path), \
             patch("app.services.ipo.store.get_ipo_data_dir", return_value=Path(tmp)):
            yield path


def seed(rows):
    write_market_store({"schema_version": 1, "updated_at": "old", "ipos": deepcopy(rows)})


def test_online_preview_and_commit_correct_authoritative_existing_fields(market_file):
    seed([existing_record()])
    krx = FakeKrx({2026: [krx_row()]})

    with patch("app.services.ipo.historical_online_sync.calculate_wealth_ipo_score", return_value={"total_score": 77}) as score:
        preview = create_online_historical_preview(
            "alice", krx_client=krx, from_year=2026, to_year=2026, today=date(2026, 10, 31)
        )
        assert preview["summary"]["updated"] == 1
        assert preview["summary"]["new"] == 0
        fields = {item["field"] for item in preview["changes"][0]["changes"]}
        assert fields == {"market", "actual_listing_date", "final_offer_price", "lead_managers"}
        assert read_market_store()["ipos"][0]["market"] == "KOSDAQ"  # preview is read-only

        result = commit_online_historical_preview(preview["preview_ticket"], "alice")

    assert result["updated"] == 1
    saved = read_market_store()["ipos"][0]
    assert saved["market"] == "KOSPI"
    assert saved["actual_listing_date"] == "2026-10-14"
    assert saved["final_offer_price"] == 13500.0
    assert saved["lead_managers"] == ["하나증권"]
    assert saved["sources"]["official_historical_online"]["source"] == "KRX_MDCSTAT20001"
    assert saved["score"] == {"total_score": 77}
    score.assert_called_once()


def test_blank_krx_fields_never_erase_existing_values(market_file):
    seed([existing_record(actual_listing_date="2026-10-14")])
    krx = FakeKrx({2026: [krx_row(final_offer_price=None, market="", lead_managers=[])]})
    preview = create_online_historical_preview(
        "alice", krx_client=krx, from_year=2026, to_year=2026, today=date(2026, 10, 31)
    )
    assert preview["summary"]["updated"] == 0
    assert preview["summary"]["unchanged"] == 1
    saved = read_market_store()["ipos"][0]
    assert saved["market"] == "KOSDAQ"
    assert saved["final_offer_price"] == 12000.0
    assert saved["lead_managers"] == ["기존증권"]


def test_name_mismatch_is_review_only_and_not_auto_corrected(market_file):
    seed([existing_record(company_name="다른회사")])
    krx = FakeKrx({2026: [krx_row()]})
    preview = create_online_historical_preview(
        "alice", krx_client=krx, from_year=2026, to_year=2026, today=date(2026, 10, 31)
    )
    assert preview["summary"]["review_required"] == 1
    assert preview["summary"]["updated"] == 0
    assert preview["issues"][0]["reason"] == "COMPANY_NAME_CONFLICT"


def test_missing_historical_record_is_added_on_confirmed_commit(market_file):
    seed([])
    krx = FakeKrx({2026: [krx_row()]})
    with patch("app.services.ipo.historical_online_sync.calculate_wealth_ipo_score", return_value={"total_score": 10}):
        preview = create_online_historical_preview(
            "alice", krx_client=krx, from_year=2026, to_year=2026, today=date(2026, 10, 31)
        )
        assert preview["summary"]["new"] == 1
        assert read_market_store()["ipos"] == []
        result = commit_online_historical_preview(preview["preview_ticket"], "alice")
    assert result["committed_new"] == 1
    saved = read_market_store()["ipos"][0]
    assert saved["stock_code"] == "250030"
    assert saved["market"] == "KOSPI"
    assert saved["sources"]["official_historical_online"]["source"] == "KRX_MDCSTAT20001"


def test_preview_queries_each_supported_year_only_when_explicitly_requested(market_file):
    seed([])
    krx = FakeKrx({
        2024: [krx_row(stock_code="240001", company_name="2024회사", actual_listing_date="2024-06-01")],
        2025: [krx_row(stock_code="250001", company_name="2025회사", actual_listing_date="2025-06-01")],
        2026: [krx_row(stock_code="260001", company_name="2026회사", actual_listing_date="2026-06-01")],
    })
    preview = create_online_historical_preview(
        "alice", krx_client=krx, from_year=2024, to_year=2026, today=date(2026, 10, 2)
    )
    assert krx.calls == [
        ("2024-01-01", "2024-12-31"),
        ("2025-01-01", "2025-12-31"),
        ("2026-01-01", "2026-10-02"),
    ]
    assert preview["summary"]["fetched"] == 3
    assert preview["summary"]["new"] == 3


def test_commit_rejects_stale_market_digest(market_file):
    seed([existing_record()])
    krx = FakeKrx({2026: [krx_row()]})
    preview = create_online_historical_preview(
        "alice", krx_client=krx, from_year=2026, to_year=2026, today=date(2026, 10, 31)
    )

    changed = read_market_store()
    changed["ipos"][0]["memo"] = "changed elsewhere"
    write_market_store(changed)

    with pytest.raises(HistoricalOnlineSyncError) as exc:
        commit_online_historical_preview(preview["preview_ticket"], "alice")
    assert exc.value.code == "PREVIEW_STALE"
    assert read_market_store()["ipos"][0]["market"] == "KOSDAQ"


def test_preview_ticket_is_user_bound(market_file):
    seed([existing_record()])
    krx = FakeKrx({2026: [krx_row()]})
    preview = create_online_historical_preview(
        "alice", krx_client=krx, from_year=2026, to_year=2026, today=date(2026, 10, 31)
    )
    with pytest.raises(HistoricalOnlineSyncError) as exc:
        commit_online_historical_preview(preview["preview_ticket"], "bob")
    assert exc.value.code == "PREVIEW_TICKET_INVALID"
