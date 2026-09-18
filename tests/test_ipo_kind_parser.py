import unittest

from app.services.ipo.kind_client import parse_kind_html, KindParserError, parse_schedule_range


SAMPLE_KIND_HTML = """
<html>
<body>
<table class="list type_001" summary="공모진행일정 목록">
  <thead>
    <tr>
      <th scope="col">회사명</th>
      <th scope="col">증권구분</th>
      <th scope="col">수요예측일</th>
      <th scope="col">청약일</th>
      <th scope="col">납입일</th>
      <th scope="col">공모가(원)</th>
      <th scope="col">공모금액(백만원)</th>
      <th scope="col">상장예정일</th>
      <th scope="col">대표주관사</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="#view" onclick="fnOpen('20260901001');">메쥬</a></td>
      <td>주권(코스닥)</td>
      <td>2026.09.04 ~ 2026.09.10</td>
      <td>2026.09.17 ~ 2026.09.18</td>
      <td>2026.09.22</td>
      <td>21,600</td>
      <td>35,000</td>
      <td>2026.09.30</td>
      <td>신한투자증권</td>
    </tr>
    <tr>
      <td>알파로보틱스</td>
      <td>주권(유가증권)</td>
      <td>2026.09.08 ~ 2026.09.14</td>
      <td>2026.09.23 ~ 2026.09.24</td>
      <td>2026.09.26</td>
      <td>15,000</td>
      <td>20,000</td>
      <td>2026.10.05</td>
      <td>KB증권</td>
    </tr>
  </tbody>
</table>
</body>
</html>
"""

SAMPLE_EMPTY_KIND_HTML = """
<html>
<body>
<div class="no_data">
  <p>조회된 내역이 없습니다.</p>
</div>
</body>
</html>
"""



LIVE_STYLE_KIND_HTML = """
<section id="section-talbe" class="scrarea type-00">
<table class="list type-00 tmt30" summary="회사명, 신고서제출일, 수요예측일정, 청약일정, 납입일, 확정곰모가, 공모금액(백만원), 상장예정일, 상장주선인/지정자문인">
<thead><tr class="first" id="title-contents"></tr></thead>
<tbody>
<tr>
<td><a onclick="fnOpen('20260901001');">브릴스</a></td>
<td>2026.08.01</td>
<td>2026.09.10 ~ 2026.09.11</td>
<td>2026.09.17 ~ 2026.09.18</td>
<td>2026.09.22</td>
<td>19,500</td>
<td>39,000</td>
<td>2026.09.30</td>
<td>아이비케이투자증권</td>
</tr>
</tbody>
</table>
</section>
<script>fn_InitTitle("회사명,신고서제출일,수요예측일정,청약일정,납입일,확정공모가,공모금액<br/>(백만원),상장예정일,상장주선인/<br/>지정자문인", "true,true,false,false,false,false,false,true,false");</script>
"""

LIVE_STYLE_EMPTY_KIND_HTML = """
<section><table class="list type-00 tmt30" summary="회사명, 신고서제출일, 수요예측일정, 청약일정, 납입일, 확정곰모가, 공모금액(백만원), 상장예정일, 상장주선인/지정자문인">
<thead><tr class="first" id="title-contents"></tr></thead>
<tbody><tr class="first"><td class="first null" colspan="9">조회된 결과값이 없습니다.</td></tr></tbody>
</table></section>
"""

SAMPLE_MALFORMED_KIND_HTML = """
<html>
<body>
<table class="broken_table">
  <tr>
    <td>엉뚱한내용1</td>
    <td>엉뚱한내용2</td>
  </tr>
</table>
</body>
</html>
"""


class KindParserTests(unittest.TestCase):
    def test_parse_live_contract_with_empty_thead_and_js_titles(self):
        items = parse_kind_html(LIVE_STYLE_KIND_HTML)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["company_name"], "브릴스")
        self.assertEqual(item["filing_date"], "2026-08-01")
        self.assertEqual(item["subscription_start"], "2026-09-17")
        self.assertEqual(item["subscription_end"], "2026-09-18")
        self.assertEqual(item["final_offer_price"], 19500.0)
        self.assertEqual(item["expected_listing_date"], "2026-09-30")
        self.assertEqual(item["lead_managers"], ["아이비케이투자증권"])

    def test_live_empty_result_phrase_is_authoritative_empty(self):
        self.assertEqual(parse_kind_html(LIVE_STYLE_EMPTY_KIND_HTML), [])

    def test_parse_valid_kind_html(self):
        items = parse_kind_html(SAMPLE_KIND_HTML)
        self.assertEqual(len(items), 2)

        meju = items[0]
        self.assertEqual(meju["company_name"], "메쥬")
        self.assertEqual(meju["demand_forecast_start"], "2026-09-04")
        self.assertEqual(meju["demand_forecast_end"], "2026-09-10")
        self.assertEqual(meju["subscription_start"], "2026-09-17")
        self.assertEqual(meju["subscription_end"], "2026-09-18")
        self.assertEqual(meju["payment_date"], "2026-09-22")
        self.assertEqual(meju["final_offer_price"], 21600.0)
        self.assertEqual(meju["offering_amount_million_krw"], 35000.0)
        self.assertEqual(meju["expected_listing_date"], "2026-09-30")
        self.assertEqual(meju["lead_manager"], "신한투자증권")
        self.assertEqual(meju["kind_bz_procs_no"], "20260901001")

        alpha = items[1]
        self.assertEqual(alpha["company_name"], "알파로보틱스")
        self.assertEqual(alpha["subscription_start"], "2026-09-23")
        self.assertEqual(alpha["lead_manager"], "KB증권")

    def test_parse_empty_kind_html(self):
        items = parse_kind_html(SAMPLE_EMPTY_KIND_HTML)
        self.assertEqual(items, [])

    def test_parse_malformed_kind_html_fail_closed(self):
        with self.assertRaises(KindParserError):
            parse_kind_html(SAMPLE_MALFORMED_KIND_HTML)

    def test_parse_schedule_range(self):
        s1, e1 = parse_schedule_range("2026.09.17 ~ 2026.09.18")
        self.assertEqual(s1, "2026-09-17")
        self.assertEqual(e1, "2026-09-18")

        s2, e2 = parse_schedule_range("2026/09/22")
        self.assertEqual(s2, "2026-09-22")
        self.assertEqual(e2, "2026-09-22")


if __name__ == "__main__":
    unittest.main()
