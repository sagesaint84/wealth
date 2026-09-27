(function () {
  const originalRender = typeof window.renderDividends === 'function'
    ? window.renderDividends
    : (typeof renderDividends === 'function' ? renderDividends : null);

  if (!originalRender) return;

  function sourceLabel(source) {
    if (source === 'kind_etf_confirmed_overlay') return 'KIND ETF 확정 분배금 반영';
    if (source === 'opendart_confirmed_disclosure') return 'OpenDART 확정 공시';
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
    let confirmedOverrideCount = 0;
    let kindEtfConfirmedEventCount = 0;
    let kindEtfOverrideCount = 0;

    rows.forEach((row) => {
      const source = row?.forecast_source || {};
      const numeric = source.numeric_source || 'legacy_fallback';
      counts[numeric] = (counts[numeric] || 0) + 1;
      if (source.official_data_available) officialEvidenceCount += 1;
      if (source.recent_decision_disclosure) recentDecisionCount += 1;
      if (source.confirmed_amount === true) confirmedAmountCount += 1;
      if (source.confirmed_numeric_override === true) confirmedOverrideCount += 1;
      kindEtfConfirmedEventCount += Number(source.kind_etf_confirmed_event_count || 0);
      kindEtfOverrideCount += Number(source.kind_etf_numeric_override_count || 0);
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
    if (confirmedOverrideCount > 0) {
      pieces.push(`확정 공시 금액 반영 ${confirmedOverrideCount}종목`);
    }
    if (kindEtfConfirmedEventCount > 0) {
      pieces.push(`KIND ETF 확정 분배 이벤트 ${kindEtfConfirmedEventCount}건`);
    }
    if (kindEtfOverrideCount > 0) {
      pieces.push(`KIND ETF 공식금액 반영 ${kindEtfOverrideCount}건`);
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
      note.textContent = '배당결정 원문에서 주당배당금이 구조 검증된 경우만 확정금액으로 표시합니다. 지급예정일이 확인되고 기존 예상월과 안전하게 매칭될 때만 해당 월 추정금액을 확정 공시값으로 교체하며, 지급일은 임의 생성하지 않습니다.';
    }
    banner.appendChild(note);

    const links = document.createElement('div');
    links.style.marginTop = '5px';
    links.style.display = 'flex';
    links.style.gap = '10px';
    links.style.flexWrap = 'wrap';

    const kindUrl = policy.kind_etf_reference_url || policy.kind_reference_url;
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
      link.textContent = 'KIND ETF/배당정보 ↗';
      link.style.color = '#7dd3fc';
      links.appendChild(link);
    }
    if (links.childNodes.length) banner.appendChild(links);
  }

  function money(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '확인 불가';
    return `₩${Math.round(Number(value)).toLocaleString('ko-KR')}`;
  }

  function percent(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '확인 불가';
    return `${Number(value).toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function estimatedModeActive() {
    const active = document.querySelector('#dividendModeTabs .heatmap-tab.active');
    return !active || active?.dataset?.divMode === 'estimated';
  }

  function ensureAfterTaxPanel() {
    const cards = document.querySelector('.dividend-summary-cards');
    if (!cards) return null;
    let panel = document.getElementById('portfolioAfterTaxDividendPanel');
    if (panel) return panel;

    panel = document.createElement('section');
    panel.id = 'portfolioAfterTaxDividendPanel';
    panel.setAttribute('aria-label', '포트폴리오 세후 배당수익률');
    panel.style.cssText = [
      'margin:14px 0',
      'padding:14px',
      'border:1px solid rgba(99,102,241,.3)',
      'border-radius:12px',
      'background:rgba(15,23,42,.48)',
      'color:#e2e8f0',
    ].join(';');
    cards.insertAdjacentElement('afterend', panel);
    return panel;
  }

  function renderAfterTaxPanel(data) {
    const panel = ensureAfterTaxPanel();
    if (!panel) return;
    panel.hidden = !estimatedModeActive();
    if (panel.hidden) return;

    const view = data?.portfolio_after_tax;
    if (!view || view.calculation_status === 'unavailable') {
      panel.innerHTML = `
        <div style="font-weight:750;font-size:14px;">포트폴리오 세후 배당수익률</div>
        <div style="margin-top:5px;font-size:12px;color:#94a3b8;">배당 forecast 또는 알려진 세금 기준을 확인할 수 없어 계산하지 않았습니다.</div>
      `;
      return;
    }

    const complete = view.calculation_status === 'complete';
    const coverage = Number(view.after_tax_dividend_coverage_pct || 0);
    const afterCash = complete
      ? view.after_known_tax_cash_krw
      : view.calculable_after_known_tax_cash_krw;
    const afterCashLabel = complete ? '알려진 세금 후 예상 현금' : '계산 가능 부분 · 알려진 세금 후';
    const marketYield = complete
      ? `${percent(view.gross_yield_on_market_value_pct)} → ${percent(view.after_known_tax_yield_on_market_value_pct)}`
      : `${percent(view.gross_yield_on_market_value_pct)} → 전체 계산 보류`;
    const costYield = complete
      ? `${percent(view.gross_yield_on_cost_pct)} → ${percent(view.after_known_tax_yield_on_cost_pct)}`
      : `${percent(view.gross_yield_on_cost_pct)} → 전체 계산 보류`;
    const attributionNote = view.forecast_attribution_complete
      ? ''
      : ` · 미귀속 예상 ${money(view.unattributed_annual_dividend_krw)}`;

    const instrumentRows = (Array.isArray(view.instruments) ? view.instruments : [])
      .filter((row) => Number(row?.gross_annual_dividend_krw || 0) > 0)
      .map((row) => {
        const knownTax = row.calculation_status === 'calculated' ? money(row.known_tax_krw) : '계산 제외';
        const after = row.calculation_status === 'calculated' ? money(row.after_known_tax_cash_krw) : '확인 불가';
        return `
          <tr>
            <td style="padding:8px 7px;white-space:nowrap;"><strong>${escapeHtml(row.name || row.code)}</strong><br><small style="color:#94a3b8;">${escapeHtml(row.code)} · ${escapeHtml(row.currency)}</small></td>
            <td style="padding:8px 7px;">${escapeHtml(row.display_asset_class || '-')}</td>
            <td style="padding:8px 7px;text-align:right;">${money(row.market_value_krw)}</td>
            <td style="padding:8px 7px;text-align:right;">${money(row.gross_annual_dividend_krw)}</td>
            <td style="padding:8px 7px;text-align:right;">${knownTax}</td>
            <td style="padding:8px 7px;text-align:right;">${after}</td>
            <td style="padding:8px 7px;text-align:right;">${percent(row.gross_yield_market_pct)}${row.after_known_tax_yield_market_pct === null ? '' : ` → ${percent(row.after_known_tax_yield_market_pct)}`}</td>
            <td style="padding:8px 7px;text-align:right;">${percent(row.gross_yield_cost_pct)}${row.after_known_tax_yield_cost_pct === null ? '' : ` → ${percent(row.after_known_tax_yield_cost_pct)}`}</td>
            <td style="padding:8px 7px;">${escapeHtml(row.calculation_status)}</td>
          </tr>
        `;
      }).join('');

    panel.innerHTML = `
      <div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;">
        <div>
          <div style="font-weight:800;font-size:15px;">포트폴리오 세후 배당수익률</div>
          <div style="margin-top:3px;font-size:11.5px;color:#94a3b8;">최종 종합소득세가 아니라 기존 검증 엔진의 원천징수·알려진 세금 기준 screening입니다.</div>
        </div>
        <span style="font-size:11px;padding:3px 7px;border-radius:999px;border:1px solid rgba(148,163,184,.28);color:#cbd5e1;">${complete ? '전체 계산 가능' : '부분 계산'}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:9px;margin-top:12px;">
        <div style="padding:10px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">세전 예상 배당</div><strong style="display:block;margin-top:4px;font-size:16px;">${money(view.gross_annual_dividend_krw)}</strong></div>
        <div style="padding:10px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">${afterCashLabel}</div><strong style="display:block;margin-top:4px;font-size:16px;">${money(afterCash)}</strong></div>
        <div style="padding:10px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">평가금액 기준 세전 → 알려진 세금 후</div><strong style="display:block;margin-top:4px;font-size:16px;">${marketYield}</strong><small style="display:block;margin-top:5px;color:#94a3b8;">평균매입가 기준 ${costYield}</small></div>
        <div style="padding:10px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">세후 계산 커버리지</div><strong style="display:block;margin-top:4px;font-size:16px;">${percent(coverage)}</strong></div>
      </div>
      <div style="margin-top:9px;font-size:11.5px;line-height:1.55;color:#94a3b8;">
        평가금액 기준은 현재 주식 평가액만 사용하며 현금·예수금은 제외합니다. 평균매입가 기준은 평균매입가×수량이며 외화자산은 현재환율로 환산합니다.${attributionNote}
        ${complete ? '' : `<br><strong style="color:#fbbf24;">계산 커버리지가 100%가 아니므로 포트폴리오 전체의 알려진 세금 후 배당수익률은 표시하지 않습니다.</strong> 계산 제외 예상 배당: ${money(view.unsupported_gross_dividend_krw)}`}
      </div>
      <details style="margin-top:10px;">
        <summary style="cursor:pointer;font-size:12px;font-weight:700;">종목별 계산 근거 보기</summary>
        <div style="overflow-x:auto;margin-top:8px;">
          <table style="width:100%;border-collapse:collapse;font-size:11.5px;min-width:920px;">
            <thead style="color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.22);"><tr>
              <th style="padding:7px;text-align:left;">종목</th><th style="padding:7px;text-align:left;">유형</th><th style="padding:7px;text-align:right;">평가금액</th><th style="padding:7px;text-align:right;">세전 예상배당</th><th style="padding:7px;text-align:right;">알려진 세금</th><th style="padding:7px;text-align:right;">예상 수령액</th><th style="padding:7px;text-align:right;">평가금액 수익률</th><th style="padding:7px;text-align:right;">평균매입가 수익률</th><th style="padding:7px;text-align:left;">상태</th>
            </tr></thead>
            <tbody>${instrumentRows || '<tr><td colspan="9" style="padding:10px;color:#94a3b8;">예상 배당 종목이 없습니다.</td></tr>'}</tbody>
          </table>
        </div>
      </details>
    `;
  }

  function syncAfterTaxVisibility() {
    const panel = document.getElementById('portfolioAfterTaxDividendPanel');
    if (panel) panel.hidden = !estimatedModeActive();
  }

  document.addEventListener('click', (event) => {
    if (event.target?.closest?.('#dividendModeTabs [data-div-mode]')) {
      setTimeout(syncAfterTaxVisibility, 0);
    }
  });

  function wrappedRender(data) {
    originalRender(data);
    try {
      renderSourceStatus(data);
    } catch (err) {
      console.warn('배당 예상 출처 표시 실패:', err);
    }
    try {
      renderAfterTaxPanel(data);
    } catch (err) {
      console.warn('포트폴리오 세후 배당수익률 표시 실패:', err);
    }
  }

  window.renderDividends = wrappedRender;
  try {
    renderDividends = wrappedRender;
  } catch (_) {
    // Some browsers expose the top-level function only through window.
  }
})();
