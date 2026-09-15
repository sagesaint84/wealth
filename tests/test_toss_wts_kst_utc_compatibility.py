from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.services.toss_wts_adapter import (
    TOSSCTL_DATE_TIMEZONE_CONFLICT,
    TossWtsAdapter,
    TossWtsAdapterError,
    TossWtsConfig,
    resolve_tossctl_profit_daily_range,
)


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
INDEX_HTML = ROOT / "app" / "static" / "index.html"
MAIN_PY = ROOT / "app" / "main.py"


class TossWtsKstUtcDateCompatibilityTests(unittest.TestCase):
    def test_kst_today_before_0900_uses_previous_utc_date(self) -> None:
        result = resolve_tossctl_profit_daily_range(
            "2026-09-01",
            "2026-09-15",
            now=datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(result["date_range_adjusted"])
        self.assertEqual(result["requested_to_date"], "2026-09-15")
        self.assertEqual(result["effective_to_date"], "2026-09-14")
        self.assertEqual(result["compatibility_code"], TOSSCTL_DATE_TIMEZONE_CONFLICT)

    def test_kst_today_after_0900_is_not_adjusted(self) -> None:
        result = resolve_tossctl_profit_daily_range(
            "2026-09-01",
            "2026-09-15",
            now=datetime(2026, 9, 15, 0, 1, tzinfo=timezone.utc),
        )
        self.assertFalse(result["date_range_adjusted"])
        self.assertEqual(result["effective_to_date"], "2026-09-15")

    def test_historical_date_is_unchanged_before_0900(self) -> None:
        result = resolve_tossctl_profit_daily_range(
            "2026-09-01",
            "2026-09-14",
            now=datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(result["date_range_adjusted"])
        self.assertEqual(result["effective_to_date"], "2026-09-14")

    def test_requested_date_earlier_than_safe_date_is_unchanged(self) -> None:
        result = resolve_tossctl_profit_daily_range(
            "2026-08-01",
            "2026-09-10",
            now=datetime(2026, 9, 14, 17, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(result["date_range_adjusted"])
        self.assertEqual(result["effective_to_date"], "2026-09-10")

    @staticmethod
    def _configured(temp_dir: str) -> TossWtsConfig:
        root = Path(temp_dir)
        executable = root / "tossctl"
        executable.write_text("synthetic", encoding="utf-8")
        config_dir = root / "config"
        config_dir.mkdir()
        (config_dir / "session.json").write_text("{}", encoding="utf-8")
        return TossWtsConfig(True, executable, config_dir, "v0.50.3", 3)

    def test_known_future_date_stderr_has_specific_safe_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = TossWtsAdapter(self._configured(temp_dir))
            completed = Mock(
                returncode=1,
                stdout="",
                stderr="2026-09-15 는 미래입니다 (credential=DO_NOT_EXPOSE)",
            )
            with patch.dict("os.environ", {"WEALTH_ENV": "production"}), patch(
                "app.services.toss_wts_adapter.subprocess.run", return_value=completed
            ):
                with self.assertRaises(TossWtsAdapterError) as caught:
                    adapter.get_profit_daily("2026-09-01", "2026-09-14")
        self.assertEqual(caught.exception.code, TOSSCTL_DATE_TIMEZONE_CONFLICT)
        self.assertNotIn("DO_NOT_EXPOSE", str(caught.exception))

    def test_unrelated_nonzero_exit_keeps_generic_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = TossWtsAdapter(self._configured(temp_dir))
            completed = Mock(returncode=1, stdout="", stderr="unrelated provider failure")
            with patch.dict("os.environ", {"WEALTH_ENV": "production"}), patch(
                "app.services.toss_wts_adapter.subprocess.run", return_value=completed
            ):
                with self.assertRaises(TossWtsAdapterError) as caught:
                    adapter.get_profit_daily("2026-09-01", "2026-09-14")
        self.assertEqual(caught.exception.code, "NONZERO_EXIT")

    def test_adapter_sends_effective_date_and_preserves_requested_metadata(self) -> None:
        query_range = {
            "requested_from_date": "2026-09-01",
            "requested_to_date": "2026-09-15",
            "effective_from_date": "2026-09-01",
            "effective_to_date": "2026-09-14",
            "date_range_adjusted": True,
            "compatibility_code": TOSSCTL_DATE_TIMEZONE_CONFLICT,
        }
        payload = {"currency": "KRW", "stocks": [], "fetched_at": "2026-09-14T17:00:00Z"}
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = TossWtsAdapter(self._configured(temp_dir))
            completed = Mock(returncode=0, stdout=json.dumps(payload), stderr="")
            with patch.dict("os.environ", {"WEALTH_ENV": "production"}), patch(
                "app.services.toss_wts_adapter.resolve_tossctl_profit_daily_range",
                return_value=query_range,
            ), patch(
                "app.services.toss_wts_adapter.subprocess.run", return_value=completed
            ) as run:
                result = adapter.get_profit_daily("2026-09-01", "2026-09-15")
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index("--to") + 1], "2026-09-14")
        self.assertEqual(result["requested_to_date"], "2026-09-15")
        self.assertEqual(result["effective_to_date"], "2026-09-14")

    @classmethod
    def _run_frontend_fetch(cls, status: int, payload: dict) -> dict:
        if not shutil.which("node"):
            raise unittest.SkipTest("node runtime is not available")
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const helperStart = source.indexOf('function clearTossWtsFetchLoadingRow');
const helperEnd = source.indexOf('\nfunction updateTossWtsStatusUI', helperStart);
const fetchStart = source.indexOf('async function fetchTossWtsRealizedFeed');
const fetchEnd = source.indexOf('\nfunction updateWtsSelectionUI', fetchStart);
const input = JSON.parse(process.argv[2]);
const elements = {
  tossWtsFromDate: { value: '2026-09-01' },
  tossWtsToDate: { value: '2026-09-15' },
  tossWtsBasisSelect: { value: 'KRW' },
  tossWtsTableBody: {
    innerHTML: '<tr><td class="toss-wts-loading">loading</td></tr>',
    querySelector(selector) { return selector === '.toss-wts-loading' && this.innerHTML.includes('toss-wts-loading') ? {} : null; },
  },
};
const sandbox = {
  document: { getElementById: id => elements[id] || null },
  fetch: async () => ({ status: input.status, ok: input.status >= 200 && input.status < 300, json: async () => input.payload }),
  html: value => String(value),
  tossWtsState: {
    loading: false, rows: [], selectionTokens: [], selectedIndices: new Set(), importedIndices: new Set(),
    importPreferences: new Map(), previewTicket: null, lastRequested: null,
  },
  setTossWtsLoading: value => { sandbox.tossWtsState.loading = value; },
  showTossWtsMessage: (message, type) => { sandbox.message = { message, type }; },
  hideTossWtsMessage: () => { sandbox.message = { hidden: true }; },
  updateTossWtsMetaUI: () => {}, populateWtsAccounts: () => {}, updateWtsSelectionUI: () => {},
  sortBrokerRealizedFeedRows: (rows, selectionTokens) => ({ rows, selectionTokens }),
  renderTossWtsFeedTable: rows => { sandbox.renderedRows = rows.length; elements.tossWtsTableBody.innerHTML = 'rendered'; },
};
vm.runInNewContext(
  source.slice(helperStart, helperEnd) + '\n' + source.slice(fetchStart, fetchEnd) +
  '\nthis.fetchTossWtsRealizedFeed = fetchTossWtsRealizedFeed;', sandbox
);
sandbox.fetchTossWtsRealizedFeed().then(() => process.stdout.write(JSON.stringify({
  table: elements.tossWtsTableBody.innerHTML,
  message: sandbox.message,
  renderedRows: sandbox.renderedRows || 0,
  requested: sandbox.tossWtsState.lastRequested,
  effective: sandbox.tossWtsState.providerEffective,
  loading: sandbox.tossWtsState.loading,
}))).catch(error => { console.error(error); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", script, str(WEALTH_JS), json.dumps({"status": status, "payload": payload})],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(completed.stdout)

    def test_frontend_specific_notice_and_success_display(self) -> None:
        result = self._run_frontend_fetch(200, {
            "requested": {"from_date": "2026-09-01", "to_date": "2026-09-15", "profit_rate_basis": "KRW"},
            "provider_effective": {"from_date": "2026-09-01", "to_date": "2026-09-14"},
            "date_compatibility": {"adjusted": True, "code": TOSSCTL_DATE_TIMEZONE_CONFLICT},
            "fetched_at": "2026-09-14T17:00:00Z",
            "rows": [{"date": "2026-09-14"}],
            "selection_tokens": ["synthetic"],
        })
        self.assertEqual(result["renderedRows"], 1)
        self.assertEqual(result["requested"]["to_date"], "2026-09-15")
        self.assertEqual(result["effective"]["to_date"], "2026-09-14")
        self.assertIn("현재 2026-09-14까지", result["message"]["message"])
        self.assertIn("오전 9시 이후", result["message"]["message"])

    def test_frontend_clears_loading_row_after_502(self) -> None:
        result = self._run_frontend_fetch(502, {"detail": {"code": "INVALID_JSON"}})
        self.assertNotIn("toss-wts-loading", result["table"])
        self.assertIn("toss-wts-empty", result["table"])
        self.assertFalse(result["loading"])

    def test_frontend_uses_specific_timezone_error_for_known_503(self) -> None:
        result = self._run_frontend_fetch(
            503,
            {"detail": {"code": TOSSCTL_DATE_TIMEZONE_CONFLICT}},
        )
        self.assertNotIn("toss-wts-loading", result["table"])
        self.assertIn("오전 9시 이후", result["table"])
        self.assertIn("WTS CLI 날짜 제한", result["message"]["message"])
        self.assertNotIn("연동 런타임을 사용할 수 없습니다", result["message"]["message"])

    def test_confirmation_wording_describes_runtime_not_live_authentication(self) -> None:
        html = INDEX_HTML.read_text(encoding="utf-8")
        js = WEALTH_JS.read_text(encoding="utf-8")
        self.assertIn("WTS 런타임 확인</button>", html)
        self.assertIn("런타임 확인 완료", js)
        self.assertIn("WTS 로컬 런타임이 확인되었습니다", js)
        self.assertNotIn("세션 확인 완료", js)

    def test_backend_keeps_requested_and_effective_ranges_distinct(self) -> None:
        source = MAIN_PY.read_text(encoding="utf-8")
        self.assertIn('feed_response["provider_effective"]', source)
        self.assertIn('feed_response["date_compatibility"]', source)
        self.assertIn('raw_result.get("effective_to_date")', source)


if __name__ == "__main__":
    unittest.main()
