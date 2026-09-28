(function () {
  const originalRender = typeof window.renderDividends === 'function'
    ? window.renderDividends
    : null;
  if (!originalRender) return;

  const SOURCE_LABELS = {
    kind_etf_confirmed_overlay: 'KIND ETF 확정 분배금 반영',
    opendart_confirmed_disclosure: 'OpenDART 확정공시',
    opendart_historical_fill: 'OpenDART 공식 이력',
    naver: '네이버 추정',
    yahoo_history: 'Yahoo 최근 이력',
    kind_etf_distribution: 'KIND ETF 분배금',
    legacy_fallback: '기존 추정',
  };

  function sourceLabel(value) {
    return SOURCE_LABELS[value] || value || '미확인';
  }

  function money(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `₩${Math.round(number).toLocaleString('ko-KR')}` : '-';
  }

  function percent(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(2)}%` : '-';
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

  function chip(label, value, tone = 'neutral') {
    const tones = {
      official: 'border:rgba(56,189,248,.32);background:rgba(14,116,144,.13);color:#bae6fd;',
      confirmed: 'border:rgba(52,211,153,.32);background:rgba(5,150,105,.11);color:#a7f3d0;',
      estimate: 'border:rgba(167,139,250,.28);background:rgba(109,40,217,.10);color:#ddd6fe;',
      warning: 'border:rgba(251,191,36,.30);background:rgba(180,83,9,.10);color:#fde68a;',
      neutral: 'border:rgba(148,163,184,.24);background:rgba(30,41,59,.38);color:#cbd5e1;',
    };
    return `<span style="display:inline-flex;gap:5px;align-items:center;padding:4px 8px;border:1px solid;border-radius:999px;font-size:11px;line-height:1;${tones[tone] || tones.neutral}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></span>`;
  }

  function sourceConnection(policy) {
    const status = policy?.status || 'legacy_only';
    if (status === 'ok') {
      return { html: chip('공식자료', '연결됨', 'official'), note: 'OpenDART/KIND 공식 근거를 함께 확인합니다.' };
    }
    if (status === 'missing_api_key') {
      return { html: chip('OpenDART', '미연동', 'warning'), note: '현재 금액은 네이버/Yahoo 기반 추정입니다. OpenDART 키를 설정하면 공식 이력과 최근 공시 존재 여부를 함께 확인합니다.' };
    }
    if (status === 'network_disabled') {
      return { html: chip('외부 네트워크', '비활성', 'warning'), note: '외부 네트워크가 비활성이라 공식자료를 조회하지 못했습니다. 기존 추정은 유지합니다.' };
    }
    if (status === 'opendart_unavailable' || status === 'official_enrichment_failed') {
      return { html: chip('공식자료', '조회 실패', 'warning'), note: '공식자료 조회에 실패해 기존 추정을 유지했습니다.' };
    }
    return { html: chip('예측 source', '기존 추정', 'neutral'), note: '현재 확인 가능한 기존 추정 데이터를 표시합니다.' };
  }

  function ensureBanner() {
    const section = document.getElementById('dividendSection')
      || document.querySelector('[data-dividend-section]')
      || document.getElementById('dividendModeTabs')?.closest('section')
      || document.getElementById('dividendModeTabs')?.parentElement;
    if (!section) return null;
    let banner = document.getElementById('dividendSourceStatus');
    if (banner) return banner;
    banner = document.createElement('div');
    banner.id = 'dividendSourceStatus';
    banner.style.cssText = [
      'margin:10px 0 12px',
      'padding:11px 12px',
      'border:1px solid rgba(148,163,184,.22)',
      'border-radius:10px',
      'background:rgba(15,23,42,.36)',
      'font-size:11.5px',
      'line-height:1.55',
    ].join(';');
    const modeTabs = document.getElementById('dividendModeTabs');
    if (modeTabs?.parentElement) modeTabs.parentElement.insertAdjacentElement('afterend', banner);
    else section.prepend(banner);
    return banner;
  }

  function renderSourceStatus(data) {
    const banner = ensureBanner();
    if (!banner) return;
    const policy = data?.forecast_source_policy || {};
    const intelligence = data?.dividend_intelligence || {};
    const trust = intelligence?.trust || {};
    const counts = policy.source_counts || policy.numeric_source_counts || {};
    const recentDecisionCount = Number(policy.recent_decision_disclosure_count || 0);
    const confirmedAmountCount = Number(policy.confirmed_amount_count || 0);
    const confirmedOverrideCount = Number(policy.confirmed_numeric_override_count || trust.official_confirmed_applied_count || 0);
    const kindEtfConfirmedEventCount = Number(policy.kind_etf_confirmed_event_count || 0);
    const kindEtfOverrideCount = Number(policy.kind_etf_numeric_override_count || 0);
    const officialCount = Number(trust.official_evidence_count || 0);
    const estimatedCount = Number(trust.estimated_or_heuristic_count || 0);
    const dartUrl = safeLink(policy.opendart_guide_url);
    const kindUrl = safeLink(policy.kind_etf_reference_url || policy.kind_reference_url);
    const connection = sourceConnection(policy);

    const sourceBreakdown = Object.entries(counts)
      .filter(([, count]) => Number(count) > 0)
      .map(([source, count]) => `${sourceLabel(source)} ${Number(count)}종목`);
    if (recentDecisionCount) sourceBreakdown.push(`최근 배당결정 공시 ${recentDecisionCount}건`);
    if (confirmedAmountCount) sourceBreakdown.push(`구조 검증 확정금액 ${confirmedAmountCount}종목`);
    if (kindEtfConfirmedEventCount) sourceBreakdown.push(`KIND ETF 확정 이벤트 ${kindEtfConfirmedEventCount}건`);
    if (kindEtfOverrideCount) sourceBreakdown.push(`KIND 공식금액 반영 ${kindEtfOverrideCount}건`);

    const links = [
      dartUrl ? `<a href="${escapeHtml(dartUrl)}" target="_blank" rel="noopener noreferrer" style="color:#7dd3fc;">OpenDART 공식자료 ↗</a>` : '',
      kindUrl ? `<a href="${escapeHtml(kindUrl)}" target="_blank" rel="noopener noreferrer" style="color:#7dd3fc;">KIND ETF/배당정보 ↗</a>` : '',
    ].filter(Boolean).join('<span style="color:#475569;">·</span>');

    banner.innerHTML = `
      <div style="display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap;">
        <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;">
          <strong style="font-size:12px;">배당 예상 근거</strong>
          ${connection.html}
          ${chip('공식 근거', `${officialCount}종목`, 'official')}
          ${chip('확정금액 반영', `${confirmedOverrideCount}종목`, confirmedOverrideCount ? 'confirmed' : 'neutral')}
          ${chip('이력·시장 추정', `${estimatedCount}종목`, 'estimate')}
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">${links}</div>
      </div>
      <details style="margin-top:8px;">
        <summary style="cursor:pointer;color:#94a3b8;font-size:11px;">출처별 상세와 확정금액 반영 원칙</summary>
        <div style="margin-top:6px;color:#94a3b8;">
          ${escapeHtml(connection.note)}<br>
          ${sourceBreakdown.length ? escapeHtml(sourceBreakdown.join(' · ')) : '현재 보유종목의 배당 자료가 없습니다.'}
          <br>공식 공시 존재와 forecast 확정금액 반영은 별개입니다. 지급예정일과 금액을 구조적으로 검증하고 기존 예상월과 안전하게 일치할 때만 확정 공시값을 반영하며, 지급일은 임의 생성하지 않습니다.
        </div>
      </details>
    `;
  }

  function estimatedModeActive() {
    const active = document.querySelector('#dividendModeTabs .heatmap-tab.active');
    return !active || active?.dataset?.divMode === 'estimated';
  }

  function ensureAfterTaxPanel() {
    const cards = document.getElementById('dividendSummaryCards')
      || document.querySelector('[data-dividend-summary-cards]')
      || document.getElementById('dividendModeTabs')?.parentElement?.parentElement;
    if (!cards) return null;
    let panel = document.getElementById('portfolioAfterTaxDividendPanel');
    if (panel) return panel;
    panel = document.createElement('section');
    panel.id = 'portfolioAfterTaxDividendPanel';
    panel.setAttribute('aria-label', '포트폴리오 배당 현금흐름 및 Dividend Intelligence');
    panel.style.cssText = [
      'margin:14px 0',
      'padding:14px',
      'border:1px solid rgba(99,102,241,.28)',
      'border-radius:12px',
      'background:linear-gradient(180deg,rgba(15,23,42,.52),rgba(15,23,42,.34))',
      'font-size:12px',
    ].join(';');
    cards.insertAdjacentElement('afterend', panel);
    return panel;
  }

  function evidenceHtml(evidence) {
    const label = escapeHtml(evidence?.label || '근거 확인 불가');
    const url = safeLink(evidence?.evidence_url);
    return `<div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap;"><span>${label}</span>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="color:#7dd3fc;white-space:nowrap;">원문 ↗</a>` : ''}</div>`;
  }

  function qualificationHtml(qualification) {
    const status = qualification?.status || 'not_confirmed';
    const spec = {
      official_qualified: ['공식 해당', '#a7f3d0', 'rgba(5,150,105,.13)', 'rgba(52,211,153,.34)'],
      official_not_qualified: ['공식 미해당', '#fecaca', 'rgba(185,28,28,.10)', 'rgba(248,113,113,.30)'],
      not_confirmed: ['확인 대기', '#fde68a', 'rgba(180,83,9,.09)', 'rgba(251,191,36,.28)'],
      source_unavailable: ['조회 불가', '#cbd5e1', 'rgba(51,65,85,.30)', 'rgba(148,163,184,.24)'],
      not_applicable: ['대상 아님', '#94a3b8', 'rgba(30,41,59,.25)', 'rgba(100,116,139,.20)'],
    }[status] || ['확인 대기', '#fde68a', 'rgba(180,83,9,.09)', 'rgba(251,191,36,.28)'];
    const url = safeLink(qualification?.source_url || qualification?.kind_reference_url);
    return `<div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap;"><span style="display:inline-flex;padding:3px 7px;border:1px solid ${spec[3]};border-radius:999px;background:${spec[2]};color:${spec[1]};font-size:10.5px;font-weight:700;white-space:nowrap;">${spec[0]}</span>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" style="color:#7dd3fc;font-size:10.5px;white-space:nowrap;">공식 근거 ↗</a>` : ''}</div>`;
  }

  function highDividendSummaryHtml(high) {
    if (!high || !Object.keys(high).length) {
      return `<div style="color:#94a3b8;">고배당기업 공식 자격 데이터를 아직 확인할 수 없습니다.</div>`;
    }
    const status = high.source_status || 'source_unavailable';
    const qualified = Number(high.official_qualified_count || 0);
    const notQualified = Number(high.official_not_qualified_count || 0);
    const pending = Number(high.not_confirmed_count || 0);
    const unavailable = Number(high.source_unavailable_count || 0);
    const ok = (status === 'ok' || status === 'no_applicable_holdings') && unavailable === 0;
    const share = high.qualified_projected_gross_share_pct == null ? '-' : percent(high.qualified_projected_gross_share_pct);
    const sourceUrl = safeLink(high.kind_reference_url);
    return `
      <div style="display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;">
        <div>
          <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;"><strong>고배당기업 공식 자격</strong>${chip(ok ? '공식 조회' : '조회 상태', ok ? '확인' : '제한', ok ? 'official' : 'warning')}</div>
          <div style="margin-top:5px;color:#94a3b8;font-size:11px;">회사가 공식 기업가치 제고 계획 공시에 기재한 고배당기업 여부만 표시합니다. Wealth가 요건을 추정하지 않으며 세제특례를 자동 적용하지 않습니다.</div>
        </div>
        ${sourceUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer" style="color:#7dd3fc;font-size:11px;white-space:nowrap;">KIND 고배당기업 현황 ↗</a>` : ''}
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:7px;margin-top:9px;">
        <div style="padding:8px;border-radius:8px;background:rgba(5,150,105,.08);border:1px solid rgba(52,211,153,.16);"><div style="color:#94a3b8;font-size:10.5px;">공식 해당</div><strong style="display:block;margin-top:2px;">${qualified}종목</strong></div>
        <div style="padding:8px;border-radius:8px;background:rgba(30,41,59,.34);"><div style="color:#94a3b8;font-size:10.5px;">관련 예상 배당</div><strong style="display:block;margin-top:2px;">${money(high.qualified_projected_gross_krw || 0)}</strong><small style="color:#94a3b8;">전체 예상의 ${share}</small></div>
        <div style="padding:8px;border-radius:8px;background:rgba(30,41,59,.34);"><div style="color:#94a3b8;font-size:10.5px;">공식 미해당 / 확인 대기</div><strong style="display:block;margin-top:2px;">${notQualified} / ${pending}</strong></div>
        <div style="padding:8px;border-radius:8px;background:rgba(30,41,59,.34);"><div style="color:#94a3b8;font-size:10.5px;">공식 조회 불가</div><strong style="display:block;margin-top:2px;">${unavailable}종목</strong></div>
      </div>
    `;
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
      return `<div><strong>예측 정확도</strong><div style="margin-top:3px;color:#94a3b8;">평가 데이터를 확인할 수 없습니다. · ${scope} 보유 snapshot 기준</div></div>`;
    }
    if (accuracy.status !== 'ready') {
      const count = Number(accuracy.snapshot_count || 0);
      const latest = accuracy.latest_snapshot_as_of_date ? ` · 최근 ${escapeHtml(accuracy.latest_snapshot_as_of_date)}` : '';
      return `<div><strong>예측 정확도 · 데이터 누적 중</strong><div style="margin-top:3px;color:#94a3b8;">snapshot ${count}개${latest} · ${scope} 보유 snapshot 기준</div></div>`;
    }
    const months = Number(accuracy.evaluated_month_count || 0);
    const amount = accuracy.amount_accuracy_complete === true
      ? `MAE ${money(accuracy.mae_krw)} · WAPE ${percent(accuracy.wape_percent)}`
      : '지급월/이벤트 평가는 가능하지만 비교 가능한 gross 금액 또는 forecast attribution이 불완전합니다.';
    return `<div><strong>예측 정확도 · 과거 point-in-time</strong><div style="margin-top:3px;color:#cbd5e1;">${amount}</div><div style="margin-top:3px;color:#64748b;">완료 월 ${months}개 · 현재 월 제외 · 과거 snapshot 재생성 없음</div></div>`;
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
      statusNode.textContent = checkbox.checked ? '켜짐 · 새 이벤트만 알림' : '꺼짐 · 기본값';
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
        statusNode.textContent = checkbox.checked ? '켜짐 · 새 이벤트만 알림' : '꺼짐 · 기본값';
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
      panel.innerHTML = `<div style="font-weight:750;font-size:14px;">Dividend Intelligence</div><div style="margin-top:5px;font-size:12px;color:#94a3b8;">배당 forecast 또는 알려진 세금 기준을 확인할 수 없어 계산하지 않았습니다.</div>`;
      return;
    }

    const complete = view.calculation_status === 'complete';
    const coverage = Number(view.after_tax_dividend_coverage_pct || 0);
    const afterCash = complete ? view.after_known_tax_cash_krw : view.calculable_after_known_tax_cash_krw;
    const gross = Number(view.gross_annual_dividend_krw || 0);
    const knownTax = Math.max(gross - Number(afterCash || 0), 0);
    const marketAfterYield = complete ? view.after_known_tax_yield_on_market_value_pct : null;
    const costAfterYield = complete ? view.after_known_tax_yield_on_cost_pct : null;
    const attributionNote = view.forecast_attribution_complete ? '' : ` · 미귀속 예상 ${money(view.unattributed_annual_dividend_krw)}`;
    const trust = intelligence?.trust || {};
    const high = intelligence?.high_dividend || {};
    const intelligenceRows = Array.isArray(intelligence?.instruments) && intelligence.instruments.length
      ? intelligence.instruments
      : (Array.isArray(view.instruments) ? view.instruments : []);

    const instrumentRows = intelligenceRows
      .filter((row) => Number(row?.gross_annual_dividend_krw || 0) > 0)
      .map((row) => {
        const tax = row.calculation_status === 'calculated' ? money(row.known_tax_krw) : '계산 제외';
        const after = row.calculation_status === 'calculated' ? money(row.after_known_tax_cash_krw) : '확인 불가';
        const grossContribution = row.gross_portfolio_contribution_pct == null ? '-' : percent(row.gross_portfolio_contribution_pct);
        const afterContribution = row.calculable_after_known_tax_contribution_pct == null ? '-' : percent(row.calculable_after_known_tax_contribution_pct);
        return `
          <tr>
            <td style="padding:8px 7px;vertical-align:top;"><strong>${escapeHtml(row.name || row.code)}</strong><br><small style="color:#94a3b8;">${escapeHtml(row.code)} · ${escapeHtml(row.currency)}</small>${accountDetailsHtml(row)}</td>
            <td style="padding:8px 7px;vertical-align:top;">${evidenceHtml(row.forecast_evidence)}</td>
            <td style="padding:8px 7px;vertical-align:top;">${qualificationHtml(row.high_dividend_qualification)}</td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${money(row.gross_annual_dividend_krw)}<br><small style="color:#94a3b8;">기여 ${grossContribution}</small></td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${tax}</td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${after}<br><small style="color:#94a3b8;">기여 ${afterContribution}</small></td>
            <td style="padding:8px 7px;text-align:right;vertical-align:top;">${percent(row.gross_yield_market_pct)}${row.after_known_tax_yield_market_pct === null ? '' : ` → ${percent(row.after_known_tax_yield_market_pct)}`}</td>
            <td style="padding:8px 7px;vertical-align:top;">${escapeHtml(row.calculation_status)}</td>
          </tr>`;
      }).join('');

    panel.innerHTML = `
      <div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;">
        <div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;"><strong style="font-size:15px;">Dividend Intelligence</strong><span style="color:#64748b;">배당 현금흐름 · 근거 · 공식 자격</span></div>
          <div style="margin-top:3px;font-size:11px;color:#94a3b8;">최종 종합소득세가 아니라 기존 검증 엔진의 원천징수·알려진 세금 기준 screening입니다. 세전 예상 ${money(gross)}</div>
        </div>
        ${chip('세후 계산', complete ? '전체 가능' : `부분 ${percent(coverage)}`, complete ? 'confirmed' : 'warning')}
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-top:12px;">
        <div style="padding:11px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">알려진 세금 후 예상 현금</div><strong style="display:block;margin-top:4px;font-size:18px;">${money(afterCash)}</strong></div>
        <div style="padding:11px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">알려진 세금</div><strong style="display:block;margin-top:4px;font-size:18px;">${complete ? money(knownTax) : '계산 가능 부분만'}</strong></div>
        <div style="padding:11px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">평가금액 기준 세후 배당수익률</div><strong style="display:block;margin-top:4px;font-size:18px;">${marketAfterYield == null ? '전체 계산 보류' : percent(marketAfterYield)}</strong><small style="display:block;margin-top:4px;color:#94a3b8;">평균매입가 기준 ${costAfterYield == null ? '-' : percent(costAfterYield)}</small></div>
        <div style="padding:11px;border-radius:9px;background:rgba(30,41,59,.56);"><div style="font-size:11px;color:#94a3b8;">세후 계산 커버리지</div><strong style="display:block;margin-top:4px;font-size:18px;">${percent(coverage)}</strong></div>
      </div>

      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:9px;padding:8px 0;">
        ${chip('공식 근거', `${Number(trust.official_evidence_count || 0)}종목`, 'official')}
        ${chip('확정금액 반영', `${Number(trust.official_confirmed_applied_count || 0)}종목`, 'confirmed')}
        ${chip('추정', `${Number(trust.estimated_or_heuristic_count || 0)}종목`, 'estimate')}
        ${chip('미귀속 residual', money(trust.unattributed_residual_krw || 0), Number(trust.unattributed_residual_krw || 0) ? 'warning' : 'neutral')}
      </div>

      <div style="margin-top:3px;padding:11px;border:1px solid rgba(56,189,248,.16);border-radius:10px;background:rgba(14,116,144,.05);">${highDividendSummaryHtml(high)}</div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:8px;margin-top:9px;">
        <div style="padding:10px;border-radius:9px;background:rgba(30,41,59,.30);font-size:11.5px;line-height:1.5;">${accuracyHtml(intelligence?.accuracy)}</div>
        <div style="padding:10px;border:1px solid rgba(148,163,184,.15);border-radius:9px;display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;">
          <div><strong style="font-size:11.5px;">배당·금융소득 알림</strong><div style="margin-top:2px;color:#94a3b8;font-size:10.5px;">기본 OFF · 일일 마감 새 공식 이벤트와 개인별 금융소득 상태만 중복 없이 알림</div></div>
          <label style="display:flex;gap:7px;align-items:center;font-size:11px;cursor:pointer;"><input id="dividendIntelligenceAlertsEnabled" type="checkbox"><span id="dividendIntelligenceAlertStatus">설정 확인 중…</span></label>
        </div>
      </div>

      <div style="margin-top:9px;font-size:10.8px;line-height:1.55;color:#64748b;">평가금액은 현재 주식 평가액만 사용하며 현금·예수금은 제외합니다. 평균매입가 기준은 평균매입가×수량이고 외화자산은 현재환율로 환산합니다.${attributionNote}${complete ? '' : `<br><strong style="color:#fbbf24;">커버리지가 100%가 아니므로 포트폴리오 전체 세후 수익률은 표시하지 않습니다.</strong> 계산 제외 예상 배당: ${money(view.unsupported_gross_dividend_krw)}`}</div>

      <details style="margin-top:10px;">
        <summary style="cursor:pointer;font-size:12px;font-weight:700;">종목·계좌별 근거와 공식 자격 보기</summary>
        <div style="overflow-x:auto;margin-top:8px;">
          <table style="width:100%;border-collapse:collapse;font-size:11.2px;min-width:1180px;">
            <thead style="color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.22);"><tr>
              <th style="padding:7px;text-align:left;">종목 / 계좌</th>
              <th style="padding:7px;text-align:left;">배당 예상 근거</th>
              <th style="padding:7px;text-align:left;">고배당기업 공식 자격</th>
              <th style="padding:7px;text-align:right;">세전 예상 / 기여</th>
              <th style="padding:7px;text-align:right;">알려진 세금</th>
              <th style="padding:7px;text-align:right;">예상 수령 / 기여</th>
              <th style="padding:7px;text-align:right;">평가금액 수익률</th>
              <th style="padding:7px;text-align:left;">상태</th>
            </tr></thead>
            <tbody>${instrumentRows || '<tr><td colspan="8" style="padding:10px;color:#94a3b8;">예상 배당 종목이 없습니다.</td></tr>'}</tbody>
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