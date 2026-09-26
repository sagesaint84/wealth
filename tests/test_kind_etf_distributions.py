from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import AsyncMock, patch

from app.services import etf_kind_distributions as kind


SEARCH_HTML = """
<table><tbody>
<tr>
  <td>4</td><td>2026-07-29 16:55</td>
  <td><a title="KODEX 미국S&amp;P500">KODEX 미국S&amp;P500</a></td>
  <td><a href="#viewer" onclick="openDisclsViewer('20260729000913','')"
      title="ETF이익금분배신고(분배금안내)(일괄공시)">분배금 공시</a></td>
  <td>신한펀드파트너스</td>
</tr>
<tr>
  <td>3</td><td>2026-07-28 17:34</td><td>ETF</td>
  <td><a href="#viewer" onclick="openDisclsViewer('20260728000862','')"
      title="ETF이익금분배 수익자 확정을 위한 설정/환매접수 일시중지 안내(일괄공시)">안내</a></td>
  <td>신한펀드파트너스</td>
</tr>
</tbody></table>
"""

DOCUMENT_HTML = """
<html><body><table>
<tr><th>종목코드</th><th>종목약명</th><th>투자신탁 분배금 지급기준일</th>
<th>투자신탁 분배금 지급예정일</th><th>분배금(원)</th><th>기타</th></tr>
<tr><td>KR7379800006</td><td>KODEX 미국S&amp;P500</td><td>2026-07-31</td>
<td>2026-08-04</td><td>132</td><td>-</td></tr>
<tr><td>KR70005G0001</td><td>IBK K-AI반도체코어테크</td><td>2026-07-31</td>
<td>2026-08-04</td><td>2,638</td><td>-</td></tr>
</table></body></html>
"""


def make_summary(*, is_etf: bool = True, annual: float = 1_000) -> dict:
    schedule = [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)]
    if annual > 0:
        for month in [1, 4, 7, 10]:
            item = {
                "code": "379800",
                "name": "KODEX 미국S&P500",
                "quantity": 10,
                "currency": "KRW",
                "payout_krw": 250,
                "payout_orig": 250,
                "div_yield": 1.0,
            }
            schedule[month - 1]["items"].append(item)
            schedule[month - 1]["total_krw"] = 250
    return {
        "total_annual_dividend_krw": annual,
        "monthly_avg_dividend_krw": round(annual / 12),
        "dividend_paying_count": 1 if annual else 0,
        "portfolio_yield": 1.0,
        "monthly_schedule": schedule,
        "holding_dividends": [
            {
                "code": "379800",
                "name": "KODEX 미국S&P500",
                "quantity": 10,
                "currency": "KRW",
                "is_etf": is_etf,
                "annual_div_per_share": annual / 10,
                "annual_payout_krw": annual,
                "annual_payout_orig": annual,
                "payout_months": [1, 4, 7, 10] if annual else [],
                "forecast_source": {"numeric_source": "naver"},
            }
        ],
        "forecast_source_policy": {},
    }


class KindEtfParserTests(unittest.TestCase):
    def test_short_code_from_numeric_and_alphanumeric_isin(self):
        self.assertEqual(kind.short_code_from_isin("KR7379800006"), "379800")
        self.assertEqual(kind.short_code_from_isin("KR70005G0001"), "0005G0")
        self.assertIsNone(kind.short_code_from_isin("US1234567890"))

    def test_search_parser_keeps_distribution_filing_only(self):
        rows = kind.parse_kind_etf_search_results(SEARCH_HTML)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["receipt_no"], "20260729000913")
        self.assertIn("ETF이익금분배신고", rows[0]["title"])

    def test_viewer_external_document_path_is_structured(self):
        viewer = """
        <input id="docLocPath" value="/external/2026/07/29/000913/20260729002071/68659.htm" />
        <link href="/external/report_xml.css" />
        """
        self.assertEqual(
            kind.extract_external_document_paths(viewer),
            ["/external/2026/07/29/000913/20260729002071/68659.htm"],
        )

    def test_distribution_document_parses_target_row(self):
        events = kind.parse_kind_distribution_document(
            DOCUMENT_HTML,
            target_short_code="379800",
        )
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["isin"], "KR7379800006")
        self.assertEqual(event["record_date"], "2026-07-31")
        self.assertEqual(event["payment_date"], "2026-08-04")
        self.assertEqual(event["amount_per_unit_krw"], 132.0)
        self.assertTrue(event["confirmed_amount"])

    def test_incomplete_distribution_row_is_not_confirmed(self):
        html = DOCUMENT_HTML.replace("2026-08-04</td><td>132", "-</td><td>132")
        self.assertEqual(
            kind.parse_kind_distribution_document(html, target_short_code="379800"),
            [],
        )


class KindEtfEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_record_month_moves_legacy_item_to_payment_month(self):
        summary = make_summary()
        official = {
            "status": "ok",
            "events": [
                {
                    "isin": "KR7379800006",
                    "short_code": "379800",
                    "name": "KODEX 미국S&P500",
                    "record_date": "2026-07-31",
                    "payment_date": "2026-08-04",
                    "amount_per_unit_krw": 132,
                    "receipt_no": "20260729000913",
                    "confirmed_amount": True,
                }
            ],
        }
        with (
            patch.object(kind, "external_network_allowed", return_value=True),
            patch.object(
                kind,
                "fetch_kind_etf_distribution_events",
                new=AsyncMock(return_value=official),
            ),
        ):
            result = await kind.enrich_dividend_summary_with_kind_etf_distributions(
                summary,
                [
                    {
                        "code": "379800",
                        "currency": "KRW",
                        "quantity": 10,
                        "current_price": 20_000,
                    }
                ],
                as_of=date(2026, 9, 26),
            )

        row = result["holding_dividends"][0]
        self.assertEqual(result["monthly_schedule"][6]["total_krw"], 0)
        self.assertEqual(result["monthly_schedule"][7]["total_krw"], 1_320)
        self.assertEqual(row["payout_months"], [1, 4, 8, 10])
        self.assertEqual(row["annual_payout_krw"], 2_070)
        self.assertEqual(result["total_annual_dividend_krw"], 2_070)
        self.assertEqual(row["forecast_source"]["numeric_source"], "kind_etf_confirmed_overlay")
        self.assertEqual(row["forecast_source"]["kind_etf_numeric_override_count"], 1)
        self.assertTrue(official["events"][0]["numeric_override"])

    async def test_zero_legacy_forecast_can_create_multiple_confirmed_events(self):
        summary = make_summary(annual=0)
        official = {
            "status": "ok",
            "events": [
                {
                    "record_date": "2026-07-31",
                    "payment_date": "2026-08-04",
                    "amount_per_unit_krw": 100,
                    "confirmed_amount": True,
                },
                {
                    "record_date": "2026-08-31",
                    "payment_date": "2026-09-03",
                    "amount_per_unit_krw": 110,
                    "confirmed_amount": True,
                },
            ],
        }
        with (
            patch.object(kind, "external_network_allowed", return_value=True),
            patch.object(
                kind,
                "fetch_kind_etf_distribution_events",
                new=AsyncMock(return_value=official),
            ),
        ):
            result = await kind.enrich_dividend_summary_with_kind_etf_distributions(
                summary,
                [{"code": "379800", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_payout_krw"], 2_100)
        self.assertEqual(row["payout_months"], [8, 9])
        self.assertEqual(result["dividend_paying_count"], 1)

    async def test_positive_forecast_without_safe_month_match_is_evidence_only(self):
        summary = make_summary()
        official = {
            "status": "ok",
            "events": [
                {
                    "record_date": "2026-06-30",
                    "payment_date": "2026-08-04",
                    "amount_per_unit_krw": 132,
                    "confirmed_amount": True,
                }
            ],
        }
        with (
            patch.object(kind, "external_network_allowed", return_value=True),
            patch.object(
                kind,
                "fetch_kind_etf_distribution_events",
                new=AsyncMock(return_value=official),
            ),
        ):
            result = await kind.enrich_dividend_summary_with_kind_etf_distributions(
                summary,
                [{"code": "379800", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        self.assertEqual(result["total_annual_dividend_krw"], 1_000)
        self.assertEqual(
            result["holding_dividends"][0]["forecast_source"]["kind_etf_numeric_override_count"],
            0,
        )
        self.assertFalse(official["events"][0]["numeric_override"])

    async def test_non_etf_row_is_not_queried(self):
        summary = make_summary(is_etf=False)
        mocked = AsyncMock()
        with (
            patch.object(kind, "external_network_allowed", return_value=True),
            patch.object(kind, "fetch_kind_etf_distribution_events", new=mocked),
        ):
            result = await kind.enrich_dividend_summary_with_kind_etf_distributions(
                summary,
                [{"code": "379800", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        mocked.assert_not_awaited()
        self.assertEqual(result["forecast_source_policy"]["kind_etf_status"], "no_domestic_etf")

    async def test_network_disabled_preserves_legacy(self):
        summary = make_summary()
        with patch.object(kind, "external_network_allowed", return_value=False):
            result = await kind.enrich_dividend_summary_with_kind_etf_distributions(
                summary,
                [{"code": "379800", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        self.assertEqual(result["total_annual_dividend_krw"], 1_000)
        self.assertEqual(result["forecast_source_policy"]["kind_etf_status"], "network_disabled")


if __name__ == "__main__":
    unittest.main()
