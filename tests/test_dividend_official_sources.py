from __future__ import annotations

from datetime import date
import io
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

from app.services import dividend_official_sources as official


class DividendOfficialSourcesTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_corp_code_zip_maps_listed_stock_codes(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<result>
  <list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name><stock_code>005930</stock_code></list>
  <list><corp_code>00000001</corp_code><corp_name>Unlisted</corp_name><stock_code></stock_code></list>
</result>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("CORPCODE.xml", xml)
        self.assertEqual(
            official._parse_corp_code_zip(buf.getvalue()),
            {"005930": "00126380"},
        )

    def test_extracts_ordinary_share_cash_dps(self):
        rows = [
            {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "1,444"},
            {"se": "주당 현금배당금(원)", "stock_knd": "우선주", "thstrm": "1,445"},
            {"se": "현금배당수익률(%)", "stock_knd": "보통주", "thstrm": "2.3"},
        ]
        self.assertEqual(official._extract_ordinary_cash_dps(rows), 1444.0)

    def test_decision_title_never_confirms_amount(self):
        result = official._latest_dividend_decision(
            [
                {
                    "report_nm": "현금ㆍ현물배당 결정",
                    "rcept_no": "20260319000123",
                    "rcept_dt": "20260319",
                }
            ]
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["confirmed_amount"])
        self.assertIn("20260319000123", result["viewer_url"])

    async def test_missing_api_key_fails_open(self):
        with patch.object(official, "external_network_allowed", return_value=True):
            result = await official.get_official_dividend_evidence(
                [{"code": "005930", "currency": "KRW"}],
                api_key="",
                as_of=date(2026, 9, 26),
            )
        self.assertEqual(result["status"], "missing_api_key")
        self.assertEqual(result["evidence"], {})
        self.assertFalse(result["policy"]["opendart_configured"])

    async def test_network_disabled_fails_open(self):
        with patch.object(official, "external_network_allowed", return_value=False):
            result = await official.get_official_dividend_evidence(
                [{"code": "005930", "currency": "KRW"}],
                api_key="test-key",
                as_of=date(2026, 9, 26),
            )
        self.assertEqual(result["status"], "network_disabled")
        self.assertEqual(result["evidence"], {})

    async def test_official_historical_dps_fills_only_missing_legacy_value(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 10,
                    "currency": "KRW",
                    "annual_div_per_share": 0,
                    "div_yield": 0,
                    "annual_payout_krw": 0,
                    "annual_payout_orig": 0,
                    "payout_months": [4],
                }
            ],
            "monthly_schedule": [],
        }
        holdings = [
            {
                "code": "005930",
                "name": "삼성전자",
                "quantity": 10,
                "currency": "KRW",
                "current_price": 70_000,
            }
        ]
        evidence = {
            "status": "ok",
            "policy": {"opendart_configured": True},
            "evidence": {
                "005930": {
                    "official_data_available": True,
                    "historical": {
                        "ordinary_cash_dps_krw": 1_444,
                        "business_year": 2025,
                    },
                    "recent_decision_disclosure": None,
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
                holdings,
                fx_rate=1_400,
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_div_per_share"], 1_444)
        self.assertEqual(row["annual_payout_krw"], 14_440)
        self.assertEqual(row["forecast_source"]["numeric_source"], "opendart_historical_fill")
        self.assertFalse(row["forecast_source"]["confirmed_amount"])
        self.assertEqual(result["total_annual_dividend_krw"], 14_440)
        self.assertEqual(result["monthly_schedule"][3]["total_krw"], 14_440)

    async def test_official_history_does_not_override_nonzero_naver_forecast(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 10,
                    "currency": "KRW",
                    "annual_div_per_share": 1_500,
                    "div_yield": 2.0,
                    "annual_payout_krw": 15_000,
                    "annual_payout_orig": 15_000,
                    "payout_months": [4],
                }
            ],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 15_000,
        }
        evidence = {
            "status": "ok",
            "policy": {},
            "evidence": {
                "005930": {
                    "official_data_available": True,
                    "historical": {
                        "ordinary_cash_dps_krw": 1_444,
                        "business_year": 2025,
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
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_div_per_share"], 1_500)
        self.assertEqual(row["forecast_source"]["numeric_source"], "naver")
        self.assertEqual(
            row["forecast_source"]["official_historical_annual_div_per_share_krw"],
            1_444,
        )

    async def test_us_holding_remains_yahoo_history(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "SCHD",
                    "name": "SCHD",
                    "quantity": 10,
                    "currency": "USD",
                    "annual_div_per_share": 2.5,
                    "payout_months": [3, 6, 9, 12],
                }
            ]
        }
        with patch.object(
            official,
            "get_official_dividend_evidence",
            new=AsyncMock(return_value={"status": "no_domestic_holdings", "policy": {}, "evidence": {}}),
        ):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "SCHD", "currency": "USD", "quantity": 10}],
            )
        self.assertEqual(
            result["holding_dividends"][0]["forecast_source"]["numeric_source"],
            "yahoo_history",
        )


if __name__ == "__main__":
    unittest.main()
