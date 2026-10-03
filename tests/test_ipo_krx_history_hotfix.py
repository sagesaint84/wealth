from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.ipo import source_discovery
from app.services.ipo.krx_authenticated_client import (
    AuthenticatedKrxHistoricalClient,
)
from app.services.ipo.krx_client import (
    KRX_NEW_LISTINGS_BLD,
    KRX_NEW_LISTINGS_MENU_ID,
    parse_krx_new_listings_json,
)
from app.services.ipo.store import validate_market_store


class FakeResponse:
    def __init__(
        self,
        *,
        status_code=200,
        payload=None,
        text="",
        headers=None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    @property
    def is_error(self):
        return self.status_code >= 400

    @property
    def is_redirect(self):
        return 300 <= self.status_code < 400

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return FakeResponse(text="ok")

    def post(self, url, *, data=None, headers=None, **kwargs):
        self.calls.append(
            ("POST", url, {"data": data, "headers": headers, **kwargs})
        )

        if url.endswith("MDCCOMS001D1.cmd"):
            return FakeResponse(
                payload={"_error_code": "CD001"},
                text='{"_error_code":"CD001"}',
            )

        return FakeResponse(
            text=(
                '{"output":[{'
                '"ISU_CD":"250030",'
                '"ISU_NM":"\\uc9c4\\ucf54\\uc2a4\\ud14d",'
                '"LIST_DD":"2026/10/14",'
                '"PUBOFR_PRC":"13,500",'
                '"MKT_NM":"\\ucf54\\uc2a4\\ub2e5",'
                '"LEADCOM_MBR_NM":"\\ud558\\ub098\\uc99d\\uad8c"'
                '}]}'
            ),
        )

    def close(self):
        pass


def test_real_krx_new_listing_fields_are_parsed():
    rows = parse_krx_new_listings_json(
        {
            "output": [
                {
                    "ISU_CD": "250030",
                    "ISU_NM": "\uc9c4\ucf54\uc2a4\ud14d",
                    "LIST_DD": "2026/10/14",
                    "PUBOFR_PRC": "13,500",
                    "MKT_NM": "\ucf54\uc2a4\ub2e5",
                    "LEADCOM_MBR_NM": "\ud558\ub098\uc99d\uad8c",
                }
            ]
        }
    )

    assert rows[0]["stock_code"] == "250030"
    assert rows[0]["actual_listing_date"] == "2026-10-14"
    assert rows[0]["final_offer_price"] == 13500.0
    assert rows[0]["lead_managers"] == ["\ud558\ub098\uc99d\uad8c"]


def test_authenticated_history_uses_correct_issue_screen_and_menu():
    fake = FakeClient()

    with patch(
        "app.services.ipo.krx_authenticated_client.load_user_krx_credentials",
        return_value={"login_id": "user", "password": "pw"},
    ), patch(
        "app.services.ipo.krx_authenticated_client.require_external_network",
        return_value=None,
    ), patch(
        "app.services.ipo.krx_authenticated_client.httpx.Client",
        return_value=fake,
    ):
        client = AuthenticatedKrxHistoricalClient(username="alice")
        rows = client.fetch_new_listings(
            "2026-01-01",
            "2026-10-03",
        )

    assert rows[0]["stock_code"] == "250030"

    calls = [
        call
        for call in fake.calls
        if call[0] == "POST"
        and call[1].endswith("getJsonData.cmd")
    ]

    assert len(calls) == 1

    payload = calls[0][2]["data"]
    headers = calls[0][2]["headers"]

    assert (
        KRX_NEW_LISTINGS_BLD
        == "dbms/MDC/STAT/issue/MDCSTAT20001"
    )
    assert KRX_NEW_LISTINGS_MENU_ID == "MDC02021301"

    assert payload["bld"] == KRX_NEW_LISTINGS_BLD
    assert "standard/MDCSTAT20001" not in payload["bld"]
    assert payload["isurCd"] == "ALL"
    assert payload["isurCd2"] == "ALL"
    assert payload["listClssCd"] == "ALL"

    assert (
        f"menuId={KRX_NEW_LISTINGS_MENU_ID}"
        in headers["Referer"]
    )


def test_dart_identity_does_not_create_duplicate_stock_code():
    market = {
        "schema_version": 1,
        "ipos": [
            {
                "ipo_id": "ipo_existing",
                "company_name": "existing",
                "stock_code": "250030",
                "subscription_start": "2026-10-01",
            },
            {
                "ipo_id": "ipo_candidate",
                "company_name": "\uc9c4\ucf54\uc2a4\ud14d",
                "subscription_start": "2026-10-02",
            },
        ],
    }

    dart = MagicMock()
    dart.get_corp_code_master.return_value = [
        {
            "corp_name": "\uc9c4\ucf54\uc2a4\ud14d",
            "corp_code": "12345678",
            "stock_code": "250030",
        }
    ]
    dart.get_filing_list.return_value = {"list": []}
    dart.get_equity_registration_statements.return_value = {}

    source_discovery._apply_dart_schedules(
        market,
        dart=dart,
        target_date_str="2026-10-03",
        start=date(2026, 9, 1),
        end=date(2026, 11, 30),
    )

    candidate = market["ipos"][1]

    assert not candidate.get("stock_code")

    identity = candidate["sources"]["dart_identity"]

    assert identity["reported_stock_code"] == "250030"
    assert (
        identity["stock_code_conflict_ipo_id"]
        == "ipo_existing"
    )

    validate_market_store(market)


def test_krx_openapi_uses_connected_badge_design():
    root = Path(__file__).resolve().parents[1]

    html = (root / "app/static/index.html").read_text(
        encoding="utf-8"
    )
    js = (root / "app/static/wealth.js").read_text(
        encoding="utf-8"
    )

    assert (
        'id="openapiKrxSection" class="openapi-broker-card"'
        in html
    )
    assert (
        'id="openapiKrxBadge" '
        'class="openapi-badge disconnected"'
        in html
    )

    assert (
        "data.configured ? 'connected' : 'disconnected'"
        in js
    )
