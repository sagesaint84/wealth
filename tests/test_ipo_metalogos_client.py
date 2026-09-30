from __future__ import annotations

import unittest

from app.services.ipo.metalogos_client import parse_metalogos_stock_html


class MetalogosIpoClientTests(unittest.TestCase):
    def test_parses_schedule_market_and_reference_score_without_wealth_features(self):
        html = """
        <html><body>
          <h1>멜콘 공모주 핵심 요약</h1>
          <div>공모가: 12,300원</div>
          <div>청약일: 2026.10.01 (목) ~ ~ 10.02 (금)</div>
          <div>상장일: 2026.10.15 (목)</div>
          <h2>멜콘</h2><div>코스닥 179880</div>
          <h3>멜콘 매력지수</h3><strong>87</strong>
          <div>수요예측 참여기관 수 2,405</div>
          <div>공모가 상단 이상 참여기관 수 2,402</div>
          <div>의무보유 확약기관 수 797</div>
          <div>유통가능비율 34.50%</div>
          <div>수요예측일 2026.09.24 (목)</div>
        </body></html>
        """
        row = parse_metalogos_stock_html(html, source_url="https://metalogos.ai/160ipo/stock/example")
        self.assertEqual(row["company_name"], "멜콘")
        self.assertEqual(row["market"], "KOSDAQ")
        self.assertEqual(row["stock_code"], "179880")
        self.assertEqual((row["subscription_start"], row["subscription_end"]), ("2026-10-01", "2026-10-02"))
        self.assertEqual(row["expected_listing_date"], "2026-10-15")
        self.assertEqual(row["final_offer_price"], 12300.0)
        self.assertEqual(row["sources"]["metalogos160"]["attractiveness_score"], 87)
        self.assertEqual(row["sources"]["metalogos160"]["tradable_share_ratio_reference"], 34.5)
        self.assertNotIn("features", row)


if __name__ == "__main__":
    unittest.main()
