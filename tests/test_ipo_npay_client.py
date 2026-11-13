from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from app.services.ipo.npay_client import NPAY_IPO_URL, NpayIpoClient, NpayIpoClientError, parse_npay_ipo_html


class NpayIpoClientTests(unittest.TestCase):
    def test_official_https_response_is_parsed_without_following_redirects(self):
        html = "<html>다가오는 청약 종목 D-2 11.12 예정 다음기업 공모가 10,000원</html>"
        rows = self.fetch_with_response(200, text=html)
        self.assertEqual(rows[0]["subscription_start"], "2026-11-12")

    def test_redirects_are_rejected_without_a_second_request(self):
        for status in (301, 302, 303, 307, 308):
            for location in (
                "https://example.invalid/ipo",
                "http://ustock.naver.com/service/ipo",
                "https://ustock.naver.com/service/ipo?next=1",
            ):
                with self.subTest(status=status, location=location):
                    with self.assertRaisesRegex(NpayIpoClientError, f"redirect refused .*{status}"):
                        self.fetch_with_response(status, location=location)

    def fetch_with_response(self, status, *, text="", location=None):
        requests = []
        real_client = httpx.Client

        def respond(request):
            requests.append(str(request.url))
            headers = {"Location": location} if location else {}
            return httpx.Response(status, text=text, headers=headers)

        try:
            with patch("app.services.ipo.npay_client.require_external_network"), patch(
                "app.services.ipo.npay_client.httpx.Client",
                side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs),
            ):
                return NpayIpoClient().fetch_upcoming_ipos(target_date_str="2026-11-10")
        finally:
            self.assertEqual(requests, [NPAY_IPO_URL])


    def test_parses_active_row_with_only_the_visible_close_date(self):
        html = """
        <html><body><section>다가오는 청약 종목</section>
        <div>청약진행중 1 청약예정 1</div>
        <div>진행중 11.11 마감 <strong>하나에어로다이내믹스</strong> 공모가 5,700원 기관경쟁률 1051.38:1</div>
        <div>D-2 11.12 예정 <strong>다음기업</strong> 공모가 9,600 ~ 11,700원 기관경쟁률 -</div>
        </body></html>
        """
        rows = parse_npay_ipo_html(html, target_date_str="2026-11-10")
        active = next(row for row in rows if row["company_name"] == "하나에어로다이내믹스")
        upcoming = next(row for row in rows if row["company_name"] == "다음기업")
        self.assertEqual(active["npay_subscription_status"], "active")
        self.assertEqual(active["subscription_end"], "2026-11-11")
        self.assertNotIn("subscription_start", active)
        self.assertEqual(upcoming["npay_subscription_status"], "upcoming")
        self.assertEqual(upcoming["subscription_start"], "2026-11-12")
        self.assertNotIn("subscription_end", upcoming)
        self.assertEqual(active["sources"]["npay"]["url"], "https://ustock.naver.com/service/ipo?schedule=toBeIPOList")
        self.assertTrue(active["sources"]["npay"]["observed_at"])

    def test_parses_upcoming_general_and_spac_rows(self):
        html = """
        <html><body>
          <section>다가오는 청약 종목</section>
          <div>D-1 10.01 예정 <strong>멜콘</strong> 공모가 12,300원 기관경쟁률 1,136.84:1</div>
          <div>D-2 10.02 예정 <strong>진코스텍</strong> 공모가 23,500원 기관경쟁률 1,097.62:1</div>
          <div>D-15 10.15 예정 <strong>에스케이증권제14호기업인수목적</strong> 공모가 2,000원 기관경쟁률 -</div>
          <h2>청약 전에도 비상장 주식으로 미리 거래할 수 있어요!</h2>
        </body></html>
        """
        rows = parse_npay_ipo_html(html, target_date_str="2026-09-30")
        self.assertEqual([row["company_name"] for row in rows], [
            "멜콘", "진코스텍", "에스케이증권제14호기업인수목적",
        ])
        self.assertEqual(rows[1]["subscription_start"], "2026-10-02")
        self.assertNotIn("subscription_end", rows[1])
        self.assertEqual(rows[1]["final_offer_price"], 23500.0)
        self.assertEqual(
            rows[1]["sources"]["npay"]["institutional_competition_ratio_reference"],
            1097.62,
        )
        self.assertEqual(rows[2]["listing_track"], "spac")

    def test_parses_offer_band_without_promoting_reference_score_feature(self):
        html = """
        <html><body>다가오는 청약 종목
        D-7 10.07 예정 엘리스그룹 공모가 70,400 ~ 90,500원 기관경쟁률 -
        청약 전에도 비상장 주식으로 미리 거래할 수 있어요!</body></html>
        """
        row = parse_npay_ipo_html(html, target_date_str="2026-09-30")[0]
        self.assertEqual((row["offer_band_low"], row["offer_band_high"]), (70400.0, 90500.0))
        self.assertNotIn("features", row)

    def test_year_boundary_chooses_next_january(self):
        html = """
        <html><body>다가오는 청약 종목
        D-2 01.02 예정 새해기업 공모가 10,000원 기관경쟁률 -
        청약 전에도 비상장 주식으로 미리 거래할 수 있어요!</body></html>
        """
        row = parse_npay_ipo_html(html, target_date_str="2026-12-31")[0]
        self.assertEqual(row["subscription_start"], "2027-01-02")

    def test_fails_closed_without_page_contract(self):
        with self.assertRaises(NpayIpoClientError):
            parse_npay_ipo_html("<html>not ipo</html>", target_date_str="2026-09-30")

    def test_intact_schedule_with_no_rows_is_distinct_from_fetch_error(self):
        html = "<html>다가오는 청약 종목 청약진행중 청약예정</html>"
        self.assertEqual(parse_npay_ipo_html(html, target_date_str="2026-09-30"), [])

    def test_empty_body_remains_a_fetch_contract_error(self):
        with self.assertRaisesRegex(NpayIpoClientError, "response is empty"):
            parse_npay_ipo_html("", target_date_str="2026-09-30")


if __name__ == "__main__":
    unittest.main()
