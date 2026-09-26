(function () {
  const originalRender = typeof window.renderDividends === 'function'
    ? window.renderDividends
    : (typeof renderDividends === 'function' ? renderDividends : null);

  if (!originalRender) return;

  function sourceLabel(source) {
    if (source === 'opendart_historical_fill') return 'OpenDART 공식 이력 보정';
    if (source === 'naver') return '네이버 추정';
    if (source === 'yahoo_history') return 'Yahoo 최근 배당 이력';
    return '기존 추정';
  }

  function ensureBanner() {
    const cards = document.querySelector('.dividend-summary-cards');
    if (!cards) return null;
    let banner = document.getElementById('dividendForecastSourceBanner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'dividendForecastSourceBanner';
      banner.style.cssText = [
        'margin:0 0 12px',
        'padding:10px 12px',
        'border:1px solid rgba(148,163,184,.28)',
        'border-radius:10px',
        'background:rgba(15,23,42,.42)',
        'font-size:12px',
        'line-height:1.55',
        'color:#cbd5e1',
      ].join(';');
      cards.parentNode.insertBefore(banner, cards);
    }
    return banner;
  }

  function renderSourceStatus(data) {
    const banner = ensureBanner();
    if (!banner) return;
    banner.replaceChildren();

    const policy = data?.forecast_source_policy || {};
    const status = policy.status || 'legacy_only';
    const rows = Array.isArray(data?.holding_dividends) ? data.holding_dividends : [];
    const counts = {};
    let recentDecisionCount = 0;
    let officialEvidenceCount = 0;
    let confirmedAmountCount = 0;

    rows.forEach((row) => {
      const source = row?.forecast_source || {};
      const numeric = source.numeric_source || 'legacy_fallback';
      counts[numeric] = (counts[numeric] || 0) + 1;
      if (source.official_data_available) officialEvidenceCount += 1;
      if (source.recent_decision_disclosure) recentDecisionCount += 1;
      if (source.confirmed_amount === true) confirmedAmountCount += 1;
    });

    const title = document.createElement('div');
    title.style.fontWeight = '700';
    title.style.color = '#e2e8f0';

    if (status === 'ok') {
      title.textContent = `📑 배당 예상 출처 · OpenDART 공식자료 ${officialEvidenceCount}종목 참조`;
    } else if (status === 'missing_api_key') {
      title.textContent = '📑 배당 예상 출처 · OpenDART 미연동';
    } else if (status === 'network_disabled') {
      title.textContent = '📑 배당 예상 출처 · 외부 네트워크 비활성';
    } else if (status === 'opendart_unavailable' || status === 'official_enrichment_failed') {
      title.textContent = '📑 배당 예상 출처 · 공식자료 조회 실패, 기존 추정 유지';
    } else {
      title.textContent = '📑 배당 예상 출처 · 기존 추정 데이터';
    }
    banner.appendChild(title);

    const detail = document.createElement('div');
    detail.style.marginTop = '3px';
    const pieces = Object.entries(counts)
      .filter(([, count]) => count > 0)
      .map(([source, count]) => `${sourceLabel(source)} ${count}종목`);
    if (recentDecisionCount > 0) {
      pieces.push(`최근 배당결정 공시 ${recentDecisionCount}건`);
    }
    if (confirmedAmountCount > 0) {
      pieces.push(`구조 검증된 확정금액 ${confirmedAmountCount}종목`);
    }
    detail.textContent = pieces.length
      ? pieces.join(' · ')
      : '현재 보유종목의 배당 자료가 없습니다.';
    banner.appendChild(detail);

    const note = document.createElement('div');
    note.style.marginTop = '3px';
    note.style.color = '#94a3b8';
    if (status === 'missing_api_key') {
      note.textContent = '현재 금액은 네이버/Yahoo 기반 추정입니다. OpenDART 키를 설정하면 공식 이력과 최근 공시 존재 여부를 함께 확인합니다.';
    } else {
      note.textContent = '공식 과거 DPS는 기존 추정이 없을 때만 보정하며, 배당결정 공시가 존재해도 금액이 구조적으로 검증되지 않으면 확정금액으로 표시하지 않습니다.';
    }
    banner.appendChild(note);

    const links = document.createElement('div');
    links.style.marginTop = '5px';
    links.style.display = 'flex';
    links.style.gap = '10px';
    links.style.flexWrap = 'wrap';

    const kindUrl = policy.kind_reference_url;
    const dartUrl = policy.opendart_guide_url;
    if (typeof dartUrl === 'string' && dartUrl.startsWith('https://')) {
      const link = document.createElement('a');
      link.href = dartUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'OpenDART 공식자료 ↗';
      link.style.color = '#7dd3fc';
      links.appendChild(link);
    }
    if (typeof kindUrl === 'string' && kindUrl.startsWith('https://')) {
      const link = document.createElement('a');
      link.href = kindUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'KIND 배당정보 ↗';
      link.style.color = '#7dd3fc';
      links.appendChild(link);
    }
    if (links.childNodes.length) banner.appendChild(links);
  }

  function wrappedRender(data) {
    originalRender(data);
    try {
      renderSourceStatus(data);
    } catch (err) {
      console.warn('배당 예상 출처 표시 실패:', err);
    }
  }

  window.renderDividends = wrappedRender;
  try {
    renderDividends = wrappedRender;
  } catch (_) {
    // Some browsers expose the top-level function only through window.
  }
})();
