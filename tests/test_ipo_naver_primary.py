"""Synthetic provider observations; never read or write real financial data."""
from copy import deepcopy
from datetime import date
from unittest.mock import Mock, patch

import pytest

from app.services.ipo import source_discovery as discovery
from app.services.ipo.display import display_records
from app.services.ipo.presentation import derive_market_state, present_market_store
from app.services.ipo.store import get_ipo_calendar_events, merge_ipo_record


def younggwang():
    # Normalized observation contract, not a claim that the current summary
    # parser fetches the detail page. New detail retrieval remains deferred.
    return {"company_name": "영광", "stock_code": "359410",
            "subscription_start": "2026-10-22", "subscription_end": "2026-10-23",
            "final_offer_price": 17000, "lead_managers": ["한국투자증권"],
            "expected_listing_date": "2026-11-02", "sources": {"npay": {
                "url": "https://ustock.naver.com/service/ipo/359410",
                "observed_at": "2026-10-21T10:00:00+09:00"}}}


def observed_market():
    market = {"ipos": [{"ipo_id": "kept-359410", "company_name": "영광", "stock_code": "359410",
                        "sources": {"dart_schedule_verification": {
                            "status": "unverified", "reason": "no_linked_filing"}}}]}
    discovery._apply_observation(market, younggwang(), source_name="npay")
    return market


@pytest.mark.parametrize("day,state", [(21, "UPCOMING"), (22, "SUBSCRIPTION_OPEN"),
                                      (23, "SUBSCRIPTION_OPEN"), (24, "LISTING_UPCOMING")])
def test_younggwang_inclusive_kst_dates_keep_dart_failure_and_all_fields(day, state):
    market = observed_market()
    before = deepcopy(market)
    row = display_records(market["ipos"])[0]
    assert derive_market_state(row, date(2026, 10, day)) == state
    assert row["sources"]["dart_schedule_verification"] == {
        "status": "unverified", "reason": "no_linked_filing"}
    assert (row["final_offer_price"], row["lead_managers"], row["expected_listing_date"]) == (
        17000, ["한국투자증권"], "2026-11-02")
    assert market == before


@pytest.mark.parametrize("status,state", [("postponed", "POSTPONED"), ("withdrawn", "WITHDRAWN")])
def test_explicit_stop_wins_over_primary_dates(status, state):
    market = observed_market()
    market["ipos"][0]["sources"]["dart_schedule_status"] = {"status": status}
    assert derive_market_state(market["ipos"][0], date(2026, 10, 23)) == state
    with patch("app.services.ipo.store.read_market_store", return_value=market):
        assert get_ipo_calendar_events(None, "2026-10-01", "2026-11-30") == []


def test_source_badge_or_mismatched_field_evidence_does_not_confirm_unknown_dates():
    row = observed_market()["ipos"][0]
    row["sources"].pop("schedule_fields")
    assert derive_market_state(display_records([row])[0], date(2026, 10, 23)) == "DATE_UNKNOWN"
    row = observed_market()["ipos"][0]
    row["subscription_end"] = "2026-10-24"
    assert derive_market_state(row, date(2026, 10, 23)) == "DATE_UNKNOWN"


def test_naver_fields_win_over_dart_but_unprovided_fields_can_be_enriched():
    market = observed_market()
    discovery._apply_observation(market, {"stock_code": "359410", "company_name": "영광",
        "subscription_start": "2026-10-25", "subscription_end": "2026-10-26",
        "final_offer_price": 16000, "lead_managers": ["다른증권"], "refund_date": "2026-10-28",
        "sources": {"dart_schedule": {"source_date": "20261021"}}}, source_name="dart")
    row = market["ipos"][0]
    assert row["subscription_start"] == "2026-10-22" and row["final_offer_price"] == 17000
    assert row["lead_managers"] == ["한국투자증권"] and row["refund_date"] == "2026-10-28"


def test_price_band_is_not_final_price_and_changed_schedule_keeps_original_id():
    market = {"ipos": []}
    item = younggwang()
    item.pop("final_offer_price")
    item.update(offer_band_low=14000, offer_band_high=17000)
    discovery._apply_observation(market, item, source_name="npay")
    row = market["ipos"][0]
    kept_id = row["ipo_id"]
    assert row.get("final_offer_price") is None
    item = younggwang()
    item.update(subscription_start="2026-10-26", subscription_end="2026-10-27")
    discovery._apply_observation(market, item, source_name="npay")
    assert len(market["ipos"]) == 1 and row["ipo_id"] == kept_id
    assert row["subscription_start"] == "2026-10-26" and row["final_offer_price"] == 17000


@pytest.mark.parametrize("missing", ["subscription_end", "final_offer_price", "lead_managers"])
def test_missing_field_does_not_erase_other_observed_facts(missing):
    item = younggwang()
    item.pop(missing)
    market = {"ipos": []}
    discovery._apply_observation(market, item, source_name="npay")
    row = market["ipos"][0]
    assert row["subscription_start"] == "2026-10-22"
    assert row["expected_listing_date"] == "2026-11-02"
    if missing != "final_offer_price":
        assert row["final_offer_price"] == 17000


def test_conflicting_identifiers_and_duplicate_identities_never_redirect_observation():
    market = observed_market()
    before = deepcopy(market)
    item = younggwang()
    item["stock_code"] = "999999"
    _, review = discovery._apply_observation(market, item, source_name="npay")
    assert review and market == before
    market["ipos"].append({**deepcopy(market["ipos"][0]), "ipo_id": "duplicate"})
    before = deepcopy(market)
    _, review = discovery._apply_observation(market, younggwang(), source_name="npay")
    assert review and market == before


def test_failed_collection_preserves_observation_and_never_instantiates_metalogos():
    market = observed_market()
    before = deepcopy(market)
    kind, naver, npay, dart = (Mock() for _ in range(4))
    for read in (kind.fetch_pubofr_schedule_items, naver.fetch_ipo_discovery_items, npay.fetch_upcoming_ipos):
        read.side_effect = RuntimeError("synthetic outage")
    dart.is_configured.return_value = False
    saved = []
    with patch.object(discovery, "read_market_store", return_value=market), \
         patch.object(discovery, "write_market_store", side_effect=lambda value: saved.append(deepcopy(value))), \
         patch.object(discovery, "MetalogosIpoClient") as metalogos:
        result = discovery.discover_and_merge_primary_sources(username=None, target_date_str="2026-10-23",
            kind_client=kind, naver_client=naver, npay_client=npay, dart_client=dart)
    metalogos.assert_not_called()
    assert result["statuses"]["npay"].startswith("source_error")
    row = saved[0]["ipos"][0]
    assert row["sources"]["schedule_fields"] == before["ipos"][0]["sources"]["schedule_fields"]
    assert derive_market_state(row, date(2026, 10, 23)) == "SUBSCRIPTION_OPEN"
    assert market == before


def test_calendar_list_and_application_sale_account_links_are_read_only_and_consistent():
    market = observed_market()
    row = market["ipos"][0]
    market["ipos"].append({**deepcopy(row), "ipo_id": "old-alias"})
    apps = {"kept-359410": {"applied_owners": ["본인"], "applicants": {"본인": {
        "account_id": "kept-account", "allocation": {"quantity": 5, "links": [
            {"pnl_record_id": "sale-1", "matched_quantity": 2}]}}}}}
    portfolio = {"settings": {"ipo": {"applications": apps}}}
    pnl = [{"id": "sale-1", "quantity": 2, "account_id": "kept-account"}]
    before = deepcopy((market, portfolio, pnl))
    with patch("app.services.ipo.store.read_market_store", return_value=market), \
         patch("app.services.ipo.presentation._read_portfolio_for_presentation", return_value=portfolio), \
         patch("app.services.ipo.presentation.read_pnl_records_readonly", return_value=pnl), \
         patch("app.services.ipo.applications.get_user_applications", return_value={"applications": apps}), \
         patch("app.services.ipo.applications.portfolio.write_financial_json") as write:
        listing = present_market_store("synthetic", market, date(2026, 10, 23))["ipos"]
        events = get_ipo_calendar_events("synthetic", "2026-10-01", "2026-11-30", "본인")
    write.assert_not_called()
    assert len(listing) == 1 and listing[0]["market_state"] == "SUBSCRIPTION_OPEN"
    assert listing[0]["user_state"] == "PARTIALLY_SOLD"
    assert set(listing[0]["application_record_ids"]) == {"kept-359410", "old-alias"}
    assert len(events) == 3 and all("확인 필요" not in e["title"] for e in events)
    assert all(e["meta"]["schedule_verification"] == "unverified" for e in events)
    assert all(e["meta"]["offer_price"] == 17000 for e in events)
    assert (market, portfolio, pnl) == before


def test_expected_listing_date_alone_does_not_assert_actual_listing():
    row = observed_market()["ipos"][0]
    assert derive_market_state(row, date(2026, 11, 2)) == "LISTING_UPCOMING"
    row["actual_listing_date"] = "2026-11-02"
    assert derive_market_state(row, date(2026, 11, 2)) == "LISTED"


def test_older_primary_snapshot_cannot_replace_newer_field_values():
    market = observed_market()
    item = younggwang()
    item["sources"]["npay"]["observed_at"] = "2026-10-20T10:00:00+09:00"
    item.update(subscription_start="2026-10-24", subscription_end="2026-10-25", final_offer_price=16000)
    discovery._apply_observation(market, item, source_name="npay")
    row = market["ipos"][0]
    assert row["subscription_start"] == "2026-10-22" and row["final_offer_price"] == 17000
    assert row["sources"]["schedule_fields"]["subscription_start"]["observed_at"].startswith("2026-10-21")


def test_observation_dates_are_normalized_to_kst_without_changing_original_source():
    market = {"ipos": []}
    item = younggwang()
    item["sources"]["npay"]["observed_at"] = "2026-10-20T16:00:00+00:00"
    discovery._apply_observation(market, item, source_name="npay")
    row = market["ipos"][0]
    assert row["sources"]["npay"]["observed_at"] == "2026-10-20T16:00:00+00:00"
    assert row["sources"]["schedule_fields"]["subscription_start"]["observed_at"] == "2026-10-21T01:00:00+09:00"
    assert row["sources"]["final_offer_price"]["source_date"] == "2026-10-21"


def test_base_store_merge_preserves_primary_values_during_failed_refresh():
    market = observed_market()
    before = deepcopy(market["ipos"][0]["sources"]["schedule_fields"])
    merge_ipo_record(market, {"stock_code": "359410", "subscription_start": "2026-10-25",
                             "final_offer_price": 16000, "sources": {"dart": {"rcept_no": "kept"}}})
    row = market["ipos"][0]
    assert row["subscription_start"] == "2026-10-22" and row["final_offer_price"] == 17000
    assert row["sources"]["schedule_fields"] == before


def test_primary_price_provenance_preserves_first_observation_and_score_cutoff():
    from app.services.ipo.score import calculate_wealth_ipo_score
    from tests.test_ipo_alice_metalogos_acceptance import alice
    row = alice()
    row["features"]["pricing_discipline"] = {"value": 100, "status": "ok", "source_date": "20261006"}
    item = {"company_name": row["company_name"], "stock_code": row["stock_code"],
            "final_offer_price": 90500, "sources": {"npay": {
                "url": "https://ustock.naver.com/service/ipo/0158S0",
                "observed_at": "2026-10-07T10:00:00+09:00"}}}
    discovery._apply_observation({"ipos": [row]}, item, source_name="npay")
    assert row["sources"]["final_offer_price"]["source_date"] == "2026-10-07"
    assert "pricing_discipline" in calculate_wealth_ipo_score(row, [])['core_missing']
    item["sources"]["npay"]["observed_at"] = "2026-10-08T10:00:00+09:00"
    discovery._apply_observation({"ipos": [row]}, item, source_name="npay")
    assert row["sources"]["final_offer_price"]["source_date"] == "2026-10-07"
