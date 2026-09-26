from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import AsyncMock, patch

from app.services.dividend_confirmed_disclosures import parse_dividend_decision_document
from app.services import dividend_official_sources as official


DISCLOSURE = """
<html><body><table>
<tr><th>구분</th><th>내용</th></tr>
<tr><td>3. 1주당 배당금 (원)</td><td>보통주식</td><td>1,250</td></tr>
<tr><td>배당기준일</td><td>2026년 09월 30일</td></tr>
<tr><td>배당금지급 예정일자</td><td>2026-11-20</td></tr>
</table></body></html>
"""


class ConfirmedDividendDisclosureParserTests(unittest.TestCase):
    def test_structurally_parses_amount_and_dates(self):
        result = parse_dividend_decision_document(
            DISCLOSURE,
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000123",
            receipt_date="20260926",
            viewer_url="https://dart.fss.or.kr/example",
            as_of=date(2026, 9, 26),
        )
        self.assertTrue(result["structured_verification"])
        self.assertTrue(result["confirmed_amount"])
        self.assertEqual(result["ordinary_cash_dps_krw"], 1250.0)
        self.assertEqual(result["record_date"], "2026-09-30")
        self.assertEqual(result["payment_date"], "2026-11-20")
        self.assertTrue(result["future_payment"])

    def test_missing_payment_date_is_not_invented(self):
        result = parse_dividend_decision_document(
            "<table><tr><td>1주당 배당금(원)</td><td>보통주식</td><td>500</td></tr></table>",
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000124",
            as_of=date(2026, 9, 26),
        )
        self.assertTrue(result["confirmed_amount"])
        self.assertIsNone(result["payment_date"])
        self.assertFalse(result["confirmed_payment_date"])
        self.assertIsNone(result["future_payment"])

    def test_title_match_without_structured_amount_is_not_confirmed(self):
        result = parse_dividend_decision_document(
            "<table><tr><td>배당기준일</td><td>2026-09-30</td></tr></table>",
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000125",
        )
        self.assertFalse(result["confirmed_amount"])
        self.assertFalse(result["structured_verification"])

    def test_non_decision_report_is_rejected(self):
        result = parse_dividend_decision_document(
            DISCLOSURE,
            report_name="사업보고서",
            receipt_no="20260926000126",
        )
        self.assertFalse(result["confirmed_amount"])
        self.assertEqual(result["reason"], "not_dividend_decision_report")


class ConfirmedDividendForecastIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_future_amount_replaces_matching_month_estimate(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 10,
                    "currency": "KRW",
                    "annual_div_per_share": 4000,
                    "annual_payout_orig": 40000,
                    "annual_payout_krw": 40000,
                    "payout_months": [4, 5, 8, 11],
                    "div_yield": 5.0,
                }
            ],
            "monthly_schedule": [
                {"month": m, "total_krw": (10000 if m in {4, 5, 8, 11} else 0), "items": ([{
                    "code": "005930", "name": "삼성전자", "quantity": 10,
                    "currency": "KRW", "payout_krw": 10000, "payout_orig": 10000,
                    "div_yield": 5.0,
                }] if m in {4, 5, 8, 11} else [])}
                for m in range(1, 13)
            ],
            "total_annual_dividend_krw": 40000,
            "monthly_avg_dividend_krw": 3333,
            "portfolio_yield": 5.0,
        }
        evidence = {
            "status": "ok",
            "policy": {},
            "evidence": {
                "005930": {
                    "official_data_available": True,
                    "historical": {},
                    "recent_decision_disclosure": {"receipt_no": "20260926000123"},
                    "structured_decision_disclosure": {
                        "confirmed_amount": True,
                        "structured_verification": True,
                        "ordinary_cash_dps_krw": 1250,
                        "payment_date": "2026-11-20",
                        "future_payment": True,
                    },
                }
            },
        }
        with patch.object(
            official,
            "get_official_dividend_evidence",
            new=AsyncMock(return_value=evidence),
        ):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10, "current_price": 80000}],
                as_of=date(2026, 9, 26),
            )
        row = result["holding_dividends"][0]
        november = result["monthly_schedule"][10]
        self.assertEqual(november["total_krw"], 12500)
        self.assertEqual(row["annual_payout_krw"], 42500)
        self.assertEqual(row["annual_div_per_share"], 4250)
        self.assertEqual(result["total_annual_dividend_krw"], 42500)
        self.assertEqual(row["forecast_source"]["numeric_source"], "opendart_confirmed_disclosure")
        self.assertTrue(row["forecast_source"]["confirmed_amount"])
        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])

    async def test_confirmed_amount_without_payment_date_keeps_numeric_fallback(self):
        summary = {
            "holding_dividends": [{
                "code": "005930", "name": "삼성전자", "quantity": 10,
                "currency": "KRW", "annual_div_per_share": 1500,
                "annual_payout_orig": 15000, "annual_payout_krw": 15000,
                "payout_months": [11],
            }],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 15000,
        }
        evidence = {
            "status": "ok", "policy": {}, "evidence": {"005930": {
                "official_data_available": True,
                "historical": {},
                "structured_decision_disclosure": {
                    "confirmed_amount": True,
                    "structured_verification": True,
                    "ordinary_cash_dps_krw": 1700,
                    "payment_date": None,
                    "future_payment": None,
                },
            }},
        }
        with patch.object(official, "get_official_dividend_evidence", new=AsyncMock(return_value=evidence)):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        source = result["holding_dividends"][0]["forecast_source"]
        self.assertTrue(source["confirmed_amount"])
        self.assertFalse(source["confirmed_numeric_override"])
        self.assertEqual(source["numeric_source"], "naver")
        self.assertEqual(result["total_annual_dividend_krw"], 15000)

    async def test_confirmed_event_can_create_forecast_when_legacy_is_zero(self):
        summary = {
            "holding_dividends": [{
                "code": "005930", "name": "삼성전자", "quantity": 10,
                "currency": "KRW", "annual_div_per_share": 0,
                "annual_payout_orig": 0, "annual_payout_krw": 0,
                "payout_months": [],
            }],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 0,
        }
        evidence = {
            "status": "ok", "policy": {}, "evidence": {"005930": {
                "official_data_available": True,
                "historical": {},
                "structured_decision_disclosure": {
                    "confirmed_amount": True,
                    "structured_verification": True,
                    "ordinary_cash_dps_krw": 600,
                    "payment_date": "2026-12-20",
                    "future_payment": True,
                },
            }},
        }
        with patch.object(official, "get_official_dividend_evidence", new=AsyncMock(return_value=evidence)):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_payout_krw"], 6000)
        self.assertEqual(result["monthly_schedule"][11]["total_krw"], 6000)
        self.assertEqual(row["payout_months"], [12])
        self.assertEqual(result["dividend_paying_count"], 1)
        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])

    def test_latest_correction_filing_wins(self):
        selected = official._latest_dividend_decision([
            {
                "report_nm": "현금ㆍ현물배당 결정",
                "rcept_no": "20260313000100",
                "rcept_dt": "20260313",
            },
            {
                "report_nm": "[정정]현금ㆍ현물배당 결정",
                "rcept_no": "20260420000276",
                "rcept_dt": "20260420",
            },
        ])
        self.assertIsNotNone(selected)
        self.assertEqual(selected["receipt_no"], "20260420000276")
        self.assertFalse(selected["confirmed_amount"])


if __name__ == "__main__":
    unittest.main()
