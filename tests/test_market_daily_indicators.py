"""Official data contracts, cache failures, and zero-write query boundaries."""
import asyncio
import json
from copy import deepcopy
from datetime import date
from unittest.mock import Mock

import pytest

from app.services import market_indicators as indicators
from app.services.market_read_cache import MarketReadCache
from tests.regression_support import authenticated_request, import_main_without_loading_real_env


def test_treasury_xml_uses_ten_year_column_and_actual_observation_dates():
    xml = '''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices">
      <entry><d:NEW_DATE>2026-10-21T00:00:00</d:NEW_DATE><d:BC_10YEAR>4.10</d:BC_10YEAR><d:BC_2YEAR>9</d:BC_2YEAR></entry>
      <entry><d:NEW_DATE>2026-10-22T00:00:00</d:NEW_DATE><d:BC_10YEAR>4.15</d:BC_10YEAR></entry>
      <entry><d:NEW_DATE>2026-10-23T00:00:00</d:NEW_DATE><d:BC_10YEAR/></entry></feed>'''
    result = indicators.yield_observation(indicators.parse_treasury_yields(xml), date(2026, 10, 23))
    assert result["value"] == 4.15 and result["observed_date"] == "2026-10-22"
    assert result["previous_observed_date"] == "2026-10-21"
    assert result["unit"] == "연%"
    assert result["change_pp"] == pytest.approx(.05)
    assert result["change_bp"] == pytest.approx(5)
    assert result["series"] == [4.10, 4.15]


def ecos_payload(**changes):
    row = {"STAT_CODE": "817Y002", "ITEM_CODE1": "010210000", "UNIT_NAME": "연%",
           "TIME": "20261022", "DATA_VALUE": "3.125"}
    return {"StatisticSearch": {"list_total_count": 1, "row": [{**row, **changes}]}}


def test_ecos_exact_contract_missing_values_and_errors():
    assert indicators.parse_ecos_yields(ecos_payload()) == [("2026-10-22", 3.125)]
    assert indicators.parse_ecos_yields(ecos_payload(DATA_VALUE="-")) == []
    for changes in [{"ITEM_CODE1": "wrong"}, {"UNIT_NAME": "%p"}, {"TIME": "20260230"}]:
        with pytest.raises(ValueError):
            indicators.parse_ecos_yields(ecos_payload(**changes))
    with pytest.raises(ValueError):
        indicators.parse_ecos_yields({"RESULT": {"CODE": "ERROR-100"}})
    with pytest.raises(ValueError):
        indicators.yield_observation([], date(2026, 10, 23))
    with pytest.raises(ValueError):
        indicators.yield_observation([("2026-10-22", float("nan"))], date(2026, 10, 23))


def test_cache_singleflight_failure_keeps_last_success_and_is_bounded(monkeypatch):
    import app.services.market_read_cache as module
    clock = [100.0]
    monkeypatch.setattr(module, "monotonic", lambda: clock[0])
    cache = MarketReadCache(ttl=900, capacity=2)
    calls = []
    async def load():
        calls.append(1)
        await asyncio.sleep(0)
        return {"value": 4.15}
    async def fail():
        raise OSError("offline")
    async def scenario():
        first, second = await asyncio.gather(cache.get("US", load), cache.get("US", load))
        assert len(calls) == 1 and second["cache_hit"]
        first["value"]["value"] = 0
        assert (await cache.get("US", load))["value"]["value"] == 4.15
        clock[0] += 901
        failure = await cache.get("US", fail)
        assert failure["update_delayed"] and failure["error"] == "source_unavailable"
        assert failure["retrieved_at"] == second["retrieved_at"]
        assert failure["value"]["value"] == 4.15
        assert (await cache.get("missing", fail))["value"] is None
        await cache.get("third", fail)
        assert len(cache.values) == 2
    asyncio.run(scenario())


def test_provider_errors_not_configured_and_cnn_reference_are_honest(monkeypatch):
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    monkeypatch.setattr(indicators, "_cache", MarketReadCache(ttl=1))
    async def failed():
        raise OSError("no connection")
    monkeypatch.setattr(indicators, "_treasury", failed)
    result = asyncio.run(indicators.get_market_indicators())
    us, kr = result["rates"]
    assert us["status"] == "source_error" and us["value"] is None and us["retrieved_at"] is None
    assert kr["status"] == "not_configured" and kr["value"] is None
    assert result["fear_greed"]["score"] is None
    assert result["fear_greed"]["status"] == "not_connected"
    assert result["fear_greed"]["source_url"] == "https://www.cnn.com/markets/fear-and-greed"


def test_stale_observation_is_distinct_from_successful_fetch(monkeypatch):
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    monkeypatch.setattr(indicators, "_cache", MarketReadCache(ttl=1))
    async def old():
        return indicators.yield_observation([("2000-01-03", 6.58)], date(2000, 1, 3))
    monkeypatch.setattr(indicators, "_treasury", old)
    us = asyncio.run(indicators.get_market_indicators())["rates"][0]
    assert us["status"] == "stale" and us["observation_stale"]
    assert us["retrieved_at"] and not us["update_delayed"]


def test_ecos_api_key_in_path_is_redacted():
    from app.logging_security import redact_credential_urls
    text = "https://ecos.bok.or.kr/api/StatisticSearch/synthetic-secret/json/kr/1/100/817Y002"
    assert "synthetic-secret" not in redact_credential_urls(text)
    assert "/StatisticSearch/[REDACTED]/" in redact_credential_urls(text)


def test_readonly_portfolio_query_never_bootstraps_user_files(tmp_path, monkeypatch):
    from app.services import portfolio, user_manager
    monkeypatch.setattr(user_manager, "USERS_DIR", tmp_path / "users")
    def forbidden(*a, **kw):
        raise AssertionError("Query must not bootstrap or write")
    monkeypatch.setattr(user_manager, "get_user_data_dir", forbidden)
    monkeypatch.setattr(portfolio, "write_portfolio", forbidden)
    assert portfolio.read_portfolio_readonly("synthetic")["holdings"] == []
    assert list(tmp_path.iterdir()) == []


def test_signal_and_market_routes_zero_financial_writes(monkeypatch):
    main = import_main_without_loading_real_env()
    from app.services import portfolio, financial_json, secure_files, user_manager
    snapshot = {"accounts": [], "holdings": [], "settings": {}}
    before = deepcopy(snapshot)
    monkeypatch.setattr(portfolio, "read_portfolio_readonly", lambda name: snapshot)
    writes = Mock(side_effect=AssertionError("Financial writes forbidden"))
    for module in [portfolio, main]:
        monkeypatch.setattr(module, "write_portfolio", writes)
    monkeypatch.setattr(financial_json, "write_financial_json", writes)
    monkeypatch.setattr(secure_files, "atomic_write_private_json", writes)
    monkeypatch.setattr(user_manager, "get_user_data_dir", writes)
    monkeypatch.setattr(main, "read_portfolio", writes)
    async def index_quotes():
        return {"markets": [{"symbol": "KOSPI", "price": 123}], "exchange_rate": None}
    async def reference_quotes():
        return {"rates": [], "fear_greed": {"score": None, "status": "not_connected"}}
    monkeypatch.setattr(main, "fetch_market_overview", index_quotes)
    monkeypatch.setattr(indicators, "get_market_indicators", reference_quotes)
    response = asyncio.run(main.get_holding_signals(authenticated_request()))
    assert json.loads(response.body)["items"] == []
    assert response.headers["Cache-Control"] == "no-store"
    assert asyncio.run(main.market_overview())["markets"][0]["price"] == 123
    assert snapshot == before and writes.call_count == 0


@pytest.mark.parametrize("mismatch", [{}, {"symbol": "OTHER"}, {"currency": "KRW"}, {"instrumentType": "MUTUALFUND"}])
def test_yahoo_signal_adapter_requires_adjustment_and_exact_identity(monkeypatch, mismatch):
    from app.services import web_finance
    import httpx
    requests = []
    def response(request):
        requests.append(request)
        assert request.url.params["includeAdjustedClose"] == "true"
        return httpx.Response(200, json={"chart": {"result": [{
            "meta": {"symbol": "TEST", "instrumentType": "ETF", "currency": "USD", "exchangeTimezoneName": "America/New_York", "exchangeName": "NMS", **mismatch},
            "timestamp": [1792675800], "indicators": {"quote": [{"close": [200]}], "adjclose": [{"adjclose": [100]}]}
        }]}})
    client = httpx.AsyncClient
    monkeypatch.setattr(web_finance, "external_network_allowed", lambda: True)
    monkeypatch.setattr(web_finance, "_signal_series_cache", MarketReadCache(ttl=900))
    monkeypatch.setattr(web_finance.httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(response)))
    result = asyncio.run(web_finance.fetch_signal_daily_series("TEST", "USD", "US"))
    if mismatch:
        assert result["value"] is None and result["update_delayed"]
    else:
        assert result["value"]["adjustment"] == "adjusted_close"
        assert result["value"]["candles"][0]["close"] == 100
    assert len(requests) == 1


def test_krx_alphanumeric_etf_code_uses_existing_adjusted_chart_route(monkeypatch):
    from app.services import web_finance
    import httpx
    def response(request):
        assert request.url.path.endswith("/0015B0.KS")
        return httpx.Response(200, json={"chart": {"result": [{
            "meta": {"symbol": "0015B0.KS", "currency": "KRW", "instrumentType": "ETF",
                     "exchangeTimezoneName": "Asia/Seoul", "exchangeName": "KSC"},
            "timestamp": [1792710000], "indicators": {"adjclose": [{"adjclose": [10000]}]}
        }]}})
    client = httpx.AsyncClient
    monkeypatch.setattr(web_finance, "external_network_allowed", lambda: True)
    monkeypatch.setattr(web_finance, "_signal_series_cache", MarketReadCache(ttl=900))
    monkeypatch.setattr(web_finance.httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(response)))
    result = asyncio.run(web_finance.fetch_signal_daily_series("0015B0", "KRW", "KOSPI"))
    assert result["value"]["calendar"] == "XKRX"
    assert result["value"]["candles"][0]["close"] == 10000
