from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNER_JS = ROOT / "app" / "static" / "wealth-accountinfo-owner-options.js"


class AccountInfoPreviewActionFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.owner_js = OWNER_JS.read_text(encoding="utf-8")

    def test_preview_ready_uses_visible_populated_preview(self) -> None:
        self.assertIn("host.style.display !== 'none'", self.owner_js)
        self.assertIn("host.childElementCount > 0", self.owner_js)

    def test_submit_label_changes_to_explicit_save_action(self) -> None:
        self.assertIn("previewIsReady() ? '선택 계좌 추가' : '가져오기'", self.owner_js)
        self.assertIn("if (!submit || submit.disabled) return;", self.owner_js)

    def test_form_mutations_resync_action_label_after_busy_state(self) -> None:
        self.assertIn("const actionObserver = new MutationObserver(scheduleActionSync)", self.owner_js)
        self.assertIn("attributeFilter: ['style', 'disabled']", self.owner_js)
        self.assertIn("childList: true", self.owner_js)


if __name__ == "__main__":
    unittest.main()
