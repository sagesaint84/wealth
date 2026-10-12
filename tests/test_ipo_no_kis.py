"""IPO public-source acceptance: no broker credential or token dependency."""
from __future__ import annotations

import asyncio
import ast
import copy
import json
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.automation.dispatcher import KST, execute_job
from app.services.ipo import orchestrator, refresh_adapter
from app.services.ipo.identity import spac_name_key
from app.services.ipo.source_discovery import discover_and_merge_primary_sources
from app.services.ipo.store import get_ipo_calendar_events, read_market_store


GENERAL = {
    "company_name": "합성테크", "stock_code": "123456", "listing_track": "general",
    "corp_code": "01000001", "market": "KOSDAQ",
    "demand_forecast_start": "2026-10-01", "demand_forecast_end": "2026-10-02",
    "subscription_start": "2026-10-05", "subscription_end": "2026-10-06",
    "payment_date": "2026-10-08", "refund_date": "2026-10-08",
    "expected_listing_date": "2026-10-15", "final_offer_price": 24000,
    "lead_managers": ["합성증권"], "kind_bz_procs_no": "fixture-1",
}


@pytest.fixture
def public_sources(tmp_path):
    market_file = tmp_path / "market.json"
    market_file.write_text(json.dumps({"schema_version": 1, "ipos": []}), encoding="utf-8")
    kind = MagicMock()
    kind.fetch_pubofr_schedule_items.side_effect = lambda **kw: [copy.deepcopy(GENERAL)]
    dart = MagicMock()
    dart.is_configured.return_value = False
    naver = MagicMock()
    naver.fetch_ipo_discovery_items.return_value = []
    npay = MagicMock()
    npay.fetch_upcoming_ipos.return_value = []
    metalogos = MagicMock()
    metalogos.fetch_company_items.return_value = []
    with ExitStack() as stack:
        for target, value in (
            ("app.services.ipo.store.get_market_file", market_file),
            ("app.services.ipo.store.get_ipo_data_dir", tmp_path),
            ("app.services.ipo.orchestrator.KindClient", kind),
            ("app.services.ipo.orchestrator.DartClient", dart),
            ("app.services.ipo.source_discovery.KindClient", kind),
            ("app.services.ipo.source_discovery.DartClient", dart),
            ("app.services.ipo.source_discovery.NaverIpoDiscoveryClient", naver),
            ("app.services.ipo.source_discovery.NpayIpoClient", npay),
            ("app.services.ipo.source_discovery.MetalogosIpoClient", metalogos),
            ("app.services.ipo.refresh_adapter.refresh_missing_metalogos_references", {"status": "ok"}),
            ("app.services.ipo.refresh_adapter._targeted_dart_enrichment", {"status": "ok"}),
            ("app.services.ipo.applications.get_user_applications", {}),
        ):
            stack.enter_context(patch(target, return_value=value))
        yield market_file, kind


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("mode", ["morning", "evening", "manual"])
def test_public_refresh_never_constructs_kis_or_looks_up_its_credentials(public_sources, configured, mode):
    import app.main as main
    # A configured broker is deliberately available; IPO must never resolve it.
    with patch("app.services.kis_openapi.KISOpenAPI._access_token") as token_call, \
         patch("app.services.kis_openapi.httpx.AsyncClient.post") as http_post, \
         patch("app.services.kis_openapi.KISOpenAPI") as kis, \
         patch("app.services.user_openapi.get_user_openapi_config", return_value={
             "kis": {"app_key": "synthetic", "app_secret": "synthetic"} if configured else {}
         }) as credentials:
        if mode == "manual":
            token = main._serializer.dumps({"user": "fixture", "role": "user"})
            with patch("app.services.user_manager.get_user_by_name", return_value={"username": "fixture", "role": "user"}), \
                 patch("app.services.ipo.orchestrator.refresh_ipo_market", side_effect=lambda **kw: refresh_adapter.refresh_ipo_market(
                     username=kw.get("username"), target_date_str="2026-10-04")):
                response = TestClient(main.app).post("/api/ipo/market/refresh", headers={"Cookie": f"{main.COOKIE_NAME}={token}"})
            assert response.status_code == 200, response.text
        else:
            hour = 7 if mode == "morning" else 18
            result = asyncio.run(execute_job(
                {"job": f"ipo_refresh_{mode}", "owner": "fixture", "scope": "global", "scheduled_time": f"{hour:02}:30"},
                now=datetime(2026, 10, 4, hour, 30, tzinfo=KST),
                ipo_refresh_runner=refresh_adapter.refresh_ipo_market_enriched,
            ))
            assert result["status"] == "success", result
            assert result["details"]["status"] == "ok"
        kis.assert_not_called()
        credentials.assert_not_called()
        token_call.assert_not_called()
        assert not any("/oauth2/tokenP" in str(call) for call in http_post.call_args_list)
        public_sources[1].fetch_pubofr_schedule_items.assert_called_once_with(
            from_date="2025-10-04", to_date="2026-10-04")
        ipo = read_market_store()["ipos"][0]
        for key, value in GENERAL.items():
            assert ipo[key] == value
        assert "kis" not in ipo["sources"]
        assert "score" in ipo
        events = get_ipo_calendar_events("fixture", "2026-10-01", "2026-10-31")
        assert events  # Calendar/reminders consume the shared market without broker credentials.


@pytest.mark.parametrize("name,alias", [
    ("케이비제34호기업인수목적", "KB스팩34호"),
    ("엔에이치스팩34호", "NH제34호스팩"),
    ("아이비케이제31호기업인수목적", "IBK스팩31호"),
])
def test_spac_alias_discovery_retains_one_identity_and_complete_fields(public_sources, name, alias):
    item = dict(GENERAL, company_name=name, stock_code="0197V0", listing_track="spac", final_offer_price=2000)
    kind = MagicMock(); kind.fetch_pubofr_schedule_items.return_value = [item]
    naver = MagicMock(); naver.fetch_ipo_discovery_items.return_value = [
        dict(item, company_name=alias, stock_code=None, expected_listing_date="2026-10-16")]
    off = MagicMock(); off.is_configured.return_value = False
    empty = MagicMock(); empty.fetch_upcoming_ipos.return_value = []; empty.fetch_company_items.return_value = []
    result = discover_and_merge_primary_sources(
        username="fixture", target_date_str="2026-10-04", kind_client=kind,
        naver_client=naver, npay_client=empty, metalogos_client=empty, dart_client=off,
    )
    ipos = read_market_store()["ipos"]
    assert result["total_ipos"] == len(ipos) == 1
    assert spac_name_key(item) == spac_name_key(dict(item, company_name=alias))
    for key in ("stock_code", "subscription_start", "subscription_end", "final_offer_price", "lead_managers", "expected_listing_date"):
        assert ipos[0][key] == item[key]
    assert ipos[0]["score"]["status"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("name,alias", [
    ("케이비제34호기업인수목적", "KB스팩34호"),
    ("엔에이치스팩34호", "NH제34호스팩"),
    ("아이비케이제31호기업인수목적", "IBK스팩31호"),
])
def test_kind_without_stock_code_and_track_is_completed_by_union_without_repeat_duplicates(public_sources, name, alias):
    _, kind = public_sources
    # Routine KIND schedule rows do not provide a stock code or explicit listing track.
    row = {k: v for k, v in dict(GENERAL, company_name=name, final_offer_price=2000).items()
           if k not in {"stock_code", "corp_code", "kind_bz_procs_no", "listing_track"}}
    kind.fetch_pubofr_schedule_items.side_effect = lambda **kw: [copy.deepcopy(row)]
    naver = MagicMock()
    naver.fetch_ipo_discovery_items.return_value = [
        dict(row, company_name=alias, stock_code="0197V0", listing_track="spac")]
    with patch("app.services.ipo.source_discovery.NaverIpoDiscoveryClient", return_value=naver):
        ids = []
        for _ in range(2):
            result = refresh_adapter.refresh_ipo_market(username="fixture", target_date_str="2026-10-04")
            assert result["status"] == "ok"
            ipos = read_market_store()["ipos"]
            assert len(ipos) == 1
            ipo = ipos[0]
            ids.append(ipo["ipo_id"])
            assert ipo["stock_code"] == "0197V0"
            assert ipo["listing_track"] == "spac"
            assert ipo["score"]["status"] == "NOT_APPLICABLE"
            for key in ("subscription_start", "subscription_end", "final_offer_price", "lead_managers", "expected_listing_date"):
                assert ipo[key] == row[key]
        assert ids[0] == ids[1]
    assert kind.fetch_pubofr_schedule_items.call_count == 2


def test_historical_kis_provenance_survives_kind_refresh(public_sources):
    path, _ = public_sources
    old = dict(GENERAL, ipo_id="retained", sources={"kis": {"schedule_source": "ksdinfo_pub_offer", "listing_events": [{"evidence": "old"}]}})
    path.write_text(json.dumps({"schema_version": 1, "ipos": [old]}), encoding="utf-8")
    result = refresh_adapter.refresh_ipo_market(username="fixture", target_date_str="2026-10-04")
    assert result["status"] == "ok"
    assert "kis" not in result["sources"]
    assert read_market_store()["ipos"][0]["sources"]["kis"] == old["sources"]["kis"]


def test_empty_or_failed_kind_preserves_canonical_bytes(public_sources):
    path, kind = public_sources
    before = path.read_bytes()
    kind.fetch_pubofr_schedule_items.side_effect = None
    kind.fetch_pubofr_schedule_items.return_value = []
    result = refresh_adapter._BASE_REFRESH_MARKET(target_date_str="2026-10-04")
    assert result["status"] == "preserved"
    assert path.read_bytes() == before
    kind.fetch_pubofr_schedule_items.side_effect = RuntimeError("source failed")
    result = refresh_adapter._BASE_REFRESH_MARKET(target_date_str="2026-10-04")
    assert result["status"] == "preserved"
    assert path.read_bytes() == before


def test_failed_kind_is_not_retried_by_discovery_and_next_refresh_is_fresh(public_sources):
    _, kind = public_sources
    kind.fetch_pubofr_schedule_items.side_effect = RuntimeError("source failed")
    result = refresh_adapter.refresh_ipo_market(username="fixture", target_date_str="2026-10-04")
    assert result["sources"]["kind"].startswith("source_error")
    assert result["sources"]["kind_discovery"].startswith("source_error")
    assert kind.fetch_pubofr_schedule_items.call_count == 1
    kind.fetch_pubofr_schedule_items.side_effect = lambda **kw: [copy.deepcopy(GENERAL)]
    result = refresh_adapter.refresh_ipo_market(username="fixture", target_date_str="2026-10-04")
    assert result["status"] == "ok"
    assert kind.fetch_pubofr_schedule_items.call_count == 2


@pytest.mark.parametrize("change", [
    {"subscription_end": "2026-10-07"}, {"final_offer_price": 3000},
    {"company_name": "KB스팩35호"}, {"stock_code": "654321"}, {"payment_date": "2026-10-09"},
])
def test_spac_alias_does_not_merge_another_offering(change):
    from app.services.ipo.source_discovery import _unique_name_match
    old = dict(GENERAL, company_name="케이비제34호기업인수목적", listing_track="spac", final_offer_price=2000)
    incoming = dict(old, company_name="KB스팩34호")
    incoming.update(change)
    assert _unique_name_match(incoming, [old]) is None


def test_no_ipo_kis_network_references_or_obsolete_client_methods():
    root = Path(__file__).resolve().parents[1]
    banned = ("KISOpenAPI", "fetch_ipo_subscription_schedule", "fetch_listing_schedule", "KIS_IPO_PUB_OFFER_PATH", "KIS_LIST_INFO_PATH")
    for path in (root / "app/services/ipo").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(word in source for word in banned), path.name
    # Broker client retains its general account methods but exposes no obsolete IPO endpoint.
    current = (root / "app/services/kis_openapi.py").read_text(encoding="utf-8")
    removed = {"_validate_ksdinfo_body", "_fetch_ksdinfo_pages", "fetch_ipo_subscription_schedule", "fetch_listing_schedule", "fetch_multiple_domestic_stock_info", "fetch_domestic_stock_info"}
    klass = next(n for n in ast.parse(current).body if isinstance(n, ast.ClassDef) and n.name == "KISOpenAPI")
    assert not removed.intersection(n.name for n in klass.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
