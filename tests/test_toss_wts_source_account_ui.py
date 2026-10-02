from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "app" / "static" / "index.html"
WEALTH_CSS = ROOT / "app" / "static" / "wealth.css"


def test_toss_wts_stale_kis_source_account_control_is_hidden_as_a_whole() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    css = WEALTH_CSS.read_text(encoding="utf-8")

    assert 'id="kisSourceAccount"' in html
    assert 'for="kisSourceAccount">한투 원본 계좌</label>' in html
    assert ".toss-wts-control-item:has(#kisSourceAccount){display:none!important}" in css


def test_toss_wts_source_account_fix_does_not_hide_destination_account_controls() -> None:
    css = WEALTH_CSS.read_text(encoding="utf-8")

    assert "#tossWtsImportAccount" not in css
    assert "#tossWtsDestination" not in css
