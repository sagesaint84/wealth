"""Synthetic display metadata: isolated users, atomic patches and no financial changes."""
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from app.services import color_preferences as colors, portfolio
from regression_support import empty_portfolio, import_main_without_loading_real_env


@pytest.fixture
def users(tmp_path, monkeypatch):
    def directory(username=None):
        path = tmp_path / (username or 'alice')
        path.mkdir(exist_ok=True)
        return path
    monkeypatch.setattr('app.services.user_manager.get_user_data_dir', directory)
    for user in ('alice', 'bob'):
        data = empty_portfolio(bank_accounts=[{'id':user, 'balance':123456}], settings={'existing':'preserved'})
        data['updated_at'] = 'unchanged'
        portfolio.write_financial_json(directory(user)/'portfolio.json', data)
    return directory


def test_round_trip_reset_and_financial_bytes_semantics(users):
    path = users('alice')/'portfolio.json'
    before = path.read_bytes()
    assert colors.read_colors('alice') == colors.empty()
    assert path.read_bytes() == before
    payload = {'group':'asset_category_colors','key':'real_estate','color':' #aBcDeF '}
    assert colors.patch_color('alice', payload)['asset_category_colors'] == {'real_estate':'#ABCDEF'}
    after = json.loads(path.read_text(encoding='utf-8'))
    original = json.loads(before)
    del after['settings']['visualization_colors']
    assert after == original
    saved = path.read_bytes()
    colors.patch_color('alice', payload)
    assert path.read_bytes() == saved  # no-op does not rewrite
    assert colors.read_colors('bob') == colors.empty()
    colors.patch_color('alice', dict(payload, color=None))
    assert colors.read_colors('alice') == colors.empty()


@pytest.mark.parametrize('patch', [
    {'color':'red'}, {'color':'#123'}, {'color':'#12345678'}, {'color':float('nan')},
    {'key':'constructor'}, {'key':'bad key'}, {'group':'financial'},
    {'group':'calendar_event_colors','key':'unknown'},
    {'group':'calendar_event_colors','key':'interest'}, {'username':'bob'},
])
def test_invalid_patch_preserves_bytes(users, patch):
    before = (users('alice')/'portfolio.json').read_bytes()
    with pytest.raises(ValueError):
        colors.patch_color('alice', dict({'group':'stock_category_colors','key':'cash','color':'#123456'}, **patch))
    assert (users('alice')/'portfolio.json').read_bytes() == before


def test_concurrent_independent_keys_are_preserved(users):
    keys = ['id:sector-'+str(i) for i in range(16)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda key: colors.patch_color('alice', {'group':'stock_category_colors','key':key,'color':'#ff5a5f'}), keys))
    assert colors.read_colors('alice')['stock_category_colors'] == dict.fromkeys(keys, '#FF5A5F')


def test_failed_write_does_not_change_canonical_bytes(users, monkeypatch):
    path = users('alice')/'portfolio.json'
    before = path.read_bytes()
    def fail(*args, **kwargs):
        raise OSError('synthetic write failure')
    monkeypatch.setattr(portfolio, 'write_financial_json', fail)
    with pytest.raises(OSError, match='synthetic write failure'):
        colors.patch_color('alice', {'group':'asset_category_colors','key':'cash','color':'#22C7B8'})
    assert path.read_bytes() == before


@pytest.mark.parametrize('stored', [{'asset_category_colors':[]}, {'asset_category_colors':{'cash':'bad'}}, {'unknown':{}}])
def test_malformed_stored_settings_fail_closed(users, stored):
    path = users('alice')/'portfolio.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['settings']['visualization_colors'] = stored
    portfolio.write_financial_json(path, data)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        colors.patch_color('alice', {'group':'asset_category_colors','key':'cash','color':'#123456'})
    assert path.read_bytes() == before


def test_api_authentication_and_user_scope(users, monkeypatch):
    from fastapi.testclient import TestClient
    main = import_main_without_loading_real_env()
    monkeypatch.setattr('app.services.user_manager.get_user_by_name', lambda name: {'username':name,'role':'user'})
    with TestClient(main.app) as client:
        assert client.get('/api/color-preferences').status_code == 401
        client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({'user':'alice','role':'user'}))
        payload = {'group':'calendar_event_colors','key':'dividend','color':'#ff5fa2'}
        assert client.patch('/api/color-preferences', json=payload).status_code == 200
        assert client.get('/api/color-preferences').json()['calendar_event_colors']['dividend'] == '#FF5FA2'
        before = (users('alice')/'portfolio.json').read_bytes()
        assert client.patch('/api/color-preferences', json=dict(payload,key='interest')).status_code == 400
        assert (users('alice')/'portfolio.json').read_bytes() == before
        assert colors.read_colors('bob') == colors.empty()
        assert client.patch('/api/color-preferences', json=dict(payload,username='bob')).status_code == 400
