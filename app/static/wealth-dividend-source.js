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
    if (recentDecisionCount > 0) pieces.push(`최근 배당결정 공시 ${recentDecisionCount}건`);
    if (confirmedAmountCount > 0) pieces.push(`구조 검증된 확정금액 ${confirmedAmountCount}종목`);
    if (confirmedOverrideCount > 0) pieces.push(`확정 공시 금액 반영 ${confirmedOverrideCount}종목`);
    if (kindEtfConfirmedEventCount > 0) pieces.push(`KIND ETF 확정 분배 이벤트 ${kindEtfConfirmedEventCount}건`);
    if (kindEtfOverrideCount > 0) pieces.push(`KIND ETF 공식금액 반영 ${kindEtfOverrideCount}건`);
    detail.textContent = pieces.length ? pieces.join(' · ') : '현재 보유종목의 배당 자료가 없습니다.';
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

  function safeLink(value) {
    return typeof value === 'string' && value.startsWith('https://') ? value : null;
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
    panel.setAttribute('aria-label', '포트폴리오 세후 배당수익률 및 Dividend Intelligence');
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

  function evidenceHtml(evidence) {
    const label = escapeHtml(evidence?.label || '근거 확인 불가');
    const url = safeLink(evidence?.evidence_url);
    const link = url
      ? ` <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="color:#7dd3fc;white-space:nowrap;">원문 ↗</a>`
      : '';
    return `<span>${label}${link}</span>`;
  }

  function accountDetailsHtml(row) {
    const accounts = Array.isArray(row?.accounts) ? row.accounts : [];
    if (!accounts.length) return '<span style="color:#64748b;">계좌 귀속 확인 불가</span>';
    const items = accounts.map((account) => `
      <div style="display:grid;grid-template-columns:minmax(150px,1fr) repeat(3,minmax(95px,auto));gap:8px;padding:5px 0;border-top:1px solid rgba(148,163,184,.12);align-items:center;">
        <span>${escapeHtml(account.account_label || '-')}<br><small style="color:#64748b;">현재 보유수량 ${percent(account.quantity_share_pct)} 비례 추정</small></span>
        <span style="text-align:right;">${money(account.gross_annual_dividend_krw)}</span>
        <span style="text-align:right;">${account.known_tax_krw === null ? '확인 불가' : money(account.known_tax_krw)}</span>
        <span style="text-align:right;">${account.after_known_tax_cash_krw === null ? '확인 불가' : money(account.after_known_tax_cash_krw)}</span>
      </div>
    `).join('');
    return `
      <details style="margin-top:5px;">
        <summary style="cursor:pointer;color:#cbd5e1;">계좌별 추정 보기</summary>
        <div style="margin-top:4px;min-width:490px;">
          <div style="display:grid;grid-template-columns:minmax(150px,1fr) repeat(3,minmax(95px,auto));gap:8px;color:#64748b;font-size:10.5px;"><span>계좌</span><span style="text-align:right;">세전</span><span style="text-align:right;">알려진 세금</span><span style="text-align:right;">예상 수령</span></div>
          ${items}
          <div style="margin-top:5px;color:#64748b;font-size:10.5px;">계좌별 금액은 현재 보유수량 비례 추정이며 배당 권리(entitlement) 확정이 아닙니다.</div>
        </div>
      </details>
    `;
  }

  function accuracyHtml(accuracy) {
    const scope = escapeHtml(accuracy?.scope_owner || '모두');
    if (!accuracy || accuracy.status === 'unavailable') {
      return `<div style="color:#94a3b8;">예측 정확도 데이터를 확인할 수 없습니다. · ${scope} 보유 snapshot 기준</div>`;
    }
    if (accuracy.status !== 'ready') {
      const count = Number(accuracy.snapshot_count || 0);
      const latest = accuracy.latest_snapshot_as_of_date ? ` · 최근 snapshot ${escapeHtml(accuracy.latest_snapshot_as_of_date)}` : '';
      return `<div><strong>측정 데이터 누적 중</strong><span style="color:#94a3b8;"> · snapshot ${count}개${latest} · ${scope} 보유 snapshot 기준</span></div>`;
    }
    const months = Number(accuracy.evaluated_month_count || 0);
    const amount = accuracy.amount_accuracy_complete === true
      ? `MAE ${money(accuracy.mae_krw)} · WAPE ${percent(accuracy.wape_percent)}`
      : '지급월/이벤트 평가는 가능하지만 비교 가능한 gross 금액 또는 forecast attribution이 불완전합니다.';
    return `
      <div><strong>과거 point-in-time 예측 평가</strong><span style="color:#94a3b8;"> · 완료 월 ${months}개 · ${scope} 보유 snapshot 기준</span></div>
      <div style="margin-top:3px;color:${accuracy.amount_accuracy_complete === true ? '#cbd5e1' : '#fbbf24'};">${amount}</div>
      <div style="margin-top:3px;color:#64748b;">진행 중인 현재 월은 제외하며 과거 snapshot을 현재 holdings/source로 재생성하지 않습니다.</div>
    `;
  }

  async function loadAlertSetting(panel) {
    const checkbox = panel.querySelector('#dividendIntelligenceAlertsEnabled');
    const statusNode = panel.querySelector('#dividendIntelligenceAlertStatus');
    if (!checkbox || !statusNode || checkbox.dataset.loaded === '1') return;
    checkbox.dataset.loaded = '1';
    try {
      const response = await fetch('/api/settings/automation', { credentials: 'same-origin' });
      if (!response.ok) throw new Error('settings fetch failed');
      const payload = await response.json();
      checkbox.checked = payload?.automation?.dividend_intelligence_alerts?.enabled === true;
      statusNode.textContent = checkbox.checked ? '켜짐 · 일일 마감 시 새 이벤트만 알림' : '꺼짐 · 기본값';
    } catch (_) {
      checkbox.disabled = true;
      statusNode.textContent = '설정 확인 불가';
      return;
    }

    checkbox.addEventListener('change', async () => {
      const next = checkbox.checked;
      checkbox.disabled = true;
      statusNode.textContent = '저장 중…';
      try {
        const response = await fetch('/api/settings/automation', {
          method: 'PATCH',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ automation: { dividend_intelligence_alerts: { enabled: next } } }),
        });
        if (!response.ok) throw new Error('settings update failed');
        const payload = await response.json();
        checkbox.checked = payload?.automation?.dividend_intelligence_alerts?.enabled === true;
        statusNode.textContent = checkbox.checked ? '켜짐 · 일일 마감 시 새 이벤트만 알림' : '꺼짐 · 기본값';
      } catch (_) {
        checkbox.checked = !next;
        statusNode.textContent = '저장 실패';
      } finally {
        checkbox.disabled = false;
      }
    });
  }

  function renderAfterTaxPanel(data) {
    const panel = ensureAfterTaxPanel();
    if (!panel) return;
    panel.hidden = !estimatedModeActive();
    if (panel.hidden) return;

    const view = data?.portfolio_after_tax;
    const intelligence = data?.dividend_intelligence || {};
    if (!view || view.calculation_status === 'unavailable') {
      panel.innerHTML = `
        <div style="font-weight:750;font-size:14px;">포트폴리오 세후 배당수익률</div>
        <div style="margin-top:5px;font-size:12px;color:#94a3b8;">배당 forecast 또는 알려진 세금 기준을 확인할 수 없어 계산하지 않았습니다.</div>
      `;
      return;
    }

    const complete = view.calculation_status === 'complete';
    const coverage = Number(view.after_tax_dividend_coverage_pct || 0);
    const afterCash = complete ? view.after_known_tax_cash_krw : view.calculable_after_known_tax_cash_krw;
    const afterCashLabel = complete ? '알려진 세금 후 예상 현금' : '계산 가능 부분 · 알려진 세금 후';
    const marketYield = complete
      ? `${percent(view.gross_yield_on_market_value_pct)} → ${percent(view.after_known_tax_yield_on_market_value_pct)}`
      : `${percent(view.gross_yield_on_market_value_pct)} → 전체 계산 보류`;
    const costYield = complete
      ? `${percent(view.gross_yield_on_cost_pct)} → ${percent(view.after_known_tax_yield_on_cost_pct)}`
      : `${percent(view.gross_yield_on_cost_pct)} → 전체 계산 보류`;
    const attributionNote = view.forecast_attribution_complete ? '' : ` · 미귀속 예상 ${money(view.unattributed_annual_dividend_krw)}`;
    const trust = intelligence?.trust || {};
    const intelligenceRows = Array.isArray(intelligence?.instruments) && intelligence.instruments.length
      ? intelligence.instruments
      : (Array.isArray(view.instruments) ? view.instruments : []);

    const instrumentRows = intelligenceRows
      .filter((row) => Number(row?.gross_annual_dividend_krw || 0) > 0)
      .map((row) => {
        const knownTax = row.calculation_status === 'calculated' ? money(row.known_tax_krw) : '계산 제외';
        const after = row.calculation_status === 'calculated' ? money(row.after_known_tax_cash_krw) : '확인 불가';
        const grossContribution = row.gross_portfolio_contribution_pct == null ? '-' : percent(row.gross_portfolio_contribution_pct);
        const afterContribution = row.calculable_after_known_tax_contribution_pct == null ? '-' : percent(row.calculable_after_known_tax_contribution_pct);
        return `
          <tr>
            <td style="padding:8px 7px;vertical-align:top;"><strong>${escapeHtml(row.name || row.code)}</strong><br><small style="color:#94a3b8;">${escapeHtml(row.code)} · ${escapeHtml(row.currency)}</small>${accountDetailsHtml(row)}</td>
            <td style="padding:8px 7px;vertical-align:top;">${escapeHtml(row.display_asset_class || '-')}</td>
            <td style="padding:8px 7px;vertical-align:top;">${evidenceHtml(row.forecast_evidence)}</td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${money(row.gross_annual_dividend_krw)}<br><small style="color:#94a3b8;">기여 ${grossContribution}</small></td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${knownTax}</td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${after}<br><small style="color:#94a3b8;">계산가능 현금 기여 ${afterContribution}</small></td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${percent(row.gross_yield_market_pct)}${row.after_known_tax_yield_market_pct === null ? '' : ` → ${percent(row.after_known_tax_yield_market_pct)}`}</td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${percent(row.gross_yield_cost_pct)}${row.after_known_tax_yield_cost_pct === null ? '' : ` → ${percent(row.after_known_tax_yield_cost_pct)}`}</td>
            <td style="padding:8px 7px;vertical-align:top;">${escapeHtml(row.calculation_status)}</td>
          </tr>
        `;
      }).join('');

    panel.innerHTML = `
      <div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;">
        <div>
          <div style="font-weight:800;font-size:15px;">포트폴리오 세후 배당수익률 · Dividend Intelligence</div>
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
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:9px;margin-top:9px;">
        <div style="padding:10px;border:1px solid rgba(56,189,248,.18);border-radius:9px;background:rgba(14,116,144,.08);"><div style="font-size:11px;color:#94a3b8;">공식 근거 확인</div><strong style="display:block;margin-top:4px;">${Number(trust.official_evidence_count || 0)}종목</strong><small style="color:#94a3b8;">확정금액 반영 ${Number(trust.official_confirmed_applied_count || 0)}종목</small></div>
        <div style="padding:10px;border:1px solid rgba(148,163,184,.16);border-radius:9px;background:rgba(30,41,59,.35);"><div style="font-size:11px;color:#94a3b8;">이력/시장/휴리스틱 추정</div><strong style="display:block;margin-top:4px;">${Number(trust.estimated_or_heuristic_count || 0)}종목</strong></div>
        <div style="padding:10px;border:1px solid rgba(148,163,184,.16);border-radius:9px;background:rgba(30,41,59,.35);"><div style="font-size:11px;color:#94a3b8;">종목 미귀속 residual</div><strong style="display:block;margin-top:4px;">${money(trust.unattributed_residual_krw || 0)}</strong><small style="color:#94a3b8;">종목/계좌에 임의 배분하지 않음</small></div>
      </div>
      <div style="margin-top:9px;padding:10px;border-radius:9px;background:rgba(30,41,59,.34);font-size:11.5px;line-height:1.55;">${accuracyHtml(intelligence?.accuracy)}</div>
      <div style="margin-top:9px;padding:10px;border:1px solid rgba(148,163,184,.16);border-radius:9px;display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;">
        <div><strong style="font-size:12px;">배당·금융소득 알림</strong><div style="margin-top:2px;color:#94a3b8;font-size:11px;">기본 OFF. 켜면 일일 마감에서 새 공식 배당 이벤트와 가족 구성원별 금융소득 watch/2천만원 상태만 중복 없이 알립니다. 가족 합계에는 법정 기준을 적용하지 않습니다.</div></div>
        <label style="display:flex;gap:7px;align-items:center;font-size:11.5px;cursor:pointer;"><input id="dividendIntelligenceAlertsEnabled" type="checkbox"><span id="dividendIntelligenceAlertStatus">설정 확인 중…</span></label>
      </div>
      <div style="margin-top:9px;font-size:11.5px;line-height:1.55;color:#94a3b8;">
        평가금액 기준은 현재 주식 평가액만 사용하며 현금·예수금은 제외합니다. 평균매입가 기준은 평균매입가×수량이며 외화자산은 현재환율로 환산합니다.${attributionNote}
        ${complete ? '' : `<br><strong style="color:#fbbf24;">계산 커버리지가 100%가 아니므로 포트폴리오 전체의 알려진 세금 후 배당수익률은 표시하지 않습니다.</strong> 계산 제외 예상 배당: ${money(view.unsupported_gross_dividend_krw)}`}
      </div>
      <details style="margin-top:10px;">
        <summary style="cursor:pointer;font-size:12px;font-weight:700;">종목·계좌별 계산 근거 보기</summary>
        <div style="overflow-x:auto;margin-top:8px;">
          <table style="width:100%;border-collapse:collapse;font-size:11.5px;min-width:1120px;">
            <thead style="color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.22);"><tr>
              <th style="padding:7px;text-align:left;">종목 / 계좌</th><th style="padding:7px;text-align:left;">유형</th><th style="padding:7px;text-align:left;">예상 근거</th><th style="padding:7px;text-align:right;">세전 예상배당 / 기여</th><th style="padding:7px;text-align:right;">알려진 세금</th><th style="padding:7px;text-align:right;">예상 수령액 / 기여</th><th style="padding:7px;text-align:right;">평가금액 수익률</th><th style="padding:7px;text-align:right;">평균매입가 수익률</th><th style="padding:7px;text-align:left;">상태</th>
            </tr></thead>
            <tbody>${instrumentRows || '<tr><td colspan="9" style="padding:10px;color:#94a3b8;">예상 배당 종목이 없습니다.</td></tr>'}</tbody>
          </table>
        </div>
      </details>
    `;
    loadAlertSetting(panel);
  }

  function syncAfterTaxVisibility() {
    const panel = document.getElementById('portfolioAfterTaxDividendPanel');
    if (panel) panel.hidden = !estimatedModeActive();
  }

  document.addEventListener('click', (event) => {
    if (event.target?.closest?.('#dividendModeTabs [data-div-mode]')) setTimeout(syncAfterTaxVisibility, 0);
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
