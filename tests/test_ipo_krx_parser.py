import unittest
from unittest.mock import patch
import httpx

from app.services.ipo.krx_client import (
    parse_krx_new_listings_json,
    parse_krx_returns_json,
    parse_krx_listed_master_json,
    KrxClient,
    KrxParserError,
    KrxClientError,
)
from app.services.network_policy import ExternalNetworkDisabled

SAMPLE_KRX_LISTINGS_JSON = """{
  "output": [
    {
      "ISU_SRT_CD": "489570",
      "ISU_ABBRV": "메쥬",
      "LIST_DD": "2026/09/30",
      "IPO_PRC": "21,600",
      "MKT_NM": "KOSDAQ"
    },
    {
      "ISU_SRT_CD": "490110",
      "ISU_ABBRV": "알파로보틱스",
      "LIST_DD": "2026/10/05",
      "IPO_PRC": "15,000",
      "MKT_NM": "KOSPI"
    }
  ]
}"""

SAMPLE_KRX_RETURNS_JSON = """{
  "output": [
    {
      "ISU_SRT_CD": "489570",
      "R0": "125.5",
      "R1M": "85.2",
      "R3M": "60.0"
    }
  ]
}"""


class KrxParserTests(unittest.TestCase):
    def test_parse_valid_new_listings(self):
        items = parse_krx_new_listings_json(SAMPLE_KRX_LISTINGS_JSON)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["stock_code"], "489570")
        self.assertEqual(items[0]["company_name"], "메쥬")
        self.assertEqual(items[0]["actual_listing_date"], "2026-09-30")
        self.assertEqual(items[0]["final_offer_price"], 21600.0)
        self.assertEqual(items[0]["market"], "KOSDAQ")

    def test_parse_valid_returns(self):
        items = parse_krx_returns_json(SAMPLE_KRX_RETURNS_JSON)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["stock_code"], "489570")
        self.assertEqual(items[0]["r0"], 125.5)
        self.assertEqual(items[0]["r1m"], 85.2)
        self.assertEqual(items[0]["r3m"], 60.0)

    def test_parse_invalid_json_fails_closed(self):
        with self.assertRaises(KrxParserError):
            parse_krx_new_listings_json("{invalid_json}")

    def test_parse_mismatched_schema_fails_closed(self):
        with self.assertRaises(KrxParserError):
            parse_krx_new_listings_json('{"unexpected": 123}')

    def test_parse_listed_master_fixture_preserves_alphanumeric_code_and_fields(self):
        fixture = """{
          "block1": [
            {
              "full_code": "KR70197V0000",
              "short_code": "0197V0",
              "codeName": "엔에이치스팩34호",
              "marketCode": "KSQ",
              "marketName": "코스닥",
              "marketEngName": "KOSDAQ"
            }
          ],
          "CURRENT_DATETIME": "2026.09.18 PM 10:34:00"
        }"""
        items = parse_krx_listed_master_json(fixture)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["stock_code"], "0197V0")
        self.assertEqual(items[0]["full_code"], "KR70197V0000")
        self.assertEqual(items[0]["company_name"], "엔에이치스팩34호")
        self.assertEqual(items[0]["market_code"], "KSQ")
        self.assertEqual(items[0]["market_name"], "코스닥")
        self.assertEqual(items[0]["market_eng_name"], "KOSDAQ")

    def test_parse_listed_master_missing_block1_fails_closed(self):
        with self.assertRaises(KrxParserError):
            parse_krx_listed_master_json('{"output": []}')

    def test_parse_listed_master_block1_non_list_fails_closed(self):
        with self.assertRaises(KrxParserError):
            parse_krx_listed_master_json('{"block1": "not-a-list"}')

    def test_parse_listed_master_invalid_json_fails_closed(self):
        with self.assertRaises(KrxParserError):
            parse_krx_listed_master_json("invalid json {")

    def test_krx_client_network_policy_is_enforced_before_http(self):
        client = KrxClient()
        with patch("app.services.ipo.krx_client.require_external_network", side_effect=ExternalNetworkDisabled("blocked")):
            with self.assertRaises(ExternalNetworkDisabled):
                client.fetch_listed_master()

    def test_krx_client_http_500_fails_closed(self):
        client = KrxClient()
        mock_resp = httpx.Response(500, request=httpx.Request("POST", "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"), text="Internal Server Error")
        with patch("app.services.ipo.krx_client.require_external_network"):
            with patch("httpx.Client.post", return_value=mock_resp):
                with self.assertRaises(KrxClientError):
                    client.fetch_listed_master()

    def test_krx_client_official_host_allowlist_enforced(self):
        with self.assertRaises(KrxClientError):
            KrxClient(base_url="https://malicious.krx.co.kr")
        with self.assertRaises(KrxClientError):
            KrxClient(base_url="http://data.krx.co.kr")

    def test_krx_client_payload_bld_exact_and_headers(self):
        client = KrxClient()
        mock_resp = httpx.Response(
            200,
            request=httpx.Request("POST", "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"),
            text='{"block1": [{"short_code": "0197V0", "full_code": "KR70197V0000", "codeName": "엔에이치스팩34호", "marketCode": "KSQ"}]}',
        )
        with patch("app.services.ipo.krx_client.require_external_network") as guard:
            with patch("httpx.Client.post", return_value=mock_resp) as post:
                items = client.fetch_listed_master()
                guard.assert_called_once_with("KRX")
                _, kwargs = post.call_args
                self.assertEqual(kwargs["data"]["bld"], "dbms/comm/finder/finder_stkisu")
                self.assertEqual(kwargs["data"]["mktsel"], "ALL")
                self.assertEqual(kwargs["data"]["typeNo"], "0")
                self.assertEqual(kwargs["data"]["searchText"], "")
                self.assertIn("application/x-www-form-urlencoded", kwargs["headers"]["Content-Type"])
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]["stock_code"], "0197V0")

    def test_krx_client_zero_rows_fail_closed(self):
        client = KrxClient()
        mock_resp = httpx.Response(
            200,
            request=httpx.Request("POST", "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"),
            text='{"block1": []}',
        )
        with patch("app.services.ipo.krx_client.require_external_network"):
            with patch("httpx.Client.post", return_value=mock_resp):
                with self.assertRaises(KrxClientError) as ctx:
                    client.fetch_listed_master()
                self.assertIn("zero usable rows", str(ctx.exception))

    def test_krx_client_all_blank_rows_fail_closed(self):
        client = KrxClient()
        mock_resp = httpx.Response(
            200,
            request=httpx.Request("POST", "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"),
            text='{"block1": [{"short_code": "", "codeName": ""}]}',
        )
        with patch("app.services.ipo.krx_client.require_external_network"):
            with patch("httpx.Client.post", return_value=mock_resp):
                with self.assertRaises(KrxClientError) as ctx:
                    client.fetch_listed_master()
                self.assertIn("zero usable rows", str(ctx.exception))

    def test_krx_client_empty_body_fails_closed(self):
        client = KrxClient()
        mock_resp = httpx.Response(200, request=httpx.Request("POST", "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"), text="   ")
        with patch("app.services.ipo.krx_client.require_external_network"):
            with patch("httpx.Client.post", return_value=mock_resp):
                with self.assertRaises(KrxClientError):
                    client.fetch_listed_master()


if __name__ == "__main__":
    unittest.main()
