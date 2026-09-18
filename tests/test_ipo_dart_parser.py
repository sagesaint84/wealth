import unittest

from app.services.ipo.dart_parser import DartSemanticParser


SAMPLE_DART_DOC = """
<html>
<body>
<h2>1. 수요예측 결과</h2>
<p>기관투자자 경쟁률: 854.2 : 1</p>

<table>
  <caption>수요예측 신청가격 분포</caption>
  <thead>
    <tr><th>구분</th><th>신청건수</th><th>신청수량</th><th>비율</th></tr>
  </thead>
  <tbody>
    <tr><td>밴드상단초과</td><td>1,200</td><td>45,000,000</td><td>90.0%</td></tr>
    <tr><td>밴드상단</td><td>100</td><td>4,000,000</td><td>8.0%</td></tr>
    <tr><td>밴드하단</td><td>10</td><td>1,000,000</td><td>2.0%</td></tr>
    <tr><td>가격미제시</td><td>5</td><td>500,000</td><td>1.0%</td></tr>
    <tr><td>합계</td><td>1,315</td><td>50,500,000</td><td>100.0%</td></tr>
  </tbody>
</table>

<table>
  <caption>의무보유확약 신청현황</caption>
  <thead>
    <tr><th>확약기간</th><th>신청건수</th><th>신청수량</th></tr>
  </thead>
  <tbody>
    <tr><td>6개월</td><td>150</td><td>10,000,000</td></tr>
    <tr><td>3개월</td><td>100</td><td>8,000,000</td></tr>
    <tr><td>1개월</td><td>50</td><td>2,000,000</td></tr>
    <tr><td>미확약</td><td>1,015</td><td>30,500,000</td></tr>
    <tr><td>합계</td><td>1,315</td><td>50,500,000</td></tr>
  </tbody>
</table>

<h2>2. 유통가능물량</h2>
<p>상장 직후 유통가능 물량은 2,500,000주로 전체 발행주식총수의 25.0%입니다.</p>

<h2>3. 공모 개요</h2>
<p>당사는 이번 공모에서 전량 신주모집(구주매출 없음)으로 진행합니다.</p>

<table>
  <caption>보호예수 및 매각제한 일정</caption>
  <thead><tr><th>구분</th><th>주식수</th><th>해제시기</th></tr></thead>
  <tbody>
    <tr><td>전문투자자</td><td>500,000</td><td>상장 후 1개월</td></tr>
    <tr><td>벤처금융</td><td>300,000</td><td>상장 후 3개월</td></tr>
    <tr><td>합계</td><td>10,000,000</td><td>발행주식총수</td></tr>
  </tbody>
</table>

<h2>4. 인수인의 의견 및 가치평가</h2>
<p>비교기업 PER 배수 산정 결과 유사회사의 평균 PER은 24.5배이며, 당사의 공모가 기준 PER은 19.6배입니다.</p>

<table>
  <caption>요약 재무제표</caption>
  <thead><tr><th>과목</th><th>2025년(제3기)</th><th>2024년(제2기)</th><th>2023년(제1기)</th></tr></thead>
  <tbody>
    <tr><td>매출액</td><td>40,000</td><td>30,000</td><td>20,000</td></tr>
    <tr><td>영업이익</td><td>8,000</td><td>5,000</td><td>2,000</td></tr>
    <tr><td>자산총계</td><td>50,000</td><td>35,000</td><td>25,000</td></tr>
    <tr><td>현금및현금성자산</td><td>10,000</td><td>8,000</td><td>5,000</td></tr>
    <tr><td>단기차입금</td><td>2,000</td><td>1,500</td><td>1,000</td></tr>
  </tbody>
</table>
</body>
</html>
"""


class DartParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = DartSemanticParser()

    def test_parse_competition_ratio(self):
        ratio = self.parser.extract_competition_ratio(SAMPLE_DART_DOC)
        self.assertEqual(ratio, 854.2)

    def test_parse_lockup_commitment_ratio(self):
        # 10M + 8M + 2M = 20M committed out of 50.5M total = ~39.60%
        ratio = self.parser.extract_lockup_commitment_ratio(SAMPLE_DART_DOC)
        self.assertIsNotNone(ratio)
        self.assertAlmostEqual(ratio, 39.6, places=1)

    def test_parse_high_bid_ratio(self):
        # 45M + 4M = 49M at or above band high
        # Specified total = 50.5M - 0.5M = 50M -> 49M / 50M = 98.0%
        ratio = self.parser.extract_high_bid_ratio(SAMPLE_DART_DOC)
        self.assertEqual(ratio, 98.0)

    def test_high_bid_ratio_missing_if_unspecified_over_50_percent(self):
        doc_unspecified_heavy = """
        <table>
          <caption>수요예측 신청가격 분포</caption>
          <tbody>
            <tr><td>밴드상단</td><td>4,000,000</td></tr>
            <tr><td>가격미제시</td><td>6,000,000</td></tr>
            <tr><td>합계</td><td>10,000,000</td></tr>
          </tbody>
        </table>
        """
        # Specified = 4M, which is < 50% of 10M total -> status must be missing
        ratio = self.parser.extract_high_bid_ratio(doc_unspecified_heavy)
        self.assertIsNone(ratio)

    def test_parse_tradable_share_ratio(self):
        ratio = self.parser.extract_tradable_share_ratio(SAMPLE_DART_DOC)
        self.assertEqual(ratio, 25.0)

    def test_parse_secondary_sale_explicit_zero(self):
        # Text says "구주매출 없음"
        ratio = self.parser.extract_secondary_sale_ratio(SAMPLE_DART_DOC)
        self.assertEqual(ratio, 0.0)

    def test_parse_unlock_3m_ratio(self):
        # 500k + 300k = 800k out of 10M total = 8.0%
        ratio = self.parser.extract_unlock_3m_ratio(SAMPLE_DART_DOC)
        self.assertEqual(ratio, 8.0)

    def test_parse_relative_valuation(self):
        val = self.parser.extract_relative_valuation(SAMPLE_DART_DOC)
        self.assertEqual(val["valuation_method"], "PER")
        self.assertEqual(val["peer_median_multiple"], 24.5)
        self.assertEqual(val["issuer_multiple"], 19.6)
        self.assertAlmostEqual(val["valuation_ratio"], 0.8, places=2)

    def test_parse_financials(self):
        fin = self.parser.extract_financial_ratios(SAMPLE_DART_DOC)
        # Revenue CAGR: 2023: 20,000 -> 2025: 40,000 (2 years) -> (40000/20000)^0.5 - 1 = sqrt(2) - 1 = 41.42%
        self.assertAlmostEqual(fin["revenue_cagr"], 41.42, places=1)

        # Operating margin: 8,000 / 40,000 = 20.0%
        self.assertEqual(fin["operating_margin"], 20.0)

        # Net debt to assets: (2,000 - 10,000) / 50,000 = -8,000 / 50,000 = -16.0%
        self.assertEqual(fin["net_debt_to_assets"], -16.0)

    def test_full_document_provenance_structure(self):
        feats = self.parser.parse_document(SAMPLE_DART_DOC, rcept_no="20260901000123", source_date="2026-09-01")
        for feat_name, item in feats.items():
            self.assertIn("status", item)
            self.assertIn("source", item)
            self.assertEqual(item["source"], "dart_document")
            self.assertEqual(item["rcept_no"], "20260901000123")
            self.assertEqual(item["parser_version"], "ipo-dart-v1")


if __name__ == "__main__":
    unittest.main()
