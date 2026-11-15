from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.services.ipo import historical_online_sync, source_discovery
from app.services.ipo.krx_authenticated_client import AuthenticatedKrxHistoricalClient
from app.services.user_krx_credentials import (
    credential_path, krx_credential_status, load_user_krx_credentials,
    save_user_krx_credentials,
)


class _FakeResponse:
    def __init__(self, *, status_code=200, payload=None, text=''):
        self.status_code = status_code; self._payload = payload; self.text = text
    @property
    def is_error(self): return self.status_code >= 400
    @property
    def is_redirect(self): return 300 <= self.status_code < 400
    def json(self): return self._payload


class _FakeHttpxClient:
    def __init__(self): self.calls = []; self.closed = False
    def get(self, url, **kwargs): self.calls.append(('GET', url)); return _FakeResponse(text='ok')
    def post(self, url, *, data=None, **kwargs):
        self.calls.append(('POST', url))
        if url.endswith('MDCCOMS001D1.cmd'):
            return _FakeResponse(payload={'_error_code':'CD001'}, text='{"_error_code":"CD001"}')
        return _FakeResponse(text='{"output":[{"ISU_SRT_CD":"250030","ISU_ABBRV":"진코스텍","LIST_DD":"2026/10/14","IPO_PRC":"13500","MKT_NM":"코스닥","LEAD_MGR":"하나증권"}]}')
    def close(self): self.closed = True


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("2026-10-02", (date(2026, 9, 1), date(2026, 11, 30))),
        ("2026-11-01", (date(2026, 10, 1), date(2026, 12, 31))),
        ("2026-12-15", (date(2026, 11, 1), date(2027, 1, 31))),
        ("2027-01-10", (date(2026, 12, 1), date(2027, 2, 28))),
        ("2028-02-10", (date(2028, 1, 1), date(2028, 3, 31))),
    ],
)
def test_interactive_window_rolls_with_target_month(target, expected):
    assert source_discovery._month_window(target) == expected


def test_dart_skips_corp_master_when_bounded_candidates_already_have_corp_code():
    market = {'ipos':[{'company_name':'진코스텍','corp_code':'12345678','subscription_start':'2026-10-02'}]}
    dart = MagicMock(); dart.get_filing_list.return_value = {'list':[]}; dart.get_equity_registration_statements.return_value = {}
    source_discovery._apply_dart_schedules(market, dart=dart, target_date_str='2026-10-02', start=date(2026,9,1), end=date(2026,11,30))
    dart.get_corp_code_master.assert_not_called()


def test_krx_credentials_are_user_scoped_and_masked():
    with tempfile.TemporaryDirectory() as tmp, patch('app.services.user_krx_credentials.get_user_data_dir', return_value=Path(tmp) / 'alice'):
        status = save_user_krx_credentials('alice', {'login_id':'mykrxid','password':'super-secret'})
        assert status['configured'] is True
        assert status['login_id'] == 'mykr****'
        assert 'password' not in status
        raw = load_user_krx_credentials('alice')
        assert raw == {'login_id':'mykrxid','password':'super-secret'}
        assert credential_path('alice').parent.name == 'secrets'


def test_online_history_without_user_credentials_fails_before_network():
    with patch.object(AuthenticatedKrxHistoricalClient, 'credentials_configured', return_value=False):
        with pytest.raises(historical_online_sync.HistoricalOnlineSyncError) as exc:
            historical_online_sync.create_online_historical_preview('alice')
    assert exc.value.code == 'KRX_AUTH_REQUIRED'
    assert 'OpenAPI 설정' in str(exc.value)


def test_authenticated_krx_history_uses_user_credentials_and_reuses_session():
    fake = _FakeHttpxClient()
    with patch('app.services.ipo.krx_authenticated_client.load_user_krx_credentials', return_value={'login_id':'test-user','password':'test-password'}), \
         patch('app.services.ipo.krx_authenticated_client.require_external_network', return_value=None), \
         patch('app.services.ipo.krx_authenticated_client.httpx.Client', return_value=fake):
        client = AuthenticatedKrxHistoricalClient(username='alice')
        first = client.fetch_new_listings('2026-01-01','2026-06-30')
        second = client.fetch_new_listings('2026-07-01','2026-10-02')
    assert first[0]['stock_code'] == '250030'
    assert second[0]['actual_listing_date'] == '2026-10-14'
    assert len([u for m,u in fake.calls if m == 'POST' and u.endswith('MDCCOMS001D1.cmd')]) == 1
    assert len([u for m,u in fake.calls if m == 'POST' and u.endswith('getJsonData.cmd')]) == 2


def test_krx_credentials_are_not_wired_through_env_or_compose():
    root = Path(__file__).resolve().parents[1]
    env = (root / '.env.example').read_text(encoding='utf-8')
    compose = (root / 'docker-compose.ghcr.yml').read_text(encoding='utf-8')
    assert 'KRX_ID' not in env and 'KRX_PW' not in env
    assert 'KRX_ID' not in compose and 'KRX_PW' not in compose


def test_settings_surface_contains_user_krx_settings_controls():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'app/static/wealth-settings-surface.js').read_text(encoding='utf-8')
    js = (root / 'app/static/wealth.js').read_text(encoding='utf-8')
    for token in ('openapiKrxLoginId','openapiKrxPassword','openapiKrxBadge'):
        assert token in html
    assert '/api/user/krx-marketplace-config' in js
    assert 'WEALTH_KRX_MARKETPLACE_CONFIG_V1' in js
