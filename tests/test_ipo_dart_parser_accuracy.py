import unittest

from app.services.ipo.dart_parser import DartSemanticParser


MELCON_DEMAND_TABLES = """
<table>
  <tr><th>구분</th><th>국내 기관투자자</th><th>외국 기관투자자</th><th>합계</th></tr>
  <tr><th>건수</th><td>991</td><td>212</td><td>296</td><td>27</td><td>7</td><td>588</td><td>178</td><td>3</td><td>103</td><td>2,405</td></tr>
  <tr><th>수량</th><td>831,412,000</td><td>203,919,000</td><td>194,588,000</td><td>49,250,000</td><td>12,775,000</td><td>419,785,000</td><td>248,070,000</td><td>2,706,000</td><td>112,237,000</td><td>2,074,742,000</td></tr>
  <tr><th>경쟁률</th><td>455.57</td><td>111.74</td><td>106.62</td><td>26.99</td><td>7.00</td><td>230.02</td><td>135.93</td><td>1.48</td><td>61.50</td><td>1,136.84</td></tr>
</table>

<table>
  <tr><th>구분</th><th>국내 기관투자자</th></tr>
  <tr><th>건수</th><th>수량</th><th>신청가격</th></tr>
  <tr><td>6개월 확약</td><td>20</td><td>18,655,000</td><td>12,300</td></tr>
  <tr><td>합계</td><td>991</td><td>831,412,000</td><td>12,334</td></tr>
</table>

<table>
  <tr><th>구분</th><th>외국 기관투자자(거래실적 유)</th><th>외국 기관투자자(거래실적 무)</th><th>합계</th></tr>
  <tr><th>건수</th><th>수량</th><th>신청가격</th><th>건수</th><th>수량</th><th>신청가격</th><th>건수</th><th>수량</th><th>신청가격</th></tr>
  <tr><td>6개월 확약</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>51</td><td>44,996,000</td><td>12,300</td></tr>
  <tr><td>3개월 확약</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>92</td><td>89,848,000</td><td>12,375</td></tr>
  <tr><td>1개월 확약</td><td>-</td><td>-</td><td>-</td><td>12</td><td>21,900,000</td><td>12,300</td><td>143</td><td>138,080,000</td><td>12,308</td></tr>
  <tr><td>15일 확약</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>511</td><td>475,465,000</td><td>12,301</td></tr>
  <tr><td>미확약</td><td>3</td><td>2,706,000</td><td>12,300</td><td>91</td><td>90,337,000</td><td>12,300</td><td>1,608</td><td>1,326,353,000</td><td>12,341</td></tr>
  <tr><td>합 계</td><td>3</td><td>2,706,000</td><td>12,300</td><td>103</td><td>112,237,000</td><td>12,300</td><td>2,405</td><td>2,074,742,000</td><td>12,331</td></tr>
</table>

<p>(나) 수요예측 신청가격 분포</p>
<table>
  <tr><th>구분</th><th>참여건수 기준</th><th>신청수량 기준</th></tr>
  <tr><th>참여건수(건)</th><th>비율</th><th>신청수량(주)</th><th>비율</th></tr>
  <tr><td>가격 미제시</td><td>7</td><td>0.29%</td><td>9,388,000</td><td>0.45%</td></tr>
  <tr><td>12,300원(상단) 초과</td><td>36</td><td>1.50%</td><td>36,252,000</td><td>1.75%</td></tr>
  <tr><td>12,300원(상단)</td><td>2,359</td><td>98.09%</td><td>2,026,760,000</td><td>97.69%</td></tr>
  <tr><td>10,700원(하단)</td><td>3</td><td>0.12%</td><td>2,342,000</td><td>0.11%</td></tr>
  <tr><td>합계</td><td>2,405</td><td>100.00%</td><td>2,074,742,000</td><td>100.00%</td></tr>
</table>
"""


class DartParserAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.parser = DartSemanticParser()

    def test_competition_ratio_uses_rightmost_total(self):
        self.assertEqual(self.parser.extract_competition_ratio(MELCON_DEMAND_TABLES), 1136.84)

    def test_lockup_ratio_uses_complete_total_table(self):
        self.assertEqual(self.parser.extract_lockup_commitment_ratio(MELCON_DEMAND_TABLES), 36.07)

    def test_partial_multigroup_lockup_table_is_not_promoted(self):
        partial = """
        <table>
          <tr><th>구분</th><th>국내 기관투자자</th></tr>
          <tr><th>건수</th><th>수량</th><th>신청가격</th></tr>
          <tr><td>6개월 확약</td><td>20</td><td>18,655,000</td><td>12,300</td></tr>
          <tr><td>합계</td><td>991</td><td>831,412,000</td><td>12,334</td></tr>
        </table>
        """
        self.assertIsNone(self.parser.extract_lockup_commitment_ratio(partial))

    def test_high_bid_ratio_handles_heading_outside_table(self):
        self.assertEqual(self.parser.extract_high_bid_ratio(MELCON_DEMAND_TABLES), 99.89)

    def test_relative_valuation_uses_semantic_table_cells(self):
        doc = """
        <table>
          <tr><td>평가방법</td><td>상대가치법</td></tr>
          <tr><td>평가모형</td><td>PER</td></tr>
          <tr><td>적용근거</td><td>구 분</td><td>수 치</td><td>참고 사항</td></tr>
          <tr><td>②</td><td>비교대상회사 PER</td><td>26.18 배</td><td>1. 공모가격에 대한 의견</td></tr>
          <tr><td>주당 평가가액</td><td>14,173 원</td><td>① x ② ÷③</td></tr>
          <tr><td>공모가 산정 결과</td><td>12,300 원</td><td>수요예측 이후 확정</td></tr>
        </table>
        <table>
          <tr><td>주당 확정공모가액</td><td>12,300 원</td></tr>
        </table>
        <p>(주4) 정정 전</p>
        <table>
          <tr><td>평가모형</td><td>PER</td></tr>
          <tr><td>②</td><td>비교대상회사 PER</td><td>1.00 배</td></tr>
          <tr><td>주당 평가가액</td><td>15,580 원</td></tr>
          <tr><td>공모가 산정 결과</td><td>12,300 원</td></tr>
        </table>
        """
        value = self.parser.extract_relative_valuation(doc)
        self.assertEqual(value["valuation_method"], "PER")
        self.assertEqual(value["peer_median_multiple"], 26.18)
        self.assertEqual(value["issuer_multiple"], 22.72)
        self.assertEqual(value["valuation_ratio"], 0.8678)

    def test_tradable_ratio_reads_explicit_prose_and_avoids_stale_amendment(self):
        doc = """
        <table><tr><td>
          당사의 상장예정주식수 12,575,000주 중 34.57%에 해당하는
          4,346,680주는 상장 직후 유통가능 물량에 해당합니다.
          3개월 후 누적 35.16%, 12개월 후 누적 36.55%입니다.
        </td></tr></table>
        <p>(주4) 정정 전</p>
        <table><tr><td>
          당사의 상장예정주식수 12,575,000주 중 34.13%에 해당하는
          4,291,000주는 상장 직후 유통가능 물량에 해당합니다.
        </td></tr></table>
        """
        self.assertEqual(self.parser.extract_tradable_share_ratio(doc), 34.57)


if __name__ == "__main__":
    unittest.main()
