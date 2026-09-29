from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMPORT_JS = ROOT / "app" / "static" / "wealth-accountinfo-import.js"
MONEY_JS = ROOT / "app" / "static" / "wealth-money-input.js"


class AccountInfoPdfImportFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = IMPORT_JS.read_text(encoding="utf-8")
        cls.money_js = MONEY_JS.read_text(encoding="utf-8")

    def test_loader_and_pdf_accept_are_wired_without_replacing_csv_import(self) -> None:
        self.assertIn("/static/wealth-accountinfo-import.js?v=10.6a", self.money_js)
        self.assertIn(".csv,.xlsx,.xlsm,.pdf,application/pdf", self.js)
        self.assertIn("if (!isPdfFile(file)) return;", self.js)
        self.assertIn("event.stopImmediatePropagation()", self.js)

    def test_pdf_is_parsed_in_browser_and_not_uploaded_for_preview(self) -> None:
        self.assertIn("pdfjs.getDocument({ data: bytes })", self.js)
        self.assertIn("PDF 파일 자체는 Wealth 서버나 외부 분석 서비스로 업로드하지 않고 현재 브라우저에서만 읽습니다.", self.js)
        self.assertNotIn("formData.append('file', file)", self.js)

    def test_preview_masks_account_numbers_and_requires_owner(self) -> None:
        self.assertIn("function maskAccountNo", self.js)
        self.assertIn("maskAccountNo(row.account_no)", self.js)
        self.assertIn("PDF에 추가할 계좌의 소유자를 선택해 주세요.", self.js)
        self.assertIn("owner_conflict", self.js)

    def test_accountinfo_row_contract_uses_table_anchor_and_page_continuation(self) -> None:
        self.assertIn("function isRowAnchor", self.js)
        self.assertIn("x > 10 && x < 75", self.js)
        self.assertIn("if (current) rows.push(current)", self.js)
        self.assertIn("조회기준일", self.js)
        self.assertIn("opened_at", self.js)
        self.assertIn("last_transaction_at", self.js)

    def test_brokerage_reported_balance_is_never_imported_as_cash(self) -> None:
        self.assertIn("증권계좌 잔액은 예수금으로 간주하지 않습니다", self.js)
        self.assertIn("const values = [owner,row.institution,accountName,row.account_no,row.suggested_type,0,0,'미적용'", self.js)
        self.assertNotIn("row.reported_balance_krw,row.reported_balance_krw", self.js)

    def test_bank_balance_is_imported_only_to_bank_account_endpoint(self) -> None:
        self.assertIn("jsonFetch('/api/bank-accounts'", self.js)
        self.assertIn("balance: Number(row.reported_balance_krw || 0)", self.js)
        self.assertIn("청약·적금·외화 상품은 확인 필요", self.js)
        self.assertIn("REVIEW_BANK_PRODUCT", self.js)

    def test_duplicate_detection_uses_institution_and_normalized_account_number(self) -> None:
        self.assertIn("canonicalInstitution", self.js)
        self.assertIn("digits(account?.account_no)", self.js)
        self.assertIn("digits(account?.account_number)", self.js)
        self.assertIn("item.account_no === accountNo && item.institution === institution", self.js)

    def test_brokerage_type_suggestions_are_conservative(self) -> None:
        self.assertIn("return 'isa'", self.js)
        self.assertIn("return 'pension_savings'", self.js)
        self.assertIn("return 'irp'", self.js)
        self.assertIn("REVIEW_BROKER_PRODUCT", self.js)
        self.assertIn("퇴직연금", self.js)
        self.assertIn("금현물", self.js)

    def test_sensitive_example_account_numbers_are_not_committed(self) -> None:
        # Uploaded AccountInfo documents are format references only. Raw personal
        # account numbers must never become source/test fixtures.
        for forbidden in ("37727895601", "17401024998", "58001160801018", "100021913790"):
            self.assertNotIn(forbidden, self.js)
            self.assertNotIn(forbidden, self.money_js)


if __name__ == "__main__":
    unittest.main()
