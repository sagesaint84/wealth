from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.services.kb_openapi import KBOpenAPI, KBOpenAPIError
from app.services.kis_openapi import KISOpenAPI, KISOpenAPIError
from app.services.kiwoom_openapi import KiwoomOpenAPI, KiwoomOpenAPIError
from app.services.nhplug_openapi import NhPlugOpenAPI, NhPlugOpenAPIError
from app.services.toss_openapi import TossOpenAPI, TossOpenAPIError
from app.services.broker_holdings_sync import (
    ALL_MARKETS,
    BrokerHoldingsResult,
    DOMESTIC_MARKET,
    HoldingsResultState,
    OVERSEAS_MARKET,
    ProviderHoldingScope,
)
from regression_support import authenticated_request, empty_portfolio, import_main_without_loading_real_env


class FakeResponse:
    def __init__(self, body, *, status=200, headers=None):
        self._body = body
        self.status_code = status
        self.headers = headers or {}
        self.is_error = status >= 400

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeClient:
    def __init__(self, *, gets=None, posts=None):
        self.gets = list(gets or [])
        self.posts = list(posts or [])
        self.requests = []

    async def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        return self.gets.pop(0)

    async def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.posts.pop(0)


def holding(identifier, source, account_id, code, market, currency="KRW", quantity=1):
    return {
        "id": identifier,
        "source": source,
        "accountId": account_id,
        "account_id": account_id,
        "code": code,
        "name": code,
        "quantity": quantity,
        "avg_price": 1,
        "current_price": 1,
        "currency": currency,
        "market": market,
    }



class AdapterContractTests(unittest.IsolatedAsyncioTestCase):
    def test_kb_header_only_response_is_envelope_error(self):
        with self.assertRaisesRegex(KBOpenAPIError, "잔고 데이터 없이"):
            KBOpenAPI._normalize_response({"dataHeader": {"resultCode": "x"}}, require_data_body=True)

    def test_kb_data_body_response_remains_supported(self):
        body = KBOpenAPI._normalize_response({"dataHeader": {}, "dataBody": {"Record1": []}}, require_data_body=True)
        self.assertEqual(body["Record1"], [])

    async def test_kb_true_zero_requires_both_documented_lists(self):
        client = KBOpenAPI.__new__(KBOpenAPI)
        client.call = AsyncMock(side_effect=[{"Record1": []}, {"Record2": []}])
        self.assertEqual(await client.sync_holdings(), [])

    async def test_kb_unexpected_schema_is_not_zero(self):
        client = KBOpenAPI.__new__(KBOpenAPI)
        client.call = AsyncMock(side_effect=[{}, {"Record2": []}])
        with self.assertRaises(KBOpenAPIError):
            await client.sync_holdings()

    async def test_toss_success_and_zero_cash_are_valid(self):
        client = TossOpenAPI.__new__(TossOpenAPI)
        client.last_accounts = []
        client._get = AsyncMock(side_effect=[
            [{"accountSeq": 7, "accountNo": "0000000007"}],
            {"items": [{"symbol": "QQQM", "name": "Synthetic", "quantity": "3", "currency": "USD", "marketCountry": "US"}]},
            {"cashBuyingPower": "0"}, {"cashBuyingPower": "12.5"},
        ])
        records = await client.sync_holdings()
        cash = await client.get_buying_power(7)
        self.assertEqual((records[0]["code"], records[0]["account_key"]), ("QQQM", "7"))
        self.assertEqual(cash, {"KRW": 0.0, "USD": 12.5})

    async def test_toss_cash_missing_field_is_failure_not_zero(self):
        client = TossOpenAPI.__new__(TossOpenAPI)
        client._get = AsyncMock(return_value={"unexpected": 0})
        with self.assertRaises(TossOpenAPIError):
            await client.get_buying_power(1)

    async def test_namoo_logger_path_raises_original_adapter_error(self):
        client = NhPlugOpenAPI.__new__(NhPlugOpenAPI)
        client.last_accounts = []
        client.account_cash = {}
        client._accounts = AsyncMock(return_value=[{"acct_no": "00000000001", "acct_type": "01"}])

        async def call(path, _, **kwargs):
            if path.startswith("/krstock"):
                return {"Output_0": {"dca": "0"}, "Output_1": []}
            raise NhPlugOpenAPIError("synthetic overseas failure")

        client._call = call
        with self.assertRaisesRegex(NhPlugOpenAPIError, "synthetic"):
            await client.sync_holdings()

    async def test_namoo_normal_zero_with_official_envelope(self):
        client = NhPlugOpenAPI.__new__(NhPlugOpenAPI)
        client.last_accounts = []
        client.account_cash = {}
        client._accounts = AsyncMock(return_value=[{"acct_no": "00000000001", "acct_type": "01"}])
        client._call = AsyncMock(return_value={"Output_0": {"dca": "0"}, "Output_1": []})
        self.assertEqual(await client.sync_holdings(), [])
        self.assertEqual(client.account_cash["00000000001"]["KRW"], 0.0)

    async def test_namoo_continuation_passes_cts_to_next_request(self):
        client = NhPlugOpenAPI.__new__(NhPlugOpenAPI)
        client._call = AsyncMock(side_effect=[
            {"Output_1": [], "_wealth_continuation": {"cts": "NEXT", "flag": "Y"}},
            {"Output_1": [], "_wealth_continuation": {"cts": "", "flag": "N"}},
        ])
        pages = await client._call_pages("/fixture", {"act_no": "synthetic"})
        self.assertEqual(len(pages), 2)
        self.assertEqual(client._call.await_args_list[1].kwargs["cts"], "NEXT")

    def test_kis_account_format(self):
        client = KISOpenAPI.__new__(KISOpenAPI)
        for raw, expected in (("1234567801", ("12345678", "01")), ("12345678", ("12345678", "01")), ("1234****", ("", ""))):
            client.account_no = raw
            self.assertEqual(client._parse_account_no(), expected)

    async def test_kis_official_zero_and_pagination(self):
        client = KISOpenAPI.__new__(KISOpenAPI)
        client.account_no = "1234567801"
        client.base_url = "https://openapi.koreainvestment.com:9443"
        client.app_key = "fixture-key"; client.app_secret = "fixture-secret"
        fake = FakeClient(gets=[
            FakeResponse({"rt_cd": "0", "output1": [], "output2": [{"dnca_tot_amt": "10"}], "ctx_area_fk100": "A", "ctx_area_nk100": "B"}, headers={"tr_cont": "M"}),
            FakeResponse({"rt_cd": "0", "output1": [], "output2": []}),
        ])
        holdings, cash = await client.fetch_domestic_balance(fake, "fixture-token")
        self.assertEqual((holdings, cash), ([], 10.0))
        self.assertEqual(fake.requests[1][2]["headers"]["tr_cont"], "N")

    async def test_kis_api_and_schema_errors_are_not_zero(self):
        client = KISOpenAPI.__new__(KISOpenAPI)
        client.account_no = "1234567801"; client.base_url = "https://openapi.koreainvestment.com:9443"
        client.app_key = "fixture"; client.app_secret = "fixture"
        for body in ({"rt_cd": "1", "msg1": "synthetic error", "output1": [], "output2": []}, {"rt_cd": "0", "output2": []}):
            with self.subTest(body=body), self.assertRaises(KISOpenAPIError):
                await client.fetch_domestic_balance(FakeClient(gets=[FakeResponse(body)]), "fixture-token")

    async def test_kiwoom_official_account_holdings_cash_and_zero(self):
        client = KiwoomOpenAPI.__new__(KiwoomOpenAPI)
        client.base_url = "https://api.kiwoom.com"
        fake = FakeClient(posts=[
            FakeResponse({"acctNo": "1234567890", "return_code": 0}),
            FakeResponse({"acnt_evlt_remn_indv_tot": [{"stk_cd": "A005930", "stk_nm": "Synthetic", "rmnd_qty": "3", "pur_pric": "100", "cur_prc": "+120"}], "return_code": 0}),
            FakeResponse({"entr": "0", "return_code": 0}),
        ])
        account = await client.fetch_account_number(fake, "fixture-token")
        holdings, cash = await client.fetch_domestic_balance(fake, "fixture-token")
        self.assertEqual(account, "1234567890")
        self.assertEqual((holdings[0]["symbol"], holdings[0]["quantity"], cash), ("005930", 3.0, 0.0))
        self.assertNotIn("acnt_no", fake.requests[1][2]["json"])

    async def test_kiwoom_error_or_malformed_schema_is_not_zero(self):
        client = KiwoomOpenAPI.__new__(KiwoomOpenAPI); client.base_url = "https://api.kiwoom.com"
        for body in ({"return_code": 1, "return_msg": "synthetic"}, {"return_code": 0}):
            with self.subTest(body=body), self.assertRaises(KiwoomOpenAPIError):
                await client.fetch_domestic_balance(FakeClient(posts=[FakeResponse(body)]), "fixture-token")

    async def test_kiwoom_continuation_uses_official_headers(self):
        client = KiwoomOpenAPI.__new__(KiwoomOpenAPI); client.base_url = "https://api.kiwoom.com"
        fake = FakeClient(posts=[
            FakeResponse({"acnt_evlt_remn_indv_tot": [], "return_code": 0}, headers={"cont-yn": "Y", "next-key": "NEXT"}),
            FakeResponse({"acnt_evlt_remn_indv_tot": [], "return_code": 0}),
            FakeResponse({"entr": "0", "return_code": 0}),
        ])
        self.assertEqual(await client.fetch_domestic_balance(fake, "fixture-token"), ([], 0.0))
        self.assertEqual(fake.requests[1][2]["headers"]["next-key"], "NEXT")


class EndpointDataProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_kb_failure_does_not_read_or_write_portfolio(self):
        main = import_main_without_loading_real_env()

        class FailedKB:
            configured = True
            async def sync_holdings(self):
                raise KBOpenAPIError("synthetic failure")

        with patch.object(main, "KBOpenAPI", return_value=FailedKB()), \
             patch.object(main, "read_portfolio") as read_portfolio, \
             patch.object(main, "write_portfolio") as write_portfolio:
            with self.assertRaises(HTTPException):
                await main.sync_kb(authenticated_request())
            read_portfolio.assert_not_called(); write_portfolio.assert_not_called()

    async def test_kis_missing_account_is_config_required_without_data_access(self):
        main = import_main_without_loading_real_env()

        class MissingAccountKIS:
            configured = True
            def _parse_account_no(self): return "", ""

        with patch.object(main, "KISOpenAPI", return_value=MissingAccountKIS()), \
             patch.object(main, "read_portfolio") as read_portfolio, \
             patch.object(main, "write_portfolio") as write_portfolio:
            result = await main.sync_kis(authenticated_request())
        self.assertEqual(result["status"], "CONFIG_REQUIRED")
        read_portfolio.assert_not_called(); write_portfolio.assert_not_called()

    async def test_kb_valid_zero_replaces_only_kb_source_and_marks_success(self):
        main = import_main_without_loading_real_env()
        data = empty_portfolio(
            accounts=[{"id": "kb", "broker": "KB증권", "name": "KB", "source": "kb_api", "account_key": "kb_primary"}],
            holdings=[
                {"id": "old-kb", "source": "kb_api", "account_id": "kb", "code": "000001"},
                {"id": "other", "source": "manual", "account_id": "other", "code": "QQQM"},
            ],
        )

        class ZeroKB:
            configured = True
            async def sync_holdings(self):
                return BrokerHoldingsResult.authoritative_result(
                    [],
                    (
                        ProviderHoldingScope("kb_primary", DOMESTIC_MARKET),
                        ProviderHoldingScope("kb_primary", OVERSEAS_MARKET),
                    ),
                    cash_valid=False,
                )
            async def refresh_prices(self, holdings): return {}, []

        written = {}
        with patch.object(main, "KBOpenAPI", return_value=ZeroKB()), \
             patch.object(main, "read_portfolio", return_value=deepcopy(data)), \
             patch.object(main, "write_portfolio", side_effect=lambda value, **_: written.update(value)):
            result = await main.sync_kb(authenticated_request())
        self.assertEqual(result["status"], "CONFIRMED_EMPTY")
        self.assertEqual([h["id"] for h in written["holdings"]], ["other"])
        self.assertIn("kb", written["settings"]["sync_last_success"])

    def test_error_masking_removes_credentials_and_full_account(self):
        main = import_main_without_loading_real_env()
        client = type("Client", (), {"app_key": "fixture-app-key", "app_secret": "fixture-secret", "account_no": "1234567890"})()
        masked = main._mask_sync_error(Exception("fixture-app-key fixture-secret 1234567890"), client)
        self.assertNotIn("fixture-app-key", masked)
        self.assertNotIn("fixture-secret", masked)
        self.assertNotIn("1234567890", masked)

    async def test_toss_holdings_success_cash_failure_preserves_cash(self):
        main = import_main_without_loading_real_env()
        data = empty_portfolio(
            accounts=[{"id": "toss-1", "broker": "토스증권", "name": "토스", "source": "toss_api", "account_key": "7", "account_no": "0007"}],
            holdings=[], settings={"cash_balances": {"toss-1": {"KRW": 5000.0, "USD": 20.0}}},
        )

        class PartialToss:
            configured = True
            last_accounts = [{"accountSeq": 7, "accountNo": "0000000007"}]
            async def sync_holdings(self):
                return BrokerHoldingsResult.authoritative_result(
                    [{"account_key": "7", "account_name": "토스", "code": "QQQM", "name": "Synthetic", "quantity": 1, "currency": "USD", "market": "TOSS_US"}],
                    (ProviderHoldingScope("7", ALL_MARKETS),),
                    cash_valid=False,
                )
            async def get_buying_power(self, _):
                raise TossOpenAPIError("synthetic cash failure")

        written = {}
        with patch.object(main, "TossOpenAPI", return_value=PartialToss()), \
             patch.object(main, "read_portfolio", return_value=deepcopy(data)), \
             patch.object(main, "write_portfolio", side_effect=lambda value, **_: written.update(value)):
            result = await main.sync_toss(authenticated_request())
        self.assertEqual(result["status"], "PARTIAL_SUCCESS")
        self.assertEqual(written["settings"]["cash_balances"]["toss-1"], {"KRW": 5000.0, "USD": 20.0})
        self.assertEqual(written["holdings"][0]["code"], "QQQM")

    async def test_sync_all_keeps_brokers_independent(self):
        main = import_main_without_loading_real_env()

        class Configured:
            configured = True
            app_key = "fixture"; app_secret = "fixture"; account_no = ""

        success = {"broker": "KB증권", "status": "SUCCESS", "message": "synthetic success", "count": 1, "holdings_valid": True, "cash_valid": False, "data_preserved": False}
        with patch.object(main, "is_test_mode", return_value=False), \
             patch.object(main, "KBOpenAPI", return_value=Configured()), \
             patch.object(main, "TossOpenAPI", return_value=Configured()), \
             patch.object(main, "NhPlugOpenAPI", return_value=Configured()), \
             patch.object(main, "KISOpenAPI", return_value=Configured()), \
             patch.object(main, "KiwoomOpenAPI", return_value=Configured()), \
             patch.object(main, "sync_kb", AsyncMock(return_value=success)), \
             patch.object(main, "sync_toss", AsyncMock(side_effect=HTTPException(400, "synthetic failure"))), \
             patch.object(main, "sync_namoo", AsyncMock(return_value={**success, "broker": "NH투자증권(나무)"})), \
             patch.object(main, "sync_kis", AsyncMock(side_effect=HTTPException(400, "synthetic failure"))), \
             patch.object(main, "sync_kiwoom", AsyncMock(return_value={**success, "broker": "키움증권"})):
            result = await main.sync_all_accounts(authenticated_request("parallel-fixture"))
        self.assertEqual(result["synced"], 3)
        self.assertEqual([item["status"] for item in result["brokers"]], ["SUCCESS", "API_ERROR", "SUCCESS", "API_ERROR", "SUCCESS"])
        self.assertTrue(all(item.get("data_preserved") for item in result["brokers"] if item["status"] == "API_ERROR"))

    async def test_duplicate_sync_request_is_rejected(self):
        main = import_main_without_loading_real_env()
        username = "duplicate-fixture"
        main._syncing_users.add(username)
        try:
            with patch.object(main, "is_test_mode", return_value=False), self.assertRaisesRegex(HTTPException, "409"):
                await main.sync_all_accounts(authenticated_request(username))
        finally:
            main._syncing_users.discard(username)


class KBEmptyBalanceRegressionTests(unittest.IsolatedAsyncioTestCase):
    def make_8092_payload(self, *, flag="A", code="8092", message="해당 계좌의 잔고 내역이 존재하지 않습니다."):
        return {
            "dataHeader": {
                "resultCode": "200",
                "processCode": code,
                "processFlag": flag,
                "processMessage": message,
            }
        }

    def make_domestic_payload(self, records=()):
        return {
            "dataHeader": {"resultCode": "200", "processCode": "0011", "processFlag": "A"},
            "dataBody": {"Record1": list(records), "nxt_key": ""},
        }

    def make_overseas_payload(self, records=()):
        return {
            "dataHeader": {"resultCode": "200", "processCode": "0011", "processFlag": "A"},
            "dataBody": {"Record2": list(records), "nxt_key": ""},
        }

    def make_domestic_row(self, code="005930", qty="10"):
        return {"is_no": f"A{code}", "is_nm": "삼성전자", "gnrl_q": qty, "sll_q": "0"}

    def make_overseas_row(self, code="AAPL", qty="5"):
        return {
            "is_cd": code, "is_nm": "Apple", "frgn_hld_q_p6": qty, "sll_q": "0",
            "crncy_clsf_nm": "USD", "mkt_clsf": "US",
            "byng_avr_prc_p4": "150.0", "now_prc_p4": "200.0",
        }

    def test_normalize_response_accepts_8092_when_allowed_for_domestic(self):
        payload = self.make_8092_payload()
        res = KBOpenAPI._normalize_response(payload, require_data_body=True, empty_record_key="Record1")
        self.assertEqual(res, {"Record1": [], "nxt_key": ""})

    def test_normalize_response_accepts_8092_when_allowed_for_overseas(self):
        payload = self.make_8092_payload()
        res = KBOpenAPI._normalize_response(payload, require_data_body=True, empty_record_key="Record2")
        self.assertEqual(res, {"Record2": [], "nxt_key": ""})

    def test_normalize_response_rejects_8092_when_empty_not_allowed(self):
        payload = self.make_8092_payload()
        with self.assertRaises(KBOpenAPIError) as ctx:
            KBOpenAPI._normalize_response(payload, require_data_body=True, empty_record_key=None)
        self.assertIn("8092", str(ctx.exception))

    def test_normalize_response_rejects_8092_when_flag_not_a(self):
        payload = self.make_8092_payload(flag="B")
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._normalize_response(payload, require_data_body=True, empty_record_key="Record1")

    def test_normalize_response_rejects_8092_when_message_different(self):
        payload = self.make_8092_payload(message="전산 시스템 점검 중입니다.")
        with self.assertRaises(KBOpenAPIError):
            KBOpenAPI._normalize_response(payload, require_data_body=True, empty_record_key="Record1")

    def test_call_rejects_allow_empty_balance_on_unsupported_endpoint(self):
        client = KBOpenAPI.__new__(KBOpenAPI)
        with self.assertRaises(KBOpenAPIError):
            import asyncio
            asyncio.run(client.call("/api/v1/szqm0771", {}, allow_empty_balance=True))

    async def _run_sync_holdings_with_responses(self, domestic_payload, overseas_payload):
        client = KBOpenAPI.__new__(KBOpenAPI)
        client.base_url = "https://mock.kbsec.com"
        client.app_key = "test_key"
        client._payload = lambda b: b
        client._access_token = AsyncMock(return_value="mock_token")

        async def fake_post(url, **_kwargs):
            if "/api/v1/ssqm1801" in url:
                return FakeResponse(domestic_payload)
            if "/api/v1/spqm2226" in url:
                return FakeResponse(overseas_payload)
            raise ValueError(f"unexpected url {url}")

        with patch("app.services.kb_openapi.require_external_network"), \
             patch("httpx.AsyncClient.post", side_effect=fake_post):
            return await client.sync_holdings()

    async def test_1_domestic_8092_empty_and_overseas_normal_empty(self):
        result = await self._run_sync_holdings_with_responses(
            self.make_8092_payload(),
            self.make_overseas_payload([]),
        )
        self.assertEqual(result.state, HoldingsResultState.AUTHORITATIVE_EMPTY)
        self.assertTrue(result.authoritative)
        self.assertEqual(len(result), 0)

    async def test_2_overseas_8092_empty_and_domestic_normal_empty(self):
        result = await self._run_sync_holdings_with_responses(
            self.make_domestic_payload([]),
            self.make_8092_payload(),
        )
        self.assertEqual(result.state, HoldingsResultState.AUTHORITATIVE_EMPTY)
        self.assertTrue(result.authoritative)
        self.assertEqual(len(result), 0)

    async def test_3_domestic_8092_and_overseas_nonempty(self):
        result = await self._run_sync_holdings_with_responses(
            self.make_8092_payload(),
            self.make_overseas_payload([self.make_overseas_row("AAPL")]),
        )
        self.assertEqual(result.state, HoldingsResultState.CONFIRMED_NONEMPTY)
        self.assertTrue(result.authoritative)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["code"], "AAPL")
        self.assertEqual(result[0]["market"], "US")

    async def test_4_overseas_8092_and_domestic_nonempty(self):
        result = await self._run_sync_holdings_with_responses(
            self.make_domestic_payload([self.make_domestic_row("005930")]),
            self.make_8092_payload(),
        )
        self.assertEqual(result.state, HoldingsResultState.CONFIRMED_NONEMPTY)
        self.assertTrue(result.authoritative)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["code"], "005930")
        self.assertEqual(result[0]["market"], "KRX")

    async def test_5_both_domestic_and_overseas_8092(self):
        result = await self._run_sync_holdings_with_responses(
            self.make_8092_payload(),
            self.make_8092_payload(),
        )
        self.assertEqual(result.state, HoldingsResultState.AUTHORITATIVE_EMPTY)
        self.assertTrue(result.authoritative)
        self.assertEqual(len(result), 0)

    async def test_6_process_flag_not_a_raises_error(self):
        with self.assertRaises(KBOpenAPIError):
            await self._run_sync_holdings_with_responses(
                self.make_8092_payload(flag="B"),
                self.make_overseas_payload([]),
            )

    async def test_7_different_process_message_raises_error(self):
        with self.assertRaises(KBOpenAPIError):
            await self._run_sync_holdings_with_responses(
                self.make_8092_payload(message="서버 내부 오류가 발생했습니다."),
                self.make_overseas_payload([]),
            )

    async def test_8_general_tr_8092_fails_closed(self):
        client = KBOpenAPI.__new__(KBOpenAPI)
        client.base_url = "https://mock.kbsec.com"
        client.app_key = "test_key"
        client._payload = lambda b: b
        client._access_token = AsyncMock(return_value="mock_token")

        async def fake_post(_url, **_kwargs):
            return FakeResponse(self.make_8092_payload())

        with patch("app.services.kb_openapi.require_external_network"), \
             patch("httpx.AsyncClient.post", side_effect=fake_post):
            with self.assertRaises(KBOpenAPIError):
                await client.call("/api/v1/szqm0771", {})

    async def test_route_sync_kb_with_both_8092_results_in_confirmed_empty(self):
        main = import_main_without_loading_real_env()
        data = empty_portfolio(
            accounts=[{"id": "a1", "broker": "KB증권", "name": "KB", "source": "kb_api", "account_key": "kb_primary"}],
            holdings=[holding("old_kb_stock", "kb_api", "a1", "005930", "KRX")],
        )
        client = KBOpenAPI.__new__(KBOpenAPI)
        client.base_url = "https://mock.kbsec.com"
        client.app_key = "test_key"
        client.app_secret = "test_secret"
        client._payload = lambda b: b
        client._access_token = AsyncMock(return_value="mock_token")
        client.refresh_prices = AsyncMock(return_value=({}, []))

        async def fake_post(_url, **_kwargs):
            return FakeResponse(self.make_8092_payload())

        written = {}
        with patch("app.services.kb_openapi.require_external_network"), \
             patch("httpx.AsyncClient.post", side_effect=fake_post), \
             patch.object(main, "KBOpenAPI", return_value=client), \
             patch.object(main, "read_portfolio", return_value=deepcopy(data)), \
             patch.object(main, "write_portfolio", side_effect=lambda val, **_: written.update(val)):
            res = await main.sync_kb(authenticated_request())

        self.assertEqual(res["status"], "CONFIRMED_EMPTY")
        self.assertEqual(res["count"], 0)
        self.assertEqual(len(written["holdings"]), 0)

if __name__ == "__main__":
    unittest.main()
