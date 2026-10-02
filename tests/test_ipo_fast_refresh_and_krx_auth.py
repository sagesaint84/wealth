from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.ipo import historical_online_sync, orchestrator, refresh_adapter
from app.services.ipo.krx_authenticated_client import AuthenticatedKrxHistoricalClient


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload=None, text: str | None = None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else ""

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeHttpxClient:
    def __init__(self, *args, **kwargs):
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return _FakeResponse(status_code=200, text="ok")

    def post(self, url, *, data=None, **kwargs):
        self.calls.append(("POST", url))
        if url.endswith("MDCCOMS001D1.cmd"):
            return _FakeResponse(status_code=200, payload={"_error_code": "CD001"}, text='{"_error_code":"CD001"}')
        return _FakeResponse(
            status_code=200,
            payload={"output": []},
            text=(
                '{"output":[{"ISU_SRT_CD":"250030","ISU_ABBRV":"진코스텍",'
                '"LIST_DD":"2026/10/14","IPO_PRC":"13500","MKT_NM":"코스닥",'
                '"LEAD_MGR":"하나증권"}]}'
            ),
        )

    def close(self):
        self.closed = True


def test_interactive_refresh_never_runs_heavy_adapter_discovery() -> None:
    with patch("app.services.ipo.orchestrator.run_ipo_daily_pipeline", return_value={"status": "ok"}) as pipeline, \
         patch("app.services.ipo.refresh_adapter._run_supplement_and_targeted") as heavy:
        result = orchestrator.refresh_ipo_market(username="alice", target_date_str="2026-10-02")

    assert result["status"] == "ok"
    pipeline.assert_called_once_with(
        username="alice",
        target_date_str="2026-10-02",
        market_only=True,
    )
    heavy.assert_not_called()
    assert orchestrator.refresh_ipo_market is refresh_adapter._BASE_REFRESH_MARKET


def test_online_history_without_credentials_fails_before_network() -> None:
    with patch.dict(os.environ, {"KRX_ID": "", "KRX_PW": ""}, clear=False):
        with pytest.raises(historical_online_sync.HistoricalOnlineSyncError) as exc:
            historical_online_sync.create_online_historical_preview("alice")

    assert exc.value.code == "KRX_AUTH_REQUIRED"
    assert "KRX_ID" in str(exc.value)
    assert "KRX_PW" in str(exc.value)


def test_authenticated_krx_history_reuses_one_login_session() -> None:
    fake = _FakeHttpxClient()
    with patch.dict(os.environ, {"KRX_ID": "test-user", "KRX_PW": "test-password"}, clear=False), \
         patch("app.services.ipo.krx_authenticated_client.require_external_network", return_value=None), \
         patch("app.services.ipo.krx_authenticated_client.httpx.Client", return_value=fake):
        client = AuthenticatedKrxHistoricalClient()
        first = client.fetch_new_listings("2026-01-01", "2026-06-30")
        second = client.fetch_new_listings("2026-07-01", "2026-10-02")

    assert first[0]["stock_code"] == "250030"
    assert first[0]["market"] == "코스닥"
    assert second[0]["actual_listing_date"] == "2026-10-14"
    login_posts = [url for method, url in fake.calls if method == "POST" and url.endswith("MDCCOMS001D1.cmd")]
    data_posts = [url for method, url in fake.calls if method == "POST" and url.endswith("getJsonData.cmd")]
    assert len(login_posts) == 1
    assert len(data_posts) == 2


def test_ghcr_compose_passes_krx_credentials_without_embedding_values() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "docker-compose.ghcr.yml").read_text(encoding="utf-8")
    assert "KRX_ID: ${KRX_ID:-}" in source
    assert "KRX_PW: ${KRX_PW:-}" in source
    assert "test-password" not in source
