import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("WEALTH_ENV", "test")
os.environ.setdefault("WEALTH_TEST_SIGNING_SECRET", "synthetic-kb-test-secret")

from app.services.kb_openapi import (
    KB_REALIZED_MAX_PAGES,
    KBOpenAPI,
    KBOpenAPIError,
    compute_kb_account_key,
    mask_kb_account,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = str(payload)

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if not self.responses:
            raise RuntimeError("No more fake responses")
        return self.responses.pop(0)


class KBRealizedTransportTests(unittest.TestCase):
    def setUp(self):
        self.client = object.__new__(KBOpenAPI)
        self.client.base_url = "https://developer.kbsec.com:32484"
        self.client.app_key = "synthetic-kb-app-key"
        self.client.app_secret = "synthetic-kb-app-secret"
        self.client.gnl_ac_no = "400277078"
        self.client.gds_no = "01"

    def test_auth_headers_and_request_shape(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200", "resultMessage": "성공"},
                "dataBody": {
                    "nxt_key": "                        ",
                    "Record1": [{"trd_dt": "20260901", "shrt_is_cd": "A005930"}],
                },
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-kb-token")),
        ):
            rows, source_key, label = asyncio.run(
                self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930")
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trd_dt"], "20260901")
        self.assertTrue(source_key)
        self.assertEqual(label, "****7078-**")
        self.assertNotIn("400277078", label)
        self.assertNotIn("01", label)

        self.assertEqual(len(fake.requests), 1)
        url, kwargs = fake.requests[0]
        self.assertTrue(url.endswith("/api/v1/ssqm2442"))
        headers = kwargs["headers"]
        self.assertEqual(headers["appKey"], "synthetic-kb-app-key")
        self.assertEqual(headers["Authorization"], "bearer synthetic-kb-token")
        self.assertEqual(headers["Content-Type"], "application/json")

        req_body = kwargs["json"]
        self.assertIn("dataHeader", req_body)
        self.assertIn("dataBody", req_body)
        body = req_body["dataBody"]
        self.assertEqual(body["md_clsf"], "2")  # Online channel semantics
        self.assertEqual(body["inq_strt_dt"], "20260901")
        self.assertEqual(body["inq_end_dt"], "20260930")
        self.assertEqual(body["gnl_ac_no"], "400277078")
        self.assertEqual(body["gds_no"], "01")
        self.assertEqual(body["nxt_key"], "")

    def test_account_tuple_stays_server_side(self):
        key = compute_kb_account_key("400277078", "01")
        label = mask_kb_account("400277078", "01")
        self.assertNotIn("400277078", key)
        self.assertNotIn("400277078", label)
        self.assertEqual(label, "****7078-**")
        self.assertNotIn("01", label)
        # Verify deterministic HMAC
        key2 = compute_kb_account_key("400277078", "01")
        self.assertEqual(key, key2)

    def test_missing_gds_no_fails_closed(self):
        # Explicit None or empty string for gds_no must fail before network request
        fake = FakeClient([])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-kb-token")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", gds_no=""))
            self.assertIn("gds_no", str(ctx.exception))
            self.assertEqual(len(fake.requests), 0)

    def test_missing_gnl_ac_no_fails_closed(self):
        fake = FakeClient([])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-kb-token")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", gnl_ac_no=""))
            self.assertIn("계좌번호", str(ctx.exception))
            self.assertEqual(len(fake.requests), 0)

    def test_md_clsf_channel_semantics(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "", "Record1": []},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930"))
        self.assertEqual(fake.requests[0][1]["json"]["dataBody"]["md_clsf"], "2")

    def test_date_normalizations(self):
        # YYYY-MM-DD -> YYYYMMDD
        s, e = KBOpenAPI.validate_and_normalize_dates("2026-09-01", "2026-09-30")
        self.assertEqual(s, "20260901")
        self.assertEqual(e, "20260930")

        # YYYYMMDD -> YYYYMMDD
        s, e = KBOpenAPI.validate_and_normalize_dates("20260901", "20260930")
        self.assertEqual(s, "20260901")
        self.assertEqual(e, "20260930")

        # Same-day query start == end is valid
        s, e = KBOpenAPI.validate_and_normalize_dates("2026-09-13", "2026-09-13")
        self.assertEqual(s, "20260913")
        self.assertEqual(e, "20260913")

        # start > end fails
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI.validate_and_normalize_dates("20260930", "20260901")

        # invalid calendar date rejected (e.g. Feb 30)
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI.validate_and_normalize_dates("20260230", "20260301")

        # garbage date rejected
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI.validate_and_normalize_dates("not-a-date", "20260930")

    def test_success_response_parsing(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200", "resultMessage": "정상"},
            "dataBody": {
                "nxt_key": "                        ",
                "Record1": [{"item": 1}],
            },
        })
        body, key = KBOpenAPI._parse_realized_response(resp)
        self.assertEqual(key, "                        ")
        self.assertEqual(len(body["Record1"]), 1)

    def test_provider_error_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "500", "resultMessage": "시스템 오류", "processCode": "ERR01"},
            "dataBody": {},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("시스템 오류", str(ctx.exception))

    def test_malformed_envelope_fails_closed(self):
        # missing dataHeader
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._parse_realized_response(FakeResponse({"dataBody": {}}))
        # missing dataBody
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._parse_realized_response(FakeResponse({"dataHeader": {"resultCode": "200"}}))
        # non-json
        bad_json_resp = FakeResponse(None)
        bad_json_resp.json = lambda: (_ for _ in ()).throw(ValueError("not json"))
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._parse_realized_response(bad_json_resp)

    def test_token_refresh_preserves_nxt_key_and_request_state(self):
        fake = FakeClient([
            FakeResponse("Unauthorized", status_code=401),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "KEY_PAGE_2", "Record1": [{"page": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "                        ", "Record1": [{"page": 2}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(side_effect=["initial-tok", "refreshed-tok"])),
        ):
            rows, _, _ = asyncio.run(
                self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock())
            )

        self.assertEqual(len(rows), 2)
        # Verify first retry used refreshed token and preserved original request
        first_req = fake.requests[0]
        self.assertEqual(first_req[1]["headers"]["Authorization"], "bearer initial-tok")
        retry_req = fake.requests[1]
        self.assertEqual(retry_req[1]["headers"]["Authorization"], "bearer refreshed-tok")
        self.assertEqual(retry_req[1]["json"]["dataBody"]["inq_strt_dt"], "20260901")
        self.assertEqual(retry_req[1]["json"]["dataBody"]["nxt_key"], "")

        # Second page had KEY_PAGE_2
        second_page = fake.requests[2]
        self.assertEqual(second_page[1]["json"]["dataBody"]["nxt_key"], "KEY_PAGE_2")

    def test_pagination_single_page_whitespace_terminal(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "   ", "Record1": [{"id": 1}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930"))
        self.assertEqual(len(rows), 1)

    def test_pagination_multiple_pages_new_nxt_key(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "NEXT_P2", "Record1": [{"id": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "NEXT_P3", "Record1": [{"id": 2}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "                        ", "Record1": [{"id": 3}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))
        self.assertEqual(len(rows), 3)
        self.assertEqual(fake.requests[1][1]["json"]["dataBody"]["nxt_key"], "NEXT_P2")
        self.assertEqual(fake.requests[2][1]["json"]["dataBody"]["nxt_key"], "NEXT_P3")

    def test_pagination_repeated_key_fails_closed(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "REPEAT_KEY", "Record1": [{"id": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "REPEAT_KEY", "Record1": [{"id": 2}]},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))
            self.assertIn("PAGINATION_CONTINUATION_KEY_REPEATED", str(ctx.exception))

    def test_pagination_malformed_non_string_key_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200"},
            "dataBody": {"nxt_key": 12345, "Record1": []},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("문자열이 아닙니다", str(ctx.exception))

    def test_pagination_null_key_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200"},
            "dataBody": {"nxt_key": None, "Record1": []},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("null", str(ctx.exception))

    def test_pagination_missing_key_fails_closed(self):
        resp = FakeResponse({
            "dataHeader": {"resultCode": "200"},
            "dataBody": {"Record1": []},
        })
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._parse_realized_response(resp)
        self.assertIn("nxt_key 필드가 누락", str(ctx.exception))

    def test_later_page_failure_returns_no_partial_feed(self):
        fake = FakeClient([
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": "PAGE_2", "Record1": [{"id": 1}]},
            }),
            FakeResponse({
                "dataHeader": {"resultCode": "500", "resultMessage": "Server error"},
                "dataBody": {},
            }),
        ])
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            with self.assertRaises(KBOpenAPIError):
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))

    def test_page_limit_guard_fails_entire_fetch(self):
        # Generate 501 responses with unique keys
        responses = [
            FakeResponse({
                "dataHeader": {"resultCode": "200"},
                "dataBody": {"nxt_key": f"KEY_{i}", "Record1": [{"id": i}]},
            })
            for i in range(KB_REALIZED_MAX_PAGES + 1)
        ]
        fake = FakeClient(responses)
        with (
            patch("app.services.kb_openapi.require_external_network"),
            patch("app.services.kb_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="tok")),
        ):
            with self.assertRaises(KBOpenAPIError) as ctx:
                asyncio.run(self.client.fetch_domestic_realized_pnl(from_date="20260901", to_date="20260930", delay=AsyncMock()))
            self.assertIn("한도", str(ctx.exception))
