from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"
INDEX_HTML = ROOT / "app" / "static" / "index.html"


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


def test_layout_stylesheet_keeps_current_release_cache_version() -> None:
    html = _index_html()

    assert '/static/wealth-layout.css?v=1.3.0' in html
