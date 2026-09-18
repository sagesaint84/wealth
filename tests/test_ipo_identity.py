import unittest

from app.services.ipo.identity import find_matching_ipo, generate_ipo_id, normalize_company_name


class IpoIdentityTests(unittest.TestCase):
    def test_normalize_company_name(self):
        self.assertEqual(normalize_company_name("(주)에이비씨"), "에이비씨")
        self.assertEqual(normalize_company_name("에이비씨 (주)"), "에이비씨")
        self.assertEqual(normalize_company_name("(유)케이비알"), "케이비알")
        self.assertEqual(normalize_company_name("에이 비 씨"), "에이비씨")

    def test_generate_ipo_id_deterministic(self):
        id1 = generate_ipo_id("테스트기업", stock_code="123450")
        id2 = generate_ipo_id("테스트기업", stock_code="123450")
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("ipo_"))

        id3 = generate_ipo_id("다른기업", stock_code="999990")
        self.assertNotEqual(id1, id3)

    def test_match_priority_1_stock_code_exact(self):
        existing = [
            {"ipo_id": "ipo_1", "company_name": "구이름기업", "stock_code": "100200", "corp_code": "00111111"},
            {"ipo_id": "ipo_2", "company_name": "기타기업", "stock_code": "300400", "corp_code": "00222222"},
        ]
        # Incoming has different company name but identical stock_code -> Match!
        incoming = {"company_name": "신규사명기업", "stock_code": "100200"}
        matched, review_req = find_matching_ipo(incoming, existing)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["ipo_id"], "ipo_1")
        self.assertFalse(review_req)

    def test_match_priority_2_corp_code_exact(self):
        existing = [
            {"ipo_id": "ipo_1", "company_name": "알파기업", "stock_code": None, "corp_code": "00555555"},
        ]
        incoming = {"company_name": "알파기업_변경", "stock_code": None, "corp_code": "00555555"}
        matched, review_req = find_matching_ipo(incoming, existing)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["ipo_id"], "ipo_1")
        self.assertFalse(review_req)

    def test_match_priority_3_kind_bz_procs_no_exact(self):
        existing = [
            {"ipo_id": "ipo_1", "company_name": "베타기업", "sources": {"kind_bz_procs_no": "20260901001"}},
        ]
        incoming = {"company_name": "베타", "kind_bz_procs_no": "20260901001"}
        matched, review_req = find_matching_ipo(incoming, existing)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["ipo_id"], "ipo_1")
        self.assertFalse(review_req)

    def test_match_priority_4_corp_code_and_offering_period(self):
        existing = [
            {"ipo_id": "ipo_1", "company_name": "감마기업", "corp_code": "00777777", "subscription_start": "2026-09-15"},
        ]
        incoming = {"company_name": "감마홀딩스", "corp_code": "00777777", "subscription_start": "2026-09-15"}
        matched, review_req = find_matching_ipo(incoming, existing)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["ipo_id"], "ipo_1")
        self.assertFalse(review_req)

    def test_match_priority_5_company_name_only_forbids_auto_merge(self):
        existing = [
            {"ipo_id": "ipo_1", "company_name": "동일사명", "stock_code": "111111", "corp_code": "00111111"},
        ]
        # Same company name but incoming lacks identifier or has differing id -> MUST NOT auto-merge
        incoming = {"company_name": "동일사명", "stock_code": None, "corp_code": None}
        matched, review_req = find_matching_ipo(incoming, existing)
        self.assertIsNone(matched)
        self.assertTrue(review_req)

    def test_no_match(self):
        existing = [
            {"ipo_id": "ipo_1", "company_name": "기존기업", "stock_code": "111111", "corp_code": "00111111"},
        ]
        incoming = {"company_name": "완전신규기업", "stock_code": "999999", "corp_code": "00999999"}
        matched, review_req = find_matching_ipo(incoming, existing)
        self.assertIsNone(matched)
        self.assertFalse(review_req)


if __name__ == "__main__":
    unittest.main()
