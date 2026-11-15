from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
IPO_JS = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


def test_historical_dialog_keeps_offline_official_file_import() -> None:
    assert 'id="ipoHistoricalOnlinePreviewBtn"' not in INDEX
    assert "온라인 과거자료 재수집은 비활성화" in INDEX
    assert 'id="ipoHistoricalImportFile"' in INDEX


def test_historical_import_uses_only_offline_file_endpoints() -> None:
    assert "/api/ipo/historical-import/preview" in IPO_JS
    assert "/api/ipo/historical-import/commit" in IPO_JS
    assert "/api/ipo/historical-sync/preview" not in IPO_JS
    assert "/api/ipo/historical-sync/commit" not in IPO_JS


def test_backend_rejects_disabled_online_historical_sync() -> None:
    assert '@app.post("/api/ipo/historical-sync/preview")' in MAIN
    assert '@app.post("/api/ipo/historical-sync/commit")' in MAIN
    assert MAIN.count('"IPO_NPAY_ONLY_HISTORICAL_SYNC_DISABLED"') == 2
