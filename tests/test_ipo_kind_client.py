import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.services.ipo.kind_client import KindClient, KindClientError
from app.services.network_policy import ExternalNetworkDisabled


LIVE_ROW = """
<section id="section-talbe"><table summary="회사명,신고서제출일,수요예측일정,청약일정,납입일,확정공모가,공모금액(백만원),상장예정일,상장주선인/지정자문인">
<thead><tr id="title-contents"></tr></thead><tbody>
<tr><td>브릴스</td><td>2026.07.13</td><td>2026.09.09 ~ 2026.09.15</td><td>2026.09.17 ~ 2026.09.18</td><td>2026.09.22</td><td>19,500</td><td>23,400</td><td>2026.10.01</td><td>IBK투자증권(주)</td></tr>
</tbody></table></section>
<script>fn_InitTitle("회사명,신고서제출일,수요예측일정,청약일정,납입일,확정공모가,공모금액<br/>(백만원),상장예정일,상장주선인/<br/>지정자문인", "true,true,false,false,false,false,false,true,false");</script>
"""

EMPTY_PAGE = """
<section><table summary="회사명,신고서제출일,수요예측일정,청약일정,납입일,확정공모가,공모금액(백만원),상장예정일,상장주선인/지정자문인">
<thead><tr id="title-contents"></tr></thead><tbody><tr><td colspan="9">조회된 결과값이 없습니다.</td></tr></tbody></table></section>
"""


class KindClientTests(unittest.TestCase):
    def test_fetch_html_uses_utf8_form_contract(self):
        request = httpx.Request("POST", "https://kind.krx.co.kr/listinvstg/pubofrprogcom.do")
        response = httpx.Response(200, request=request, text=LIVE_ROW, headers={"content-type": "text/html; charset=UTF-8"})
        with patch("app.services.ipo.kind_client.require_external_network") as guard, patch("httpx.Client.post", return_value=response) as post:
            body = KindClient().fetch_pubofr_schedule_html(
                "2025-09-18", "2026-09-18", corp_name="브릴스", page_size=100, page_index=1
            )

        guard.assert_called_once_with("KIND")
        self.assertIn("브릴스", body)
        _, kwargs = post.call_args
        self.assertEqual(kwargs["data"]["searchCorpName"], "브릴스")
        self.assertEqual(kwargs["data"]["searchCorpNameTmp"], "브릴스")
        self.assertEqual(kwargs["data"]["currentPageSize"], "100")
        self.assertEqual(kwargs["data"]["pageIndex"], "1")
        self.assertIn("charset=UTF-8", kwargs["headers"]["Content-Type"])

    def test_network_policy_is_enforced_before_http(self):
        with patch(
            "app.services.ipo.kind_client.require_external_network",
            side_effect=ExternalNetworkDisabled("blocked"),
        ), patch("httpx.Client.post") as post:
            with self.assertRaises(ExternalNetworkDisabled):
                KindClient().fetch_pubofr_schedule_html("2025-09-18", "2026-09-18")
        post.assert_not_called()

    def test_http_error_fails_closed(self):
        request = httpx.Request("POST", "https://kind.krx.co.kr/listinvstg/pubofrprogcom.do")
        response = httpx.Response(500, request=request, text="server error")
        with patch("app.services.ipo.kind_client.require_external_network"), patch("httpx.Client.post", return_value=response):
            with self.assertRaises(KindClientError):
                KindClient().fetch_pubofr_schedule_html("2025-09-18", "2026-09-18")

    def test_paginated_items_stop_on_authoritative_empty_page(self):
        client = KindClient()
        client.fetch_pubofr_schedule_html = MagicMock(side_effect=[LIVE_ROW, EMPTY_PAGE])
        items = client.fetch_pubofr_schedule_items(
            "2025-09-18", "2026-09-18", corp_name="브릴스", page_size=1, max_pages=3
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["expected_listing_date"], "2026-10-01")
        self.assertEqual(client.fetch_pubofr_schedule_html.call_count, 2)

    def test_repeated_pagination_page_fails_closed(self):
        client = KindClient()
        client.fetch_pubofr_schedule_html = MagicMock(side_effect=[LIVE_ROW, LIVE_ROW])
        with self.assertRaises(KindClientError):
            client.fetch_pubofr_schedule_items(
                "2025-09-18", "2026-09-18", corp_name="브릴스", page_size=1, max_pages=3
            )

    def test_official_https_host_is_required(self):
        with self.assertRaises(KindClientError):
            KindClient(base_url="http://kind.krx.co.kr")
        with self.assertRaises(KindClientError):
            KindClient(base_url="https://example.com")


if __name__ == "__main__":
    unittest.main()
