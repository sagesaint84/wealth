"""Demo writes must use authenticated identity and disposable storage only."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import inspect
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
import pytest

from app.services import portfolio, user_manager
from regression_support import import_main_without_loading_real_env


@pytest.fixture
def demo_storage(tmp_path, monkeypatch):
    # Exercise the real get_user_data_dir(), including its legacy None fallback,
    # without ever resolving a path into the repository's data directory.
    monkeypatch.setattr(user_manager, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(user_manager, 'USERS_DIR', tmp_path / 'users')
    monkeypatch.setattr(user_manager, 'USERS_FILE', tmp_path / 'users.json')
    for username in ('user_a', 'sagesaint', 'user_b'):
        data = deepcopy(portfolio.EMPTY_PORTFOLIO)
        data['accounts'] = [{'id': f'synthetic-{username}', 'name': username}]
        portfolio.write_portfolio(data, username=username)
    return tmp_path


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


def assert_demo_only_for_a(root: Path, before: dict[str, bytes]) -> None:
    after = snapshot(root)
    assert after.keys() == before.keys()
    for username in ('sagesaint', 'user_b'):
        key = f'users/{username}/portfolio.json'
        assert after[key] == before[key], f'{username} portfolio changed'
    assert after['users/user_a/portfolio.json'] != before['users/user_a/portfolio.json']
    data = portfolio.read_portfolio(username='user_a')
    assert len(data['accounts']) == 3
    assert {h['code'] for h in data['holdings']} == {'005930', '000660', 'AAPL', 'NVDA'}
    assert len(data['holdings']) == 4
    assert data['settings']['fx_rates']['USD'] == 1350.0
    assert data['settings']['fx_info']['source'] == '예시 데이터'
    assert sorted(data['settings']['cash_balances'].values(), key=lambda v: v['KRW']) == [
        {'KRW': 1200000.0, 'USD': 0.0}, {'KRW': 5000000.0, 'USD': 2500.0},
    ]


@pytest.mark.parametrize('spoof_identity', [False, True])
def test_authenticated_demo_endpoint_only_writes_current_user(demo_storage, monkeypatch, spoof_identity):
    main = import_main_without_loading_real_env()
    # Signed-cookie parsing and require_login still run; only the persisted user
    # lookup is synthetic, so users.json/credentials are never loaded.
    monkeypatch.setattr(user_manager, 'get_user_by_name', lambda name:
                        {'username': name, 'role': 'user'} if name == 'user_a' else None)
    before = snapshot(demo_storage)
    with TestClient(main.app) as client:
        client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({'user': 'user_a'}))
        response = client.post('/api/demo?username=user_b' if spoof_identity else '/api/demo',
                               json={'username': 'sagesaint'} if spoof_identity else None)
    assert response.status_code == 200
    assert response.json() == {'message': '예시 데이터를 불러왔습니다.'}
    assert_demo_only_for_a(demo_storage, before)


def test_seed_demo_service_isolates_user_and_preserves_other_bytes(demo_storage):
    before = snapshot(demo_storage)
    portfolio.seed_demo(username='user_a')
    assert_demo_only_for_a(demo_storage, before)


@pytest.mark.parametrize('cookie', [None, 'invalid', 'deleted-user'])
def test_unauthenticated_demo_never_writes(demo_storage, monkeypatch, cookie):
    main = import_main_without_loading_real_env()
    monkeypatch.setattr(user_manager, 'get_user_by_name', lambda name: None)
    before = snapshot(demo_storage)
    with patch.object(main, 'seed_demo', wraps=portfolio.seed_demo) as seed, TestClient(main.app) as client:
        if cookie:
            token = main._serializer.dumps({'user': cookie}) if cookie == 'deleted-user' else cookie
            client.cookies.set(main.COOKIE_NAME, token)
        response = client.post('/api/demo?username=sagesaint', json={'username': 'user_a'})
        seed.assert_not_called()
    assert response.status_code == 401
    assert snapshot(demo_storage) == before


def test_demo_handler_rejects_missing_identity_even_without_middleware(demo_storage):
    main = import_main_without_loading_real_env()
    before = snapshot(demo_storage)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/demo', 'headers': []})
    with patch.object(main, 'seed_demo') as seed, pytest.raises(HTTPException) as error:
        asyncio.run(main.load_demo(request))
    assert error.value.status_code == 401
    seed.assert_not_called()
    assert snapshot(demo_storage) == before


def test_seed_demo_requires_username(demo_storage):
    assert inspect.signature(portfolio.seed_demo).parameters['username'].default is inspect.Parameter.empty
    before = snapshot(demo_storage)
    with pytest.raises(TypeError):
        portfolio.seed_demo()
    assert snapshot(demo_storage) == before


@pytest.mark.parametrize('username', [None, '', '  ', 123])
def test_seed_demo_rejects_explicit_fallback_identities(demo_storage, username):
    before = snapshot(demo_storage)
    with patch.object(portfolio, 'write_portfolio') as write, pytest.raises(ValueError):
        portfolio.seed_demo(username=username)
    write.assert_not_called()
    assert snapshot(demo_storage) == before
