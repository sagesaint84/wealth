from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.kis_openapi import (
    KIS_IPO_PUB_OFFER_PATH,
    KIS_IPO_PUB_OFFER_TR_ID,
    KIS_LIST_INFO_PATH,
    KIS_LIST_INFO_TR_ID,
    KIS_STOCK_INFO_PATH,
    KIS_STOCK_INFO_TR_ID,
    KISOpenAPI,
    KISOpenAPIError,
    normalize_kis_ipo_subscription_row,
    normalize_kis_listing_schedule_row,
    normalize_kis_stock_info_response,
)


class FakeResponse:
    def __init__(self, body, *, status=200, headers=None):
        self._body = body
        self.status_code = status
        self.headers = headers or {}
        self.is_error = status >= 400
        self.text = "" if isinstance(body, dict) else str(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class IpoKisScheduleTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self):
        client = KISOpenAPI.__new__(KISOpenAPI)
        client.base_url = "https://openapi.koreainvestment.com:9443"
        client.app_key = "fixture-key"
        client.app_secret = "fixture-secret"
        client.account_no = ""
        return client

    def test_public_offer_live_contract_normalizes_general_and_spac(self):
        general = normalize_kis_ipo_subscription_row({
            "record_date": "2026/09/18",
            "sht_cd": "468670",
            "isin_name": "브릴스",
            "fix_subscr_pri": "        19500",
            "subscr_dt": "2026/09/17 ~ 2026/09/18",
            "pay_dt": "2026/09/22",
            "refund_dt": "2026/09/22",
            "list_dt": "",
            "lead_mgr": "아이비케이투자증권",
            "pub_bf_cap": "1,000",
            "pub_af_cap": "2,000",
            "assign_stk_qty": "3000",
        })
        self.assertEqual(general["company_name"], "브릴스")
        self.assertEqual(general["stock_code"], "468670")
        self.assertEqual(general["listing_track"], "general")
        self.assertEqual(general["subscription_start"], "2026-09-17")
        self.assertEqual(general["subscription_end"], "2026-09-18")
        self.assertEqual(general["payment_date"], "2026-09-22")
        self.assertEqual(general["refund_date"], "2026-09-22")
        self.assertIsNone(general["expected_listing_date"])
        self.assertEqual(general["final_offer_price"], 19500.0)
        self.assertEqual(general["lead_managers"], ["아이비케이투자증권"])

        spac = normalize_kis_ipo_subscription_row({
            "sht_cd": "0200G0",
            "isin_name": "한국제17호기업인수목적",
            "fix_subscr_pri": "2000",
            "subscr_dt": "2026/09/10 ~ 2026/09/11",
            "pay_dt": "2026/09/15",
            "refund_dt": "2026/09/15",
            "list_dt": "",
            "lead_mgr": "한국투자증권",
        })
        self.assertEqual(spac["listing_track"], "spac")

        spac2 = normalize_kis_ipo_subscription_row({
            "sht_cd": "0197V0",
            "isin_name": "엔에이치스팩34호",
            "fix_subscr_pri": "2000",
            "subscr_dt": "2026/09/01 ~ 2026/09/02",
            "pay_dt": "2026/09/04",
            "refund_dt": "2026/09/04",
            "list_dt": "2026/09/10",
            "lead_mgr": "NH투자증권",
        })
        self.assertEqual(spac2["listing_track"], "spac")
        self.assertEqual(spac2["expected_listing_date"], "2026-09-10")

    def test_lead_managers_split_and_deduplicate(self):
        item = normalize_kis_ipo_subscription_row({
            "sht_cd": "0035S0",
            "isin_name": "빅웨이브로보틱스",
            "fix_subscr_pri": "18000",
            "subscr_dt": "2026/09/15 ~ 2026/09/16",
            "pay_dt": "2026/09/18",
            "refund_dt": "2026/09/18",
            "list_dt": "",
            "lead_mgr": "유진투자증권 / 미래에셋증권 / 유진투자증권",
        })
        self.assertEqual(item["lead_managers"], ["유진투자증권", "미래에셋증권"])

    def test_blank_listing_placeholder_rows_are_ignored(self):
        self.assertIsNone(normalize_kis_listing_schedule_row({
            "list_dt": "", "sht_cd": "", "isin_name": "", "stk_kind": "", "issue_type": "",
            "issue_stk_qty": "", "tot_issue_stk_qty": "", "issue_price": "",
        }))

    def test_listing_event_live_contract_is_not_promoted_to_actual_listing(self):
        item = normalize_kis_listing_schedule_row({
            "list_dt": "20260921",
            "sht_cd": "0161M0",
            "isin_name": "네오사피엔스",
            "stk_kind": "보통",
            "issue_type": "통일교체",
            "issue_stk_qty": "10135845",
            "tot_issue_stk_qty": "12215845",
            "issue_price": "500",
        })
        self.assertEqual(item["listing_date"], "2026-09-21")
        self.assertEqual(item["stock_code"], "0161M0")
        self.assertEqual(item["issue_type"], "통일교체")
        self.assertNotIn("actual_listing_date", item)
        self.assertNotIn("expected_listing_date", item)

    def test_nonblank_malformed_rows_fail_closed(self):
        with self.assertRaises(KISOpenAPIError):
            normalize_kis_ipo_subscription_row({"isin_name": "회사", "sht_cd": "123456", "subscr_dt": "not-a-date"})
        with self.assertRaises(KISOpenAPIError):
            normalize_kis_listing_schedule_row({"isin_name": "회사", "sht_cd": "123456", "list_dt": "bad"})

    async def test_ksdinfo_contract_and_m_only_pagination(self):
        client = self.make_client()
        fake = FakeClient([
            FakeResponse({"rt_cd": "0", "output1": [{"page": 1}]}, headers={"tr_cont": "M"}),
            FakeResponse({"rt_cd": "0", "output1": [{"page": 2}]}, headers={"tr_cont": "E"}),
        ])
        with patch("app.services.kis_openapi.asyncio.sleep", new=AsyncMock()):
            rows = await client._fetch_ksdinfo_pages(
                fake,
                "fixture-token",
                path=KIS_IPO_PUB_OFFER_PATH,
                tr_id=KIS_IPO_PUB_OFFER_TR_ID,
                from_date="2026-09-01",
                to_date="20261031",
                label="공모주청약일정",
            )
        self.assertEqual(rows, [{"page": 1}, {"page": 2}])
        self.assertEqual(fake.requests[0][1]["headers"]["tr_id"], KIS_IPO_PUB_OFFER_TR_ID)
        self.assertEqual(fake.requests[0][1]["params"], {
            "SHT_CD": "", "CTS": "", "F_DT": "20260901", "T_DT": "20261031",
        })
        self.assertEqual(fake.requests[1][1]["headers"]["tr_cont"], "N")

    async def test_f_header_is_terminal_for_ksd_schedule_contract(self):
        client = self.make_client()
        fake = FakeClient([
            FakeResponse({"rt_cd": "0", "output1": [{"page": 1}]}, headers={"tr_cont": "F"}),
            FakeResponse({"rt_cd": "0", "output1": [{"page": 2}]}, headers={"tr_cont": "E"}),
        ])
        rows = await client._fetch_ksdinfo_pages(
            fake,
            "fixture-token",
            path=KIS_LIST_INFO_PATH,
            tr_id=KIS_LIST_INFO_TR_ID,
            from_date="20260901",
            to_date="20261031",
            stock_code="468670",
            label="상장정보일정",
        )
        self.assertEqual(rows, [{"page": 1}])
        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(fake.requests[0][1]["params"]["SHT_CD"], "468670")

    async def test_api_and_schema_errors_fail_closed(self):
        client = self.make_client()
        for body in (
            {"rt_cd": "1", "msg1": "synthetic error", "output1": []},
            {"rt_cd": "0"},
            {"rt_cd": "0", "output1": {}},
        ):
            with self.subTest(body=body):
                fake = FakeClient([FakeResponse(body)])
                with self.assertRaises(KISOpenAPIError):
                    await client._fetch_ksdinfo_pages(
                        fake,
                        "fixture-token",
                        path=KIS_IPO_PUB_OFFER_PATH,
                        tr_id=KIS_IPO_PUB_OFFER_TR_ID,
                        from_date="20260901",
                        to_date="20261031",
                        label="공모주청약일정",
                    )

    async def test_page_limit_fails_closed_instead_of_returning_partial_data(self):
        client = self.make_client()
        fake = FakeClient([
            FakeResponse({"rt_cd": "0", "output1": [{"page": 1}]}, headers={"tr_cont": "M"}),
        ])
        with patch("app.services.kis_openapi.asyncio.sleep", new=AsyncMock()):
            with self.assertRaisesRegex(KISOpenAPIError, "연속조회 한도"):
                await client._fetch_ksdinfo_pages(
                    fake,
                    "fixture-token",
                    path=KIS_IPO_PUB_OFFER_PATH,
                    tr_id=KIS_IPO_PUB_OFFER_TR_ID,
                    from_date="20260901",
                    to_date="20261031",
                    label="공모주청약일정",
                    max_pages=1,
                )

    def test_stock_info_ksq_normalizes_correctly(self):
        body = {
            "rt_cd": "0",
            "msg_cd": "KIOK0530",
            "output": {
                "pdno": "00000A0197V0",
                "prdt_name": "엔에이치기업인수목적34호",
                "mket_id_cd": "KSQ",
                "scts_mket_lstg_dt": "",
                "kosdaq_mket_lstg_dt": "20260910",
                "frbd_mket_lstg_dt": "",
                "issu_pric": "2000",
            },
        }
        res = normalize_kis_stock_info_response(body, requested_stock_code="0197V0")
        self.assertEqual(res["stock_code"], "0197V0")
        self.assertEqual(res["product_code"], "00000A0197V0")
        self.assertEqual(res["company_name"], "엔에이치기업인수목적34호")
        self.assertEqual(res["market_code"], "KSQ")
        self.assertEqual(res["listing_date"], "2026-09-10")
        self.assertEqual(res["issue_price"], 2000.0)

    def test_stock_info_future_date_extracted_faithfully(self):
        body = {
            "rt_cd": "0",
            "output": {
                "pdno": "00000A0161M0",
                "prdt_name": "네오사피엔스",
                "mket_id_cd": "KSQ",
                "kosdaq_mket_lstg_dt": "20260921",
                "issu_pric": "10000",
            },
        }
        res = normalize_kis_stock_info_response(body, requested_stock_code="0161M0")
        self.assertEqual(res["listing_date"], "2026-09-21")

    def test_stock_info_rt_cd_nonzero_fails_closed(self):
        with self.assertRaises(KISOpenAPIError):
            normalize_kis_stock_info_response({"rt_cd": "1", "msg1": "조회 실패"}, requested_stock_code="0197V0")

    def test_stock_info_output_missing_or_not_dict_fails_closed(self):
        for invalid in [{"rt_cd": "0"}, {"rt_cd": "0", "output": []}, {"rt_cd": "0", "output": "invalid"}]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(KISOpenAPIError):
                    normalize_kis_stock_info_response(invalid, requested_stock_code="0197V0")

    def test_stock_info_unknown_market_code_does_not_guess_date(self):
        body = {
            "rt_cd": "0",
            "output": {
                "pdno": "123456",
                "prdt_name": "기타종목",
                "mket_id_cd": "KNX",
                "frbd_mket_lstg_dt": "20260910",
                "kosdaq_mket_lstg_dt": "20260910",
                "issu_pric": "5000",
            },
        }
        res = normalize_kis_stock_info_response(body, requested_stock_code="123456")
        self.assertIsNone(res["listing_date"])

    async def test_fetch_domestic_stock_info_request_contract(self):
        client = self.make_client()
        mock_resp = FakeResponse({
            "rt_cd": "0",
            "output": {
                "pdno": "00000A0197V0",
                "prdt_name": "엔에이치스팩34호",
                "mket_id_cd": "KSQ",
                "kosdaq_mket_lstg_dt": "20260910",
                "issu_pric": "2000",
            },
        })
        with patch("app.services.kis_openapi.require_external_network") as guard:
            with patch.object(client, "_access_token", AsyncMock(return_value="token123")):
                with patch("app.services.kis_openapi.httpx.AsyncClient") as mock_client_cls:
                    mock_http = AsyncMock()
                    mock_http.get.return_value = mock_resp
                    mock_client_cls.return_value.__aenter__.return_value = mock_http

                    res = await client.fetch_domestic_stock_info("0197V0")
                    guard.assert_called_once_with("KIS OpenAPI")
                    self.assertEqual(res["stock_code"], "0197V0")
                    self.assertEqual(res["listing_date"], "2026-09-10")

                    mock_http.get.assert_awaited_once()
                    call_args, call_kwargs = mock_http.get.call_args
                    url = call_args[0]
                    self.assertIn(KIS_STOCK_INFO_PATH, url)
                    self.assertEqual(call_kwargs["headers"]["tr_id"], KIS_STOCK_INFO_TR_ID)
                    self.assertEqual(call_kwargs["params"]["PRDT_TYPE_CD"], "300")
                    self.assertEqual(call_kwargs["params"]["PDNO"], "0197V0")


if __name__ == "__main__":
    unittest.main()
