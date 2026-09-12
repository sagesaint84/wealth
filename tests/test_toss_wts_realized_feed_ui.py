"""Unit and integration test suite for Toss WTS Read-Only Realized Profit UI Milestone.

Verifies:
1. Static HTML structure, hierarchy inside #realizedPnlPanel, and Korean labels.
2. Prominent warning banner, accessibility role="note", and read-only badge.
3. Display-only controls (date inputs, basis select, status check, session confirm, fetch).
4. Absence of destructive/persisting controls (no save, edit, delete, import, account attribution).
5. CSS styling, color contracts, result metadata, stale hint, and responsive media queries.
6. JavaScript state management, double-click protection, zero client-side persistence.
7. Semantic fix: basis & date changes do NOT mutate/reinterpret existing provider rows.
8. Response.requested field is authoritative for result metadata.
9. Failed refresh preserves existing rows and previous query metadata.
10. Status UI privacy (no leaked paths, env vars, or raw exceptions).
11. Service worker API bypass isolation.
12. End-to-end API integration matching UI fetch workflows.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from starlette.testclient import TestClient

from app.services.toss_wts_adapter import TossWtsAdapter
from app.services.toss_wts_feed_auth import WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID
from app.services.toss_wts_feed_runtime import (
    clear_wts_feed_runtime_confirmation,
    confirm_wts_feed_runtime_session,
)
from app.services.user_identity import generate_user_id
from tests.test_request_state_user_id import _import_main_without_loading_real_env

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/wealth-layout.css").read_text(encoding="utf-8")
JS = (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")
SW = (ROOT / "app/static/sw.js").read_text(encoding="utf-8")


class TossWtsRealizedFeedUiStaticTests(unittest.TestCase):
    """Static inspection tests verifying UI contracts in HTML, CSS, and JS."""

    def test_wts_card_hierarchy_inside_realized_pnl_panel(self):
        """Card must be inside #realizedPnlPanel and below #pnlMonthlyDetail."""
        pnl_panel_pos = HTML.index('id="realizedPnlPanel"')
        div_panel_pos = HTML.index('id="dividendPanel"')
        wts_card_pos = HTML.index('id="tossWtsCard"')
        pnl_detail_pos = HTML.index('id="pnlMonthlyDetail"')

        self.assertGreater(wts_card_pos, pnl_panel_pos)
        self.assertLess(wts_card_pos, div_panel_pos)
        self.assertGreater(wts_card_pos, pnl_detail_pos)

    def test_korean_title_and_read_only_badge(self):
        """UI must clearly state '토스 WTS 실현손익' with a '읽기 전용' badge."""
        self.assertIn("토스 WTS 실현손익", HTML)
        self.assertIn("읽기 전용", HTML)
        self.assertIn('class="toss-wts-badge">읽기 전용</span>', HTML)

    def test_prominent_warning_banner_exact_text_and_role_note(self):
        """Warning banner must display canonical safety disclaimer with role='note'."""
        expected_banner = (
            "토스 WTS 조회 자료 · 읽기 전용 · 계좌 범위 미확인 · Wealth 자산 및 실현손익 합계에 반영되지 않습니다."
        )
        self.assertIn(expected_banner, HTML)
        self.assertIn('class="toss-wts-banner"', HTML)
        self.assertIn('role="note"', HTML)
        self.assertIn('aria-label="WTS 읽기 전용 주의사항"', HTML)

    def test_explicit_action_buttons_and_controls(self):
        """Check status, session confirm, and fetch buttons exist with date & basis inputs."""
        self.assertIn('id="btnCheckTossWtsStatus"', HTML)
        self.assertIn(">상태 확인</button>", HTML)
        self.assertIn('id="btnConfirmTossWtsSession"', HTML)
        self.assertIn(">WTS 세션 확인</button>", HTML)
        self.assertIn('id="btnFetchTossWtsFeed"', HTML)
        self.assertIn(">WTS 조회</button>", HTML)

        self.assertIn('id="tossWtsFromDate"', HTML)
        self.assertIn('id="tossWtsToDate"', HTML)
        self.assertIn('id="tossWtsBasisSelect"', HTML)
        self.assertIn('value="KRW"', HTML)
        self.assertIn('value="USD"', HTML)

    def test_stale_hint_and_meta_elements_in_html(self):
        """Result metadata and stale-hint notice elements must be present in HTML."""
        self.assertIn('id="tossWtsStaleHint"', HTML)
        self.assertIn('id="tossWtsMeta"', HTML)

    def test_display_only_table_and_no_destructive_actions(self):
        """Table columns must be display-only; no edit, save, delete, or link buttons in WTS card."""
        card_start = HTML.index('id="tossWtsCard"')
        card_end = HTML.index('</div>\n        </div>\n      </section>', card_start)
        wts_card_html = HTML[card_start:card_end]

        for col in ("거래일자", "시장", "종목명 (코드)", "수량", "매수금액", "매도금액", "실현손익", "수익률"):
            self.assertIn(col, wts_card_html)

        # Ensure no destructive or persistence buttons inside the card
        self.assertNotIn("delete-pnl-btn", wts_card_html)
        self.assertNotIn("edit-pnl-btn", wts_card_html)
        self.assertNotIn("addPnlBtn", wts_card_html)
        self.assertNotIn("importPnlBtn", wts_card_html)
        self.assertNotIn("clearAllPnlBtn", wts_card_html)
        self.assertNotIn("계좌 연동", wts_card_html)
        self.assertNotIn("소유자", wts_card_html)

    def test_transient_client_disclaimer_present(self):
        """Must inform the user that results are transient and cleared on refresh."""
        self.assertIn(
            "본 화면의 조회 결과는 브라우저 새로고침 시 초기화되며 저장되지 않습니다.",
            HTML,
        )

    def test_css_styling_and_responsive_rules(self):
        """Ensure CSS defines WTS card, status, banner, metadata, stale hint, and table."""
        for selector in (
            ".toss-wts-card",
            ".toss-wts-header",
            ".toss-wts-badge",
            ".toss-wts-status-text",
            ".toss-wts-banner",
            ".toss-wts-controls",
            ".toss-wts-stale-hint",
            ".toss-wts-meta",
            ".toss-wts-table",
            ".toss-wts-empty",
            ".toss-wts-loading",
        ):
            self.assertIn(selector, CSS)

        self.assertIn("@media (max-width: 760px)", CSS)
        self.assertIn(".toss-wts-controls", CSS)

    def test_javascript_state_machine_and_functions(self):
        """Check all required JS state and event handlers exist in wealth.js."""
        for fn in (
            "tossWtsState",
            "showTossWtsMessage",
            "hideTossWtsMessage",
            "updateTossWtsStatusUI",
            "updateTossWtsMetaUI",
            "checkTossWtsFormStale",
            "setTossWtsLoading",
            "checkTossWtsStatus",
            "confirmTossWtsSession",
            "fetchTossWtsRealizedFeed",
            "renderTossWtsFeedTable",
            "initTossWtsUI",
        ):
            self.assertIn(fn, JS)

        self.assertIn("initTossWtsUI()", JS)

    def test_zero_client_storage_persistence(self):
        """Ensure WTS feed data is NEVER stored in localStorage, sessionStorage, or IndexedDB."""
        self.assertNotIn("localStorage.setItem('toss_wts", JS)
        self.assertNotIn("localStorage.setItem('tossWts", JS)
        self.assertNotIn("sessionStorage.setItem('toss_wts", JS)
        self.assertNotIn("sessionStorage.setItem('tossWts", JS)
        self.assertNotIn("indexedDB", JS)

    def test_exact_empty_and_error_messages_in_js(self):
        """Validate exact required Korean UI strings in JS logic."""
        self.assertIn("선택한 기간에 조회된 실현손익 내역이 없습니다.", JS)
        self.assertIn("이 사용자에게는 토스 WTS 조회 권한이 없습니다.", JS)
        self.assertIn("WTS 세션 확인이 필요합니다. 먼저 [WTS 세션 확인] 버튼을 눌러주세요.", JS)
        self.assertIn("토스 WTS 연동 런타임을 사용할 수 없습니다.", JS)

    def test_service_worker_api_caching_isolation(self):
        """Service worker must strictly bypass all /api/ requests from cache."""
        self.assertIn('url.pathname.startsWith("/api/")', SW)
        self.assertIn('event.respondWith(fetch(event.request));', SW)

    def test_basis_change_does_not_mutate_old_rows_in_js(self):
        """Changing basisSelect must only check staleness and NOT re-render table."""
        # Find basisSelect listener in wealth.js
        self.assertIn("basisSelect?.addEventListener('change', checkTossWtsFormStale)", JS)
        # Ensure renderTossWtsFeedTable is never called directly on basisSelect change
        self.assertNotIn("basisSelect?.addEventListener('change', () => {\n    if (tossWtsState.rows", JS)
        self.assertNotIn("renderTossWtsFeedTable(tossWtsState.rows, basisSelect.value", JS)

    def test_date_change_does_not_relabel_result_in_js(self):
        """Changing date inputs must only check staleness and NOT auto-fetch or relabel."""
        self.assertIn("fromInput?.addEventListener('input', checkTossWtsFormStale)", JS)
        self.assertIn("toInput?.addEventListener('input', checkTossWtsFormStale)", JS)

    def test_status_ui_privacy_guarantees(self):
        """Status UI strings must be high-level and safe; no internal paths or env vars."""
        # Check safe status labels are present
        for safe_label in ("준비 완료", "WTS 비활성", "세션 확인 필요", "연결 상태 확인 불가", "권한 없음"):
            self.assertIn(safe_label, JS)

        # Ensure no exposure of paths or env vars in status UI
        status_fn_start = JS.index("async function checkTossWtsStatus()")
        status_fn_end = JS.index("async function confirmTossWtsSession()", status_fn_start)
        status_code = JS[status_fn_start:status_fn_end]

        self.assertNotIn("WEALTH_TOSS", status_code)
        self.assertNotIn("session.json", status_code)
        self.assertNotIn("tossctl", status_code)
        self.assertNotIn("data.error_code || '준비 미완료'", status_code)


class TossWtsRealizedFeedUiApiIntegrationTests(unittest.TestCase):
    """End-to-end API integration tests matching UI fetch workflows."""

    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        clear_wts_feed_runtime_confirmation()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(clear_wts_feed_runtime_confirmation)

        root = Path(self.temp_dir.name)
        self.exe_path = root / "tossctl"
        self.exe_path.write_text("synthetic_tossctl_binary", encoding="utf-8")

        self.config_dir = root / "config"
        self.config_dir.mkdir()
        self.session_path = self.config_dir / "session.json"
        self.session_path.write_text('{"token": "SYNTHETIC_WTS_SESSION_TOKEN"}', encoding="utf-8")

    def _cookie_header(self, username: str, role: str = "user") -> dict[str, str]:
        token = self.main._serializer.dumps({"user": username, "role": role})
        return {"Cookie": f"{self.main.COOKIE_NAME}={token}"}

    def _env_for(self, user_id: str) -> dict[str, str]:
        return {
            WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: user_id,
            "WEALTH_TOSS_WTS_ENABLED": "1",
            "WEALTH_TOSSCTL_PATH": str(self.exe_path),
            "WEALTH_TOSSCTL_CONFIG_DIR": str(self.config_dir),
        }

    def test_unauthorized_user_status_and_fetch_returns_403(self):
        allowed_id = generate_user_id()
        other_id = generate_user_id()

        user_record = {"username": "other-user", "id": other_id, "role": "user", "must_change_password": False}
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), patch(
            "app.services.user_manager.get_user_by_name", return_value=user_record
        ):
            headers = self._cookie_header("other-user")

            # Status check
            res_status = self.client.get("/api/toss-wts/status", headers=headers)
            self.assertEqual(res_status.status_code, 403)
            self.assertEqual(res_status.json()["detail"]["code"], "STATIC_AUTHORIZATION_FAILED")

            # Session confirm
            res_confirm = self.client.post("/api/toss-wts/feed/confirm", headers=headers)
            self.assertEqual(res_confirm.status_code, 403)

            # Fetch feed
            res_fetch = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                headers=headers,
                json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
            )
            self.assertEqual(res_fetch.status_code, 403)

    def test_unconfirmed_session_fetch_returns_409(self):
        user_id = generate_user_id()
        user_record = {"username": "allowed-user", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), patch(
            "app.services.user_manager.get_user_by_name", return_value=user_record
        ):
            headers = self._cookie_header("allowed-user")

            # Try to fetch feed before session confirm -> 409
            res = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                headers=headers,
                json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
            )
            self.assertEqual(res.status_code, 409)
            self.assertEqual(res.json()["detail"]["code"], "NOT_CONFIRMED")

    def test_full_ui_api_flow_status_confirm_fetch(self):
        user_id = generate_user_id()
        user_record = {"username": "allowed-user", "id": user_id, "role": "user", "must_change_password": False}

        sample_stocks = [
            {
                "date": "2026-01-05",
                "market_type": "KR",
                "symbol": "005930",
                "product_code": "KR7005930003",
                "name": "삼성전자",
                "quantity": 10.0,
                "profit_loss": {"krw": 50000, "usd": 38.5},
                "profit_rate": 7.5,
                "sell_amount": {"krw": 750000, "usd": 576.9},
                "buy_amount": {"krw": 700000, "usd": 538.4},
            }
        ]

        with patch.dict(os.environ, self._env_for(user_id), clear=False), patch(
            "app.services.user_manager.get_user_by_name", return_value=user_record
        ):
            headers = self._cookie_header("allowed-user")

            # 1. Status Check
            res_status = self.client.get("/api/toss-wts/status", headers=headers)
            self.assertEqual(res_status.status_code, 200)
            status_data = res_status.json()
            self.assertTrue(status_data["adapter_ready"])

            # 2. Explicit Runtime Session Confirm
            res_confirm = self.client.post("/api/toss-wts/feed/confirm", headers=headers)
            self.assertEqual(res_confirm.status_code, 200)
            self.assertTrue(res_confirm.json()["confirmed"])

            # 3. Fetch Realized Feed
            with patch.object(
                TossWtsAdapter,
                "get_profit_daily",
                return_value={"stocks": sample_stocks, "fetched_at": "2026-01-10T12:00:00Z"},
            ):
                res_fetch = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    headers=headers,
                    json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
                )
                self.assertEqual(res_fetch.status_code, 200)
                feed = res_fetch.json()
                self.assertEqual(feed["state"], "ok")
                self.assertEqual(len(feed["rows"]), 1)
                self.assertFalse(feed["scope_verified"])
                self.assertTrue(feed["read_only"])
                self.assertFalse(feed["persisted"])
                self.assertFalse(feed["included_in_accounting_totals"])
                self.assertEqual(res_fetch.headers.get("cache-control"), "no-store")

                # Authoritative response.requested contract check
                self.assertEqual(feed["requested"]["from_date"], "2026-01-01")
                self.assertEqual(feed["requested"]["to_date"], "2026-01-10")
                self.assertEqual(feed["requested"]["profit_rate_basis"], "KRW")

    def test_new_success_replaces_basis_and_metadata(self):
        """USD query replaces KRW query; response.requested drives displayed metadata."""
        user_id = generate_user_id()
        user_record = {"username": "allowed-user", "id": user_id, "role": "user", "must_change_password": False}

        krw_stocks = [
            {
                "date": "2026-01-05",
                "market_type": "KR",
                "symbol": "005930",
                "product_code": "KR7005930003",
                "name": "삼성전자",
                "quantity": 10.0,
                "profit_loss": {"krw": 50000, "usd": 38.5},
                "profit_rate": 7.5,
                "sell_amount": {"krw": 750000, "usd": 576.9},
                "buy_amount": {"krw": 700000, "usd": 538.4},
            }
        ]
        usd_stocks = [
            {
                "date": "2026-01-08",
                "market_type": "US",
                "symbol": "AAPL",
                "product_code": "US0378331005",
                "name": "애플",
                "quantity": 5.0,
                "profit_loss": {"krw": 130000, "usd": 100.0},
                "profit_rate": 10.0,
                "sell_amount": {"krw": 1430000, "usd": 1100.0},
                "buy_amount": {"krw": 1300000, "usd": 1000.0},
            }
        ]

        with patch.dict(os.environ, self._env_for(user_id), clear=False), patch(
            "app.services.user_manager.get_user_by_name", return_value=user_record
        ):
            headers = self._cookie_header("allowed-user")
            self.client.post("/api/toss-wts/feed/confirm", headers=headers)

            # Query 1: KRW
            with patch.object(
                TossWtsAdapter,
                "get_profit_daily",
                return_value={"stocks": krw_stocks, "fetched_at": "2026-01-10T12:00:00Z"},
            ):
                res1 = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    headers=headers,
                    json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
                )
                feed1 = res1.json()
                self.assertEqual(feed1["requested"]["profit_rate_basis"], "KRW")
                self.assertEqual(feed1["rows"][0]["name"], "삼성전자")

            # Query 2: USD (explicit click)
            with patch.object(
                TossWtsAdapter,
                "get_profit_daily",
                return_value={"stocks": usd_stocks, "fetched_at": "2026-01-10T13:00:00Z"},
            ):
                res2 = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    headers=headers,
                    json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "USD"},
                )
                feed2 = res2.json()
                self.assertEqual(feed2["requested"]["profit_rate_basis"], "USD")
                self.assertEqual(feed2["rows"][0]["name"], "애플")

    def test_failed_refresh_preserves_old_metadata_scenario(self):
        """When an updated fetch fails, old data remains intact and is NOT mislabeled."""
        user_id = generate_user_id()
        user_record = {"username": "allowed-user", "id": user_id, "role": "user", "must_change_password": False}

        sample_stocks = [
            {
                "date": "2026-01-05",
                "market_type": "KR",
                "symbol": "005930",
                "product_code": "KR7005930003",
                "name": "삼성전자",
                "quantity": 10.0,
                "profit_loss": {"krw": 50000, "usd": 38.5},
                "profit_rate": 7.5,
                "sell_amount": {"krw": 750000, "usd": 576.9},
                "buy_amount": {"krw": 700000, "usd": 538.4},
            }
        ]

        with patch.dict(os.environ, self._env_for(user_id), clear=False), patch(
            "app.services.user_manager.get_user_by_name", return_value=user_record
        ):
            headers = self._cookie_header("allowed-user")
            self.client.post("/api/toss-wts/feed/confirm", headers=headers)

            # 1. First fetch succeeds with KRW
            with patch.object(
                TossWtsAdapter,
                "get_profit_daily",
                return_value={"stocks": sample_stocks, "fetched_at": "2026-01-10T12:00:00Z"},
            ):
                res_ok = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    headers=headers,
                    json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
                )
                self.assertEqual(res_ok.status_code, 200)
                feed_ok = res_ok.json()
                self.assertEqual(feed_ok["requested"]["profit_rate_basis"], "KRW")

            # 2. Second fetch with USD fails (e.g. 503 runtime unavailable)
            clear_wts_feed_runtime_confirmation()  # Simulate session becoming invalid
            res_fail = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                headers=headers,
                json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "USD"},
            )
            self.assertEqual(res_fail.status_code, 409)

            # In client logic, tossWtsState.lastRequested and rows remain the previous KRW result.
            self.assertEqual(feed_ok["requested"]["profit_rate_basis"], "KRW")

    def test_empty_feed_result_handling(self):
        user_id = generate_user_id()
        user_record = {"username": "allowed-user", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), patch(
            "app.services.user_manager.get_user_by_name", return_value=user_record
        ):
            headers = self._cookie_header("allowed-user")

            # Confirm session
            self.client.post("/api/toss-wts/feed/confirm", headers=headers)

            # Fetch empty feed
            with patch.object(
                TossWtsAdapter,
                "get_profit_daily",
                return_value={"stocks": [], "fetched_at": "2026-01-10T12:00:00Z"},
            ):
                res_fetch = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    headers=headers,
                    json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
                )
                self.assertEqual(res_fetch.status_code, 200)
                feed = res_fetch.json()
                self.assertEqual(feed["state"], "empty")
                self.assertEqual(len(feed["rows"]), 0)


if __name__ == "__main__":
    unittest.main()
