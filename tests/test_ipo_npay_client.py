from __future__ import annotations

import unittest

from app.services.ipo.npay_client import NpayIpoClientError, parse_npay_ipo_html


class NpayIpoClientTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
