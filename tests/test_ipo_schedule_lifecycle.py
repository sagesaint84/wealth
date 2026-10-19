"""Synthetic official notices: no credentials, market files or network reads."""
from copy import deepcopy
from datetime import date
from unittest.mock import patch

import pytest

from app.services.ipo.dart_client import DartClient
from app.services.ipo.dart_offering_schedule import dart_schedule_restriction
from app.services.ipo.source_discovery import _apply_dart_schedules, _fetch_dart_schedules, _apply_observation
from app.services.ipo.store import get_ipo_calendar_events


def filing(day, title, serial="000001"):
    return {"rcept_dt": day, "rcept_no": day + serial, "report_nm": title,
            "corp_code": "01000001", "corp_name": "유캐스트"}


ORIGINAL = filing("20260909", "증권신고서(지분증권)")
DEMAND = filing("20261001", "정정신고서제출요구 (2026.09.09. 제출 증권신고서(지분증권))")
WINDOW = {"target_date_str": "2026-10-19", "start": date(2026, 9, 1), "end": date(2026, 11, 30)}


def market():
    return {"ipos": [{"ipo_id": "synthetic-eucast", "company_name": "유캐스트",
        "corp_code": "01000001", "subscription_start": "2026-10-19",
        "subscription_end": "2026-10-20", "expected_listing_date": "2026-10-30",
        "sources": {"dart_schedule": {"source_date": "20260909", "rcept_no": ORIGINAL["rcept_no"]}}}]}


class SyntheticDart:
    def __init__(self, rows, selected=ORIGINAL, dates="2026.10.19 ~ 10.20", fail_structured=False):
        self.rows, self.selected, self.dates = rows, selected, dates
        self.fail_structured = fail_structured
        self.calls = []

    def get_filing_list(self, **kwargs):
        self.calls.append(kwargs)
        return {"list": deepcopy(self.rows), "total_page": 1}

    def get_equity_registration_statements(self, **kwargs):
        if self.fail_structured:
            raise RuntimeError("synthetic unavailable")
        return {"group": [{"title": "general", "list": [{
            **self.selected, "sbd": self.dates, "pymd": "2026.11.26"}]}]}


def events(data):
    with patch("app.services.ipo.store.read_market_store", return_value=data):
        return get_ipo_calendar_events(None, "2026-09-01", "2026-11-30")


@pytest.mark.parametrize("title,status", [
    (DEMAND["report_nm"], "postponed"),
    ("정정신고서제출요구", "postponed"),
    ("철회신고서(지분증권)", "withdrawn"), ("철회신고서", "withdrawn"),
])
def test_official_stop_suppresses_old_calendar_without_deleting_dates(title, status):
    data = market()
    before = deepcopy(data)
    dart = SyntheticDart([ORIGINAL, filing("20261001", title)])
    _apply_dart_schedules(data, dart=dart, **WINDOW)
    ipo = data["ipos"][0]
    assert ipo["sources"]["dart_schedule_status"]["status"] == status
    assert events(data) == []
    for key in ("ipo_id", "company_name", "corp_code", "subscription_start", "subscription_end"):
        assert ipo[key] == before["ipos"][0][key]
    assert dart.calls[0]["pblntf_ty"] == dart.calls[0]["pblntf_detail_ty"] == ""
    # Unofficial portal dates must never reopen the stopped schedule.
    _apply_observation(data, {"company_name": "유캐스트", "subscription_start": "2026-10-19",
        "subscription_end": "2026-10-20"}, source_name="npay")
    assert events(data) == []


@pytest.mark.parametrize("title", ["[기재정정]증권신고서(지분증권)",
    "정정신고서제출요구 (증권신고서(채무증권))", "정정신고서제출요구 (사업보고서)"])
def test_unrelated_notice_or_normal_amendment_does_not_suspend(title):
    assert dart_schedule_restriction([filing("20261001", title)]) is None
    data = market()
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, filing("20261001", title)]), **WINDOW)
    assert len([e for e in events(data) if e["type"] == "ipo_subscription"]) == 2


def test_structured_failure_still_preserves_stop_and_future_failed_refresh_cannot_reopen():
    data = market()
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, DEMAND], fail_structured=True), **WINDOW)
    assert events(data) == []
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL], fail_structured=True), **WINDOW)
    assert data["ipos"][0]["sources"]["dart_schedule_status"]["status"] == "postponed"
    assert events(data) == []


def test_newer_official_registration_with_new_dates_reopens_schedule():
    data = market()
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, DEMAND]), **WINDOW)
    amended = filing("20261018", "[기재정정]증권신고서(지분증권)")
    dart = SyntheticDart([ORIGINAL, DEMAND, amended], selected=amended, dates="2026.11.19 ~ 11.20")
    _apply_dart_schedules(data, dart=dart, **WINDOW)
    assert data["ipos"][0]["sources"]["dart_schedule_status"]["status"] == "scheduled"
    assert [e["date"] for e in events(data) if e["type"] == "ipo_subscription"] == ["2026-11-19", "2026-11-20"]
    # A stale refresh cannot bring an older stop notice back over the new filing.
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, DEMAND]), **WINDOW)
    assert data["ipos"][0]["sources"]["dart_schedule_status"]["status"] == "scheduled"
    assert [e["date"] for e in events(data) if e["type"] == "ipo_subscription"] == ["2026-11-19", "2026-11-20"]


def test_unlinked_amendment_does_not_clear_demand_or_affect_other_issuer():
    data = market()
    data["ipos"].append({"ipo_id": "other", "company_name": "다른합성기업",
                         "subscription_start": "2026-10-19", "subscription_end": "2026-10-20"})
    reads = {"failed": 0, "candidates": [{"index": 0, "corp_code": "01000001", "master_row": {},
        "status": "ok", "restriction": dart_schedule_restriction([DEMAND]),
        "filing": ORIGINAL, "raw_structured": {}}]}
    _apply_dart_schedules(data, dart=None, prefetched=reads, **WINDOW)
    assert {e["source_id"] for e in events(data)} == {"other"}


def test_actual_listing_survives_suspended_expected_dates():
    data = market()
    data["ipos"][0]["actual_listing_date"] = "2026-11-30"
    data["ipos"][0]["sources"]["dart_schedule_status"] = {"status": "withdrawn"}
    result = events(data)
    assert len(result) == 1 and result[0]["type"] == "ipo_listing"
    assert result[0]["meta"]["listing_status"] == "actual"


def test_unfiltered_client_request_keeps_default_request_contract():
    dart = DartClient(api_key="synthetic-no-network")
    with patch.object(dart, "_request_json", return_value={"list": []}) as request:
        dart.get_filing_list("01000001", "20260901", "20261019", pblntf_ty="", pblntf_detail_ty="")
        assert "pblntf_ty" not in request.call_args.args[1]
        assert "pblntf_detail_ty" not in request.call_args.args[1]
        dart.get_filing_list("01000001", "20260901", "20261019")
        assert request.call_args.args[1]["pblntf_detail_ty"] == "C001"


def test_notice_on_second_page_is_not_missed():
    dart = SyntheticDart([ORIGINAL, DEMAND])
    def pages(**kwargs):
        return {"total_page": 2, "list": [ORIGINAL] if kwargs["page_no"] == 1 else [DEMAND]}
    dart.get_filing_list = pages
    reads = _fetch_dart_schedules(market(), dart=dart, **WINDOW)
    assert reads["candidates"][0]["restriction"]["status"] == "postponed"


def test_unknown_official_state_is_not_presented_as_open_subscription():
    data = market()
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL], fail_structured=True), **WINDOW)
    result = events(data)
    assert len([e for e in result if e["type"] == "ipo_subscription"]) == 2
    assert all("확인 필요" in e["title"] for e in result)
    assert all(e["meta"]["schedule_verification"] == "unverified" for e in result)
    assert data["ipos"][0]["subscription_start"] == "2026-10-19"
    _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL]), **WINDOW)
    assert "청약 첫째날" in events(data)[0]["title"]


def test_other_issuer_notice_or_structured_response_cannot_cancel_or_reassign_ipo():
    for structured in (False, True):
        data = market()
        dart = SyntheticDart([ORIGINAL] if structured else [{**DEMAND, "corp_code": "99999999"}])
        if structured:
            dart.selected = {**ORIGINAL, "corp_code": "99999999"}
        _apply_dart_schedules(data, dart=dart, **WINDOW)
        ipo = data["ipos"][0]
        assert ipo["corp_code"] == "01000001" and ipo["company_name"] == "유캐스트"
        assert "dart_schedule_status" not in ipo["sources"]
        assert all("확인 필요" in e["title"] for e in events(data))


def test_ambiguous_master_name_does_not_select_first_company():
    data = market()
    data["ipos"][0].pop("corp_code")
    dart = SyntheticDart([ORIGINAL, DEMAND])
    dart.get_corp_code_master = lambda: [
        {"corp_name": "유캐스트", "corp_code": "01000001"},
        {"corp_name": "유캐스트", "corp_code": "99999999"}]
    reads = _fetch_dart_schedules(data, dart=dart, **WINDOW)
    assert reads["candidates"][0]["status"] == "ignored"
    assert dart.calls == []


@pytest.mark.parametrize("notice", [DEMAND, filing("20261001", "철회신고서(지분증권)")])
def test_duplicate_notice_idempotence_and_application_checks_survive_reopening(notice):
    data = market()
    applications = {"applications": {"synthetic-eucast": {
        "applied_owners": ["합성소유자"], "target_owners": ["합성소유자"], "all_applied": True}}}
    original_applications = deepcopy(applications)
    with patch("app.services.ipo.store.read_market_store", side_effect=lambda: data), \
         patch("app.services.ipo.applications.get_user_applications", return_value=applications), \
         patch("app.services.ipo.applications.portfolio.write_financial_json") as save:
        before = get_ipo_calendar_events("synthetic-user", "2026-10-01", "2026-11-30", "합성소유자")
        assert before[0]["meta"]["is_applied_by_owner"] is True
        dart = SyntheticDart([ORIGINAL, notice, notice])
        for _ in range(2):
            _apply_dart_schedules(data, dart=dart, **WINDOW)
            assert get_ipo_calendar_events("synthetic-user", "2026-10-01", "2026-11-30") == []
        _apply_observation(data, {"company_name": "유캐스트", "corp_code": "01000001",
            "subscription_start": "2026-11-01", "subscription_end": "2026-11-02"}, source_name="kind")
        assert data["ipos"][0]["subscription_start"] == "2026-10-19"
        amended = filing("20261018", "[발행조건확정]증권신고서(지분증권)")
        _apply_dart_schedules(data, dart=SyntheticDart([ORIGINAL, notice, amended],
            selected=amended, dates="2026.11.19 ~ 11.20"), **WINDOW)
        reopened = get_ipo_calendar_events("synthetic-user", "2026-10-01", "2026-11-30", "합성소유자")
        assert reopened[0]["date"] == "2026-11-19"
        assert reopened[0]["source_id"] == "synthetic-eucast"
        assert reopened[0]["meta"]["is_applied_by_owner"] is True
        save.assert_not_called()
    assert applications == original_applications
