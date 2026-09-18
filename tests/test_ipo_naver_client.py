"""Unit tests for NAVER IPO client and response parser."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from app.services.ipo.naver_client import (
    NAVER_OFFICIAL_HOSTS,
    NAVER_STOCK_BASE_URL,
    NaverIpoClient,
    NaverIpoClientError,
    normalize_naver_ipo_code,
    parse_naver_ipo_listing_json,
)
from app.services.network_policy import ExternalNetworkDisabled


SAMPLE_LISTING_PAYLOAD = {
    "ipoStatusType": "LISTING",
    "examinationList": [],
    "demandForecastingList": [],
    "forecastingCompleteList": [],
    "subscriptionList": [],
    "subscriptionCompleteList": [],
    "listingList": [
        {
            "ipoCode": "A0197V0",
            "compName": "엔에이치스팩34호",
            "marketType": "KOSDAQ",
            "gsrClass": "S",
            "lcalDate": "2026-09-10",
            "ipoStatus": "상장",
            "fixPubPrice": "2000",
        }
    ],
}


class NaverIpoClientTests(unittest.TestCase):
    def test_01_code_normalization_exact_a_prefix_removal(self):
        self.assertEqual(normalize_naver_ipo_code("A0197V0"), "0197V0")
        self.assertEqual(normalize_naver_ipo_code("A468670"), "468670")
        self.assertEqual(normalize_naver_ipo_code("0197V0"), "0197V0")

    def test_02_code_normalization_alphanumeric_preservation(self):
        self.assertEqual(normalize_naver_ipo_code("0197V0"), "0197V0")
        self.assertEqual(normalize_naver_ipo_code("468670"), "468670")
        self.assertEqual(normalize_naver_ipo_code("A0161M0"), "0161M0")
        self.assertEqual(normalize_naver_ipo_code("A0200G0"), "0200G0")

        # Invalid cases: length
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("A123")  # too short
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("A1234567")  # too long

        # Invalid cases: Korean / Unicode
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("가나다라마바")  # Korean 6 chars
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("A가나다라마")  # Korean with A prefix
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("Ａ01970")  # Fullwidth Unicode A

        # Invalid cases: special characters
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("019-V0")  # hyphen
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("A0197_")  # underscore
        with self.assertRaises(NaverIpoClientError):
            normalize_naver_ipo_code("019 70")  # space

    def test_03_ipo_status_type_not_listing_fail_closed(self):
        bad_payload = dict(SAMPLE_LISTING_PAYLOAD)
        bad_payload["ipoStatusType"] = "LISTING_UPCOMING"
        with self.assertRaises(NaverIpoClientError) as ctx:
            parse_naver_ipo_listing_json(bad_payload)
        self.assertIn("Unexpected ipoStatusType", str(ctx.exception))

    def test_04_listing_list_missing_fail_closed(self):
        bad_payload = {"ipoStatusType": "LISTING"}
        with self.assertRaises(NaverIpoClientError) as ctx:
            parse_naver_ipo_listing_json(bad_payload)
        self.assertIn("missing listingList", str(ctx.exception))

    def test_05_listing_list_non_list_fail_closed(self):
        bad_payload = {"ipoStatusType": "LISTING", "listingList": "not_a_list"}
        with self.assertRaises(NaverIpoClientError) as ctx:
            parse_naver_ipo_listing_json(bad_payload)
        self.assertIn("must be a list", str(ctx.exception))

    def test_06_invalid_json_fail_closed(self):
        with self.assertRaises(NaverIpoClientError):
            parse_naver_ipo_listing_json("{broken json")

    def test_07_row_non_dict_fail_closed(self):
        bad_payload = {"ipoStatusType": "LISTING", "listingList": ["not_a_dict"]}
        with self.assertRaises(NaverIpoClientError) as ctx:
            parse_naver_ipo_listing_json(bad_payload)
        self.assertIn("item must be dict", str(ctx.exception))

    def test_08_malformed_lcal_date_fail_closed(self):
        def _make_payload(date_val: str):
            return {
                "ipoStatusType": "LISTING",
                "listingList": [
                    {
                        "ipoCode": "A0197V0",
                        "compName": "테스트",
                        "marketType": "KOSDAQ",
                        "lcalDate": date_val,
                        "ipoStatus": "상장",
                    }
                ],
            }

        # Valid date passes
        parsed = parse_naver_ipo_listing_json(_make_payload("2026-09-10"))
        self.assertEqual(parsed[0]["actual_listing_date"], "2026-09-10")

        # Wrong delimiter fails
        with self.assertRaises(NaverIpoClientError):
            parse_naver_ipo_listing_json(_make_payload("2026/09/10"))

        # 2026-02-30 (invalid calendar date) fails
        with self.assertRaises(NaverIpoClientError):
            parse_naver_ipo_listing_json(_make_payload("2026-02-30"))

        # 2026-13-01 (invalid month) fails
        with self.assertRaises(NaverIpoClientError):
            parse_naver_ipo_listing_json(_make_payload("2026-13-01"))

        # 2026-9-10 (not 2-digit month) fails
        with self.assertRaises(NaverIpoClientError):
            parse_naver_ipo_listing_json(_make_payload("2026-9-10"))

    def test_09_unknown_blank_ipocode_fail_closed(self):
        bad_payload = {
            "ipoStatusType": "LISTING",
            "listingList": [
                {
                    "ipoCode": "",
                    "compName": "테스트",
                    "marketType": "KOSDAQ",
                    "lcalDate": "2026-09-10",
                    "ipoStatus": "상장",
                }
            ],
        }
        with self.assertRaises(NaverIpoClientError) as ctx:
            parse_naver_ipo_listing_json(bad_payload)
        self.assertIn("Missing ipoCode", str(ctx.exception))

    def test_10_official_host_allowlist(self):
        with self.assertRaises(NaverIpoClientError) as ctx:
            NaverIpoClient("https://malicious.com")
        self.assertIn("Host not in official NAVER allowlist", str(ctx.exception))

    def test_11_https_only(self):
        with self.assertRaises(NaverIpoClientError) as ctx:
            NaverIpoClient("http://stock.naver.com")
        self.assertIn("requires https", str(ctx.exception))

    def test_12_network_policy_before_http(self):
        # By default in unittests, external network is disabled
        client = NaverIpoClient()
        with self.assertRaises(ExternalNetworkDisabled):
            client.fetch_completed_listings()

    @patch("app.services.ipo.naver_client.require_external_network")
    @patch("httpx.Client")
    def test_13_http_500_fail_closed(self, mock_client_cls, mock_require_net):
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_http.get.return_value = mock_resp

        client = NaverIpoClient()
        with self.assertRaises(NaverIpoClientError) as ctx:
            client.fetch_completed_listings()
        self.assertIn("HTTP error 500", str(ctx.exception))

    @patch("app.services.ipo.naver_client.require_external_network")
    @patch("httpx.Client")
    def test_14_empty_response_fail_closed(self, mock_client_cls, mock_require_net):
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "   "
        mock_http.get.return_value = mock_resp

        client = NaverIpoClient()
        with self.assertRaises(NaverIpoClientError) as ctx:
            client.fetch_completed_listings()
        self.assertIn("Empty response body", str(ctx.exception))

    @patch("app.services.ipo.naver_client.require_external_network")
    @patch("httpx.Client")
    def test_15_request_contract(self, mock_client_cls, mock_require_net):
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = json.dumps(SAMPLE_LISTING_PAYLOAD)
        mock_http.get.return_value = mock_resp

        client = NaverIpoClient()
        results = client.fetch_completed_listings(page_size=100)

        mock_http.get.assert_called_once()
        url, kwargs = mock_http.get.call_args
        self.assertEqual(url[0], "https://stock.naver.com/api/domestic/market/ipo/progress")
        self.assertEqual(
            kwargs["params"],
            {"IpoProgressType": "LISTING", "startIdx": 0, "pageSize": 100},
        )
        self.assertEqual(
            kwargs["headers"]["Referer"],
            "https://stock.naver.com/market/stock/kr/ipo/recent",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["stock_code"], "0197V0")

    @patch("app.services.ipo.naver_client.require_external_network")
    @patch("httpx.Client")
    def test_16_pagination_aggregate_full_and_partial(self, mock_client_cls, mock_require_net):
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http

        # Page 0 has 2 items (with page_size=2)
        page0 = {
            "ipoStatusType": "LISTING",
            "listingList": [
                {
                    "ipoCode": "A0197V0",
                    "compName": "종목1",
                    "marketType": "KOSDAQ",
                    "lcalDate": "2026-09-10",
                    "ipoStatus": "상장",
                },
                {
                    "ipoCode": "A0200G0",
                    "compName": "종목2",
                    "marketType": "KOSDAQ",
                    "lcalDate": "2026-09-11",
                    "ipoStatus": "상장",
                },
            ],
        }
        # Page 1 has 1 item (< page_size=2), so terminates
        page1 = {
            "ipoStatusType": "LISTING",
            "listingList": [
                {
                    "ipoCode": "A468670",
                    "compName": "종목3",
                    "marketType": "KOSDAQ",
                    "lcalDate": "2026-09-12",
                    "ipoStatus": "상장",
                }
            ],
        }

        resp0 = MagicMock(status_code=200, text=json.dumps(page0))
        resp1 = MagicMock(status_code=200, text=json.dumps(page1))
        mock_http.get.side_effect = [resp0, resp1]

        client = NaverIpoClient()
        results = client.fetch_completed_listings(page_size=2, max_pages=10)
        self.assertEqual(len(results), 3)
        self.assertEqual([r["stock_code"] for r in results], ["0197V0", "0200G0", "468670"])
        self.assertEqual(mock_http.get.call_count, 2)

    @patch("app.services.ipo.naver_client.require_external_network")
    @patch("httpx.Client")
    def test_17_empty_next_page_terminal(self, mock_client_cls, mock_require_net):
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http

        page0 = {
            "ipoStatusType": "LISTING",
            "listingList": [
                {
                    "ipoCode": "A0197V0",
                    "compName": "종목1",
                    "marketType": "KOSDAQ",
                    "lcalDate": "2026-09-10",
                    "ipoStatus": "상장",
                },
            ],
        }
        page1 = {
            "ipoStatusType": "LISTING",
            "listingList": [],
        }

        resp0 = MagicMock(status_code=200, text=json.dumps(page0))
        resp1 = MagicMock(status_code=200, text=json.dumps(page1))
        mock_http.get.side_effect = [resp0, resp1]

        client = NaverIpoClient()
        results = client.fetch_completed_listings(page_size=1, max_pages=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["stock_code"], "0197V0")
        self.assertEqual(mock_http.get.call_count, 2)

    @patch("app.services.ipo.naver_client.require_external_network")
    @patch("httpx.Client")
    def test_18_repeated_page_signature_fail_closed(self, mock_client_cls, mock_require_net):
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http

        page_identical = {
            "ipoStatusType": "LISTING",
            "listingList": [
                {
                    "ipoCode": "A0197V0",
                    "compName": "종목1",
                    "marketType": "KOSDAQ",
                    "lcalDate": "2026-09-10",
                    "ipoStatus": "상장",
                },
            ],
        }

        resp0 = MagicMock(status_code=200, text=json.dumps(page_identical))
        resp1 = MagicMock(status_code=200, text=json.dumps(page_identical))
        mock_http.get.side_effect = [resp0, resp1]

        client = NaverIpoClient()
        with self.assertRaises(NaverIpoClientError) as ctx:
            client.fetch_completed_listings(page_size=1, max_pages=5)
        self.assertIn("repeated page signature", str(ctx.exception))

    @patch("app.services.ipo.naver_client.require_external_network")
    @patch("httpx.Client")
    def test_19_max_pages_exhaustion_prohibits_partial_return(self, mock_client_cls, mock_require_net):
        mock_http = MagicMock()
        mock_client_cls.return_value = mock_http

        def make_page(idx: int):
            return MagicMock(
                status_code=200,
                text=json.dumps({
                    "ipoStatusType": "LISTING",
                    "listingList": [
                        {
                            "ipoCode": f"A0000{idx:02d}",
                            "compName": f"종목{idx}",
                            "marketType": "KOSDAQ",
                            "lcalDate": "2026-09-10",
                            "ipoStatus": "상장",
                        }
                    ],
                }),
            )

        mock_http.get.side_effect = [make_page(i) for i in range(3)]

        client = NaverIpoClient()
        with self.assertRaises(NaverIpoClientError) as ctx:
            client.fetch_completed_listings(page_size=1, max_pages=3)
        self.assertIn("exhausted with full pages", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
