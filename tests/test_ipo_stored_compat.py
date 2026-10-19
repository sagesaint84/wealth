"""Persisted legacy shapes; all records and application links are synthetic."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import date
from unittest.mock import patch

import httpx
import pytest

from app.services.ipo.display import display_records
from app.services.ipo.presentation import present_market_store
from app.services.ipo.source_discovery import _apply_dart_schedules
from app.services.ipo import refresh_adapter as adapter
from app.services.ipo.dart_client import DartAuthError
from tests.test_ipo_schedule_lifecycle import market, events, SyntheticDart, ORIGINAL, DEMAND, WINDOW, filing


def presented(data, applications=None):
    pf = {"settings": {"ipo": {"applications": applications or {}}}}
    with patch("app.services.ipo.presentation._read_portfolio_for_presentation", return_value=pf), \
         patch("app.services.ipo.presentation.read_pnl_records_readonly", return_value=[]):
        return present_market_store("synthetic", data, date(2026, 10, 19))["ipos"]


def aliases():
    base = {"corp_code": "01000002", "stock_code": "123456", "subscription_start": "2026-10-01",
            "subscription_end": "2026-10-02", "expected_listing_date": "2026-10-20"}
    return {"ipos": [dict(base, ipo_id="old-elice", company_name="엘리스"), dict(base,
        ipo_id="official-elice", company_name="엘리스그룹", sources={"dart_schedule": {
            "rcept_no": "20261001000002", "source_date": "20261001", "company_name": "엘리스그룹"}})]}


def test_pre_deploy_dates_are_unverified_not_open_and_never_removed_from_storage():
    data = market()
    before = deepcopy(data)
    assert presented(data)[0]["market_state"] == "DATE_UNKNOWN"
    result = events(data)
    assert len(result) == 3 and all("확인 필요" in row["title"] for row in result)
    assert data == before


@pytest.mark.parametrize("source", [None, "legacy", {"dart": "legacy-url", "kind": "legacy-url"},
    {"dart_schedule_status": "legacy", "dart_schedule_verification": "legacy"}])
def test_optional_legacy_metadata_types_do_not_break_or_rewrite_records(source):
    data = market()
    data["ipos"][0]["sources"] = source
    original = deepcopy(data)
    assert presented(data)[0]["market_state"] == "DATE_UNKNOWN"
    assert len(events(data)) == 3
    assert data == original


def test_old_store_refresh_applies_notice_to_both_surfaces_then_reopens():
    data = market()
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, DEMAND]), **WINDOW)
    assert events(data) == []
    assert presented(data)[0]["market_state"] == "POSTPONED"
    assert data["ipos"][0]["subscription_start"] == "2026-10-19"
    amended = filing("20261018", "[기재정정]증권신고서(지분증권)")
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, DEMAND, amended],
        selected=amended, dates="2026.11.19 ~ 11.20"), **WINDOW)
    assert presented(data)[0]["market_state"] == "UPCOMING"
    assert [r["date"] for r in events(data) if r["type"] == "ipo_subscription"] == ["2026-11-19", "2026-11-20"]


def test_verified_normal_offering_remains_and_stale_cache_becomes_confirmation_needed():
    data = market()
    data["ipos"][0]["sources"]["dart_schedule_verification"] = {"status": "verified", "checked_date": "2026-10-19"}
    assert presented(data)[0]["market_state"] == "SUBSCRIPTION_OPEN"
    # Projection is date-injected and does not mutate the persisted verification.
    row = display_records(data["ipos"], "2026-10-20")[0]
    assert row["sources"]["dart_schedule_verification"]["reason"] == "cache_not_current"
    assert data["ipos"][0]["sources"]["dart_schedule_verification"]["status"] == "verified"


@pytest.mark.parametrize("error,reason", [(DartAuthError("synthetic"), "api_key_invalid"),
    (httpx.ConnectError("synthetic"), "network_error"), (RuntimeError("synthetic"), "refresh_failed")])
def test_transport_and_credentials_failure_reasons_are_distinct(error, reason):
    dart = SyntheticDart([ORIGINAL])
    def fail(**kwargs):
        raise error
    dart.get_filing_list = fail
    data = market()
    _apply_dart_schedules(data, dart=dart, **WINDOW)
    assert data["ipos"][0]["sources"]["dart_schedule_verification"]["reason"] == reason
    assert presented(data)[0]["market_state"] == "DATE_UNKNOWN"


def test_official_stop_refresh_still_runs_after_base_provider_failure():
    with patch.object(adapter, "_BASE_REFRESH_MARKET", side_effect=RuntimeError("synthetic portal outage")), \
         patch.object(adapter._base, "_refresh_file_lock", side_effect=lambda: nullcontext()), \
         patch.object(adapter, "discover_and_merge_primary_sources", return_value={"statuses": {"dart_schedule": "sync_ok"}}) as official, \
         patch.object(adapter, "refresh_missing_metalogos_references", return_value={}), \
         patch.object(adapter, "_targeted_dart_enrichment", return_value={}):
        result = adapter.refresh_ipo_market(username="synthetic", target_date_str="2026-10-19")
    official.assert_called_once()
    assert result["sources"]["base_refresh"] == "failed"
    assert result["sources"]["dart_schedule"] == "sync_ok"


def test_official_identifiers_deduplicate_only_display_with_application_ids_and_links_intact():
    data = aliases()
    applications = {
        "old-elice": {"applied_owners": ["A"], "applicants": {"A": {"allocation": {"quantity": 3,
            "links": [{"pnl_record_id": "kept-link", "matched_quantity": 1}]}}}},
        "official-elice": {"applied_owners": ["B"], "applicants": {"B": {"allocation": {"quantity": 2}}}},
    }
    original, original_applications = deepcopy(data), deepcopy(applications)
    rows = presented(data, applications)
    assert len(rows) == 1 and rows[0]["company_name"] == "엘리스그룹"
    assert set(rows[0]["application_record_ids"]) == {"old-elice", "official-elice"}
    assert rows[0]["user_state"] == "LINK_DATA_MISSING"
    result = events(data)
    assert len([r for r in result if r["type"] == "ipo_listing"]) == 1
    assert data == original and applications == original_applications
    once = display_records(data["ipos"], "2026-10-19")
    assert display_records(once, "2026-10-19") == once


def test_name_suffix_alone_or_conflicting_official_ids_are_not_merged():
    for conflict in ("missing", "different", "new_offering"):
        data = aliases()
        if conflict == "missing":
            for row in data["ipos"]:
                row.pop("corp_code"); row.pop("stock_code"); row.pop("sources", None)
        elif conflict == "different":
            data["ipos"][1]["corp_code"] = "99999999"
        else:
            data["ipos"][1]["subscription_start"] = "2027-10-01"
        assert len(display_records(data["ipos"], "2026-10-19")) == 2
        assert all(r["identity_review_required"] for r in display_records(data["ipos"], "2026-10-19"))


@pytest.mark.parametrize("proof", ["kind", "receipt"])
def test_legacy_kind_or_receipt_evidence_without_stock_code(proof):
    data = aliases()
    for row in data["ipos"]:
        row.pop("corp_code"); row.pop("stock_code"); row["sources"] = {}
        if proof == "kind":
            row["kind_bz_procs_no"] = "synthetic-official-202610"
        else:
            row["sources"]["dart"] = {"rcept_no": "20261001000002"}
    assert len(display_records(data["ipos"], "2026-10-19")) == 1


def test_family_checks_from_both_ids_survive_calendar_projection_without_writes():
    data = aliases()
    applications = {"applications": {"old-elice": {"applied_owners": ["A"], "all_applied": False},
        "official-elice": {"applied_owners": ["B"], "all_applied": False}}}
    from app.services.ipo.store import get_ipo_calendar_events
    with patch("app.services.ipo.store.read_market_store", return_value=data), \
         patch("app.services.ipo.applications.get_user_applications", return_value=applications), \
         patch("app.services.ipo.applications.portfolio.write_financial_json") as write:
        for owner in ("A", "B"):
            result = get_ipo_calendar_events("synthetic", "2026-10-01", "2026-10-31", owner)
            assert len(result) == 3 and all(r["meta"]["is_applied_by_owner"] for r in result)
        write.assert_not_called()
