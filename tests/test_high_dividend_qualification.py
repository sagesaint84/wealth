from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from app.services.high_dividend_qualification import (
    KIND_HIGH_DIVIDEND_URL,
    enrich_dividend_intelligence_with_high_dividend_qualification,
    parse_high_dividend_valueup_document,
)


class HighDividendQualificationParserTests(unittest.TestCase):
    def test_parses_explicit_official_qualified_field(self) -> None:
        result = parse_high_dividend_valueup_document(
            """
            기업가치 제고 계획(자율공시)
            3. 조세특례제한법 제104조의27에 따른 고배당기업 여부 | 해당
            직전 사업연도 (2025) 배당성향(%) | 25.1
            4. 결정일자 | 2026-03-18
            """,
            report_name="기업가치제고계획(자율공시)",
            receipt_no="20260318000001",
            receipt_date="20260319",
            viewer_url="https://dart.fss.or.kr/example",
        )
        self.assertTrue(result["structured_verification"])
        self.assertEqual(result["qualification_status"], "official_qualified")
        self.assertEqual(result["qualification_value"], "해당")
        self.assertEqual(result["business_year"], 2025)
        self.assertEqual(result["decision_date"], "2026-03-18")

    def test_parses_explicit_official_not_qualified_field(self) -> None:
        result = parse_high_dividend_valueup_document(
            "조세특례제한법 제104조의27에 따른 고배당기업 여부 : 미해당"
        )
        self.assertTrue(result["structured_verification"])
        self.assertEqual(result["qualification_status"], "official_not_qualified")

    def test_narrative_word_does_not_promote_status(self) -> None:
        result = parse_high_dividend_valueup_document(
            "기업가치 제고 계획이며 향후 요건에 해당할 수 있습니다. 고배당기업 관련 검토 중"
        )
        self.assertFalse(result["structured_verification"])
        self.assertEqual(result["qualification_status"], "not_confirmed")


class HighDividendQualificationEnrichmentTests(unittest.IsolatedAsyncioTestCase):
    def _summary(self) -> dict:
        return {
            "total_annual_dividend_krw": 1_000_000,
            "portfolio_after_tax": {"gross_annual_dividend_krw": 1_000_000},
            "dividend_intelligence": {
                "contracts": {},
                "instruments": [
                    {
                        "code": "005930",
                        "name": "삼성전자",
                        "currency": "KRW",
                        "tax_engine_asset_type": "domestic_dividend_stock",
                        "gross_annual_dividend_krw": 600_000,
                    },
                    {
                        "code": "000660",
                        "name": "SK하이닉스",
                        "currency": "KRW",
                        "tax_engine_asset_type": "domestic_dividend_stock",
                        "gross_annual_dividend_krw": 300_000,
                    },
                    {
                        "code": "QQQM",
                        "name": "QQQM",
                        "currency": "USD",
                        "tax_engine_asset_type": "us_direct",
                        "gross_annual_dividend_krw": 100_000,
                    },
                ],
            },
        }

    @patch("app.services.high_dividend_qualification.external_network_allowed", return_value=True)
    @patch("app.services.high_dividend_qualification.DartClient")
    @patch("app.services.high_dividend_qualification._load_corp_code_map", new_callable=AsyncMock)
    @patch("app.services.high_dividend_qualification._fetch_company_status", new_callable=AsyncMock)
    async def test_attaches_qualified_and_not_confirmed_without_inference(
        self, fetch_status, load_map, dart_cls, _network
    ) -> None:
        dart_cls.return_value.api_key = "key"
        dart_cls.return_value.credential_source = "user"
        load_map.return_value = {"005930": "00126380", "000660": "00164779"}
        fetch_status.side_effect = [
            {
                "status": "official_qualified",
                "evidence": {
                    "receipt_no": "20260318000001",
                    "viewer_url": "https://dart.fss.or.kr/qualified",
                    "business_year": 2025,
                },
            },
            {"status": "not_confirmed", "reason": "valueup_filing_not_found"},
        ]
        summary = self._summary()
        result = await enrich_dividend_intelligence_with_high_dividend_qualification(
            summary, [], username="tester", as_of=date(2026, 9, 28)
        )
        intelligence = result["dividend_intelligence"]
        rows = {row["code"]: row for row in intelligence["instruments"]}
        self.assertEqual(
            rows["005930"]["high_dividend_qualification"]["status"],
            "official_qualified",
        )
        self.assertEqual(
            rows["000660"]["high_dividend_qualification"]["status"],
            "not_confirmed",
        )
        self.assertEqual(
            rows["QQQM"]["high_dividend_qualification"]["status"],
            "not_applicable",
        )
        high = intelligence["high_dividend"]
        self.assertEqual(high["official_qualified_count"], 1)
        self.assertEqual(high["not_confirmed_count"], 1)
        self.assertEqual(high["qualified_projected_gross_krw"], 600_000)
        self.assertEqual(high["qualified_projected_gross_share_pct"], 60.0)
        self.assertFalse(high["absence_means_unqualified"])
        self.assertFalse(high["wealth_inferred"])
        self.assertEqual(high["kind_reference_url"], KIND_HIGH_DIVIDEND_URL)
        self.assertFalse(high["tax_special_treatment_automatically_applied"])

    @patch("app.services.high_dividend_qualification.external_network_allowed", return_value=False)
    @patch("app.services.high_dividend_qualification.DartClient")
    async def test_network_failure_is_source_unavailable(self, dart_cls, _network) -> None:
        dart_cls.return_value.api_key = "key"
        dart_cls.return_value.credential_source = "user"
        summary = self._summary()
        result = await enrich_dividend_intelligence_with_high_dividend_qualification(
            summary, [], username="tester", as_of=date(2026, 9, 28)
        )
        rows = result["dividend_intelligence"]["instruments"]
        domestic = [row for row in rows if row["currency"] == "KRW"]
        self.assertTrue(
            all(
                row["high_dividend_qualification"]["status"] == "source_unavailable"
                for row in domestic
            )
        )
        self.assertEqual(
            result["dividend_intelligence"]["high_dividend"]["source_status"],
            "network_disabled",
        )


if __name__ == "__main__":
    unittest.main()
