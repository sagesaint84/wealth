"""Synthetic relay JSON and MockTransport only; no CNN/GitHub live calls."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import httpx
from httpx import AsyncClient as NativeClient
import pytest

from app.services import cnn_fear_greed as cnn
from app.services import market_read_cache as cache_module
from app.services.market_read_cache import MarketReadCache

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def payload():
    return {'updated': (NOW - timedelta(minutes=10)).isoformat().replace('+00:00', 'Z'),
            'asOf': '1999-01-01',  # unrelated MMI date must not override CNN
            'headline': {'cnn-fng': {'value': 42.25, 'date': NOW.date().isoformat(), 'zone': {'label': 'Fear'}}},
            'sources': {'cnn': {'ok': True}}, 'unavailable': []}


@pytest.fixture
def relay(monkeypatch):
    state = {'body': payload(), 'status': 200, 'calls': [], 'options': [], 'clock': 100., 'now': NOW}
    original = NativeClient
    def response(request):
        state['calls'].append(request)
        assert str(request.url) == cnn.FEED_URL and request.method == 'GET'
        assert request.headers['User-Agent'] == 'Wealth-market-relay/1.0'
        assert all(key not in request.headers for key in ('Authorization', 'Cookie', 'Referer'))
        if state.get('failure'): raise state['failure']
        if 'raw' in state:
            return httpx.Response(state['status'], content=state['raw'], headers=state.get('headers', {}))
        return httpx.Response(state['status'], json=state['body'])
    def factory(**kwargs):
        state['options'].append(kwargs)
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        assert kwargs['timeout'] == 5.0
        return original(transport=httpx.MockTransport(response), **kwargs)
    monkeypatch.setattr(cnn.httpx, 'AsyncClient', factory)
    monkeypatch.setattr(cnn, '_cache', MarketReadCache(ttl=cnn.TTL, capacity=1))
    monkeypatch.setattr(cnn, 'external_network_allowed', lambda: True)
    monkeypatch.setattr(cnn, 'require_external_network', lambda *a: None)
    monkeypatch.setattr(cnn, 'utc_now', lambda: state['now'])
    monkeypatch.setattr(cache_module, 'monotonic', lambda: state['clock'])
    return state


@pytest.mark.parametrize('score', [0, 42.25, 100])
def test_success_cache_singleflight_exact_source_and_copy_isolation(relay, score):
    relay['body']['headline']['cnn-fng']['value'] = score
    async def scenario():
        results = await asyncio.gather(*(cnn.get_cnn_fear_greed() for _ in range(12)))
        assert all(r['score'] == score and r['status'] == 'ok' for r in results)
        assert len(relay['calls']) == 1
        result = results[0]
        assert result['observed_date'] == NOW.date().isoformat()
        assert result['source_url'] == cnn.CNN_URL and result['relay_url'] == cnn.PROJECT_URL
        result['score'] = -1
        assert (await cnn.get_cnn_fear_greed())['score'] == score
        relay['clock'] += cnn.TTL - 1
        await cnn.get_cnn_fear_greed(); assert len(relay['calls']) == 1
        relay['clock'] += 2
        await cnn.get_cnn_fear_greed(); assert len(relay['calls']) == 2
    asyncio.run(scenario())


@pytest.mark.parametrize('value', [None, True, False, '42', [], {}, -0.1, 100.1, float('nan'), float('inf'), -float('inf'), 10**400])
def test_score_requires_finite_number_in_range(value):
    body = payload(); body['headline']['cnn-fng']['value'] = value
    with pytest.raises(ValueError): cnn.parse_relay(body, now=NOW)


@pytest.mark.parametrize('change', ['missing', 'bool_ok', 'false_ok', 'missing_ok', 'missing_unavailable',
                                  'invalid_unavailable', 'cnn_unavailable', 'bad_rating', 'malicious_rating',
                                  'bad_date', 'future_date', 'naive_updated', 'wrong_zone', 'future_updated', 'bad_updated'])
def test_schema_identity_and_time_fail_closed(relay, change):
    p = relay['body']; h = p['headline']['cnn-fng']
    if change == 'missing': p['headline'].pop('cnn-fng')
    if change == 'bool_ok': p['sources']['cnn']['ok'] = 1
    if change == 'false_ok': p['sources']['cnn']['ok'] = False
    if change == 'missing_ok': p['sources']['cnn'] = {}
    if change == 'missing_unavailable': p.pop('unavailable')
    if change == 'invalid_unavailable': p['unavailable'] = [None]
    if change == 'cnn_unavailable': p['unavailable'] = ['CNN']
    if change == 'bad_rating': h['zone']['label'] = 'unknown'
    if change == 'malicious_rating': h['zone']['label'] = '<img src=x onerror=alert(1)>'
    if change == 'bad_date': h['date'] = '2026-02-30'
    if change == 'future_date': h['date'] = '2026-10-28'
    if change == 'naive_updated': p['updated'] = '2026-10-27T10:00:00'
    if change == 'wrong_zone': p['updated'] = '2026-10-27T10:00:00+09:00'
    if change == 'future_updated': p['updated'] = (NOW + timedelta(minutes=6)).isoformat()
    if change == 'bad_updated': p['updated'] = '<script>bad</script>'
    result = asyncio.run(cnn.get_cnn_fear_greed())
    assert result['status'] == 'source_error' and result['score'] is None and result['rating'] is None
    assert len(relay['calls']) == 1


@pytest.mark.parametrize('status', [301, 302, 307, 308, 403, 418, 429, 500, 503])
def test_http_and_redirect_failures_have_no_numeric_fallback(relay, status):
    relay['status'] = status
    result = asyncio.run(cnn.get_cnn_fear_greed())
    assert result['score'] is None and result['status'] == 'source_error'
    assert len(relay['calls']) == 1


@pytest.mark.parametrize('failure', [httpx.ConnectError('synthetic'), httpx.ReadTimeout('synthetic')])
def test_network_and_timeout_fail_closed(relay, failure):
    relay['failure'] = failure
    assert asyncio.run(cnn.get_cnn_fear_greed())['score'] is None


@pytest.mark.parametrize('raw', [b'<html>error</html>', b'{bad', b'{"x":NaN}', b'x' * (cnn.MAX_BYTES + 1)],
                         ids=['html-response', 'malformed-json', 'nonfinite-json', 'oversized-response'])
def test_non_json_nonfinite_and_oversized_response(relay, raw):
    relay['raw'] = raw
    assert asyncio.run(cnn.get_cnn_fear_greed())['status'] == 'source_error'


def test_stream_limit_without_content_length(relay):
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(3): yield b'x' * 32768
    def response(request):
        assert str(request.url) == cnn.FEED_URL
        return httpx.Response(200, stream=Chunks())
    from unittest.mock import patch
    with patch.object(cnn.httpx, 'AsyncClient', lambda **kw: NativeClient(transport=httpx.MockTransport(response), **kw)):
        assert asyncio.run(cnn.get_cnn_fear_greed())['score'] is None


def test_total_timeout_cancels_hung_transport(relay, monkeypatch):
    timeout = asyncio.timeout
    monkeypatch.setattr(cnn.asyncio, 'timeout', lambda seconds: timeout(.01))
    async def response(request):
        assert str(request.url) == cnn.FEED_URL
        await asyncio.Event().wait()
    monkeypatch.setattr(cnn.httpx, 'AsyncClient', lambda **kw: NativeClient(transport=httpx.MockTransport(response), **kw))
    assert asyncio.run(cnn.get_cnn_fear_greed())['status'] == 'source_error'


def test_failed_refresh_backoff_never_exposes_last_success(relay):
    async def scenario():
        first = await cnn.get_cnn_fear_greed(); assert first['score'] == 42.25
        relay['clock'] += cnn.TTL + 1; relay['status'] = 503
        error = await cnn.get_cnn_fear_greed()
        assert error['score'] is None and error['rating'] is None and error['status'] == 'source_error'
        assert error['retrieved_at'] == first['retrieved_at']
        await cnn.get_cnn_fear_greed(); assert len(relay['calls']) == 2
        relay['clock'] += 61; relay['status'] = 200
        assert (await cnn.get_cnn_fear_greed())['score'] == 42.25
        assert len(relay['calls']) == 3
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['file', 'cnn_date'])
def test_old_file_or_cnn_day_hides_score(relay, kind):
    if kind == 'file': relay['body']['updated'] = (NOW - timedelta(hours=36, seconds=1)).isoformat()
    else: relay['body']['headline']['cnn-fng']['date'] = (NOW - timedelta(days=4)).date().isoformat()
    # A stale packet with today's headline is contradictory when the file is old.
    if kind == 'file': relay['body']['headline']['cnn-fng']['date'] = (NOW - timedelta(days=2)).date().isoformat()
    result = asyncio.run(cnn.get_cnn_fear_greed())
    assert result['status'] == 'stale' and result['score'] is None and result['rating'] is None


def test_cache_hit_rechecks_age_without_new_request(relay):
    relay['body']['updated'] = (NOW - timedelta(hours=35, minutes=59)).isoformat()
    relay['body']['headline']['cnn-fng']['date'] = (NOW - timedelta(days=2)).date().isoformat()
    async def scenario():
        assert (await cnn.get_cnn_fear_greed())['status'] == 'ok'
        relay['now'] += timedelta(minutes=2)
        result = await cnn.get_cnn_fear_greed()
        assert result['score'] is None and result['status'] == 'stale'
        assert len(relay['calls']) == 1
    asyncio.run(scenario())


def test_real_test_policy_short_circuits_before_client_or_cached_score(monkeypatch):
    monkeypatch.setenv('WEALTH_ENV', 'test')
    factory = Mock(side_effect=AssertionError('External client forbidden'))
    monkeypatch.setattr(cnn.httpx, 'AsyncClient', factory)
    cache = Mock(); cache.get.side_effect = AssertionError('Cache must not bypass test policy')
    monkeypatch.setattr(cnn, '_cache', cache)
    assert asyncio.run(cnn.get_cnn_fear_greed())['score'] is None
    factory.assert_not_called()
    cache.get.assert_not_called()


def test_adapter_never_writes_financial_or_user_files(relay, monkeypatch, tmp_path):
    from app.services import portfolio, financial_json, secure_files, user_manager
    sentinel = tmp_path / 'synthetic-finance.json'; sentinel.write_bytes(b'unchanged')
    forbidden = Mock(side_effect=AssertionError('Financial/user IO forbidden'))
    for mod, name in [(portfolio, 'write_portfolio'), (portfolio, 'read_portfolio'),
                      (financial_json, 'write_financial_json'), (secure_files, 'atomic_write_private_json'),
                      (user_manager, 'get_user_data_dir')]: monkeypatch.setattr(mod, name, forbidden)
    assert asyncio.run(cnn.get_cnn_fear_greed())['score'] == 42.25
    assert sentinel.read_bytes() == b'unchanged'
    forbidden.assert_not_called()
