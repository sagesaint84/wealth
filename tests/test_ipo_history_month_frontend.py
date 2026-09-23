from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _run_js_suite(script_body: str) -> str:
    source = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
    harness = f"""
const fs = require('fs');

// Minimal DOM simulation
class MockElement {{
  constructor(tag = 'div', id = '') {{
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.className = '';
    this.children = [];
    this.dataset = {{}};
    this.attributes = {{}};
    this.listeners = {{}};
    this._innerHTML = '';
    this.disabled = false;
    this.checked = false;
    this.indeterminate = false;
    this.value = '';
  }}

  get innerHTML() {{
    return this._innerHTML;
  }}

  get textContent() {{
    if (this.children.length === 0) return this._innerHTML;
    return this.children.map(c => c.textContent).join('');
  }}

  set innerHTML(html) {{
    this._innerHTML = html;
    this.children = [];
    const root = this;
    const stack = [root];

    const tokenRegex = /<!--[\\s\\S]*?-->|<(\\/)?([a-z0-9-]+)([^>]*)>|([^<]+)/gi;
    let match;
    while ((match = tokenRegex.exec(html)) !== null) {{
      if (match[0].startsWith('<!--')) continue;
      const isClose = Boolean(match[1]);
      const tag = match[2] ? match[2].toLowerCase() : null;
      const attrsStr = match[3] || '';
      const text = match[4];

      if (text) {{
        const current = stack[stack.length - 1];
        if (current && current !== root) {{
          current._innerHTML = (current._innerHTML || '') + text;
        }}
      }} else if (isClose) {{
        if (stack.length > 1 && stack[stack.length - 1].tagName.toLowerCase() === tag) {{
          stack.pop();
        }}
      }} else if (tag) {{
        const isSelfClosing = attrsStr.trim().endsWith('/') || ['input', 'img', 'br', 'hr'].includes(tag);
        const el = new MockElement(tag);
        const idMatch = attrsStr.match(/\\bid=["']([^"']+)["']/i);
        if (idMatch) el.id = idMatch[1];
        const classMatch = attrsStr.match(/\\bclass=["']([^"']+)["']/i);
        if (classMatch) el.className = classMatch[1];
        const disabledMatch = attrsStr.match(/\\bdisabled\\b/i);
        if (disabledMatch) el.disabled = true;

        const dataRegex = /\\bdata-([a-z0-9-]+)=["']([^"']*)["']/gi;
        let dataMatch;
        while ((dataMatch = dataRegex.exec(attrsStr)) !== null) {{
          const camelKey = dataMatch[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
          el.dataset[camelKey] = dataMatch[2];
        }}
        el.closest = (selector) => {{
          if (selector === '.ipo-card' && (el.className.includes('ipo-card') || el.tagName === 'ARTICLE')) return el;
          return root;
        }};

        const current = stack[stack.length - 1];
        current.children.push(el);

        if (!isSelfClosing) {{
          stack.push(el);
        }}
      }}
    }}
  }}

  addEventListener(event, fn) {{
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }}

  dispatchEvent(event) {{
    const ev = typeof event === 'string' ? {{ type: event }} : event;
    (this.listeners[ev.type] || []).forEach(fn => fn(ev));
  }}

  click() {{
    this.dispatchEvent({{ type: 'click' }});
  }}

  querySelector(selector) {{
    return this.querySelectorAll(selector)[0] || null;
  }}

  querySelectorAll(selector) {{
    const results = [];
    const check = (node) => {{
      let match = false;
      if (selector.startsWith('#')) {{
        match = node.id === selector.slice(1);
      }} else if (selector === 'article') {{
        match = node.tagName === 'ARTICLE';
      }} else if (selector === '.ipo-card') {{
        match = node.className.split(/\\s+/).includes('ipo-card') || node.tagName === 'ARTICLE';
      }} else if (selector.includes('.ipo-filter')) {{
        const hasClass = node.className.split(/\\s+/).includes('ipo-filter');
        const valMatch = selector.match(/data-filter-group="?([^"\\]]+)"?/);
        if (valMatch) {{
          match = hasClass && node.dataset.filterGroup === valMatch[1];
        }} else {{
          match = hasClass;
        }}
      }}
      if (match) results.push(node);
      (node.children || []).forEach(check);
    }};
    (this.children || []).forEach(check);
    return results;
  }}
}}

const mockWrapper = new MockElement('div', 'ipoListWrapper');
globalThis.window = {{
  addEventListener: () => {{}},
  dispatchEvent: () => {{}},
  confirm: () => true,
  alert: () => {{}},
}};
globalThis.document = {{
  getElementById: (id) => (id === 'ipoListWrapper' ? mockWrapper : null),
  createElement: (tag) => new MockElement(tag),
}};
globalThis.CustomEvent = function CustomEvent(type, opts) {{
  this.type = type;
  this.detail = opts ? opts.detail : null;
}};

eval({json.dumps(source)});

{script_body}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
        handle.write(harness)
        script_path = handle.name
    try:
        proc = subprocess.run(["node", script_path], cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"node script failed (exit {proc.returncode}):\n{proc.stderr}\nSTDOUT:\n{proc.stdout}")
        return proc.stdout.strip()
    finally:
        Path(script_path).unlink(missing_ok=True)


class IpoHistoryMonthFrontendTests(unittest.TestCase):
    def test_past_descending_and_upcoming_active_ascending_sort(self):
        script = """
        const testData = [
          { ipo_id: 'ipo-1', company_name: '과거1', filter_group: 'PAST', presentation_sort_date: '2026-08-10' },
          { ipo_id: 'ipo-2', company_name: '과거2', filter_group: 'PAST', presentation_sort_date: '2026-08-25' },
          { ipo_id: 'ipo-3', company_name: '과거3', filter_group: 'PAST', presentation_sort_date: '2026-08-15' },
          { ipo_id: 'up-1', company_name: '예정1', filter_group: 'UPCOMING', presentation_sort_date: '2026-10-20' },
          { ipo_id: 'up-2', company_name: '예정2', filter_group: 'UPCOMING', presentation_sort_date: '2026-10-05' },
        ];
        window.WealthIpoState.setMarketIpos(testData);

        // 1. PAST: should sort DESC (2026-08-25 first, then 08-15, then 08-10)
        window.WealthIpoState.setFilterGroup('PAST');
        window.WealthIpoState.setHistoryYear(2026);
        window.WealthIpoState.setHistoryMonth(8);
        window.WealthIpoState.setHistoryInitialized(true);
        window.WealthIpoState.renderIpoList();

        const cards = mockWrapper.querySelectorAll('.ipo-card');
        const pastOrder = cards.map(c => c.dataset.ipoId);

        // 2. UPCOMING: should sort ASC (2026-10-05 first, then 10-20)
        window.WealthIpoState.setFilterGroup('UPCOMING');
        window.WealthIpoState.renderIpoList();
        const upCards = mockWrapper.querySelectorAll('.ipo-card');
        const upOrder = upCards.map(c => c.dataset.ipoId);

        process.stdout.write(JSON.stringify({ pastOrder, upOrder }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertEqual(output["pastOrder"], ["ipo-2", "ipo-3", "ipo-1"])
        self.assertEqual(output["upOrder"], ["up-2", "up-1"])

    def test_default_to_latest_past_month(self):
        script = """
        const testData = [
          { ipo_id: 'ipo-july', company_name: '7월종목', filter_group: 'PAST', presentation_sort_date: '2026-07-20' },
          { ipo_id: 'ipo-aug1', company_name: '8월종목1', filter_group: 'PAST', presentation_sort_date: '2026-08-01' },
          { ipo_id: 'ipo-aug2', company_name: '8월종목2', filter_group: 'PAST', presentation_sort_date: '2026-08-28' },
        ];
        window.WealthIpoState.setHistoryInitialized(false);
        window.WealthIpoState.setHistoryYear(null);
        window.WealthIpoState.setHistoryMonth(null);
        window.WealthIpoState.setMarketIpos(testData);

        window.WealthIpoState.setFilterGroup('PAST');
        window.WealthIpoState.renderIpoList();

        const year = window.WealthIpoState.getHistoryYear();
        const month = window.WealthIpoState.getHistoryMonth();
        const cards = mockWrapper.querySelectorAll('.ipo-card').map(c => c.dataset.ipoId);

        process.stdout.write(JSON.stringify({ year, month, cards }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertEqual(output["year"], 2026)
        self.assertEqual(output["month"], 8)
        self.assertEqual(output["cards"], ["ipo-aug2", "ipo-aug1"])

    def test_all_uses_current_month_and_includes_every_status_ascending(self):
        script = """
        const cur = window.WealthIpoDate.currentKstYearMonth();
        const testData = [
          { ipo_id: 'past-sep', company_name: '과거', filter_group: 'PAST', presentation_sort_date: '2026-09-20' },
          { ipo_id: 'active-sep', company_name: '진행', filter_group: 'ACTIVE', presentation_sort_date: '2026-09-10' },
          { ipo_id: 'upcoming-sep', company_name: '예정', filter_group: 'UPCOMING', presentation_sort_date: '2026-09-05' },
          { ipo_id: 'other-month', company_name: '다른월', filter_group: 'PAST', presentation_sort_date: '2026-08-30' },
          { ipo_id: 'invalid-date', company_name: '일정미정', filter_group: 'ACTIVE', presentation_sort_date: 'not-a-date' },
        ];
        window.WealthIpoState.setMarketIpos(testData);
        window.WealthIpoState.setFilterGroup('ALL');
        window.WealthIpoState.renderIpoList();
        process.stdout.write(JSON.stringify({
          cur,
          year: window.WealthIpoState.getHistoryYear(),
          month: window.WealthIpoState.getHistoryMonth(),
          cards: mockWrapper.querySelectorAll('.ipo-card').map(c => c.dataset.ipoId),
          html: mockWrapper.innerHTML,
        }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertEqual(output["cur"], {"year": 2026, "month": 9, "key": "2026-09"})
        self.assertEqual((output["year"], output["month"]), (2026, 9))
        self.assertEqual(output["cards"][:3], ["upcoming-sep", "active-sep", "past-sep"])
        self.assertNotIn("other-month", output["cards"])
        self.assertIn("invalid-date", output["cards"])
        self.assertIn("전체 5", output["html"])
        self.assertIn("예정 1", output["html"])
        self.assertIn("진행 2", output["html"])
        self.assertIn("과거 2", output["html"])
        self.assertIn("9월 · 3건", output["html"])

    def test_all_first_visit_does_not_consume_past_default_and_explicit_month_is_shared(self):
        script = """
        const testData = [
          { ipo_id: 'past-july', company_name: '7월', filter_group: 'PAST', presentation_sort_date: '2026-07-21' },
          { ipo_id: 'past-aug', company_name: '8월', filter_group: 'PAST', presentation_sort_date: '2026-08-22' },
          { ipo_id: 'active-sep', company_name: '9월', filter_group: 'ACTIVE', presentation_sort_date: '2026-09-10' },
        ];
        window.WealthIpoState.setMarketIpos(testData);
        window.WealthIpoState.setFilterGroup('ALL');
        window.WealthIpoState.renderIpoList();
        const allFirst = [window.WealthIpoState.getHistoryYear(), window.WealthIpoState.getHistoryMonth()];
        mockWrapper.querySelector('.ipo-filter[data-filter-group="PAST"]').click();
        const pastFirst = [window.WealthIpoState.getHistoryYear(), window.WealthIpoState.getHistoryMonth()];
        mockWrapper.querySelector('#ipoPrevMonthBtn').click();
        mockWrapper.querySelector('.ipo-filter[data-filter-group="ALL"]').click();
        process.stdout.write(JSON.stringify({
          allFirst, pastFirst,
          selected: [window.WealthIpoState.getHistoryYear(), window.WealthIpoState.getHistoryMonth()],
          explicit: window.WealthIpoState.isMonthExplicitlySelected(),
        }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertEqual(output["allFirst"], [2026, 9])
        self.assertEqual(output["pastFirst"], [2026, 8])
        self.assertEqual(output["selected"], [2026, 7])
        self.assertTrue(output["explicit"])

    def test_empty_month_and_navigation_stepping(self):
        script = """
        const testData = [
          { ipo_id: 'ipo-aug', company_name: '8월종목', filter_group: 'PAST', presentation_sort_date: '2026-08-15' },
        ];
        window.WealthIpoState.setMarketIpos(testData);
        window.WealthIpoState.setFilterGroup('PAST');
        window.WealthIpoState.setHistoryYear(2026);
        window.WealthIpoState.setHistoryMonth(7);
        window.WealthIpoState.setHistoryInitialized(true);
        window.WealthIpoState.renderIpoList();

        const htmlJuly = mockWrapper.innerHTML;
        const cardsJuly = mockWrapper.querySelectorAll('.ipo-card').length;
        const hasEmptyTextJuly = htmlJuly.includes('선택한 월(2026년 7월)에 해당하는 과거 공모주 일정이 없습니다');
        const countBadgeJuly = htmlJuly.includes('7월 · 0건');

        const nextBtn = mockWrapper.querySelector('#ipoNextMonthBtn');
        nextBtn.click();

        const yearAug = window.WealthIpoState.getHistoryYear();
        const monthAug = window.WealthIpoState.getHistoryMonth();
        const cardsAug = mockWrapper.querySelectorAll('.ipo-card').length;

        mockWrapper.querySelector('#ipoPrevMonthBtn').click();
        mockWrapper.querySelector('#ipoPrevMonthBtn').click();
        const yearJune = window.WealthIpoState.getHistoryYear();
        const monthJune = window.WealthIpoState.getHistoryMonth();

        process.stdout.write(JSON.stringify({
          cardsJuly,
          hasEmptyTextJuly,
          countBadgeJuly,
          yearAug,
          monthAug,
          cardsAug,
          yearJune,
          monthJune,
        }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertEqual(output["cardsJuly"], 0)
        self.assertTrue(output["hasEmptyTextJuly"])
        self.assertTrue(output["countBadgeJuly"])
        self.assertEqual(output["yearAug"], 2026)
        self.assertEqual(output["monthAug"], 8)
        self.assertEqual(output["cardsAug"], 1)
        self.assertEqual(output["yearJune"], 2026)
        self.assertEqual(output["monthJune"], 6)

    def test_year_boundary_wrapping(self):
        script = """
        const shiftedBack = window.WealthIpoDate.shiftIpoMonth(2026, 1, -1);
        const shiftedForward = window.WealthIpoDate.shiftIpoMonth(2025, 12, 1);
        process.stdout.write(JSON.stringify({ shiftedBack, shiftedForward }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertEqual(output["shiftedBack"], {"year": 2025, "month": 12, "key": "2025-12"})
        self.assertEqual(output["shiftedForward"], {"year": 2026, "month": 1, "key": "2026-01"})

    def test_today_button_resets_to_kst_current_month(self):
        script = """
        const curKst = window.WealthIpoDate.currentKstYearMonth();
        const testData = [{ ipo_id: 'p-item', company_name: '과거아이템', filter_group: 'PAST', presentation_sort_date: '2026-08-10' }];
        window.WealthIpoState.setMarketIpos(testData);
        window.WealthIpoState.setFilterGroup('PAST');
        window.WealthIpoState.setHistoryYear(2025);
        window.WealthIpoState.setHistoryMonth(3);
        window.WealthIpoState.setHistoryInitialized(true);
        window.WealthIpoState.renderIpoList();

        const todayBtn = mockWrapper.querySelector('#ipoTodayMonthBtn');
        todayBtn.click();

        const finalYear = window.WealthIpoState.getHistoryYear();
        const finalMonth = window.WealthIpoState.getHistoryMonth();

        process.stdout.write(JSON.stringify({ curKst, finalYear, finalMonth }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertEqual(output["finalYear"], output["curKst"]["year"])
        self.assertEqual(output["finalMonth"], output["curKst"]["month"])

    def test_tab_switch_preserves_selected_month_and_count_separation(self):
        script = """
        const testData = [
          { ipo_id: 'p1', company_name: '과거1', filter_group: 'PAST', presentation_sort_date: '2026-08-10' },
          { ipo_id: 'p2', company_name: '과거2', filter_group: 'PAST', presentation_sort_date: '2026-08-20' },
          { ipo_id: 'p3', company_name: '과거3', filter_group: 'PAST', presentation_sort_date: '2026-07-05' },
          { ipo_id: 'a1', company_name: '진행1', filter_group: 'ACTIVE', presentation_sort_date: '2026-09-15' },
        ];
        window.WealthIpoState.setMarketIpos(testData);
        window.WealthIpoState.setHistoryYear(2026);
        window.WealthIpoState.setHistoryMonth(7);
        window.WealthIpoState.setHistoryInitialized(true);

        window.WealthIpoState.setFilterGroup('PAST');
        window.WealthIpoState.renderIpoList();

        const pastBtnText = mockWrapper.querySelector('.ipo-filter[data-filter-group="PAST"]').innerHTML;
        const pastTabCards = mockWrapper.querySelectorAll('.ipo-card').map(c => c.dataset.ipoId);

        const activeFilterBtn = mockWrapper.querySelector('.ipo-filter[data-filter-group="ACTIVE"]');
        activeFilterBtn.click();
        const activeTabCards = mockWrapper.querySelectorAll('.ipo-card').map(c => c.dataset.ipoId);
        const hasMonthControlInActive = Boolean(mockWrapper.querySelector('#ipoPrevMonthBtn'));

        const pastFilterBtn = mockWrapper.querySelector('.ipo-filter[data-filter-group="PAST"]');
        pastFilterBtn.click();

        const yearAfterReturn = window.WealthIpoState.getHistoryYear();
        const monthAfterReturn = window.WealthIpoState.getHistoryMonth();
        const pastCardsAfterReturn = mockWrapper.querySelectorAll('.ipo-card').map(c => c.dataset.ipoId);

        process.stdout.write(JSON.stringify({
          pastTabCards,
          pastTotalCountInFilterBtn: pastBtnText,
          activeTabCards,
          hasMonthControlInActive,
          yearAfterReturn,
          monthAfterReturn,
          pastCardsAfterReturn,
        }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertIn("과거 3", output["pastTotalCountInFilterBtn"])
        self.assertEqual(output["pastTabCards"], ["p3"])
        self.assertEqual(output["activeTabCards"], ["a1"])
        self.assertFalse(output["hasMonthControlInActive"])
        self.assertEqual(output["yearAfterReturn"], 2026)
        self.assertEqual(output["monthAfterReturn"], 7)
        self.assertEqual(output["pastCardsAfterReturn"], ["p3"])

    def test_invalid_sort_date_fallback(self):
        script = """
        const testData = [
          { ipo_id: 'p-valid', company_name: '유효과거', filter_group: 'PAST', presentation_sort_date: '2026-08-10' },
          { ipo_id: 'p-nodate', company_name: '날짜없음과거', filter_group: 'PAST', presentation_sort_date: '' },
          { ipo_id: 'p-bad', company_name: '날짜오류과거', filter_group: 'PAST', presentation_sort_date: 'invalid-date' },
        ];
        window.WealthIpoState.setMarketIpos(testData);
        window.WealthIpoState.setFilterGroup('PAST');
        window.WealthIpoState.setHistoryYear(2026);
        window.WealthIpoState.setHistoryMonth(8);
        window.WealthIpoState.setHistoryInitialized(true);
        window.WealthIpoState.renderIpoList();

        const html = mockWrapper.innerHTML;
        const allCardIds = mockWrapper.querySelectorAll('.ipo-card').map(c => c.dataset.ipoId);
        const hasFallbackHeading = html.includes('기타 / 일정 미확인 과거 공모주');

        process.stdout.write(JSON.stringify({ allCardIds, hasFallbackHeading }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertIn("p-valid", output["allCardIds"])
        self.assertIn("p-nodate", output["allCardIds"])
        self.assertIn("p-bad", output["allCardIds"])
        self.assertTrue(output["hasFallbackHeading"])

    def test_future_month_disabled(self):
        script = """
        const curKst = window.WealthIpoDate.currentKstYearMonth();
        const testData = [{ ipo_id: 'p-item', company_name: '과거아이템', filter_group: 'PAST', presentation_sort_date: '2026-08-10' }];
        window.WealthIpoState.setMarketIpos(testData);
        window.WealthIpoState.setFilterGroup('PAST');
        window.WealthIpoState.setHistoryYear(curKst.year);
        window.WealthIpoState.setHistoryMonth(curKst.month);
        window.WealthIpoState.setHistoryInitialized(true);
        window.WealthIpoState.renderIpoList();

        const nextBtn = mockWrapper.querySelector('#ipoNextMonthBtn');
        const isDisabledAtCurrent = nextBtn ? nextBtn.disabled : false;

        mockWrapper.querySelector('#ipoPrevMonthBtn').click();
        const nextBtnPast = mockWrapper.querySelector('#ipoNextMonthBtn');
        const isDisabledAtPast = nextBtnPast ? nextBtnPast.disabled : true;

        process.stdout.write(JSON.stringify({ isDisabledAtCurrent, isDisabledAtPast }));
        """
        output = json.loads(_run_js_suite(script))
        self.assertTrue(output["isDisabledAtCurrent"])
        self.assertFalse(output["isDisabledAtPast"])


if __name__ == "__main__":
    unittest.main()
