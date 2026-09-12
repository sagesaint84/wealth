import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("WEALTH_ENV", "test")
os.environ.setdefault("WEALTH_TEST_SIGNING_SECRET", "synthetic-kiwoom-test-secret")

from app.services.kiwoom_openapi import (
    KIWOOM_DOMESTIC_SAFE_CHUNK_MONTHS,
    KIWOOM_REALIZED_MAX_PAGES,
    KiwoomOpenAPI,
    KiwoomOpenAPIError,
    compute_kiwoom_account_key,
    mask_kiwoom_account,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

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
        return self.responses.pop(0)


class KiwoomRealizedTransportTests(unittest.TestCase):
    def setUp(self):
        self.client = object.__new__(KiwoomOpenAPI)
        self.client.base_url = "https://api.kiwoom.com"
        self.client.app_key = "synthetic-app-key"
        self.client.app_secret = "synthetic-app-secret"

    def test_ka10073_and_ka00001_contract(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 0, "dt_stk_rlzt_pl": [{"dt": "20260901"}]}, headers={"cont-yn": "N", "next-key": "RESIDUAL"}),
        ])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-token")),
        ):
            rows, source_key, label = asyncio.run(self.client.fetch_realized_profit(market="kr", from_date="20260901", to_date="20260930", delay=AsyncMock()))
        self.assertEqual(rows, [{"dt": "20260901"}])
        self.assertTrue(source_key); self.assertNotIn("1234567890", label)
        self.assertEqual(fake.requests[0][1]["headers"]["api-id"], "ka00001")
        realized = fake.requests[1]
        self.assertTrue(realized[0].endswith("/api/dostk/acnt"))
        self.assertEqual(realized[1]["headers"]["api-id"], "ka10073")
        self.assertEqual(realized[1]["json"], {"strt_dt": "20260901", "end_dt": "20260930"})
        self.assertEqual(len(fake.requests), 2)

    def test_domestic_calendar_chunks_cover_ranges_exactly(self):
        self.assertEqual(KIWOOM_DOMESTIC_SAFE_CHUNK_MONTHS, 3)
        cases = (
            ("20260101", "20260331"),
            ("20260101", "20260401"),
            ("20240131", "20240502"),
            ("20240229", "20250228"),
            ("20200115", "20261220"),
            ("20260913", "20260913"),
        )
        from datetime import datetime, timedelta
        for start, end in cases:
            with self.subTest(start=start, end=end):
                chunks = self.client._domestic_realized_date_chunks(start, end)
                self.assertEqual(chunks[0][0], start)
                self.assertEqual(chunks[-1][1], end)
                for index, (chunk_start, chunk_end) in enumerate(chunks):
                    start_date = datetime.strptime(chunk_start, "%Y%m%d").date()
                    end_date = datetime.strptime(chunk_end, "%Y%m%d").date()
                    self.assertLess(end_date, self.client._add_calendar_months(start_date, 3))
                    if index:
                        previous_end = datetime.strptime(chunks[index - 1][1], "%Y%m%d").date()
                        self.assertEqual(start_date, previous_end + timedelta(days=1))

    def test_domestic_chunks_aggregate_zero_and_nonzero_pages(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 0, "dt_stk_rlzt_pl": []}, headers={"cont-yn": "N"}),
            FakeResponse({"return_code": 0, "dt_stk_rlzt_pl": [{"dt": "20260410"}]}, headers={"cont-yn": "N"}),
            FakeResponse({"return_code": 0, "dt_stk_rlzt_pl": [{"dt": "20260701"}, {"dt": "20260701"}]}, headers={"cont-yn": "N"}),
        ])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-token")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_realized_profit(
                market="kr", from_date="20260101", to_date="20260701", delay=AsyncMock(),
            ))
        self.assertEqual(rows, [{"dt": "20260410"}, {"dt": "20260701"}, {"dt": "20260701"}])
        bodies = [request[1]["json"] for request in fake.requests[1:]]
        self.assertEqual(bodies, [
            {"strt_dt": "20260101", "end_dt": "20260331"},
            {"strt_dt": "20260401", "end_dt": "20260630"},
            {"strt_dt": "20260701", "end_dt": "20260701"},
        ])

    def test_domestic_all_zero_chunks_return_empty_only_after_all_requests(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 0, "dt_stk_rlzt_pl": []}, headers={"cont-yn": "N"}),
            FakeResponse({"return_code": 0, "dt_stk_rlzt_pl": []}, headers={"cont-yn": "N"}),
        ])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-token")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_realized_profit(
                market="kr", from_date="20260101", to_date="20260401", delay=AsyncMock(),
            ))
        self.assertEqual(rows, [])
        self.assertEqual(len(fake.requests), 3)

    def test_domestic_chunk_failure_is_atomic_and_token_flows_between_chunks(self):
        page_fetch = AsyncMock(side_effect=[
            ([{"dt": "20260102"}], "refreshed-token"),
            KiwoomOpenAPIError("PAGINATION_LIMIT_EXCEEDED"),
        ])
        fake = FakeClient([])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="initial-token")),
            patch.object(self.client, "discover_realized_source_account", new=AsyncMock(return_value=("synthetic", "key", "masked", "initial-token"))),
            patch.object(self.client, "_fetch_realized_pages", new=page_fetch),
        ):
            with self.assertRaisesRegex(KiwoomOpenAPIError, "PAGINATION_LIMIT_EXCEEDED"):
                asyncio.run(self.client.fetch_realized_profit(
                    market="kr", from_date="20260101", to_date="20260401", delay=AsyncMock(),
                ))
        self.assertEqual(page_fetch.await_count, 2)
        self.assertEqual(page_fetch.await_args_list[0].args[1], "initial-token")
        self.assertEqual(page_fetch.await_args_list[1].args[1], "refreshed-token")

    def test_ust21530_uses_foreign_currency_basis(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 0, "result_list": [{"sell_dt": "20260901"}]}, headers={"cont-yn": "N"}),
        ])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-token")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_realized_profit(market="us", from_date="20260901", to_date="20260930", delay=AsyncMock()))
        self.assertEqual(rows, [{"sell_dt": "20260901"}])
        realized = fake.requests[1]
        self.assertTrue(realized[0].endswith("/api/us/acnt"))
        self.assertEqual(realized[1]["headers"]["api-id"], "ust21530")
        self.assertEqual(realized[1]["json"]["fc_krw_tp"], "0")

    def test_ust21530_verified_no_data_is_a_successful_empty_result(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 20, "return_msg": "571758:조회내역이 없습니다"}, headers={"cont-yn": "N", "next-key": "RESIDUAL"}),
        ])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-token")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_realized_profit(
                market="us", from_date="2026-09-01", to_date="20260930", delay=AsyncMock(),
            ))
        self.assertEqual(rows, [])
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.requests[1][1]["json"], {"strt_dt": "20260901", "end_dt": "20260930", "fc_krw_tp": "0"})

    def test_ust21530_no_data_preserves_continuation_headers(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 20, "return_msg": "[provider] (571758: 조회내역이 없습니다.)"}, headers={"cont-yn": "Y", "next-key": "NEXT-EMPTY"}),
            FakeResponse({"return_code": 0, "result_list": [{"sell_dt": "20260902"}]}, headers={"cont-yn": "N"}),
        ])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-token")),
        ):
            rows, _, _ = asyncio.run(self.client.fetch_realized_profit(
                market="us", from_date="20260901", to_date="20260930", delay=AsyncMock(),
            ))
        self.assertEqual(rows, [{"sell_dt": "20260902"}])
        self.assertEqual(fake.requests[2][1]["headers"]["cont-yn"], "Y")
        self.assertEqual(fake.requests[2][1]["headers"]["next-key"], "NEXT-EMPTY")

    def test_no_data_envelope_variants_and_nonzero_responses_remain_narrow(self):
        for message in (
            "571758:조회내역이 없습니다",
            " [ wrapper ] (571758 : 조회내역이 없습니다.) ",
        ):
            with self.subTest(accepted_message=message):
                payload, _, _ = self.client._parse_realized_response(
                    FakeResponse({"return_code": 20, "return_msg": message}), api_id="ust21530",
                )
                self.assertTrue(payload["_kiwoom_ust21530_no_data"])
        for api_id, payload in (
            ("ust21530", {"return_code": 20, "return_msg": "571759:조회내역이 없습니다"}),
            ("ust21530", {"return_code": 20, "return_msg": "571758:다른 업무 오류"}),
            ("ust21530", {"return_code": 21, "return_msg": "571758:조회내역이 없습니다"}),
            ("ka10073", {"return_code": 20, "return_msg": "571758:조회내역이 없습니다"}),
        ):
            with self.subTest(api_id=api_id, payload=payload):
                with self.assertRaises(KiwoomOpenAPIError):
                    self.client._parse_realized_response(FakeResponse(payload), api_id=api_id)

    def test_ust21530_no_data_with_y_and_missing_key_fails_closed(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 20, "return_msg": "571758:조회내역이 없습니다"}, headers={"cont-yn": "Y"}),
        ])
        with (
            patch("app.services.kiwoom_openapi.require_external_network"),
            patch("app.services.kiwoom_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="synthetic-token")),
        ):
            with self.assertRaisesRegex(KiwoomOpenAPIError, "KEY_MISSING"):
                asyncio.run(self.client.fetch_realized_profit(
                    market="us", from_date="20260901", to_date="20260930", delay=AsyncMock(),
                ))

    def test_page_two_refresh_preserves_continuation_and_rows(self):
        fake = FakeClient([
            FakeResponse({"return_code": 0, "items": [{"page": 1}]}, headers={"cont-yn": "Y", "next-key": "FULL-NEXT"}),
            FakeResponse({"return_code": -1}, status_code=401),
            FakeResponse({"return_code": 0, "items": [{"page": 2}]}, headers={"cont-yn": "N", "next-key": "RESIDUAL"}),
        ])
        delay = AsyncMock()
        with patch.object(self.client, "_access_token", new=AsyncMock(return_value="refreshed-token")):
            rows, token = asyncio.run(self.client._fetch_realized_pages(
                fake, "first-token", path="/api/dostk/acnt", api_id="ka10073",
                body={"strt_dt": "20260901", "end_dt": "20260930"}, rows_field="items", delay=delay,
            ))
        self.assertEqual(rows, [{"page": 1}, {"page": 2}]); self.assertEqual(token, "refreshed-token")
        self.assertEqual(len(fake.requests), 3); delay.assert_awaited_once_with(0.2)
        for request in fake.requests[1:]:
            self.assertEqual(request[1]["headers"]["cont-yn"], "Y")
            self.assertEqual(request[1]["headers"]["next-key"], "FULL-NEXT")

    def test_pagination_guards_and_final_residual_key(self):
        final = AsyncMock(return_value=({"items": [{"page": 1}]}, "N", "RESIDUAL", "token"))
        with patch.object(self.client, "_post_realized_page", new=final):
            rows, _ = asyncio.run(self.client._fetch_realized_pages(
                object(), "token", path="/x", api_id="x", body={}, rows_field="items", delay=AsyncMock(),
            ))
        self.assertEqual(rows, [{"page": 1}]); self.assertEqual(final.await_count, 1)

        missing = AsyncMock(return_value=({"items": []}, "Y", "", "token"))
        with patch.object(self.client, "_post_realized_page", new=missing):
            with self.assertRaisesRegex(KiwoomOpenAPIError, "KEY_MISSING"):
                asyncio.run(self.client._fetch_realized_pages(object(), "token", path="/x", api_id="x", body={}, rows_field="items", delay=AsyncMock()))

        repeated = AsyncMock(side_effect=[
            ({"items": [{"page": 1}]}, "Y", "SAME-FULL-KEY", "token"),
            ({"items": [{"page": 2}]}, "Y", "SAME-FULL-KEY", "token"),
        ])
        with patch.object(self.client, "_post_realized_page", new=repeated):
            with self.assertRaisesRegex(KiwoomOpenAPIError, "KEY_REPEATED"):
                asyncio.run(self.client._fetch_realized_pages(object(), "token", path="/x", api_id="x", body={}, rows_field="items", delay=AsyncMock()))
        self.assertEqual(repeated.await_count, 2)

    def test_page_limit_is_ten(self):
        pages = AsyncMock(side_effect=[
            ({"items": [{"page": index + 1}]}, "Y", f"KEY-{index}", "token")
            for index in range(KIWOOM_REALIZED_MAX_PAGES)
        ])
        with patch.object(self.client, "_post_realized_page", new=pages):
            with self.assertRaisesRegex(KiwoomOpenAPIError, "PAGINATION_LIMIT_EXCEEDED"):
                asyncio.run(self.client._fetch_realized_pages(object(), "token", path="/x", api_id="x", body={}, rows_field="items", delay=AsyncMock()))
        self.assertEqual(pages.await_count, 10)

    def test_account_identity_and_secret_fail_closed(self):
        first = compute_kiwoom_account_key("1234-567890", secret="synthetic-secret")
        self.assertEqual(first, compute_kiwoom_account_key("1234567890", secret="synthetic-secret"))
        self.assertNotEqual(first, compute_kiwoom_account_key("9999999999", secret="synthetic-secret"))
        self.assertNotIn("1234567890", first)
        self.assertNotIn("1234567890", mask_kiwoom_account("1234567890"))
        with patch.dict(os.environ, {"WEALTH_ENV": "production", "DASHBOARD_SECRET_KEY": "", "WEALTH_TEST_SIGNING_SECRET": ""}, clear=False):
            with self.assertRaises(KiwoomOpenAPIError):
                compute_kiwoom_account_key("1234567890")

    def test_date_validation(self):
        self.assertEqual(self.client._validate_realized_dates("20260901", "20260930"), ("20260901", "20260930"))
        self.assertEqual(self.client._validate_realized_dates("2026-09-01", "20260930"), ("20260901", "20260930"))
        self.assertEqual(self.client._validate_realized_dates("20260901", "2026-09-30"), ("20260901", "20260930"))
        for values in (
            ("20260230", "20260930"), ("20260930", "20260901"), ("2026--09-01", "20260930"),
            ("2026-9-1", "20260930"), ("202609-01", "20260930"), ("2026/09/01", "20260930"),
            ("2026-02-30", "20260930"),
        ):
            with self.subTest(values=values), self.assertRaises(KiwoomOpenAPIError):
                self.client._validate_realized_dates(*values)


if __name__ == "__main__":
    unittest.main()
