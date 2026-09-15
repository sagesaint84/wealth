from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.services.broker_holdings_sync import (
    BrokerHoldingsResult,
    DOMESTIC_MARKET,
    HoldingsResultState,
    ProviderHoldingScope,
    ResolvedHoldingScope,
    required_finite_number,
    replace_holdings_in_scopes,
)
from app.services.kb_openapi import KBOpenAPI, KBOpenAPIError
from app.services.kis_openapi import KISOpenAPI, KISOpenAPIError
from app.services.kiwoom_openapi import KiwoomOpenAPI, KiwoomOpenAPIError
from app.services.nhplug_openapi import NhPlugOpenAPI, NhPlugOpenAPIError
from app.services.toss_openapi import TossOpenAPI, TossOpenAPIError
from regression_support import authenticated_request, empty_portfolio, import_main_without_loading_real_env


class FakeResponse:
    def __init__(self, body, *, headers=None):
        self._body = body
        self.headers = headers or {}
        self.status_code = 200
        self.is_error = False

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, *, gets=None, posts=None):
        self.gets = list(gets or [])
        self.posts = list(posts or [])

    async def get(self, *_args, **_kwargs):
        return self.gets.pop(0)

    async def post(self, *_args, **_kwargs):
        return self.posts.pop(0)


def holding(identifier, source, account_id, code, market, currency="KRW", quantity=1):
    return {
        "id": identifier,
        "source": source,
        "account_id": account_id,
        "code": code,
        "name": code,
        "quantity": quantity,
        "avg_price": 1,
        "current_price": 1,
        "currency": currency,
        "market": market,
    }


class ScopedReplacementMatrixTests(unittest.TestCase):
    SOURCES = ("kb_api", "toss_api", "nhplug_api", "kis_api", "kiwoom_api")

    def portfolio(self, source):
        overseas_without_currency = holding("overseas-no-currency", source, "a1", "US2", "US", "USD")
        overseas_without_currency.pop("currency")
        return empty_portfolio(holdings=[
            holding("target", source, "a1", "000001", "KRX"),
            holding("other-account", source, "a2", "000002", "KRX"),
            holding("overseas", source, "a1", "US1", "US", "USD"),
            overseas_without_currency,
            holding("manual", "manual", "a1", "000003", "KRX"),
            holding("other-provider", "other_api", "a1", "000004", "KRX"),
        ])

    def test_authoritative_empty_clears_only_exact_account_market_for_every_broker(self):
        for source in self.SOURCES:
            with self.subTest(source=source):
                data = self.portfolio(source)
                replace_holdings_in_scopes(
                    data, [], source=source,
                    scopes=(ResolvedHoldingScope("a1", DOMESTIC_MARKET),),
                )
                self.assertEqual(
                    {row["id"] for row in data["holdings"]},
                    {"other-account", "overseas", "overseas-no-currency", "manual", "other-provider"},
                )

    def test_nonempty_replacement_is_scoped_and_repeated_sync_is_idempotent(self):
        for source in self.SOURCES:
            with self.subTest(source=source):
                data = self.portfolio(source)
                new_row = holding("new-random-id", source, "a1", "000001", "KRX", quantity=7)
                scope = (ResolvedHoldingScope("a1", DOMESTIC_MARKET),)
                replace_holdings_in_scopes(data, [deepcopy(new_row)], source=source, scopes=scope)
                first = deepcopy(data["holdings"])
                replace_holdings_in_scopes(data, [deepcopy(new_row)], source=source, scopes=scope)
                self.assertEqual(data["holdings"], first)
                target = next(row for row in data["holdings"] if row["source"] == source and row["account_id"] == "a1" and row["market"] == "KRX")
                self.assertEqual((target["id"], target["quantity"]), ("target", 7))

    def test_out_of_scope_rows_cannot_authorize_mutation(self):
        data = self.portfolio("kis_api")
        before = deepcopy(data)
        with self.assertRaises(ValueError):
            replace_holdings_in_scopes(
                data,
                [holding("bad", "kis_api", "a2", "000009", "KRX")],
                source="kis_api",
                scopes=(ResolvedHoldingScope("a1", DOMESTIC_MARKET),),
            )
        self.assertEqual(data, before)

    def test_required_financial_quantity_rejects_blank_malformed_and_nonfinite_values(self):
        for value in (None, "", "not-a-number", "NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                required_finite_number({"quantity": value}, "quantity")


class StrictAdapterValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_toss_empty_accounts_is_scope_unverified_and_bad_rows_fail(self):
        client = TossOpenAPI.__new__(TossOpenAPI)
        client.last_accounts = []
        client._get = AsyncMock(return_value=[])
        result = await client.sync_holdings()
        self.assertEqual(result.state, HoldingsResultState.ACCOUNT_SCOPE_UNVERIFIED)
        self.assertFalse(result.authoritative)

        for account, items in (
            ({"accountNo": "synthetic"}, []),
            ({"accountSeq": 7, "accountNo": "synthetic"}, [{}]),
        ):
            with self.subTest(account=account, items=items):
                client._get = AsyncMock(side_effect=[[account], {"items": items}])
                with self.assertRaises(TossOpenAPIError):
                    await client.sync_holdings()

        client._get = AsyncMock(return_value={"items": [], "hasMore": True})
        with self.assertRaisesRegex(TossOpenAPIError, "연속조회"):
            await client.sync_holdings()

    async def test_kb_malformed_rows_fail_instead_of_becoming_empty(self):
        client = KBOpenAPI.__new__(KBOpenAPI)
        for domestic, overseas in (([{}], []), ([], [{}])):
            with self.subTest(domestic=domestic, overseas=overseas):
                client.call = AsyncMock(side_effect=[{"Record1": domestic}, {"Record2": overseas}])
                with self.assertRaises(KBOpenAPIError):
                    await client.sync_holdings()
        client.call = AsyncMock(side_effect=[{"Record1": [], "nxt_key": "NEXT"}, {"Record2": []}])
        with self.assertRaisesRegex(KBOpenAPIError, "연속조회"):
            await client.sync_holdings()

    async def test_kis_malformed_rows_fail_instead_of_becoming_empty(self):
        client = KISOpenAPI.__new__(KISOpenAPI)
        client.account_no = "1234567801"
        client.base_url = "https://openapi.koreainvestment.com:9443"
        client.app_key = "fixture"
        client.app_secret = "fixture"
        for row in ({}, {"pdno": "000001"}, {"hldg_qty": "1"}):
            with self.subTest(row=row), self.assertRaises(KISOpenAPIError):
                await client.fetch_domestic_balance(
                    FakeClient(gets=[FakeResponse({"rt_cd": "0", "output1": [row], "output2": [{"dnca_tot_amt": "0"}]})]),
                    "fixture-token",
                )

    async def test_kiwoom_malformed_rows_fail_instead_of_becoming_empty(self):
        client = KiwoomOpenAPI.__new__(KiwoomOpenAPI)
        client.base_url = "https://api.kiwoom.com"
        for row in ({}, {"stk_cd": "A000001"}, {"rmnd_qty": "1"}):
            with self.subTest(row=row), self.assertRaises(KiwoomOpenAPIError):
                await client.fetch_domestic_balance(
                    FakeClient(posts=[
                        FakeResponse({"return_code": 0, "acnt_evlt_remn_indv_tot": [row]}),
                        FakeResponse({"return_code": 0, "entr": "0"}),
                    ]),
                    "fixture-token",
                )

    async def test_nh_missing_null_and_malformed_output_are_not_empty(self):
        client = NhPlugOpenAPI.__new__(NhPlugOpenAPI)
        client.last_accounts = []
        client.account_cash = {}
        client.base_url = "https://api.nhplug.com:8443"
        client._accounts = AsyncMock(return_value=[{"acct_no": "synthetic", "acct_type": "01"}])

        for output in (None, "missing", [{}]):
            async def call(path, _input, **_kwargs):
                if path.startswith("/krstock"):
                    body = {"Output_0": {"dca": "0"}, "_wealth_continuation": {"cts": "", "flag": "N"}}
                    if output != "missing":
                        body["Output_1"] = output
                    return body
                return {"Output_0": {}, "Output_1": [], "_wealth_continuation": {"cts": "", "flag": "N"}}
            client._call = call
            with self.subTest(output=output), self.assertRaises(NhPlugOpenAPIError):
                await client.sync_holdings()

    async def test_nh_repeated_continuation_is_partial_scope_failure(self):
        client = NhPlugOpenAPI.__new__(NhPlugOpenAPI)
        client._call = AsyncMock(side_effect=[
            {"Output_1": [], "_wealth_continuation": {"cts": "NEXT", "flag": "Y"}},
            {"Output_1": [], "_wealth_continuation": {"cts": "NEXT", "flag": "Y"}},
        ])
        with self.assertRaisesRegex(NhPlugOpenAPIError, "반복"):
            await client._call_pages(
                "/fixture", {"act_no": "synthetic"}, require_complete_scope=True,
            )


class RouteFailClosedTests(unittest.IsolatedAsyncioTestCase):
    async def test_ambiguous_existing_account_scope_preserves_every_broker(self):
        main = import_main_without_loading_real_env()
        cases = (
            {
                "class_name": "KBOpenAPI", "endpoint": main.sync_kb, "broker": "KB증권", "source": "kb_api",
                "scope_key": "kb_primary", "account_key": "kb_primary", "attrs": {},
            },
            {
                "class_name": "TossOpenAPI", "endpoint": main.sync_toss, "broker": "토스증권", "source": "toss_api",
                "scope_key": "7", "account_key": "", "account_no": "0007",
                "attrs": {"last_accounts": [{"accountSeq": 7, "accountNo": "0000000007"}]},
            },
            {
                "class_name": "NhPlugOpenAPI", "endpoint": main.sync_namoo, "broker": "NH투자증권(나무)", "source": "nhplug_api",
                "scope_key": "00000000001", "account_key": "0001",
                "attrs": {"last_accounts": [{"acct_no": "00000000001", "acct_type": "01"}], "account_cash": {}, "_account_name": lambda _self, _account: "NH"},
            },
            {
                "class_name": "KISOpenAPI", "endpoint": main.sync_kis, "broker": "한국투자증권", "source": "kis_api",
                "scope_key": "1234567801", "account_key": "7801",
                "attrs": {"last_accounts": [{"account_number": "1234567801", "account_name": "KIS"}], "account_cash": {}, "_parse_account_no": lambda _self: ("12345678", "01")},
            },
            {
                "class_name": "KiwoomOpenAPI", "endpoint": main.sync_kiwoom, "broker": "키움증권", "source": "kiwoom_api",
                "scope_key": "1234567890", "account_key": "7890",
                "attrs": {"last_accounts": [{"account_number": "1234567890", "account_name": "Kiwoom"}], "account_cash": {}},
            },
        )
        for case in cases:
            with self.subTest(broker=case["broker"]):
                accounts = [
                    {"id": "a1", "broker": case["broker"], "name": "First", "source": case["source"], "account_key": case["account_key"], "account_no": case.get("account_no", "")},
                    {"id": "a2", "broker": case["broker"], "name": "Second", "source": case["source"], "account_key": case["account_key"], "account_no": case.get("account_no", "")},
                ]
                data = empty_portfolio(accounts=accounts, holdings=[
                    holding("first", case["source"], "a1", "000001", "KRX"),
                    holding("second", case["source"], "a2", "000002", "KRX"),
                ])
                result = BrokerHoldingsResult.authoritative_result(
                    [], (ProviderHoldingScope(case["scope_key"], DOMESTIC_MARKET),), cash_valid=True,
                )
                fake = type("AmbiguousScope", (), {"configured": True, **case["attrs"]})()
                fake.sync_holdings = AsyncMock(return_value=result)
                with patch.object(main, case["class_name"], return_value=fake), \
                     patch.object(main, "read_portfolio", return_value=deepcopy(data)), \
                     patch.object(main, "write_portfolio") as write_portfolio:
                    response = await case["endpoint"](authenticated_request("ambiguous-scope-fixture"))
                self.assertEqual(response["status"], "SCOPE_UNVERIFIED")
                self.assertTrue(response["data_preserved"])
                write_portfolio.assert_not_called()

    async def test_authoritative_empty_routes_replace_only_verified_account_market(self):
        main = import_main_without_loading_real_env()
        cases = (
            {
                "class_name": "KBOpenAPI", "endpoint": main.sync_kb, "broker": "KB증권", "source": "kb_api",
                "account": {"id": "a1", "broker": "KB증권", "name": "KB", "source": "kb_api", "account_key": "kb_primary"},
                "scope_key": "kb_primary", "attrs": {},
            },
            {
                "class_name": "TossOpenAPI", "endpoint": main.sync_toss, "broker": "토스증권", "source": "toss_api",
                "account": {"id": "a1", "broker": "토스증권", "name": "Toss", "source": "toss_api", "account_key": "7", "account_no": "0007"},
                "scope_key": "7", "attrs": {"last_accounts": [{"accountSeq": 7, "accountNo": "0000000007"}]},
            },
            {
                "class_name": "NhPlugOpenAPI", "endpoint": main.sync_namoo, "broker": "NH투자증권(나무)", "source": "nhplug_api",
                "account": {"id": "a1", "broker": "NH투자증권(나무)", "name": "NH", "source": "nhplug_api", "account_key": "0001", "account_no": "00000000001"},
                "scope_key": "00000000001", "attrs": {"last_accounts": [{"acct_no": "00000000001", "acct_type": "01"}], "account_cash": {"00000000001": {"KRW": 0}}, "_account_name": lambda _self, _account: "NH"},
            },
            {
                "class_name": "KISOpenAPI", "endpoint": main.sync_kis, "broker": "한국투자증권", "source": "kis_api",
                "account": {"id": "a1", "broker": "한국투자증권", "name": "KIS", "source": "kis_api", "account_key": "7801", "account_no": "1234567801"},
                "scope_key": "1234567801", "attrs": {"last_accounts": [{"account_number": "1234567801", "account_name": "KIS"}], "account_cash": {"1234567801": {"KRW": 0}}, "_parse_account_no": lambda _self: ("12345678", "01")},
            },
            {
                "class_name": "KiwoomOpenAPI", "endpoint": main.sync_kiwoom, "broker": "키움증권", "source": "kiwoom_api",
                "account": {"id": "a1", "broker": "키움증권", "name": "Kiwoom", "source": "kiwoom_api", "account_key": "7890", "account_no": "1234567890"},
                "scope_key": "1234567890", "attrs": {"last_accounts": [{"account_number": "1234567890", "account_name": "Kiwoom"}], "account_cash": {"1234567890": {"KRW": 0}}},
            },
        )
        for case in cases:
            with self.subTest(broker=case["broker"]):
                other_account = {"id": "a2", "broker": case["broker"], "name": "Other", "source": case["source"], "account_key": "other"}
                data = empty_portfolio(
                    accounts=[deepcopy(case["account"]), other_account],
                    holdings=[
                        holding("target", case["source"], "a1", "000001", "KRX"),
                        holding("same-account-overseas", case["source"], "a1", "US1", "US", "USD"),
                        holding("other-account", case["source"], "a2", "000002", "KRX"),
                        holding("manual", "manual", "a1", "000003", "KRX"),
                    ],
                )
                result = BrokerHoldingsResult.authoritative_result(
                    [],
                    (ProviderHoldingScope(case["scope_key"], DOMESTIC_MARKET),),
                    cash_valid=case["source"] != "kb_api",
                )
                fake = type("AuthoritativeEmpty", (), {"configured": True, **case["attrs"]})()
                fake.sync_holdings = AsyncMock(return_value=result)
                if case["source"] == "kb_api":
                    fake.refresh_prices = AsyncMock(return_value=({}, []))
                if case["source"] == "toss_api":
                    fake.get_buying_power = AsyncMock(return_value={"KRW": 0, "USD": 0})
                written = {}
                with patch.object(main, case["class_name"], return_value=fake), \
                     patch.object(main, "read_portfolio", return_value=deepcopy(data)), \
                     patch.object(main, "write_portfolio", side_effect=lambda value, **_: written.update(value)):
                    response = await case["endpoint"](authenticated_request("authoritative-empty-fixture"))
                self.assertEqual(response["status"], "CONFIRMED_EMPTY")
                self.assertEqual(
                    {row["id"] for row in written["holdings"]},
                    {"same-account-overseas", "other-account", "manual"},
                )

    async def test_unverified_results_preserve_data_for_all_broker_routes(self):
        main = import_main_without_loading_real_env()
        cases = (
            ("KBOpenAPI", main.sync_kb, "KB증권", {}),
            ("TossOpenAPI", main.sync_toss, "토스증권", {"last_accounts": []}),
            ("NhPlugOpenAPI", main.sync_namoo, "NH투자증권(나무)", {"last_accounts": [], "account_cash": {}}),
            ("KISOpenAPI", main.sync_kis, "한국투자증권", {"last_accounts": [], "account_cash": {}, "_parse_account_no": lambda _self: ("12345678", "01")}),
            ("KiwoomOpenAPI", main.sync_kiwoom, "키움증권", {"last_accounts": [], "account_cash": {}}),
        )
        for class_name, endpoint, broker, attrs in cases:
            with self.subTest(broker=broker):
                fake = type("Unverified", (), {"configured": True, **attrs})()
                for state in (
                    HoldingsResultState.ACCOUNT_SCOPE_UNVERIFIED,
                    HoldingsResultState.PAYLOAD_MISSING,
                    HoldingsResultState.STATUS_ONLY,
                    HoldingsResultState.MALFORMED,
                    HoldingsResultState.MARKET_SCOPE_PARTIAL,
                    HoldingsResultState.UNKNOWN_EMPTY,
                ):
                    with self.subTest(broker=broker, state=state):
                        fake.sync_holdings = AsyncMock(return_value=BrokerHoldingsResult(
                            state=state,
                            cash_valid=True,
                        ))
                        with patch.object(main, class_name, return_value=fake), \
                             patch.object(main, "read_portfolio") as read_portfolio, \
                             patch.object(main, "write_portfolio") as write_portfolio:
                            result = await endpoint(authenticated_request("scope-fixture"))
                        self.assertEqual(result["status"], "SCOPE_UNVERIFIED")
                        self.assertTrue(result["data_preserved"])
                        self.assertTrue(result["cash_valid"])
                        self.assertFalse(result["cash_updated"])
                        read_portfolio.assert_not_called()
                        write_portfolio.assert_not_called()

    async def test_malformed_provider_error_does_not_touch_cash_or_holdings(self):
        main = import_main_without_loading_real_env()
        data = empty_portfolio(
            holdings=[holding("old", "nhplug_api", "nh", "000001", "KRX")],
            settings={"cash_balances": {"nh": {"KRW": 5000}}},
        )

        class MalformedNH:
            configured = True
            async def sync_holdings(self):
                raise NhPlugOpenAPIError("나무증권 보유종목 항목 형식이 올바르지 않습니다.")

        with patch.object(main, "NhPlugOpenAPI", return_value=MalformedNH()), \
             patch.object(main, "read_portfolio", return_value=deepcopy(data)) as read_portfolio, \
             patch.object(main, "write_portfolio") as write_portfolio:
            with self.assertRaises(HTTPException):
                await main.sync_namoo(authenticated_request("malformed-fixture"))
        read_portfolio.assert_not_called()
        write_portfolio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
