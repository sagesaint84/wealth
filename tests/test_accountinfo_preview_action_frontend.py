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

    def test_toolbar_label_writes_are_idempotent(self) -> None:
        self.assertIn("if (node.textContent !== label) node.textContent = label;", self.owner_js)
        self.assertIn("if (node.title !== title) node.title = title;", self.owner_js)

    def test_body_observer_only_resyncs_toolbar_when_action_nodes_are_added(self) -> None:
        self.assertIn("let shouldSyncToolbar = false;", self.owner_js)
        self.assertIn("if (containsAccountAction(node)) shouldSyncToolbar = true;", self.owner_js)
        self.assertIn("if (shouldSyncToolbar) scheduleToolbarSync();", self.owner_js)
        self.assertNotIn("if (shouldRefreshOwner) scheduleRefresh();\n      scheduleToolbarSync();", self.owner_js)


if __name__ == "__main__":
    unittest.main()
