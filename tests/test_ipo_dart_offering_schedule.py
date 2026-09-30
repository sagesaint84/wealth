from __future__ import annotations

import unittest

from app.services.ipo.dart_offering_schedule import (
    build_dart_offering_schedule,
    parse_dart_date_range,
)


class IpoDartOfferingScheduleTests(unittest.TestCase):
    def test_parse_dot_range_with_inherited_year(self):
        self.assertEqual(
            parse_dart_date_range("2026.10.01 ~ 10.02"),
            ("2026-10-01", "2026-10-02"),
        )

    def test_parse_korean_range_with_day_only_end(self):
        self.assertEqual(
            parse_dart_date_range("2026년 10월 1일 ~ 2일"),
            ("2026-10-01", "2026-10-02"),
        )

    def test_invalid_calendar_date_is_rejected(self):
        self.assertEqual(parse_dart_date_range("2026.02.30 ~ 03.01"), (None, None))

    def test_build_schedule_from_selected_estkrs_receipt(self):
        filing = {
            "corp_code": "01000001",
            "corp_name": "진코스텍",
            "stock_code": "999999",
            "rcept_no": "20260930000123",
            "rcept_dt": "20260930",
            "report_nm": "[발행조건확정]증권신고서(지분증권)",
        }
        structured = {
            "group": [
                {
                    "title": "일반사항",
                    "list": [
                        {
                            "rcept_no": "20260930000123",
                            "corp_code": "01000001",
                            "corp_name": "진코스텍",
                            "corp_cls": "K",
                            "sbd": "2026.10.02 ~ 10.06",
                            "pymd": "2026.10.08",
                            "sband": "홈페이지 공고",
                            "asand": "주간사 홈페이지",
                        }
                    ],
                },
                {
                    "title": "인수인에 관한 사항",
                    "list": [
                        {"rcept_no": "20260930000123", "actnmn": "하나증권"},
                    ],
                },
                {
                    "title": "증권의 종류",
                    "list": [
                        {"rcept_no": "20260930000123", "slprc": "23,500"},
                    ],
                },
            ]
        }

        item = build_dart_offering_schedule(structured, filing=filing)
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["company_name"], "진코스텍")
        self.assertEqual(item["corp_code"], "01000001")
        self.assertEqual(item["stock_code"], "999999")
        self.assertEqual(item["subscription_start"], "2026-10-02")
        self.assertEqual(item["subscription_end"], "2026-10-06")
        self.assertEqual(item["payment_date"], "2026-10-08")
        self.assertEqual(item["lead_managers"], ["하나증권"])
        self.assertEqual(item["final_offer_price"], 23500.0)
        source = item["sources"]["dart_schedule"]
        self.assertEqual(source["rcept_no"], "20260930000123")
        self.assertEqual(source["board_reference"], "https://dart.fss.or.kr/dsac005/main.do")


if __name__ == "__main__":
    unittest.main()
