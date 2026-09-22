from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
WEALTH_IPO_JS = ROOT / "app" / "static" / "wealth-ipo.js"
INDEX_HTML = ROOT / "app" / "static" / "index.html"
CSS_OVERRIDES = ROOT / "app" / "static" / "wealth-overrides.css"


class MoneyLogMonthNavigationFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node runtime is not available")
        cls.wealth_js = WEALTH_JS.read_text(encoding="utf-8")
        cls.wealth_ipo_js = WEALTH_IPO_JS.read_text(encoding="utf-8")
        cls.index_html = INDEX_HTML.read_text(encoding="utf-8")
        cls.css = CSS_OVERRIDES.read_text(encoding="utf-8")

    def run_node_eval(self, script: str) -> str:
        cmd = ["node", "-e", script]
        res = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return res.stdout.strip()

    # 1. Shared date helpers tests
    def test_shared_date_helpers_defined_and_exposed(self):
        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync('{WEALTH_JS.as_posix()}', 'utf8');
        const sandbox = {{
          window: {{}},
          document: {{ querySelector: () => null, querySelectorAll: () => [] }},
          localStorage: {{ getItem: () => null, setItem: () => {{}} }},
          Intl: Intl,
          Date: Date
        }};
        vm.createContext(sandbox);
        // Execute up to window.WealthDateHelper
        const idx = code.indexOf('window.WealthDateHelper =');
        const endIdx = code.indexOf(';', idx) + 1;
        vm.runInContext(code.slice(0, endIdx), sandbox);

        const helper = sandbox.window.WealthDateHelper;
        const out = {{
          hasGetKst: typeof helper.getKstYearMonth === 'function',
          hasShift: typeof helper.shiftYearMonth === 'function',
          hasParse: typeof helper.parseYearMonth === 'function',
          kstNow: helper.getKstYearMonth(new Date('2026-09-22T08:00:00Z')),
          shiftDecToJan: helper.shiftYearMonth(2026, 12, 1),
          shiftJanToDec: helper.shiftYearMonth(2026, 1, -1),
          parseIso: helper.parseYearMonth('2026-08'),
          parseKorean: helper.parseYearMonth('2026년 8월'),
          parseInvalid: helper.parseYearMonth('invalid')
        }};
        process.stdout.write(JSON.stringify(out));
        """
        output = json.loads(self.run_node_eval(script))
        self.assertTrue(output["hasGetKst"])
        self.assertTrue(output["hasShift"])
        self.assertTrue(output["hasParse"])

        # KST (UTC+9): 2026-09-22 08:00 UTC is 17:00 KST
        self.assertEqual(output["kstNow"]["year"], 2026)
        self.assertEqual(output["kstNow"]["month"], 9)
        self.assertEqual(output["kstNow"]["key"], "2026-09")

        # Rollover check
        self.assertEqual(output["shiftDecToJan"], {"year": 2027, "month": 1, "key": "2027-01"})
        self.assertEqual(output["shiftJanToDec"], {"year": 2025, "month": 12, "key": "2025-12"})

        # Parsing check
        self.assertEqual(output["parseIso"], {"year": 2026, "month": 8, "key": "2026-08"})
        self.assertEqual(output["parseKorean"], {"year": 2026, "month": 8, "key": "2026-08"})
        self.assertIsNone(output["parseInvalid"])

    # 2. HTML month navigation controls
    def test_html_contains_month_controls_for_pnl_dividend_ledger(self):
        # PnL panel
        self.assertIn('id="pnlPrevMonthBtn"', self.index_html)
        self.assertIn('id="pnlCurrentMonthText"', self.index_html)
        self.assertIn('id="pnlMonthPicker"', self.index_html)
        self.assertIn('id="pnlNextMonthBtn"', self.index_html)
        self.assertIn('id="pnlTodayMonthBtn"', self.index_html)

        # Dividend panel
        self.assertIn('id="dividendPrevMonthBtn"', self.index_html)
        self.assertIn('id="dividendCurrentMonthText"', self.index_html)
        self.assertIn('id="dividendMonthPicker"', self.index_html)
        self.assertIn('id="dividendNextMonthBtn"', self.index_html)
        self.assertIn('id="dividendTodayMonthBtn"', self.index_html)

        # Ledger panel
        self.assertIn('id="ledgerPrevMonthBtn"', self.index_html)
        self.assertIn('id="ledgerCurrentMonthText"', self.index_html)
        self.assertIn('id="ledgerMonthPicker"', self.index_html)
        self.assertIn('id="ledgerNextMonthBtn"', self.index_html)
        self.assertIn('id="ledgerTodayMonthBtn"', self.index_html)

        # All month pickers must be type="month"
        pnl_picker = re.search(r'<input\s+type="month"[^>]*id="pnlMonthPicker"', self.index_html)
        self.assertIsNotNone(pnl_picker)
        div_picker = re.search(r'<input\s+type="month"[^>]*id="dividendMonthPicker"', self.index_html)
        self.assertIsNotNone(div_picker)
        ledger_picker = re.search(r'<input\s+type="month"[^>]*id="ledgerMonthPicker"', self.index_html)
        self.assertIsNotNone(ledger_picker)

    # 3. IPO PAST month picker in wealth-ipo.js
    def test_ipo_past_month_picker_in_ipo_js(self):
        self.assertIn('id="ipoPrevMonthBtn"', self.wealth_ipo_js)
        self.assertIn('id="ipoCurrentMonthText"', self.wealth_ipo_js)
        self.assertIn('id="ipoMonthPicker"', self.wealth_ipo_js)
        self.assertIn('id="ipoNextMonthBtn"', self.wealth_ipo_js)
        self.assertIn('id="ipoTodayMonthBtn"', self.wealth_ipo_js)
        self.assertIn('<input type="month" id="ipoMonthPicker"', self.wealth_ipo_js)

    # 4. CSS styling classes
    def test_css_classes_support_unified_month_nav(self):
        self.assertIn(".money-month-nav", self.css)
        self.assertIn(".money-month-text", self.css)
        self.assertIn(".money-month-nav-btn", self.css)
        self.assertIn(".money-month-picker", self.css)
        # Check white and oled theme overrides
        self.assertIn('[data-theme="white"] .money-month-nav', self.css)
        self.assertIn('[data-theme="oled"] .money-month-nav', self.css)

    # 5. Realized PnL summary card filtering
    def test_realized_pnl_summary_cards_filtered_by_month(self):
        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync('{WEALTH_JS.as_posix()}', 'utf8');

        // Setup DOM simulation
        const elements = {{}};
        const makeElement = () => ({{
          textContent: '',
          value: '',
          style: {{}},
          classList: {{ toggle: () => {{}}, contains: () => false, add: () => {{}}, remove: () => {{}} }},
          setAttribute: () => {{}},
          addEventListener: () => {{}}
        }});
        const document = {{
          readyState: 'loading',
          documentElement: {{ removeAttribute: () => {{}}, setAttribute: () => {{}} }},
          getElementById: (id) => elements[id] || (elements[id] = makeElement()),
          querySelector: (sel) => {{
            if (sel.startsWith('#')) return document.getElementById(sel.slice(1));
            return null;
          }},
          querySelectorAll: () => [],
          addEventListener: () => {{}}
        }};
        const location = {{ hash: '' }};
        const navigator = {{ userAgent: 'node' }};
        const window = {{
          scrollY: 0,
          pageYOffset: 0,
          location,
          navigator,
          addEventListener: () => {{}},
          requestAnimationFrame: (cb) => cb(),
          scrollTo: () => {{}}
        }};

        const sandbox = {{
          window,
          location,
          navigator,
          document,
          localStorage: {{ getItem: () => null, setItem: () => {{}} }},
          Intl,
          Date,
          console
        }};
        vm.createContext(sandbox);

        // Load wealth.js in context
        vm.runInContext(code, sandbox);

        // Mock test data with 2 different months: 2026-08 and 2026-09
        const testData = {{
          records: [
            {{ id: '1', date: '2026-08-15', name: '종목A', pnl_krw: 100000, pnl: 100000 }},
            {{ id: '2', date: '2026-08-20', name: '종목B', pnl_krw: -30000, pnl: -30000 }},
            {{ id: '3', date: '2026-09-01', name: '종목C', pnl_krw: 500000, pnl: 500000 }},
            {{ id: '4', date: '2026-09-10', name: '종목D', pnl_krw: -100000, pnl: -100000 }},
          ],
          total_win_krw: 600000,
          total_loss_krw: -130000,
          win_count: 2,
          loss_count: 2,
          win_rate: 50,
          total_pnl_krw: 470000
        }};

        // Test month 8
        sandbox.window.setSelectedPnlPeriod("2026", 8);
        sandbox.renderRealizedPnl(testData);

        const outMonth8 = {{
          totalText: elements['pnlTotal']?.textContent,
          winText: elements['pnlTotalWin']?.textContent,
          lossText: elements['pnlTotalLoss']?.textContent,
          countText: elements['pnlTotalCount']?.textContent,
          winRateText: elements['pnlWinRate']?.textContent,
        }};

        // Test month 9
        sandbox.window.setSelectedPnlPeriod("2026", 9);
        sandbox.renderRealizedPnl(testData);

        const outMonth9 = {{
          totalText: elements['pnlTotal']?.textContent,
          winText: elements['pnlTotalWin']?.textContent,
          lossText: elements['pnlTotalLoss']?.textContent,
          countText: elements['pnlTotalCount']?.textContent,
          winRateText: elements['pnlWinRate']?.textContent,
        }};

        process.stdout.write(JSON.stringify({{ m8: outMonth8, m9: outMonth9 }}));
        """
        output = json.loads(self.run_node_eval(script))
        m8 = output["m8"]
        m9 = output["m9"]

        # Month 8: +100,000 -30,000 = +70,000 net, total 2 records
        self.assertIn("70,000", m8["totalText"])
        self.assertIn("100,000", m8["winText"])
        self.assertIn("30,000", m8["lossText"])
        self.assertIn("2건", m8["countText"])

        # Month 9: +500,000 -100,000 = +400,000 net, total 2 records
        self.assertIn("400,000", m9["totalText"])
        self.assertIn("500,000", m9["winText"])
        self.assertIn("100,000", m9["lossText"])
        self.assertIn("2건", m9["countText"])

    # 6. Trade type switching preserves selected month
    def test_pnl_trade_type_switch_preserves_selected_month(self):
        self.assertNotIn("selectedPnlMonth = null;\n    loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);", self.wealth_js)
        # Ensure selectedDividendMonth is also preserved in mode tabs
    # 7. Record Date Inputs are full YYYY-MM-DD and not converted to month-only
    def test_record_date_inputs_remain_full_date(self):
        # pnlDate must not be month
        self.assertNotIn('<input type="month" id="pnlDate"', self.index_html)
        # ledger transaction date must not be month
        self.assertNotIn('<input type="month" id="ledgerTxDate"', self.index_html)
        # dividend date must not be month
        self.assertNotIn('<input type="month" id="divDate"', self.index_html)

    # 8. Actual dividend summary cards filtering
    def test_actual_dividend_summary_cards_filtered_by_month(self):
        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync('{WEALTH_JS.as_posix()}', 'utf8');

        const elements = {{}};
        const makeElement = () => ({{
          textContent: '',
          value: '',
          style: {{}},
          classList: {{ toggle: () => {{}}, contains: () => false, add: () => {{}}, remove: () => {{}} }},
          setAttribute: () => {{}},
          addEventListener: () => {{}}
        }});
        const document = {{
          readyState: 'loading',
          documentElement: {{ removeAttribute: () => {{}}, setAttribute: () => {{}} }},
          getElementById: (id) => elements[id] || (elements[id] = makeElement()),
          querySelector: (sel) => {{
            if (sel.startsWith('#')) return document.getElementById(sel.slice(1));
            return null;
          }},
          querySelectorAll: () => [],
          addEventListener: () => {{}}
        }};
        const location = {{ hash: '' }};
        const navigator = {{ userAgent: 'node' }};
        const window = {{
          scrollY: 0,
          pageYOffset: 0,
          location,
          navigator,
          addEventListener: () => {{}},
          requestAnimationFrame: (cb) => cb(),
          scrollTo: () => {{}}
        }};

        const sandbox = {{
          window,
          location,
          navigator,
          document,
          localStorage: {{ getItem: () => null, setItem: () => {{}} }},
          Intl,
          Date,
          console
        }};
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const testDividendData = {{
          records: [
            {{ id: '1', date: '2026-08-10', name: '배당주A', code: '005930', amount_krw: 50000 }},
            {{ id: '2', date: '2026-08-25', name: '배당주B', code: '000660', amount_krw: 70000 }},
            {{ id: '3', date: '2026-09-15', name: '배당주C', code: '035420', amount_krw: 150000 }},
          ],
          total_actual_dividend_krw: 270000,
          paying_stock_count: 3,
          record_count: 3
        }};

        // Test month 8
        sandbox.window.setSelectedDividendPeriod("2026", 8);
        sandbox.renderActualDividends(testDividendData);

        const outMonth8 = {{
          totalText: elements['divTotalAnnual']?.textContent,
          countText: elements['divTotalHoldings']?.textContent,
          payingCountText: elements['divPayingCount']?.textContent,
        }};

        // Test month 9
        sandbox.window.setSelectedDividendPeriod("2026", 9);
        sandbox.renderActualDividends(testDividendData);

        const outMonth9 = {{
          totalText: elements['divTotalAnnual']?.textContent,
          countText: elements['divTotalHoldings']?.textContent,
          payingCountText: elements['divPayingCount']?.textContent,
        }};

        process.stdout.write(JSON.stringify({{ m8: outMonth8, m9: outMonth9 }}));
        """
        output = json.loads(self.run_node_eval(script))
        m8 = output["m8"]
        m9 = output["m9"]

        # Month 8: 50,000 + 70,000 = 120,000 KRW, 2 items, 2 paying stocks
        self.assertIn("120,000", m8["totalText"])
        self.assertIn("2건", m8["countText"])
        self.assertIn("2종목", m8["payingCountText"])

        # Month 9: 150,000 KRW, 1 item, 1 paying stock
        self.assertIn("150,000", m9["totalText"])
        self.assertIn("1건", m9["countText"])
        self.assertIn("1종목", m9["payingCountText"])

    # 9. Independent module states
    def test_independent_module_states(self):
        script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync('{WEALTH_JS.as_posix()}', 'utf8');

        const elements = {{}};
        const makeElement = () => ({{
          textContent: '',
          value: '',
          style: {{}},
          classList: {{ toggle: () => {{}}, contains: () => false, add: () => {{}}, remove: () => {{}} }},
          setAttribute: () => {{}},
          addEventListener: () => {{}}
        }});
        const document = {{
          readyState: 'loading',
          documentElement: {{ removeAttribute: () => {{}}, setAttribute: () => {{}} }},
          getElementById: (id) => elements[id] || (elements[id] = makeElement()),
          querySelector: (sel) => {{
            if (sel.startsWith('#')) return document.getElementById(sel.slice(1));
            return null;
          }},
          querySelectorAll: () => [],
          addEventListener: () => {{}}
        }};
        const location = {{ hash: '' }};
        const navigator = {{ userAgent: 'node' }};
        const window = {{
          scrollY: 0,
          pageYOffset: 0,
          location,
          navigator,
          addEventListener: () => {{}},
          requestAnimationFrame: (cb) => cb(),
          scrollTo: () => {{}}
        }};

        const sandbox = {{
          window,
          location,
          navigator,
          document,
          localStorage: {{ getItem: () => null, setItem: () => {{}} }},
          Intl,
          Date,
          console
        }};
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        // Change PnL period to 2025-05
        sandbox.window.setSelectedPnlPeriod("2025", 5);

        // Change Dividend period to 2026-11
        sandbox.window.setSelectedDividendPeriod("2026", 11);

        const out = {{
          pnlText: elements['pnlCurrentMonthText']?.textContent,
          pnlVal: elements['pnlMonthPicker']?.value,
          divText: elements['dividendCurrentMonthText']?.textContent,
          divVal: elements['dividendMonthPicker']?.value,
        }};

        process.stdout.write(JSON.stringify(out));
        """
        output = json.loads(self.run_node_eval(script))
        self.assertEqual(output["pnlText"], "2025년 5월")
        self.assertEqual(output["pnlVal"], "2025-05")
        self.assertEqual(output["divText"], "2026년 11월")
        self.assertEqual(output["divVal"], "2026-11")

    # 10. Dashboard overview cards request year=all and trade_type=all
    def test_overview_cards_all_time_untouched(self):
        self.assertIn("api(`/api/realized-pnl?owner=${encodeURIComponent(owner)}&year=all&trade_type=all`)", self.wealth_js)

    # 11. Accessible button interactive element checks
    def test_month_selectors_are_semantic_buttons(self):
        self.assertIn('<button type="button" id="pnlCurrentMonthText"', self.index_html)
        self.assertIn('<button type="button" id="dividendCurrentMonthText"', self.index_html)
        self.assertIn('<button type="button" id="ledgerCurrentMonthText"', self.index_html)
        self.assertIn('<button type="button" class="ipo-month-text money-month-text" id="ipoCurrentMonthText"', self.wealth_ipo_js)

    # 12. Actual dividend monthly ratio card label and subtext
    def test_actual_dividend_monthly_yield_label_clarification(self):
        self.assertIn('$("#divCardLabel2").textContent = "월간 배당 수령률"', self.wealth_js)
        self.assertIn('"선택 월 수령액 / 평가금액 기준"', self.wealth_js)


if __name__ == "__main__":
    unittest.main()
