"""Static shell contract; interactive checks use the isolated ui_preview server."""
import unittest
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
        self.assertIn('data-sector-filter="${html(s.name)}" data-donut-key="${html(donutKey)}"', source)
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


if __name__ == '__main__':
    unittest.main()
