from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = (ROOT / "app/static/wealth-layout.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/wealth-layout.css").read_text(encoding="utf-8")
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")


def test_quick_access_order_and_routes():
    assert LAYOUT.index('<strong>주식 투자</strong>') < LAYOUT.index('<strong>자산 계좌</strong>') < LAYOUT.index('<strong>손익·배당</strong>') < LAYOUT.index('<strong>가계부</strong>')
    assert 'href="#invest"' in LAYOUT and 'href="#assets"' in LAYOUT and 'href="#income"' in LAYOUT and 'href="#ledger"' in LAYOUT


def test_home_summary_is_non_visual_legacy_and_portfolio_prominent():
    assert 'data-legacy-summary="true"' in LAYOUT
    assert '.wealth-home-asset-portfolio' in CSS


def test_home_kpi_secondary_rows_simplified():
    assert "['수익률', 'wealthAssetExpectedRate'" in LAYOUT
    assert "['일간 수익', 'wealthAssetDayDetail'" not in LAYOUT
    assert "['연간', 'wealthAssetYearDetail'" not in LAYOUT
    assert "['월간', 'wealthAssetMonthDetail'" not in LAYOUT


def test_history_actions_have_short_labels_and_row_actions():
    assert '>기록</button>' in HTML
    assert '>추가</button>' in HTML
    assert 'data-record-edit' in (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")
    assert 'data-record-delete' in (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")


def test_mobile_bottom_navigation_contract():
    assert 'grid-template-columns: repeat(5,1fr)' in CSS
    assert 'env(safe-area-inset-bottom)' in CSS


def test_asset_record_net_worth_invariant():
    from app.services.asset_records import normalize_record
    record = normalize_record({'date': '2026-01-01', 'total_assets_krw': 100, 'total_debt_krw': 20})
    assert record['net_worth_krw'] == 80
    edited = normalize_record({'date': '2026-01-01', 'total_assets_krw': 100, 'total_debt_krw': 30})
    assert edited['net_worth_krw'] == 70


def test_history_add_action_delegates_to_existing_form():
    planning = (ROOT / "app/static/wealth-planning.js").read_text(encoding="utf-8")
    assert "data-history-action=\"wealthAddHistory\"" in planning
    assert "wealthAddHistory')?.addEventListener('click', () => openHistory())" in planning
