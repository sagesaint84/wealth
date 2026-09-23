from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
CALENDAR_JS = ROOT / "app" / "static" / "wealth-calendar.js"


class MoneyLogCalendarFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node"):
            raise unittest.SkipTest("node runtime is not available")

    def run_node_eval(self, script: str) -> str:
        cmd = ["node"]
        res = subprocess.run(
            cmd,
            input=script,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return res.stdout.strip()

    def _execute_harness(self, test_body: str, today_kst: str = "2026-09-23") -> dict:
        calendar_path = CALENDAR_JS.as_posix()
        harness_script = f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync('{calendar_path}', 'utf8');

        function createHarness() {{
          const elements = {{}};

          class MockElement {{
            constructor(id = '', tag = 'div') {{
              this.id = id;
              this.tagName = tag.toUpperCase();
              this.textContent = '';
              this._innerHTML = '';
              this.dataset = {{}};
              const classSet = new Set();
              this.classList = {{
                _set: classSet,
                toggle: (cls, force) => {{
                  if (force === undefined) {{
                    if (classSet.has(cls)) {{ classSet.delete(cls); return false; }}
                    else {{ classSet.add(cls); return true; }}
                  }} else if (force) {{
                    classSet.add(cls); return true;
                  }} else {{
                    classSet.delete(cls); return false;
                  }}
                }},
                contains: (cls) => classSet.has(cls),
                remove: (...clss) => clss.forEach(c => classSet.delete(c)),
                add: (...clss) => clss.forEach(c => classSet.add(c)),
              }};
              this.hidden = false;
              this._eventListeners = {{}};
              this.children = [];
            }}

            set innerHTML(val) {{
              this._innerHTML = val;
              this.children = [];
              const buttonRegex = new RegExp('<button\\\\s+([^>]*?)>([\\\\s\\\\S]*?)<\\\\/button>', 'gi');
              let match;
              while ((match = buttonRegex.exec(val)) !== null) {{
                const attrs = match[1];
                const content = match[2];
                const btn = new MockElement('', 'button');
                btn._innerHTML = content;
                const classMatch = new RegExp('class=\\"([^\\"]*)\\"').exec(attrs);
                if (classMatch) {{
                  classMatch[1].trim().split(/\\s+/).forEach(c => btn.classList.add(c));
                }}
                const dateMatch = new RegExp('data-date=\\"([^\\"]*)\\"').exec(attrs);
                if (dateMatch) {{
                  btn.dataset.date = dateMatch[1];
                }}
                this.children.push(btn);
              }}
            }}

            get innerHTML() {{
              return this._innerHTML;
            }}

            addEventListener(event, fn) {{
              if (!this._eventListeners[event]) this._eventListeners[event] = [];
              this._eventListeners[event].push(fn);
            }}

            click() {{
              (this._eventListeners['click'] || []).forEach(fn => fn({{ target: this }}));
            }}

            querySelectorAll(selector) {{
              if (selector === '.cal-day-cell') {{
                return this.children.filter(c => c.classList.contains('cal-day-cell'));
              }}
              if (selector === '.cal-day-cell.is-selected') {{
                return this.children.filter(c => c.classList.contains('cal-day-cell') && c.classList.contains('is-selected'));
              }}
              return [];
            }}

            querySelector(selector) {{
              return this.querySelectorAll(selector)[0] || null;
            }}

            closest() {{ return this; }}
          }}

          function getEl(id) {{
            if (!elements[id]) elements[id] = new MockElement(id);
            return elements[id];
          }}

          const windowListeners = {{}};
          const mockWindow = {{
            addEventListener: (event, fn) => {{
              if (!windowListeners[event]) windowListeners[event] = [];
              windowListeners[event].push(fn);
            }},
            dispatchEvent: (evt) => {{
              (windowListeners[evt.type] || []).forEach(fn => fn(evt));
            }},
            WealthIpoDate: {{
              todayKst: () => '{today_kst}'
            }}
          }};

          const mockDocument = {{
            getElementById: (id) => getEl(id),
            querySelector: (sel) => {{
              if (sel === '.wealth-workspace') return {{ dataset: {{ activeView: 'income' }} }};
              if (sel === '#calendarPanel') return getEl('calendarPanel');
              if (sel.startsWith('#')) return getEl(sel.slice(1));
              return null;
            }},
            querySelectorAll: (sel) => {{
              if (sel === '.cal-day-cell.is-selected') {{
                return getEl('calendarGridWrapper').querySelectorAll(sel);
              }}
              return [];
            }}
          }};

          const eventsData = [
            {{ id: '1', date: '2026-09-23', type: 'realized_pnl', amount_krw: 50000, title: '테스트수익' }},
            {{ id: '2', date: '2026-09-18', type: 'dividend', amount_krw: 30000, title: '테스트배당', owner: '아빠' }},
            {{ id: '3', date: '2026-09-18', type: 'dividend', amount_krw: 20000, title: '엄마배당', owner: '엄마' }},
          ];

          const mockFetch = async (url) => {{
            if (url.includes('/api/ipo/applications')) {{
              return {{
                ok: true,
                json: async () => ({{ revision: 0, applications: {{}}, family_members: ['아빠', '엄마', '자녀'] }})
              }};
            }}
            if (url.includes('/api/moneylog/calendar')) {{
              return {{
                ok: true,
                json: async () => {{
                  const u = new URL(url, 'http://localhost');
                  const owner = decodeURIComponent(u.searchParams.get('owner') || '모두');
                  const filtered = eventsData.filter(e => owner === '모두' || e.owner === owner || !e.owner);
                  return {{ from: u.searchParams.get('from'), to: u.searchParams.get('to'), owner, events: filtered }};
                }}
              }};
            }}
            return {{ ok: false, status: 404 }};
          }};

          class CustomEvent {{
            constructor(type, init = {{}}) {{
              this.type = type;
              this.detail = init.detail;
            }}
          }}

          const sandbox = {{
            window: mockWindow,
            document: mockDocument,
            fetch: mockFetch,
            CustomEvent,
            URL,
            Intl,
            Date,
            console,
            alert: () => {{}},
          }};

          vm.createContext(sandbox);
          vm.runInContext(code, sandbox);
          return {{ sandbox, elements, mockWindow, getEl }};
        }}

        async function main() {{
          const harness = createHarness();
          {test_body}
        }}
        main().catch(err => {{ console.error(err); process.exit(1); }});
        """
        output_str = self.run_node_eval(harness_script)
        return json.loads(output_str)

    def test_1_initial_calendar_load_selects_kst_today(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        const selected = harness.sandbox.window.WealthCalendar.getSelectedDate();
        process.stdout.write(JSON.stringify({ selectedDate: selected }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertEqual(res["selectedDate"], "2026-09-23")

    def test_2_initial_calendar_load_today_cell_has_both_is_today_and_is_selected(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        const grid = harness.getEl('calendarGridWrapper');
        const cells = grid.querySelectorAll('.cal-day-cell');
        const cell23 = cells.find(c => c.dataset.date === '2026-09-23');
        process.stdout.write(JSON.stringify({
          found: Boolean(cell23),
          isToday: cell23 ? cell23.classList.contains('is-today') : false,
          isSelected: cell23 ? cell23.classList.contains('is-selected') : false
        }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertTrue(res["found"])
        self.assertTrue(res["isToday"])
        self.assertTrue(res["isSelected"])

    def test_3_initial_calendar_load_renders_detail_panel_for_today(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        const panel = harness.getEl('calendarDetailPanel');
        const label = harness.getEl('calendarDetailDateLabel');
        const list = harness.getEl('calendarDetailList');
        process.stdout.write(JSON.stringify({
          hidden: panel.hidden,
          labelText: label.textContent,
          hasEvents: list.innerHTML.includes('테스트수익')
        }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertFalse(res["hidden"])
        self.assertIn("2026-09-23", res["labelText"])
        self.assertTrue(res["hasEvents"])

    def test_4_explicit_user_selection_preserved_on_reload(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        const grid = harness.getEl('calendarGridWrapper');
        const cell18 = grid.querySelectorAll('.cal-day-cell').find(c => c.dataset.date === '2026-09-18');
        cell18.click();
        const selectedAfterClick = harness.sandbox.window.WealthCalendar.getSelectedDate();

        await harness.sandbox.window.loadCalendar();
        const selectedAfterReload = harness.sandbox.window.WealthCalendar.getSelectedDate();

        const label = harness.getEl('calendarDetailDateLabel');
        process.stdout.write(JSON.stringify({
          selectedAfterClick,
          selectedAfterReload,
          labelText: label.textContent
        }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertEqual(res["selectedAfterClick"], "2026-09-18")
        self.assertEqual(res["selectedAfterReload"], "2026-09-18")
        self.assertIn("2026-09-18", res["labelText"])

    def test_5_prev_month_navigation_does_not_arbitrarily_select_date_and_hides_detail(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        harness.getEl('calendarPrevMonthBtn').click();
        await new Promise(r => setTimeout(r, 20));

        const grid = harness.getEl('calendarGridWrapper');
        const cells = grid.querySelectorAll('.cal-day-cell');
        const anySelected = cells.some(c => c.classList.contains('is-selected'));
        const panel = harness.getEl('calendarDetailPanel');
        const currentYear = harness.sandbox.window.WealthCalendar.getCurrentYear();
        const currentMonth = harness.sandbox.window.WealthCalendar.getCurrentMonth();
        const selectedDate = harness.sandbox.window.WealthCalendar.getSelectedDate();

        process.stdout.write(JSON.stringify({
          currentYear,
          currentMonth,
          selectedDate,
          anySelected,
          panelHidden: panel.hidden
        }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertEqual(res["currentYear"], 2026)
        self.assertEqual(res["currentMonth"], 8)
        self.assertFalse(res["anySelected"])
        self.assertTrue(res["panelHidden"])
        self.assertEqual(res["selectedDate"], "2026-09-23")

    def test_6_today_button_navigates_to_today_month_and_selects_today(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        // Move to August
        harness.getEl('calendarPrevMonthBtn').click();
        await new Promise(r => setTimeout(r, 20));

        // Click Today button
        harness.getEl('calendarTodayBtn').click();
        await new Promise(r => setTimeout(r, 20));

        const grid = harness.getEl('calendarGridWrapper');
        const cell23 = grid.querySelectorAll('.cal-day-cell').find(c => c.dataset.date === '2026-09-23');
        const panel = harness.getEl('calendarDetailPanel');
        const label = harness.getEl('calendarDetailDateLabel');

        process.stdout.write(JSON.stringify({
          currentYear: harness.sandbox.window.WealthCalendar.getCurrentYear(),
          currentMonth: harness.sandbox.window.WealthCalendar.getCurrentMonth(),
          selectedDate: harness.sandbox.window.WealthCalendar.getSelectedDate(),
          isToday: cell23 ? cell23.classList.contains('is-today') : false,
          isSelected: cell23 ? cell23.classList.contains('is-selected') : false,
          panelHidden: panel.hidden,
          labelText: label.textContent
        }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertEqual(res["currentYear"], 2026)
        self.assertEqual(res["currentMonth"], 9)
        self.assertEqual(res["selectedDate"], "2026-09-23")
        self.assertTrue(res["isToday"])
        self.assertTrue(res["isSelected"])
        self.assertFalse(res["panelHidden"])
        self.assertIn("2026-09-23", res["labelText"])

    def test_7_closing_detail_panel_prevents_auto_today_reselection_on_reload(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        // Explicitly close detail panel
        harness.getEl('calendarDetailCloseBtn').click();

        const selectedAfterClose = harness.sandbox.window.WealthCalendar.getSelectedDate();
        const panelHiddenAfterClose = harness.getEl('calendarDetailPanel').hidden;

        // Perform calendar reload
        await harness.sandbox.window.loadCalendar();

        const selectedAfterReload = harness.sandbox.window.WealthCalendar.getSelectedDate();
        const panelHiddenAfterReload = harness.getEl('calendarDetailPanel').hidden;
        const grid = harness.getEl('calendarGridWrapper');
        const anySelected = grid.querySelectorAll('.cal-day-cell').some(c => c.classList.contains('is-selected'));

        process.stdout.write(JSON.stringify({
          selectedAfterClose,
          panelHiddenAfterClose,
          selectedAfterReload,
          panelHiddenAfterReload,
          anySelected
        }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertIsNone(res["selectedAfterClose"])
        self.assertTrue(res["panelHiddenAfterClose"])
        self.assertIsNone(res["selectedAfterReload"])
        self.assertTrue(res["panelHiddenAfterReload"])
        self.assertFalse(res["anySelected"])

    def test_8_owner_change_preserves_explicit_selection_and_filters_events(self):
        body = """
        await harness.sandbox.window.loadCalendar();
        const grid = harness.getEl('calendarGridWrapper');
        const cell18 = grid.querySelectorAll('.cal-day-cell').find(c => c.dataset.date === '2026-09-18');
        cell18.click();

        // Trigger owner change to '아빠'
        harness.mockWindow.dispatchEvent(new harness.sandbox.CustomEvent('wealth:owner', { detail: { owner: '아빠' } }));
        await new Promise(r => setTimeout(r, 20));

        const selectedAfterOwner = harness.sandbox.window.WealthCalendar.getSelectedDate();
        const label = harness.getEl('calendarDetailDateLabel');
        const list = harness.getEl('calendarDetailList');

        process.stdout.write(JSON.stringify({
          selectedAfterOwner,
          labelText: label.textContent,
          hasAppaEvent: list.innerHTML.includes('테스트배당'),
          hasUmmaEvent: list.innerHTML.includes('엄마배당')
        }));
        """
        res = self._execute_harness(body, today_kst="2026-09-23")
        self.assertEqual(res["selectedAfterOwner"], "2026-09-18")
        self.assertIn("2026-09-18", res["labelText"])
        self.assertTrue(res["hasAppaEvent"])
        self.assertFalse(res["hasUmmaEvent"])


if __name__ == "__main__":
    unittest.main()
