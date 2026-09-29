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
  const DIVIDEND_MONTHLY_GOAL_KEY = 'wealth_dividend_monthly_goal_krw_v1';

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

  function calculationStatusLabel(value) {
    return {
      calculated: '계산 완료',
      unsupported: '계산 제외',
      unavailable: '확인 불가',
      partial: '부분 계산',
    }[value] || value || '-';
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
    const section = document.getElementById('dividendPanel')
      || document.getElementById('dividendSection')
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
    const dividendPanel = document.getElementById('dividendPanel')
      || document.getElementById('dividendModeTabs')?.closest('section');
    const cards = document.getElementById('dividendSummaryCards')
      || dividendPanel?.querySelector('.dividend-summary-cards')
      || document.querySelector('[data-dividend-summary-cards]');
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
    const url = status === 'not_applicable'
      ? null
      : safeLink(qualification?.source_url || qualification?.kind_reference_url);
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

  function scheduleMonths(data) {
    const raw = data?.monthly_schedule;
    const source = Array.isArray(raw)
      ? raw
      : Object.entries(raw && typeof raw === 'object' ? raw : {}).map(([key, value]) => {
          const tail = String(key).split('-').pop();
          return { ...(value || {}), month: Number(value?.month || tail) };
        });
    const byMonth = new Map();
    source.forEach((row) => {
      const month = Number(row?.month);
      if (month >= 1 && month <= 12) byMonth.set(month, row || {});
    });
    return Array.from({ length: 12 }, (_, index) => {
      const month = index + 1;
      const row = byMonth.get(month) || {};
      return {
        month,
        total_krw: Number(row.total_krw || 0),
        items: Array.isArray(row.items) ? row.items : [],
      };
    });
  }

  function instrumentKey(code, currency) {
    const codeText = String(code || '').trim().toUpperCase();
    const currencyText = String(currency || 'KRW').trim().toUpperCase();
    return codeText ? `${codeText}|${currencyText}` : null;
  }

  function monthlyGoalStorageKey(data) {
    const owner = String(data?.dividend_intelligence?.owner || '모두').trim() || '모두';
    return `${DIVIDEND_MONTHLY_GOAL_KEY}:${owner}`;
  }

  function readMonthlyGoal(data) {
    try {
      const value = Number(localStorage.getItem(monthlyGoalStorageKey(data)) || 0);
      return Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
    } catch (_) {
      return 0;
    }
  }

  function saveMonthlyGoal(data, value) {
    try {
      const parsed = Number(value);
      const key = monthlyGoalStorageKey(data);
      if (Number.isFinite(parsed) && parsed > 0) localStorage.setItem(key, String(Math.round(parsed)));
      else localStorage.removeItem(key);
    } catch (_) {
      // localStorage may be unavailable in hardened browser contexts.
    }
  }

  function buildMonthlyAfterTaxCashflow(data, rows, view, trust) {
    const months = scheduleMonths(data).map((row) => ({
      ...row,
      covered_gross_krw: 0,
      attributed_gross_krw: 0,
      after_known_tax_cash_krw: 0,
      coverage_pct: row.total_krw > 0 ? 0 : 100,
    }));
    const instrumentMap = new Map();
    (rows || []).forEach((row) => {
      const key = instrumentKey(row?.code, row?.currency);
      if (key && !instrumentMap.has(key)) instrumentMap.set(key, row);
    });

    const grossByInstrument = new Map();
    months.forEach((monthRow, monthIndex) => {
      monthRow.items.forEach((item) => {
        const gross = Math.max(Number(item?.payout_krw || 0), 0);
        if (!gross) return;
        const key = instrumentKey(item?.code, item?.currency);
        const instrument = key ? instrumentMap.get(key) : null;
        if (!instrument || instrument.calculation_status !== 'calculated') return;
        monthRow.covered_gross_krw += gross;
        if (!grossByInstrument.has(key)) grossByInstrument.set(key, Array(12).fill(0));
        grossByInstrument.get(key)[monthIndex] += gross;
      });
    });

    const unassignedInstruments = [];
    let instrumentAnnualCash = 0;
    instrumentMap.forEach((instrument, key) => {
      if (instrument.calculation_status !== 'calculated') return;
      const annualGross = Math.max(Number(instrument.gross_annual_dividend_krw || 0), 0);
      const annualCash = Math.max(Number(instrument.after_known_tax_cash_krw || 0), 0);
      if (!(annualGross > 0) || !(annualCash >= 0)) return;
      instrumentAnnualCash += annualCash;

      const monthlyGross = grossByInstrument.get(key) || Array(12).fill(0);
      const positiveMonths = monthlyGross
        .map((value, index) => ({ value, index }))
        .filter((item) => item.value > 0);
      const scheduleGross = positiveMonths.reduce((sum, item) => sum + item.value, 0);
      const roundingTolerance = Math.max(1, (positiveMonths.length + 1) * 0.5);
      let allocatableCash = 0;
      let reason = null;

      if (!(scheduleGross > 0)) {
        reason = 'monthly_schedule_missing';
      } else if (scheduleGross > annualGross + roundingTolerance) {
        reason = 'monthly_schedule_exceeds_annual';
      } else {
        const scheduleRatio = Math.min(scheduleGross / annualGross, 1);
        allocatableCash = Math.max(Math.min(Math.round(annualCash * scheduleRatio), Math.round(annualCash)), 0);
        if (scheduleGross < annualGross - roundingTolerance) reason = 'partial_monthly_schedule';
      }

      let assigned = 0;
      if (allocatableCash > 0 && positiveMonths.length) {
        positiveMonths.forEach((item, index) => {
          const isLast = index === positiveMonths.length - 1;
          const allocated = isLast
            ? Math.max(allocatableCash - assigned, 0)
            : Math.max(Math.round(allocatableCash * item.value / scheduleGross), 0);
          months[item.index].after_known_tax_cash_krw += allocated;
          months[item.index].attributed_gross_krw += item.value;
          assigned += allocated;
        });
      }

      const unassignedCash = Math.max(Math.round(annualCash) - assigned, 0);
      if (unassignedCash > 0 || reason) {
        unassignedInstruments.push({
          code: instrument.code,
          name: instrument.name || instrument.code,
          currency: instrument.currency,
          annual_gross_krw: annualGross,
          scheduled_gross_krw: scheduleGross,
          after_known_tax_cash_krw: annualCash,
          attributed_after_known_tax_cash_krw: assigned,
          unassigned_after_known_tax_cash_krw: unassignedCash,
          schedule_coverage_pct: annualGross > 0 ? Math.min(scheduleGross / annualGross * 100, 100) : 0,
          reason: reason || 'rounding_remainder',
        });
      }
    });

    months.forEach((row) => {
      const gross = Math.max(Number(row.total_krw || 0), 0);
      row.coverage_pct = gross > 0
        ? Math.min((row.covered_gross_krw / gross) * 100, 100)
        : 100;
    });

    const attributedCash = months.reduce((sum, row) => sum + row.after_known_tax_cash_krw, 0);
    const canonicalAfterCash = view?.calculation_status === 'complete'
      ? Number(view.after_known_tax_cash_krw || 0)
      : Number(view?.calculable_after_known_tax_cash_krw || 0);
    const canonicalGross = Math.max(Number(view?.gross_annual_dividend_krw || data?.total_annual_dividend_krw || 0), 0);
    const scheduledGross = months.reduce((sum, row) => sum + Math.max(Number(row.total_krw || 0), 0), 0);
    const residual = Number(trust?.unattributed_residual_krw || 0);
    const cashTolerance = Math.max(1, (instrumentMap.size + 1) * 0.5);
    const annualCashReconciled = view?.calculation_status === 'complete'
      && Number.isFinite(canonicalAfterCash)
      && Math.abs(instrumentAnnualCash - canonicalAfterCash) <= cashTolerance;
    const annualAvailable = view?.calculation_status === 'complete'
      && residual === 0
      && annualCashReconciled;
    const unassignedCash = annualAvailable
      ? Math.max(Math.round(canonicalAfterCash) - attributedCash, 0)
      : Math.max(Math.round(instrumentAnnualCash) - attributedCash, 0);
    const attributionCoveragePct = canonicalAfterCash > 0
      ? Math.min(attributedCash / canonicalAfterCash * 100, 100)
      : (annualAvailable ? 100 : 0);
    const grossScheduleCoveragePct = canonicalGross > 0
      ? Math.min(scheduledGross / canonicalGross * 100, 100)
      : 100;
    const complete = annualAvailable
      && unassignedCash <= cashTolerance
      && !unassignedInstruments.some((row) => row.reason === 'monthly_schedule_exceeds_annual');
    const status = complete ? 'complete' : (annualAvailable ? 'partial' : 'unavailable');

    return {
      months,
      status,
      complete,
      annualAvailable,
      canonicalAfterCash,
      attributedCash,
      unassignedCash,
      attributionCoveragePct,
      canonicalGross,
      scheduledGross,
      grossScheduleCoveragePct,
      annualCashReconciled,
      unassignedInstruments,
    };
  }

  function cashflowDecisionHtml(data, rows, view, trust) {
    const flow = buildMonthlyAfterTaxCashflow(data, rows, view, trust);
    const goal = readMonthlyGoal(data);
    const annualCash = flow.annualAvailable ? flow.canonicalAfterCash : flow.attributedCash;
    const monthlyAverage = annualCash / 12;
    const ordered = [...flow.months].sort((a, b) => b.after_known_tax_cash_krw - a.after_known_tax_cash_krw);
    const maxMonth = ordered[0] || { month: 1, after_known_tax_cash_krw: 0 };
    const minMonth = ordered[ordered.length - 1] || { month: 1, after_known_tax_cash_krw: 0 };
    const maxShare = annualCash > 0 ? (maxMonth.after_known_tax_cash_krw / annualCash) * 100 : 0;
    const minimumMetMonths = goal > 0 && flow.annualAvailable
      ? flow.months.filter((row) => row.after_known_tax_cash_krw >= goal).length
      : null;
    const pendingMonths = goal > 0 && flow.status === 'partial' ? 12 - minimumMetMonths : 0;
    const annualTarget = goal * 12;
    const annualGap = goal > 0 && flow.annualAvailable ? Math.max(annualTarget - annualCash, 0) : null;
    const annualSurplus = goal > 0 && flow.annualAvailable ? Math.max(annualCash - annualTarget, 0) : null;
    const contributors = (rows || [])
      .filter((row) => row?.calculation_status === 'calculated' && Number(row?.after_known_tax_cash_krw || 0) > 0)
      .sort((a, b) => Number(b.after_known_tax_cash_krw || 0) - Number(a.after_known_tax_cash_krw || 0))
      .slice(0, 5);
    const maxCash = Math.max(...flow.months.map((row) => row.after_known_tax_cash_krw), 1);

    const monthCards = flow.months.map((row) => {
      const ratio = Math.max(Math.min(row.after_known_tax_cash_krw / maxCash, 1), 0);
      const goalMet = goal > 0 && flow.annualAvailable && row.after_known_tax_cash_krw >= goal;
      const pending = goal > 0 && flow.status === 'partial' && !goalMet;
      const incomplete = row.coverage_pct < 99.99;
      const goalBadge = goalMet
        ? `<span style="color:#6ee7b7;font-size:9.5px;">${flow.complete ? '목표 ✓' : '최소 충족 ✓'}</span>`
        : (pending ? '<span style="color:#fbbf24;font-size:9.5px;">판정 대기</span>' : '');
      return `
        <div style="padding:8px;border-radius:8px;background:rgba(15,23,42,.42);border:1px solid ${goalMet ? 'rgba(52,211,153,.24)' : (pending ? 'rgba(251,191,36,.20)' : 'rgba(148,163,184,.12)')};min-width:0;">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:5px;"><strong style="font-size:11px;">${row.month}월</strong>${goalBadge}</div>
          <div style="height:4px;border-radius:999px;background:rgba(51,65,85,.55);margin:6px 0 5px;overflow:hidden;"><div style="height:100%;width:${(ratio * 100).toFixed(1)}%;background:linear-gradient(90deg,#60a5fa,#8b5cf6);"></div></div>
          <strong style="display:block;font-size:11.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${money(row.after_known_tax_cash_krw)}</strong>
          <small style="display:block;margin-top:2px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">귀속 하한 · 세전 ${money(row.total_krw)}${incomplete ? ` · ${percent(row.coverage_pct)}` : ''}</small>
        </div>`;
    }).join('');

    const contributorHtml = contributors.length
      ? contributors.map((row, index) => {
          const share = annualCash > 0 ? Number(row.after_known_tax_cash_krw || 0) / annualCash * 100 : 0;
          return `<div style="display:grid;grid-template-columns:22px minmax(100px,1fr) auto;gap:7px;align-items:center;padding:4px 0;border-top:${index ? '1px solid rgba(148,163,184,.10)' : '0'};"><span style="color:#64748b;">${index + 1}</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(row.name || row.code)}</span><span style="text-align:right;white-space:nowrap;">${money(row.after_known_tax_cash_krw)} <small style="color:#64748b;">${percent(share)}</small></span></div>`;
        }).join('')
      : '<div style="color:#64748b;">계산 가능한 종목별 예상 수령액이 없습니다.</div>';

    const unresolvedHtml = flow.unassignedInstruments.length
      ? flow.unassignedInstruments
        .slice()
        .sort((a, b) => Number(b.unassigned_after_known_tax_cash_krw || 0) - Number(a.unassigned_after_known_tax_cash_krw || 0))
        .slice(0, 5)
        .map((row) => `<div style="display:flex;gap:8px;justify-content:space-between;border-top:1px solid rgba(148,163,184,.08);padding:3px 0;"><span>${escapeHtml(row.name || row.code)}</span><span style="white-space:nowrap;">월 미정 ${money(row.unassigned_after_known_tax_cash_krw)}</span></div>`)
        .join('')
      : '';

    let goalSummary = '<strong style="font-size:16px;">월 목표 미설정</strong><small style="display:block;margin-top:3px;color:#64748b;">알려진 세금 후 월배당 목표를 입력하면 충족 월과 연간 부족액을 계산합니다.</small>';
    if (goal > 0 && !flow.annualAvailable) {
      goalSummary = `<strong style="font-size:16px;color:#fbbf24;">목표 비교 보류</strong><small style="display:block;margin-top:3px;color:#94a3b8;">연간 알려진 세금 후 합계 자체가 완전하지 않아 목표 비교를 보류합니다.</small>`;
    } else if (goal > 0) {
      const annualText = annualGap > 0 ? `연간 총액 기준 부족 ${money(annualGap)}` : `연간 총액 기준 초과 ${money(annualSurplus)}`;
      if (flow.complete) {
        goalSummary = `<strong style="font-size:16px;">${minimumMetMonths} / 12개월 충족</strong><small style="display:block;margin-top:3px;color:${annualGap > 0 ? '#fbbf24' : '#6ee7b7'};">${annualText}</small>`;
      } else {
        goalSummary = `<strong style="font-size:16px;color:#fbbf24;">최소 ${minimumMetMonths}개월 충족 · ${pendingMonths}개월 판정 대기</strong><small style="display:block;margin-top:3px;color:${annualGap > 0 ? '#fbbf24' : '#6ee7b7'};">${annualText} · 월 미정 ${money(flow.unassignedCash)}</small>`;
      }
    }

    const attributionTone = flow.complete ? '#6ee7b7' : (flow.annualAvailable ? '#fbbf24' : '#fb7185');
    const attributionText = flow.complete
      ? '월 귀속 100%'
      : `월 귀속 ${percent(flow.attributionCoveragePct)} · 월 미정 ${money(flow.unassignedCash)}`;
    const rangeText = flow.complete
      ? '월별 알려진 세금 후 귀속 100% · 연간 known-after-tax 합계와 일치'
      : (flow.annualAvailable
        ? `연간 known-after-tax 합계는 완전 · ${attributionText}`
        : '연간 알려진 세금 후 합계가 불완전 · 목표 판단 보류');

    return `
      <div id="dividendCashflowDecision" style="margin-top:3px;padding:12px;border:1px solid rgba(139,92,246,.18);border-radius:10px;background:linear-gradient(135deg,rgba(30,41,59,.30),rgba(76,29,149,.05));">
        <div style="display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;">
          <div><strong style="font-size:13px;">선택 연도 12개월 배당 현금흐름</strong><div style="margin-top:3px;color:#94a3b8;font-size:10.8px;">종목별 연간 알려진 세금 후 예상 현금 중 기존 forecast 지급월에 안전하게 연결되는 금액만 월별로 귀속합니다. 월이 없는 금액은 임의 배분하지 않습니다.</div></div>
          <label style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;font-size:10.8px;color:#94a3b8;">알려진 세금 후 월 목표 <input id="dividendMonthlyNetGoal" name="dividend_monthly_goal_krw" type="number" min="0" step="10000" data-korean-currency value="${goal || ''}" placeholder="예: 1000000" style="width:132px;padding:6px 8px;border:1px solid rgba(148,163,184,.25);border-radius:7px;background:rgba(15,23,42,.72);color:#f8fafc;"></label>
        </div>
        <div style="margin-top:7px;color:${attributionTone};font-size:10.8px;font-weight:700;">${attributionText}</div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:7px;margin-top:10px;">
          <div style="padding:9px;border-radius:8px;background:rgba(30,41,59,.36);"><div style="font-size:10.5px;color:#94a3b8;">월평균 예상 수령</div><strong style="display:block;margin-top:2px;font-size:15px;">${money(monthlyAverage)}</strong><small style="color:#64748b;">연간 알려진 세금 후 총액 ÷ 12</small></div>
          <div style="padding:9px;border-radius:8px;background:rgba(30,41,59,.36);"><div style="font-size:10.5px;color:#94a3b8;">최대 / 최소 월</div><strong style="display:block;margin-top:2px;font-size:13px;">${maxMonth.month}월 ${money(maxMonth.after_known_tax_cash_krw)}</strong><small style="color:#64748b;">${minMonth.month}월 ${money(minMonth.after_known_tax_cash_krw)}${flow.complete ? '' : ' · 귀속분 기준'}</small></div>
          <div style="padding:9px;border-radius:8px;background:rgba(30,41,59,.36);"><div style="font-size:10.5px;color:#94a3b8;">최대월 편중</div><strong style="display:block;margin-top:2px;font-size:15px;">${percent(maxShare)}</strong><small style="color:#64748b;">${flow.complete ? '연간 예상 수령 기준' : '연간 총액 대비 귀속 하한'}</small></div>
          <div style="padding:9px;border-radius:8px;background:rgba(30,41,59,.36);"><div style="font-size:10.5px;color:#94a3b8;">월 목표 상태</div>${goalSummary}</div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(12,minmax(76px,1fr));gap:5px;margin-top:9px;overflow-x:auto;padding-bottom:2px;">${monthCards}</div>

        <div style="display:grid;grid-template-columns:minmax(280px,1.2fr) minmax(260px,.8fr);gap:8px;margin-top:9px;">
          <div style="padding:9px;border-radius:8px;background:rgba(30,41,59,.27);"><strong style="font-size:11px;">상위 예상 수령 기여 종목</strong><div style="margin-top:5px;font-size:10.8px;">${contributorHtml}</div></div>
          <div style="padding:9px;border-radius:8px;background:rgba(30,41,59,.27);font-size:10.8px;line-height:1.55;color:#94a3b8;"><strong style="color:#cbd5e1;">계산 범위</strong><br>${rangeText}<br>월별 배분은 지급 권리 확정이 아니며 기존 forecast 지급월과 기존 검증 세금 결과만 재사용합니다. residual과 월 미정 금액은 특정 월·종목에 임의 배분하지 않습니다.${unresolvedHtml ? `<details style="margin-top:5px;"><summary style="cursor:pointer;color:#cbd5e1;">월 미정 종목 보기</summary><div style="margin-top:4px;">${unresolvedHtml}</div></details>` : ''}</div>
        </div>
      </div>`;
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

  function bindCashflowGoal(panel, data) {
    const input = panel.querySelector('#dividendMonthlyNetGoal');
    if (!input || input.dataset.bound === '1') return;
    input.dataset.bound = '1';
    input.addEventListener('input', () => saveMonthlyGoal(data, input.value));
    input.addEventListener('change', () => renderAfterTaxPanel(data));
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') input.blur();
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
            <td style="padding:8px 7px;vertical-align:top;">${escapeHtml(calculationStatusLabel(row.calculation_status))}</td>
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

      ${cashflowDecisionHtml(data, intelligenceRows, view, trust)}

      <div style="margin-top:9px;padding:11px;border:1px solid rgba(56,189,248,.16);border-radius:10px;background:rgba(14,116,144,.05);">${highDividendSummaryHtml(high)}</div>

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
    bindCashflowGoal(panel, data);
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