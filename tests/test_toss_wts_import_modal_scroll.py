from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"
INDEX_HTML = ROOT / "app" / "static" / "index.html"
LAYOUT_CSS_REVISION = "2.1.3-postdeploy1"


def assert_current_layout_stylesheet(html: str) -> None:
    """Shared exact cache contract: one real stylesheet link, no comment/substring matches."""
    class Stylesheets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.layout_links = []

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            href = attributes.get('href', '')
            if tag == 'link' and attributes.get('rel') == 'stylesheet' and urlsplit(href).path == '/static/wealth-layout.css':
                self.layout_links.append(href)

    parser = Stylesheets()
    parser.feed(html)
    assert parser.layout_links == [f'/static/wealth-layout.css?v={LAYOUT_CSS_REVISION}'], parser.layout_links


def _layout_css() -> str:
    return LAYOUT_CSS.read_text(encoding="utf-8")


def _index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_broker_import_modal_is_constrained_to_viewport() -> None:
    css = _layout_css()

    assert ".toss-wts-modal {" in css
    assert "max-height: calc(100vh - 32px);" in css
    assert "max-height: calc(100dvh - 32px);" in css


def test_broker_import_modal_body_scrolls_without_hiding_header_footer() -> None:
    css = _layout_css()

    assert ".toss-wts-modal-body {" in css
    assert "min-height: 0;" in css
    assert "overflow-y: auto;" in css
    assert "overscroll-behavior: contain;" in css
    assert ".toss-wts-modal-header" in css
    assert ".toss-wts-modal-footer" in css
    assert "flex: 0 0 auto;" in css


def test_layout_stylesheet_uses_current_hotfix_cache_version() -> None:
    html = _index_html()

    assert_current_layout_stylesheet(html)
