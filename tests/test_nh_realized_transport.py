import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("WEALTH_ENV", "test")

from app.services.nhplug_openapi import NhPlugOpenAPI, NhPlugOpenAPIError, compute_nh_account_key, mask_nh_account


class _FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = "synthetic response"

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        return self._payload


class _FakeAsyncClient:
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


class NhRealizedTransportTests(unittest.TestCase):
    def setUp(self):
        # Transport methods under test need no credentials, config, or user storage.
        self.client = object.__new__(NhPlugOpenAPI)

    def test_opaque_key_is_stable_and_mask_has_no_full_account(self):
        first = compute_nh_account_key("1234567890", secret="synthetic-secret")
        second = compute_nh_account_key("1234567890", secret="synthetic-secret")
        other = compute_nh_account_key("9999999999", secret="synthetic-secret")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertNotIn("1234567890", first)
        self.assertNotIn("1234567890", mask_nh_account("1234567890"))

    def test_domestic_two_tier_uses_discovered_dates_and_official_fields(self):
        daily = [{"Output_1": [
            {"sby_dt": "20260102", "sll_qty": "1", "sll_amt": "100", "pls_amt": "10"},
            {"sby_dt": "20260102", "sll_qty": "2", "sll_amt": "200", "pls_amt": "20"},
            {"sby_dt": "20260103", "sll_qty": "0", "sll_amt": "0", "pls_amt": "5"},
        ]}]
        details = {
            "20260102": [{"Output_1": [{"iem_cd": "SYN1", "iem_nm": "Synthetic", "byn_qty": "1", "byn_amt": "90", "sll_qty": "1", "sll_amt": "100", "pls_amt": "10"}]}],
            "20260103": [{"Output_1": [{"iem_cd": "SYN2", "iem_nm": "Synthetic", "byn_qty": "1", "byn_amt": "0", "sll_qty": "0", "sll_amt": "0", "pls_amt": "5"}]}],
        }
        calls = []
        async def pages(path, input_0):
            calls.append((path, input_0))
            return daily if path.endswith("dailyPnl") else details[input_0["iqr_sta_dt"]]
        with patch.object(self.client, "_call_pages", side_effect=pages):
            rows, key, label = asyncio.run(self.client.fetch_realized_profit(act_no="1234567890", market="kr", from_date="20260101", to_date="20260131"))
        self.assertEqual(len(rows), 2)
        self.assertTrue(key)
        self.assertNotIn("1234567890", label)
        self.assertEqual([r["_wealth_date_context"] for r in rows], ["20260102", "20260103"])
        self.assertEqual(calls[1][1]["iqr_sta_dt"], calls[1][1]["iqr_end_dt"])

    def test_overseas_uses_000_only_for_discovery_and_output_zero_details(self):
        discovery = [{"Output_1": [
            {"orr_dt": "20260102", "fc_sec_trd_nat_cd": "200", "trd_cur_cd": "USD", "sll_qty": "1"},
            {"orr_dt": "20260103", "fc_sec_trd_nat_cd": "070", "trd_cur_cd": "JPY", "fc_rzt_pls": "5"},
        ]}]
        calls = []
        async def pages(path, input_0):
            calls.append((path, input_0))
            if path.endswith("periodPnl"):
                return discovery
            return [{"Output_0": [{"iem_cd": "SYN", "iem_nm": "Synthetic", "fc_rzt_pls": "1"}]}]
        with patch.object(self.client, "_call_pages", side_effect=pages):
            rows, _, _ = asyncio.run(self.client.fetch_realized_profit(act_no="1234567890", market="us", from_date="20260101", to_date="20260131"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(calls[0][1]["fc_sec_trd_nat_cd"], "000")
        self.assertTrue(all(call[1].get("fc_sec_trd_nat_cd") != "000" for call in calls[1:]))
        self.assertEqual(rows[0]["_wealth_country_context"], "200")

    def test_pagination_rejects_y_without_cts(self):
        async def call(_path, _input, cts=""):
            return {"_wealth_continuation": {"cts": "", "flag": "Y"}}
        with patch.object(self.client, "_call", side_effect=call):
            with self.assertRaises(NhPlugOpenAPIError):
                asyncio.run(self.client._call_pages("/synthetic", {}))

    def test_pagination_rejects_contradictory_states(self):
        states = [
            {"cts": "NEXT", "flag": "MAYBE"},
            {"cts": "", "flag": "MAYBE"},
        ]
        for state in states:
            with self.subTest(state=state):
                with patch.object(self.client, "_call", new=AsyncMock(return_value={"_wealth_continuation": state})):
                    with self.assertRaises(NhPlugOpenAPIError):
                        asyncio.run(self.client._call_pages("/synthetic", {}))
        for malformed in ([], {"cts": ["NEXT"], "flag": "Y"}, {"cts": "NEXT", "flag": 1}):
            with self.subTest(malformed=malformed):
                with patch.object(self.client, "_call", new=AsyncMock(return_value={"_wealth_continuation": malformed})):
                    with self.assertRaises(NhPlugOpenAPIError):
                        asyncio.run(self.client._call_pages("/synthetic", {}))

    def test_n_terminates_cleanly_with_or_without_cts(self):
        for token in ("", "FINAL-ECHO"):
            with self.subTest(token=token):
                call = AsyncMock(return_value={"Output_1": [{"page": "final"}], "_wealth_continuation": {"cts": token, "flag": "N"}})
                with patch.object(self.client, "_call", new=call):
                    pages = asyncio.run(self.client._call_pages("/synthetic", {}))
                self.assertEqual(pages[0]["Output_1"], [{"page": "final"}])
                self.assertEqual(call.await_count, 1)

    def test_y_continues_and_repeated_full_cts_stops_cleanly(self):
        repeated = AsyncMock(side_effect=[
            {"Output_1": [{"page": 1}], "_wealth_continuation": {"cts": "FULL-TOKEN", "flag": "Y"}},
            {"Output_1": [{"page": 2}], "_wealth_continuation": {"cts": "FULL-TOKEN", "flag": "Y"}},
        ])
        with patch.object(self.client, "_call", new=repeated):
            pages = asyncio.run(self.client._call_pages("/synthetic", {}))
        self.assertEqual([page["Output_1"][0]["page"] for page in pages], [1, 2])
        self.assertEqual(repeated.await_count, 2)

    def test_page_guard_remains_fail_closed(self):
        guarded = AsyncMock(side_effect=[
            {"_wealth_continuation": {"cts": f"FULL-{index}", "flag": "Y"}}
            for index in range(20)
        ])
        with patch.object(self.client, "_call", new=guarded):
            with self.assertRaises(NhPlugOpenAPIError):
                asyncio.run(self.client._call_pages("/synthetic", {}))
        self.assertEqual(guarded.await_count, 20)

    def test_business_continuation_codes_and_refresh_preserve_later_page_cts(self):
        self.client.base_url = "https://api.nhplug.com:8443"
        self.client.app_key = "synthetic-key"
        self.client.app_secret = "synthetic-secret"
        first = _FakeAsyncClient([
            _FakeResponse(
                {"rsp_cd": "00165", "rsp_msg": "continuation", "Output_1": [{"page": 1}]},
                headers={"cts": "FULL-NEXT", "cts_flag": "Y"},
            )
        ])
        second = _FakeAsyncClient([
            _FakeResponse({"rsp_cd": "IGW40043", "rsp_msg": "token expired"}, status_code=401),
            _FakeResponse(
                {"rsp_cd": "00218", "rsp_msg": "continuation complete", "Output_1": [{"page": 2}]},
                headers={"cts": "FINAL-ECHO", "cts_flag": "N"},
            ),
        ])
        with (
            patch("app.services.nhplug_openapi.require_external_network"),
            patch("app.services.nhplug_openapi.httpx.AsyncClient", side_effect=[first, second]),
            patch.object(self.client, "_access_token", new=AsyncMock(side_effect=["token-1", "token-1", "token-2"])),
        ):
            pages = asyncio.run(self.client._call_pages("/synthetic", {"query": "value"}))
        self.assertEqual([page["Output_1"][0]["page"] for page in pages], [1, 2])
        self.assertNotIn("cts", first.requests[0][1]["headers"])
        self.assertEqual(second.requests[0][1]["headers"]["cts"], "FULL-NEXT")
        self.assertEqual(second.requests[1][1]["headers"]["cts"], "FULL-NEXT")

    def test_unrecognized_business_code_is_not_accepted_by_message_text(self):
        self.client.base_url = "https://api.nhplug.com:8443"
        self.client.app_key = "synthetic-key"
        self.client.app_secret = "synthetic-secret"
        fake = _FakeAsyncClient([_FakeResponse({"rsp_cd": "99999", "rsp_msg": "처리 완료"})])
        with (
            patch("app.services.nhplug_openapi.require_external_network"),
            patch("app.services.nhplug_openapi.httpx.AsyncClient", return_value=fake),
            patch.object(self.client, "_access_token", new=AsyncMock(return_value="token")),
        ):
            with self.assertRaises(NhPlugOpenAPIError):
                asyncio.run(self.client._call("/synthetic", {}))


if __name__ == "__main__":
    unittest.main()
