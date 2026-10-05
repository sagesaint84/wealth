import unittest

from app.services.ipo.dart_parser import DartSemanticParser
from app.services.ipo.store import merge_ipo_record


class DartRealLayoutRegressionTests(unittest.TestCase):
    def setUp(self):
        self.parser = DartSemanticParser()

    def test_wide_competition_table_uses_total_column(self):
        doc = """
        <table>
          <tr>
            <th>구분</th><th>A</th><th>B</th><th>C</th><th>D</th>
            <th>E</th><th>F</th><th>G</th><th>H</th><th>I</th><th>합계</th>
          </tr>
          <tr>
            <td>신청수량</td>
            <td>12,585,000</td><td>245,921,000</td><td>68,297,000</td>
            <td>14,167,000</td><td>21,494,000</td><td>266,244,000</td>
            <td>54,503,000</td><td>18,169,000</td><td>0</td>
            <td>701,380,000</td>
          </tr>
          <tr>
            <td>경쟁률(주2)</td>
            <td>19.69</td><td>384.85</td><td>106.88</td><td>22.17</td>
            <td>33.64</td><td>416.66</td><td>85.29</td><td>28.43</td>
            <td>0.00</td><td>1,097.62</td>
          </tr>
        </table>
        """

        self.assertEqual(
            self.parser.extract_competition_ratio(doc),
            1097.62,
        )

    def test_implausible_competition_ratio_is_rejected(self):
        doc = "<p>수요예측 기관투자자 경쟁률 596400639000 : 1</p>"

        self.assertIsNone(
            self.parser.extract_competition_ratio(doc)
        )

    def test_wide_lockup_table_uses_total_minus_uncommitted(self):
        doc = """
        <table>
          <caption>의무보유확약 신청내역</caption>
          <tr>
            <th>구분</th><th>건수</th><th>신청수량</th><th>평균가격</th>
          </tr>
          <tr>
            <td>15일 확약</td>
            <td>25</td><td>8,865,000</td><td>23,520</td>
          </tr>
          <tr>
            <td>미확약</td>
            <td>1,916</td><td>664,290,000</td><td>22,645</td>
          </tr>
          <tr>
            <td>계</td>
            <td>2,006</td><td>701,380,000</td><td>22,700</td>
          </tr>
        </table>
        """

        self.assertEqual(
            self.parser.extract_lockup_commitment_ratio(doc),
            5.29,
        )

    def test_listing_statement_extracts_post_offer_shares(self):
        doc = """
        <p>
          당사의 상장예정주식수 3,786,533주 중
          58.44%에 해당하는 2,212,851주는
          상장 직후 유통가능 물량에 해당합니다.
        </p>
        """

        self.assertEqual(
            self.parser.extract_post_offer_shares(doc),
            3786533,
        )

    def test_listing_statement_rejects_inconsistent_share_ratio(self):
        doc = """
        <p>
          당사의 상장예정주식수 3,786,533주 중
          58.44%에 해당하는 1,000,000주는
          상장 직후 유통가능 물량에 해당합니다.
        </p>
        """

        self.assertIsNone(
            self.parser.extract_post_offer_shares(doc)
        )

    def test_listing_statement_rejects_ratio_outside_rounding_tolerance(self):
        doc = """
        상장예정주식수 1,000,000주 중
        50.04%에 해당하는 500,000주는
        상장 직후 유통가능 물량에 해당합니다.
        """

        self.assertIsNone(self.parser.extract_post_offer_shares(doc))

    def test_listing_statement_rejects_conflicting_valid_totals(self):
        doc = """
        <p>
          상장예정주식수 1,000,000주 중
          50.00%에 해당하는 500,000주는
          상장 직후 유통가능 물량에 해당합니다.
        </p>
        <p>
          상장예정주식수 2,000,000주 중
          50.00%에 해당하는 1,000,000주는
          상장 직후 유통가능 물량에 해당합니다.
        </p>
        """

        self.assertIsNone(
            self.parser.extract_post_offer_shares(doc)
        )

    def test_missing_refresh_does_not_erase_valid_feature(self):
        store = {
            "schema_version": 1,
            "ipos": [
                {
                    "ipo_id": "ipo-test",
                    "company_name": "진코스텍",
                    "stock_code": "250030",
                    "features": {
                        "lockup_commitment_ratio": {
                            "value": 5.29,
                            "status": "ok",
                            "source": "dart_document",
                            "rcept_no": "older",
                        }
                    },
                    "sources": {},
                }
            ],
        }

        incoming = {
            "company_name": "진코스텍",
            "stock_code": "250030",
            "features": {
                "lockup_commitment_ratio": {
                    "value": None,
                    "status": "missing",
                    "source": "dart_document",
                    "rcept_no": "newer",
                }
            },
        }

        merged, review_required = merge_ipo_record(store, incoming)

        self.assertFalse(review_required)

        feature = merged["features"]["lockup_commitment_ratio"]

        self.assertEqual(feature["status"], "ok")
        self.assertEqual(feature["value"], 5.29)


if __name__ == "__main__":
    unittest.main()
