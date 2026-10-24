"""Yahoo TNX percentage yields, cache failures, and zero-write query boundaries."""
import asyncio
import json
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import Mock

import pytest

from app.services import market_indicators as indicators
from app.services.market_read_cache import MarketReadCache
from tests.regression_support import authenticated_request, import_main_without_loading_real_env


def tnx_payload(observed=None, **meta_changes):
    observed = observed or datetime.now(timezone.utc) - timedelta(minutes=20)
    zone = ZoneInfo("America/New_York")
    day = observed.astimezone(zone).date()
    return {"chart": {"error": None, "result": [{
        "meta": {"symbol": "^TNX", "instrumentType": "INDEX", "regularMarketPrice": 4.15,
                 "regularMarketTime": int(observed.timestamp()), "exchangeTimezoneName": "America/New_York",
                 "exchangeDataDelayedBy": 15, "chartPreviousClose": 99, "previousClose": 88, **meta_changes},
        "timestamp": [int(datetime.combine(day - timedelta(days=d), time(12), tzinfo=zone).timestamp()) for d in [2, 1, 0]],
        "indicators": {"quote": [{"close": [4.0, 4.10, 4.15]}]}}]}}


def test_yahoo_tnx_is_already_percent_and_change_is_bp_not_relative_percent():
    now = datetime.fromisoformat("2026-10-23T20:00:00+00:00")
    result = indicators.parse_yahoo_tnx(tnx_payload(now), now=now)
    assert result["value"] == 4.15
    assert result["observed_date"] == "2026-10-23"
    assert result["previous_observed_date"] == "2026-10-22"
    assert result["previous_close"] == 4.10  # Ignore range anchors 99 and 88.
    assert result["unit"] == "연%"
    assert result["change_pp"] == pytest.approx(.05)
    assert result["change_bp"] == pytest.approx(5)
    assert result["observed_at"] == now.isoformat()
    assert result["quote_delay_minutes"] == 15 and not result["observation_stale"]
    assert result["series"] == [4.0, 4.10, 4.15]


@pytest.mark.parametrize("meta", [{"regularMarketPrice": None}, {"regularMarketPrice": float("nan")},
                                  {"regularMarketPrice": True}, {"symbol": "^TYX"},
                                  {"regularMarketTime": None}, {"exchangeDataDelayedBy": -1}])
def test_tnx_invalid_identity_price_and_timestamp_fail_closed(meta):
    with pytest.raises(ValueError):
        indicators.parse_yahoo_tnx(tnx_payload(**meta))


def test_tnx_previous_trading_observation_and_missing_previous_are_distinct():
    now = datetime.fromisoformat("2026-10-26T20:00:00+00:00")
    payload = tnx_payload(now)
    entry = payload["chart"]["result"][0]
    entry["timestamp"] = [int((now - timedelta(days=3)).timestamp()), int(now.timestamp())]
    entry["indicators"]["quote"][0]["close"] = [4.10, 4.15]
    result = indicators.parse_yahoo_tnx(payload, now=now)
    assert result["previous_observed_date"] == "2026-10-23"
    assert result["change_bp"] == 5 and result["series"] == [4.10, 4.15]
    entry["timestamp"] = [int(now.timestamp())]
    entry["indicators"]["quote"][0]["close"] = [4.15]
    result = indicators.parse_yahoo_tnx(payload, now=now)
    assert result["value"] == 4.15 and result["change_bp"] is None


def test_tnx_observation_uses_new_york_date_and_unknown_delay_is_not_zero():
    now = datetime.fromisoformat("2026-10-24T00:30:00+00:00")
    result = indicators.parse_yahoo_tnx(tnx_payload(now, exchangeDataDelayedBy=None), now=now)
    assert result["observed_date"] == "2026-10-23" and result["quote_delay_minutes"] is None


@pytest.mark.parametrize("failure", [None, "http", "network", "schema"])
def test_tnx_cached_yahoo_only_query_and_cnn_reference(monkeypatch, failure):
    import httpx
    requests = []
    def response(request):
        requests.append(request)
        assert request.url.host == "query1.finance.yahoo.com"
        assert request.url.path.endswith("/^TNX")
        assert dict(request.url.params) == {"interval": "1d", "range": "1mo"}
        if failure == "network":
            raise httpx.ConnectError("synthetic offline", request=request)
        return httpx.Response(503 if failure == "http" else 200,
                              json={"chart": {"result": []}} if failure == "schema" else tnx_payload())
    monkeypatch.setattr(indicators, "require_external_network", lambda *a: None)
    monkeypatch.setattr(indicators, "_cache", MarketReadCache(ttl=300, capacity=1))
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            first = await indicators.get_market_indicators(client)
            second = await indicators.get_market_indicators(client)
        assert len(requests) == 1
        assert all(r.url.host == "query1.finance.yahoo.com" for r in requests)
        assert [r["symbol"] for r in first["rates"]] == ["^TNX"]
        rate = first["rates"][0]
        assert rate["source"] == indicators.TNX_SOURCE and rate["unit"] == "연%"
        if failure:
            assert rate["value"] is None and rate["status"] == "source_error"
            assert rate["reason"] == "조회 불가" and rate["retrieved_at"] is None
        else:
            assert rate["value"] == 4.15 and rate["change_bp"] == 5
            assert rate["status"] == "ok" and second["rates"][0]["cache_hit"]
        assert first["fear_greed"]["score"] is None
        assert first["fear_greed"]["status"] == "not_connected"
        assert first["fear_greed"]["source_url"] == "https://www.cnn.com/markets/fear-and-greed"
    asyncio.run(scenario())


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


def test_stale_observation_is_distinct_from_successful_fetch(monkeypatch):
    import httpx
    old = datetime.now(timezone.utc) - timedelta(days=6)
    monkeypatch.setattr(indicators, "_cache", MarketReadCache(ttl=300))
    monkeypatch.setattr(indicators, "require_external_network", lambda *a: None)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=tnx_payload(old)))) as client:
            us = (await indicators.get_market_indicators(client))["rates"][0]
        assert us["status"] == "stale" and us["observation_stale"]
        assert us["retrieved_at"] and not us["update_delayed"]
    asyncio.run(scenario())


def test_failed_refresh_is_unavailable_and_keeps_last_success_time(monkeypatch):
    import httpx
    import app.services.market_read_cache as cache_module
    clock = [1000.0]
    calls = []
    def response(request):
        calls.append(request)
        return httpx.Response(200 if len(calls) == 1 else 503, json=tnx_payload())
    monkeypatch.setattr(cache_module, "monotonic", lambda: clock[0])
    monkeypatch.setattr(indicators, "_cache", MarketReadCache(ttl=300))
    monkeypatch.setattr(indicators, "require_external_network", lambda *a: None)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            first = (await indicators.get_market_indicators(client))["rates"][0]
            clock[0] += 301
            failed = (await indicators.get_market_indicators(client))["rates"][0]
        assert len(calls) == 2 and failed["value"] is None and failed["change_bp"] is None
        assert failed["reason"] == "조회 불가" and failed["update_delayed"]
        assert failed["retrieved_at"] == first["retrieved_at"]
    asyncio.run(scenario())


@pytest.mark.parametrize("tnx_error", [False, True])
def test_overview_reuses_one_client_preserves_indices_and_has_no_other_provider_calls(monkeypatch, tnx_error):
    import httpx
    from app.services import web_finance, portfolio, financial_json, secure_files
    requests, clients = [], []
    def response(request):
        requests.append(request)
        assert request.url.host == "query1.finance.yahoo.com"
        symbol = request.url.path.rsplit("/", 1)[-1]
        if symbol == "^TNX":
            return httpx.Response(503 if tnx_error else 200, json=tnx_payload())
        entry = {"meta": {"symbol": symbol, "regularMarketPrice": 110, "previousClose": 100},
                 "timestamp": [1700000000, 1700086400], "indicators": {"quote": [{"close": [100, 110]}]}}
        return httpx.Response(200, json={"chart": {"result": [entry]}})
    original = httpx.AsyncClient
    def client_factory(**kwargs):
        client = original(transport=httpx.MockTransport(response), **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr(web_finance, "external_network_allowed", lambda: True)
    monkeypatch.setattr(indicators, "require_external_network", lambda *a: None)
    monkeypatch.setattr(indicators, "_cache", MarketReadCache(ttl=300))
    monkeypatch.setattr(web_finance.httpx, "AsyncClient", client_factory)
    writes = Mock(side_effect=AssertionError("Market reads must not write financial data"))
    monkeypatch.setattr(portfolio, "write_portfolio", writes)
    monkeypatch.setattr(portfolio, "write_financial_json", writes)
    monkeypatch.setattr(financial_json, "write_financial_json", writes)
    monkeypatch.setattr(secure_files, "atomic_write_private_json", writes)
    result = asyncio.run(web_finance.get_web_market_overview())
    assert len(clients) == 1 and len(requests) == 25
    assert all(r.url.host == "query1.finance.yahoo.com" for r in requests)
    assert [m["symbol"] for m in result["markets"]] == ["^KS11", "^KQ11", "^GSPC", "^IXIC", "^SOX"]
    assert all(m["price"] == 110 and m["periods"] for m in result["markets"])
    assert len(result["rates"]) == 1 and result["rates"][0]["symbol"] == "^TNX"
    assert result["rates"][0]["value"] == (None if tnx_error else 4.15)
    assert result["fear_greed"]["status"] == "not_connected"
    assert writes.call_count == 0


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
    monkeypatch.setattr(main, "fetch_market_overview", index_quotes)
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
