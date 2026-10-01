from __future__ import annotations

import unittest

from app.services.ipo.metalogos_client import (
    parse_metalogos_search_stock_urls,
    parse_metalogos_sitemap_stock_urls,
    parse_metalogos_stock_html,
)


class MetalogosIpoClientTests(unittest.TestCase):

    def test_parses_public_sitemap_stock_urls_newest_first(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url>
            <loc>https://metalogos.ai/160ipo/stock/B202605064</loc>
            <lastmod>2026-09-30</lastmod>
          </url>
          <url>
            <loc>https://metalogos.ai/160ipo/stock/B202604001</loc>
            <lastmod>2026-09-20</lastmod>
          </url>
          <url>
            <loc>https://metalogos.ai/other/page</loc>
            <lastmod>2026-10-01</lastmod>
          </url>
        </urlset>
        """
        urls = parse_metalogos_sitemap_stock_urls(xml)
        self.assertEqual(
            urls,
            [
                "https://metalogos.ai/160ipo/stock/B202605064",
                "https://metalogos.ai/160ipo/stock/B202604001",
            ],
        )

    def test_public_search_extracts_detail_link(self):
        html = (
            '<a href="/160ipo/stock/B202605064">'
            'issuer</a>'
        )
        self.assertEqual(
            parse_metalogos_search_stock_urls(html),
            [
                "https://metalogos.ai/"
                "160ipo/stock/B202605064"
            ],
        )

    def test_h1_company_name_wins_over_seo_description(self):
        html = """
        <html><body>
          <div>
            description text before heading
          </div>
          <h1>
            \uba5c\ucf58 \uacf5\ubaa8\uc8fc
            \ud575\uc2ec \uc694\uc57d
          </h1>
          <div>
            \uacf5\ubaa8\uac00: 12,300\uc6d0
          </div>
          <div>
            \uccad\uc57d\uc77c:
            2026.10.01 ~ 2026.10.02
          </div>
          <div>
            \uc0c1\uc7a5\uc77c:
            2026.10.15
          </div>
          <div>
            \ucf54\uc2a4\ub2e5 179880
          </div>
        </body></html>
        """

        row = parse_metalogos_stock_html(
            html,
            source_url=(
                "https://metalogos.ai/"
                "160ipo/stock/B202605064"
            ),
        )

        self.assertEqual(
            row["company_name"],
            "\uba5c\ucf58",
        )
        self.assertEqual(
            row["stock_code"],
            "179880",
        )
        self.assertEqual(
            row["final_offer_price"],
            12300.0,
        )

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
