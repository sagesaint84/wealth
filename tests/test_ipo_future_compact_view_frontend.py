"""Core compact presentation has no async decorator dependency."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_core_compact_renderer_and_static_styles():
    source = (ROOT / 'app/static/wealth-ipo.js').read_text(encoding='utf-8')
    loader = (ROOT / 'app/static/wealth-family-financial-income-allocation.js').read_text(encoding='utf-8')
    css = (ROOT / 'app/static/wealth-layout.css').read_text(encoding='utf-8')
    assert not (ROOT / 'app/static/wealth-ipo-compact-view.js').exists()
    assert 'wealthIpoCompactViewScript' not in loader
    assert 'wealth-ipo-compact-view.js' not in loader
    assert 'MutationObserver' not in source
    assert 'wealthIpoCompactViewStyles' not in source
    assert '<article class="ipo-card ipo-compact-card' in source
    assert 'const expandedIpoIds = new Set()' in source
    assert 'expandedIpoIds.has(ipoId)' in source
    assert 'aria-expanded="${expanded}"' in source
    assert '<div class="ipo-card-body"${detailHidden}>' in source
    assert '<div class="ipo-card-footer"${detailHidden}>' in source
    assert 'grid-template-columns: minmax(0, 1fr)' in css
    assert 'repeat(auto-fill, minmax(360px, 1fr))' not in css


def test_existing_future_navigation_and_metadata_use_core_snapshot():
    source = (ROOT / 'app/static/wealth-ipo.js').read_text(encoding='utf-8')
    assert 'shiftIpoMonth(ipoHistoryYear, ipoHistoryMonth, 1)' in source
    assert 'ipoMonthExplicitlySelected = true' in source
    assert 'scoreDiagnosticText(scoreObj)' in source
    assert 'renderMetalogosReference(ipo)' in source
    assert "market || '시장 미확인'" in source
    assert "market || 'KOSDAQ'" not in source
    assert 'loadIpoMetadata' not in source
    assert 'invalidateIpoMetadata' not in source
    for key, label in [('institutional_competition_ratio', '기관경쟁률'),
                       ('lockup_commitment_ratio', '의무보유확약률'),
                       ('tradable_share_ratio', '유통가능주식비율'),
                       ('pricing_discipline', '공모가 결정정보')]:
        assert f"{key}: '{label}'" in source
