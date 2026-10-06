from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNER_JS = ROOT / "app" / "static" / "wealth-accountinfo-owner-options.js"
MONEY_JS = ROOT / "app" / "static" / "wealth-money-input.js"


class AccountInfoOwnerOptionsFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.owner_js = OWNER_JS.read_text(encoding="utf-8")
        cls.money_js = MONEY_JS.read_text(encoding="utf-8")

    def test_owner_refresh_script_is_loaded(self) -> None:
        self.assertIn("/static/wealth-accountinfo-owner-options.js?v=10.6a1", self.money_js)
        self.assertIn("data-accountinfo-owner-options", self.money_js)

    def test_family_members_api_is_authoritative_source(self) -> None:
        self.assertIn("window.fetchJson('/api/family-members')", self.owner_js)
        self.assertIn("payload?.members", self.owner_js)
        self.assertNotIn("await fetch(", self.owner_js)

    def test_render_preserves_existing_selection_and_excludes_all_when_members_exist(self) -> None:
        self.assertIn("value !== '모두'", self.owner_js)
        self.assertIn("options.includes(previous)", self.owner_js)
        self.assertIn("activeOwner !== '모두'", self.owner_js)
        self.assertIn("normalized.length ? normalized : ['모두']", self.owner_js)

    def test_refresh_runs_when_importer_select_is_added_or_pdf_entry_is_used(self) -> None:
        self.assertIn("node.id === 'accountInfoImportOwner'", self.owner_js)
        self.assertIn("target?.id === 'accountInfoBankImportBtn'", self.owner_js)
        self.assertIn("event.target?.id === 'accountImportFile'", self.owner_js)

    def test_account_action_labels_are_context_specific(self) -> None:
        self.assertIn("📂 증권계좌 가져오기", self.owner_js)
        self.assertIn("➕ 은행계좌 추가", self.owner_js)
        self.assertIn("📂 은행계좌 가져오기", self.owner_js)
        self.assertIn("document.getElementById('accountImportBtn')", self.owner_js)
        self.assertIn("document.getElementById('addBankIntegratedBtn')", self.owner_js)
        self.assertIn("document.getElementById('accountInfoBankImportBtn')", self.owner_js)


if __name__ == "__main__":
    unittest.main()
