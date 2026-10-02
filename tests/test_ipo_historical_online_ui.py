from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
IPO_JS = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


def test_historical_dialog_offers_explicit_online_full_history_query() -> None:
    assert 'id="ipoHistoricalOnlinePreviewBtn"' in INDEX
    assert "KRX 전체 과거자료 조회" in INDEX
    assert 'id="ipoHistoricalImportFile"' in INDEX


def test_online_preview_and_commit_use_separate_endpoints() -> None:
    assert "/api/ipo/historical-sync/preview" in IPO_JS
    assert "/api/ipo/historical-sync/commit" in IPO_JS
    assert "KRX_HISTORICAL_ONLINE" in IPO_JS
    assert "historicalImportMode" in IPO_JS


def test_backend_exposes_explicit_online_historical_preview_and_commit() -> None:
    assert '@app.post("/api/ipo/historical-sync/preview")' in MAIN
    assert '@app.post("/api/ipo/historical-sync/commit")' in MAIN
