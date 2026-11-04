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
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
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


    def test_m1_button_migration_is_exactly_two_native_secondary_buttons(self):
        elements = Elements((STATIC / 'index.html').read_text(encoding='utf-8'))
        migrated = [(tag, attrs) for tag, attrs in elements.elements
                    if 'wealth-ui-button' in attrs.get('class', '').split()]
        self.assertEqual({attrs['id'] for _, attrs in migrated}, {'refreshButton', 'syncAccountsButton'})
        self.assertEqual(len(migrated), 2)
        for tag, attrs in migrated:
            with self.subTest(id=attrs['id']):
                self.assertEqual(tag, 'button')
                self.assertEqual(attrs['type'], 'button')
                self.assertEqual(attrs['data-ui'], 'button')
                self.assertEqual(set(attrs['class'].split()), {'button', 'secondary', 'wealth-ui-button'})
                self.assertTrue(attrs['title'])
                self.assertNotIn('onclick', attrs)
                self.assertNotIn('tabindex', attrs)

    def test_m1_button_owner_does_not_require_important_or_change_other_components(self):
        css = (STATIC / 'wealth-layout.css').read_text(encoding='utf-8')
        start = css.index('/* M1 Button owner:')
        end = css.index('/* End M1 Button owner. */', start)
        owner = css[start:end]
        self.assertNotIn('!important', owner)
        self.assertNotIn('#refreshButton', owner)
        self.assertNotIn('#syncAccountsButton', owner)
        # Every component selector is opt-in, including variants and state rules.
        rules = re.findall(r'([^{}]+)\{([^{}]*)\}', owner)
        self.assertGreater(len(rules), 8)
        for selector, _ in rules:
            self.assertIn('.wealth-layout .button.wealth-ui-button', selector)
            self.assertIn('[data-ui="button"]', selector)
        for contract in ('--button-height: 31px', '--button-padding-inline: 10px',
                         '--button-radius: 8px', '--button-font-size: 11.5px',
                         'var(--surface-2)', 'var(--text)', 'var(--border-subtle)',
                         ':focus-visible', ':disabled', ':not(:disabled):hover',
                         '[aria-busy="true"]', 'prefers-reduced-motion'):
            self.assertIn(contract, owner)
        overrides = (STATIC / 'wealth-overrides.css').read_text(encoding='utf-8')
        self.assertIn('.button.compact,', overrides)  # Still used outside the pilot.

    def test_m1_buttons_keep_existing_action_requests_and_busy_lifecycle(self):
        source = (STATIC / 'wealth.js').read_text(encoding='utf-8')
        for button in ('refreshButton', 'syncAccountsButton'):
            self.assertEqual(source.count(f'$("#{button}")?.addEventListener("click"'), 1)
        self.assertIn('api("/api/sync/all", { method: "POST" })', source)
        self.assertIn('api("/api/refresh-prices", { method: "POST" })', source)
        self.assertIn('button.disabled = enabled;', source)
        self.assertIn('button.textContent = enabled ? "처리 중…" : button.dataset.label;', source)
        self.assertIn('finally {\n    busy(button, false);', source)

    def test_m1_changed_layout_asset_has_its_own_revision(self):
        source = (STATIC / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(source.count('/static/wealth-layout.css?v=2.1.9-m1-m2-m3-card2'), 1)
        self.assertIn('<meta name="application-version" content="2.1.9" />', source)


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
        self.assertEqual(source.count('/static/wealth-layout.css?v=2.1.9-m1-m2-m3-card2'), 1)
        self.assertIn('<meta name="application-version" content="2.1.9" />', source)


    def test_m3_metric_card_scope_and_existing_dom_contract(self):
        tree = SectionHeaderElements((STATIC / 'index.html').read_text(encoding='utf-8'))
        cards = [n for n in tree.nodes if n['attrs'].get('data-ui') == 'card']
        metrics = [n for n in tree.nodes if 'div-summary-card' in n['attrs'].get('class', '').split()]
        expected = {
            'realizedPnlPanel': ['pnlTotal', 'pnlTotalWin', 'pnlTotalLoss', 'pnlWinRate'],
            'dividendPanel': ['divTotalAnnual', 'divYield', 'divMonthlyAvg', 'divPayingCount'],
        }
        self.assertEqual(len(cards), 8)
        self.assertEqual(len(metrics), 8)
        self.assertEqual(cards, metrics)
        for panel_id, ids in expected.items():
            panel = next(n for n in tree.nodes if n['attrs'].get('id') == panel_id)
            selected = []
            for card in cards:
                parent = card
                while parent is not None and parent is not panel:
                    parent = parent['parent']
                if parent is panel:
                    selected.append(card)
            self.assertEqual(len(selected), 4)
            self.assertEqual([c['children'][1]['attrs']['id'] for c in selected], ids)
        for card in cards:
            self.assertEqual(card['tag'], 'div')
            self.assertEqual(set(card['attrs']['class'].split()), {'div-summary-card', 'wealth-ui-card'})
            self.assertEqual(card['attrs'].get('data-card-variant'), 'metric')
            self.assertEqual([n['tag'] for n in card['children']], ['span', 'strong', 'small'])
            self.assertIn('div-card-label', card['children'][0]['attrs']['class'])
            self.assertIn('div-card-val', card['children'][1]['attrs']['class'])
            self.assertNotIn('role', card['attrs'])
            self.assertNotIn('tabindex', card['attrs'])

    def test_m3_shared_frame_has_one_opt_in_owner_and_theme_tokens(self):
        css = (STATIC / 'wealth-layout.css').read_text(encoding='utf-8')
        block = css.split('/* M3 Shared Card owner.', 1)[1].split('/* End M3 Shared Card owner. */', 1)[0]
        owner = '.wealth-layout .wealth-ui-card[data-ui="card"][data-card-variant="metric"]'
        self.assertIn(owner + ' {', block)
        self.assertNotIn('!important', block)
        for declaration in ('box-sizing: border-box', 'min-width: 0', 'gap: var(--card-gap)',
                            'padding: var(--card-padding)', 'background: var(--card-metric-surface)',
                            'border: 1px solid var(--card-metric-border)', 'border-radius: var(--card-radius)',
                            'box-shadow: var(--card-metric-shadow)', 'transform: translateY(-2px)'):
            self.assertIn(declaration, block)
        self.assertIn('[data-theme="white"] .wealth-layout', block)
        self.assertIn('[data-theme="oled"] .wealth-layout', block)
        for color in ('#0d1527', '#1e2c4d', '#f8fafc', '#e2e8f0', '#070709', '#1a1a24'):
            self.assertIn(color, block)
        self.assertNotIn('grid-template', block)
        self.assertNotIn('.gain', block)
        self.assertNotIn('.loss', block)
        self.assertNotIn('wealth-ui-button', block)
        self.assertNotIn('wealth-ui-section-header', block)

    def test_m3_summary_frames_have_no_legacy_override(self):
        css = (STATIC / 'wealth-overrides.css').read_text(encoding='utf-8')
        selectors = [line.strip() for line in css.splitlines() if '.div-summary-card' in line]
        self.assertEqual(selectors, ['[data-theme="white"] .div-summary-card small,'])
        # Feature text/semantic colors and the summary grid remain outside Card.
        for selector in ('.div-card-label {', '.div-card-val {', '.div-card-val.gain {',
                         '.pnl-panel .div-card-val.gain {', '.pnl-panel .div-card-val.loss {',
                         '.dividend-summary-cards {'):
            self.assertIn(selector, css)

    def test_m3_pnl_mobile_density_and_renderer_hooks_remain_owned_correctly(self):
        css = (STATIC / 'wealth-layout.css').read_text(encoding='utf-8')
        self.assertIn('.wealth-layout #realizedPnlPanel .wealth-ui-card[data-ui="card"][data-card-variant="metric"]', css)
        self.assertIn('--card-padding: 12px;', css)
        self.assertIn('--card-overflow-wrap: anywhere;', css)
        density = (STATIC / 'wealth-ui-density.css').read_text(encoding='utf-8')
        self.assertIn('#realizedPnlPanel .div-summary-card {', density)
        js = (STATIC / 'wealth.js').read_text(encoding='utf-8')
        self.assertIn('const totalEl = $("#pnlTotal");', js)
        self.assertIn('$("#divTotalAnnual").textContent = money(totalAnnual)', js)
        self.assertNotIn('wealth-ui-card', js)

if __name__ == '__main__':
    unittest.main()
