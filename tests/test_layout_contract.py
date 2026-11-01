"""Static shell contract; interactive checks use the isolated ui_preview server."""
import unittest
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.ids = []
        self.scripts = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'script' and 'src' in attrs:
            self.scripts.append(attrs['src'].split('?')[0])


class SectionHeaderElements(HTMLParser):
    """Inspect real header nodes and their original controls without rendering."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, source):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'parent': self.stack[-1] if self.stack else None, 'children': [], 'text': ''}
        if self.stack:
            self.stack[-1]['children'].append(node)
        self.nodes.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]['text'] += data


class LayoutContractTests(unittest.TestCase):
    def test_account_list_uses_page_scroll_and_mobile_bank_cards(self):
        source = (STATIC / 'wealth-layout.css').read_text(encoding='utf-8')
        self.assertIn('#accountList.account-list { max-height: none; overflow-y: visible; }', source)
        self.assertIn('.banks-table { display: block; min-width: 0;', source)

    def test_destructive_action_disclosure_preserves_existing_buttons(self):
        source = (STATIC / 'wealth-layout.js').read_text(encoding='utf-8')
        self.assertIn('more.append(summary, button)', source)
        self.assertIn("button.closest('.wealth-row-more')", source)
        self.assertIn('childList: true, subtree: true', source)

    def test_existing_panel_and_action_ids_remain_unique(self):
        elements = Elements((STATIC / 'index.html').read_text(encoding='utf-8'))
        self.assertFalse([key for key, count in Counter(elements.ids).items() if count > 1])
        for key in ('marketPanel', 'summaryPanel', 'accountsPanel', 'holdingsPanel',
                    'recordsPanel', 'assetHeatmapPanel', 'realizedPnlPanel', 'dividendPanel',
                    'ledgerSectionPanel', 'topbarFamilyTabs', 'refreshButton', 'exportButton',
                    'importBackupBtn', 'clearButton', 'loanAccountForm'):
            with self.subTest(id=key):
                self.assertIn(key, elements.ids)

    def test_layout_listener_is_installed_before_financial_renderer(self):
        elements = Elements((STATIC / 'index.html').read_text(encoding='utf-8'))
        self.assertLess(elements.scripts.index('/static/wealth-layout.js'),
                        elements.scripts.index('/static/wealth.js'))

    def test_presentation_layer_has_no_api_or_persistence(self):
        source = (STATIC / 'wealth-layout.js').read_text(encoding='utf-8')
        for forbidden in ('fetch(', 'localStorage.setItem', '/api/', 'applied_delta', 'eval('):
            self.assertNotIn(forbidden, source)
        self.assertIn("addEventListener('wealth:summary'", source)

    def test_home_asset_donut_has_keyed_hover_contract(self):
        source = (STATIC / 'wealth-layout.js').read_text(encoding='utf-8')
        self.assertIn('key:`asset-${index}`', source)
        self.assertIn('row.dataset.donutKey=item.key', source)
        self.assertIn('window.WealthDonutHitTest = donutKeyAtPointer', source)
        self.assertIn('row.onpointerenter=()=>activate(row.dataset.donutKey)', source)
        self.assertIn('row.onfocus=()=>activate(row.dataset.donutKey)', source)
        self.assertIn('donut.onpointerleave=()=>activate(null)', source)

    def test_stock_sector_donut_preserves_filter_and_keyed_interaction(self):
        source = (STATIC / 'wealth.js').read_text(encoding='utf-8')
        self.assertIn('const donutKey = `classification:${String(s.name || \'\')}`', source)
        self.assertIn('data-sector-filter="${html(s.name)}" data-color-key="${html(window.WealthColorPreferences.keyFor(\'stock_category_colors\',s))}" data-donut-key="${html(donutKey)}"', source)
        self.assertIn("bindSectorDonutInteractions(wrap.querySelector('.sector-donut-container'))", source)
        self.assertIn("filterHoldingsByClassification(node.dataset.sectorFilter)", source)
        self.assertIn("event.key === 'Enter' || event.key === ' '", source)

    def test_strategy_and_history_interaction_contracts_are_scoped(self):
        source = (STATIC / 'wealth-planning.js').read_text(encoding='utf-8')
        css = (STATIC / 'wealth-layout.css').read_text(encoding='utf-8')
        self.assertIn('data-bucket-chart="target"', source)
        self.assertIn('data-bucket-chart="current"', source)
        self.assertIn('data-bucket-key="${esc(item.id)}"', source)
        self.assertIn('data-history-date="${esc(r.date)}"', source)
        self.assertIn('data-history-date="${esc(records[i].date)}"', source)
        self.assertIn('<div class="wealth-history-record-head"><time datetime="${esc(r.date)}">${esc(r.date)}</time><strong>${won(r.net_worth)}</strong></div>', source)
        self.assertIn('<p class="wealth-history-record-change"><span>직전 기록 대비</span><strong class="wealth-history-delta ${changeClass}">${changeText}</strong></p>', source)
        self.assertNotIn('wealth-history-value-cluster', source)
        self.assertIn("node.addEventListener('focusin'", source)
        self.assertNotIn('scrollIntoView(', source)
        self.assertIn('data-history-edit="${esc(r.date)}"', source)
        self.assertIn('data-history-delete="${esc(r.date)}"', source)
        self.assertIn('.wealth-history-delta.is-positive { color:#ef4444;', css)
        self.assertIn('.wealth-history-delta.is-negative { color:#3b82f6;', css)


    def test_m2_section_header_is_shared_by_two_section_level_headings(self):
        tree = SectionHeaderElements((STATIC / 'index.html').read_text(encoding='utf-8'))
        headers = [n for n in tree.nodes if n['attrs'].get('data-ui') == 'section-header']
        self.assertEqual(len(headers), 2)
        expected = {'realizedPnlPanel': ('PROFIT & LOSS', '실현손익'), 'dividendPanel': ('DIVIDEND', '배당금')}
        self.assertEqual({n['parent']['attrs'].get('id') for n in headers}, set(expected))
        for node in headers:
            panel = node['parent']['attrs']['id']
            with self.subTest(panel=panel):
                self.assertEqual(node['tag'], 'div')
                self.assertEqual(set(node['attrs']['class'].split()), {'panel-head', 'dividend-head', 'wealth-ui-section-header'})
                self.assertNotIn('style', node['attrs'])
                self.assertNotIn('role', node['attrs'])
                self.assertNotIn('tabindex', node['attrs'])
                self.assertEqual(len(node['children']), 4)
                leading = node['children'][0]
                self.assertIn('dividend-title-wrap', leading['attrs']['class'].split())
                self.assertIn('wealth-ui-section-header__leading', leading['attrs']['class'].split())
                group = leading['children'][0]
                self.assertEqual(group['attrs']['class'], 'wealth-ui-section-header__heading')
                self.assertEqual([c['tag'] for c in group['children']], ['p', 'h2'])
                self.assertEqual(tuple(c['text'].strip() for c in group['children']), expected[panel])
                self.assertEqual(node['children'][-1]['attrs']['class'], 'toolbar wealth-ui-section-header__actions')

    def test_m2_header_controls_keep_native_ids_order_and_accessible_names(self):
        tree = SectionHeaderElements((STATIC / 'index.html').read_text(encoding='utf-8'))
        ids = {n['attrs']['id']: n for n in tree.nodes if 'id' in n['attrs']}
        for prefix, actions in (('pnl', ('addPnlBtn', 'importPnlBtn', 'clearAllPnlBtn')),
                                ('dividend', ('refreshDividendBtn', 'addDividendBtn', 'importDividendBtn', 'clearAllDividendBtn'))):
            with self.subTest(prefix=prefix):
                nav = ids[prefix + 'PrevMonthBtn']['parent']
                self.assertEqual(nav['attrs']['role'], 'group')
                self.assertTrue(nav['attrs']['aria-label'])
                self.assertEqual([c['attrs'].get('id') for c in nav['children']],
                                 [prefix + 'PrevMonthBtn', prefix + 'CurrentMonthText', prefix + 'MonthPicker', prefix + 'NextMonthBtn', prefix + 'TodayMonthBtn'])
                for suffix in ('PrevMonthBtn', 'CurrentMonthText', 'NextMonthBtn', 'TodayMonthBtn'):
                    button = ids[prefix + suffix]
                    self.assertEqual((button['tag'], button['attrs']['type']), ('button', 'button'))
                    self.assertTrue(button['attrs']['aria-label'])
                self.assertEqual(ids[prefix + 'MonthPicker']['attrs']['type'], 'month')
                self.assertEqual(ids[prefix + 'YearSelect']['tag'], 'select')
                toolbar = ids[actions[0]]['parent']
                self.assertEqual([c['attrs'].get('id') for c in toolbar['children']], list(actions))
                for action_id in actions:
                    self.assertEqual(ids[action_id]['attrs']['type'], 'button')
                    self.assertTrue(ids[action_id]['attrs']['title'])
        source = (STATIC / 'wealth.js').read_text(encoding='utf-8')
        self.assertIn("controls?.querySelector('.dividend-head')", source)
        self.assertIn('controls.append(head);', source)
        self.assertIn('if (head && panel) panel.prepend(head);', source)

    def test_m2_header_style_owner_is_opt_in_and_survives_pending_reparenting(self):
        css = (STATIC / 'wealth-layout.css').read_text(encoding='utf-8')
        start = css.index('/* M2 SectionHeader owner:')
        end = css.index('/* End M2 SectionHeader owner. */', start)
        owner = css[start:end]
        self.assertNotIn('!important', owner)
        for forbidden in ('#realizedPnlPanel', '#dividendPanel', '#dividendPendingControls', '.wealth-page-head', '.wealth-ui-button'):
            self.assertNotIn(forbidden, owner)
        selectors = re.findall(r'([^{}]+)\{[^{}]*\}', owner)
        self.assertGreater(len(selectors), 5)
        for selector in selectors:
            self.assertIn('.wealth-layout .wealth-ui-section-header[data-ui="section-header"]', selector)
        for contract in ('--section-header-gap:', '--section-header-title-size:',
                         '__leading', '__heading', '__auxiliary', '__actions',
                         'flex-wrap: wrap', 'min-width: 0', 'max-width: 100%',
                         'font-family: inherit', 'overflow-wrap: anywhere', '@media (max-width: 600px)'):
            self.assertIn(contract, owner)
        self.assertIn('.wealth-layout :is(a,button,summary):focus-visible', css)

    def test_m2_header_layout_revision_is_exact_without_app_version_change(self):
        source = (STATIC / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(source.count('/static/wealth-layout.css?v=2.1.9-m2-header1'), 1)
        self.assertIn('<meta name="application-version" content="2.1.9" />', source)


if __name__ == '__main__':
    unittest.main()
