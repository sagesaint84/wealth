/* Wealth IPO Subsystem Frontend Module */
(() => {
  'use strict';

  const dateParts = (value) => {
    const match = typeof value === 'string' ? value.match(/^(\d{4})-(\d{2})-(\d{2})$/) : null;
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const candidate = new Date(Date.UTC(year, month - 1, day));
    if (candidate.getUTCFullYear() !== year || candidate.getUTCMonth() !== month - 1 || candidate.getUTCDate() !== day) return null;
    return { year, month, day, value };
  };

  const todayKst = (now = new Date()) => {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(now).reduce((result, part) => {
      if (part.type !== 'literal') result[part.type] = part.value;
      return result;
    }, {});
    return `${parts.year}-${parts.month}-${parts.day}`;
  };

  const subscriptionStatus = (ipo, today = todayKst()) => {
    const start = dateParts(ipo?.subscription_start);
    const end = dateParts(ipo?.subscription_end);
    const current = dateParts(today);
    if (!start || !end || !current || start.value > end.value) return null;
    if (current.value < start.value) return '예정';
    if (current.value <= end.value) return '중';
    return '마감';
  };

  const ipoMonthKey = (ipo) => {
    const raw = typeof ipo?.presentation_sort_date === 'string' ? ipo.presentation_sort_date.trim() : '';
    const parts = dateParts(raw);
    if (!parts) return null;
    const mm = String(parts.month).padStart(2, '0');
    return `${parts.year}-${mm}`;
  };

  const currentKstYearMonth = () => {
    const today = todayKst();
    const parts = dateParts(today);
    if (!parts) return { year: 2026, month: 9, key: '2026-09' };
    const mm = String(parts.month).padStart(2, '0');
    return { year: parts.year, month: parts.month, key: `${parts.year}-${mm}` };
  };

  const shiftIpoMonth = (year, month, delta) => {
    let nextMonth = month + delta;
    let nextYear = year;
    while (nextMonth < 1) {
      nextMonth += 12;
      nextYear -= 1;
    }
    while (nextMonth > 12) {
      nextMonth -= 12;
      nextYear += 1;
    }
    const mm = String(nextMonth).padStart(2, '0');
    return { year: nextYear, month: nextMonth, key: `${nextYear}-${mm}` };
  };

  const getLatestPastMonth = (ipos) => {
    const pastIpos = (ipos || []).filter(item => item && item.filter_group === 'PAST');
    const monthKeys = [];
    pastIpos.forEach(item => {
      const key = ipoMonthKey(item);
      if (key) monthKeys.push(key);
    });
    if (monthKeys.length === 0) return null;
    monthKeys.sort().reverse();
    const latest = monthKeys[0];
    const [yStr, mStr] = latest.split('-');
    return { year: parseInt(yStr, 10), month: parseInt(mStr, 10), key: latest };
  };

  window.WealthIpoDate = {
    dateParts,
    todayKst,
    subscriptionStatus,
    ipoMonthKey,
    currentKstYearMonth,
    shiftIpoMonth,
    getLatestPastMonth,
  };

  let currentRevision = 0;
  let familyMembers = ['아빠', '엄마', '자녀'];
  let userApplications = {};
  let marketIpos = [];
  let ipoFilterGroup = 'ALL';
  let refreshInFlight = false;
  let ipoHistoryYear = null;
  let ipoHistoryMonth = null;
  let ipoHistoryInitialized = false;

  function formatMoney(num) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    return Math.round(num).toLocaleString('ko-KR');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  async function loadIpoSchedule() {
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;

    try {
      // 1. Fetch user applications and current revision
      const appRes = await fetch('/api/ipo/applications');
      if (appRes.ok) {
        const appData = await appRes.json();
        currentRevision = appData.revision || 0;
        userApplications = appData.applications || {};
        if (Array.isArray(appData.family_members) && appData.family_members.length > 0) {
          familyMembers = appData.family_members;
        }
      }

      // 2. Fetch canonical market IPO records
      const marketRes = await fetch('/api/ipo/market');
      if (!marketRes.ok) {
        wrapper.innerHTML = '<p class="empty-text" style="padding:24px;text-align:center;">공모주 일정을 불러올 수 없습니다.</p>';
        return;
      }
      const marketData = await marketRes.json();
      marketIpos = Array.isArray(marketData.ipos) ? marketData.ipos : [];
      renderIpoList();
    } catch (err) {
      console.error('Failed to load IPO data:', err);
      wrapper.innerHTML = '<p class="empty-text" style="padding:24px;text-align:center;">공모주 데이터를 불러오는 중 오류가 발생했습니다.</p>';
    }
  }

  async function refreshIpoSchedule() {
    if (refreshInFlight) return;
    const button = document.getElementById('ipoRefreshBtn');
    const wrapper = document.getElementById('ipoListWrapper');
    refreshInFlight = true;
    if (button) {
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.textContent = '갱신 중…';
    }
    try {
      const res = await fetch('/api/ipo/market/refresh', { method: 'POST' });
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      const data = await res.json();
      marketIpos = Array.isArray(data.market?.ipos) ? data.market.ipos : marketIpos;
      renderIpoList();
    } catch (err) {
      console.error('Failed to refresh IPO market data:', err);
      if (wrapper) {
        const message = document.createElement('p');
        message.className = 'empty-text ipo-refresh-error';
        message.textContent = '공모주 일정 동기화에 실패했습니다. 기존 데이터를 유지합니다.';
        wrapper.prepend(message);
      }
    } finally {
      refreshInFlight = false;
      if (button) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        button.textContent = '새로고침';
      }
    }
  }

  function renderIpoList() {
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;

    if (marketIpos.length === 0) {
      wrapper.innerHTML = '<p class="empty-text" style="padding:32px;text-align:center;">등록된 공모주 일정이 없습니다.</p>';
      return;
    }

    const counts = { ALL: marketIpos.length, UPCOMING: 0, ACTIVE: 0, PAST: 0 };
    marketIpos.forEach(ipo => { if (counts[ipo.filter_group] !== undefined) counts[ipo.filter_group] += 1; });
    const labels = { ALL: '전체', UPCOMING: '예정', ACTIVE: '진행', PAST: '과거' };
    const controls = Object.entries(labels).map(([group, label]) =>
      `<button type="button" class="button secondary compact ipo-filter${ipoFilterGroup === group ? ' active' : ''}" data-filter-group="${group}">${label} ${counts[group]}</button>`
    ).join('');
    // Initialize PAST month selection if not yet done and entering PAST tab
    if (ipoFilterGroup === 'PAST' && !ipoHistoryInitialized) {
      const latestPast = getLatestPastMonth(marketIpos);
      if (latestPast) {
        ipoHistoryYear = latestPast.year;
        ipoHistoryMonth = latestPast.month;
      } else {
        const cur = currentKstYearMonth();
        ipoHistoryYear = cur.year;
        ipoHistoryMonth = cur.month;
      }
      ipoHistoryInitialized = true;
    }

    const sortAsc = (left, right) =>
      String(left.presentation_sort_date || '').localeCompare(String(right.presentation_sort_date || '')) ||
      String(left.ipo_id || '').localeCompare(String(right.ipo_id || ''));

    const sortDesc = (left, right) =>
      String(right.presentation_sort_date || '').localeCompare(String(left.presentation_sort_date || '')) ||
      String(right.ipo_id || '').localeCompare(String(left.ipo_id || ''));

    let visibleIpos = [];
    let fallbackIpos = [];
    let monthControlHtml = '';

    if (ipoFilterGroup === 'PAST') {
      const curKst = currentKstYearMonth();
      if (ipoHistoryYear === null || ipoHistoryMonth === null) {
        ipoHistoryYear = curKst.year;
        ipoHistoryMonth = curKst.month;
      }
      const selectedMonthKey = `${ipoHistoryYear}-${String(ipoHistoryMonth).padStart(2, '0')}`;
      const isCurrentOrFutureKst = selectedMonthKey >= curKst.key;

      const allPast = marketIpos.filter(ipo => ipo.filter_group === 'PAST');
      const datedPast = [];
      allPast.forEach(ipo => {
        const key = ipoMonthKey(ipo);
        if (key) {
          if (key === selectedMonthKey) {
            datedPast.push(ipo);
          }
        } else {
          fallbackIpos.push(ipo);
        }
      });

      datedPast.sort(sortDesc);
      fallbackIpos.sort(sortDesc);
      visibleIpos = datedPast;

      const monthCountText = `${ipoHistoryMonth}월 · ${datedPast.length}건`;
      const pickerVal = `${ipoHistoryYear}-${String(ipoHistoryMonth).padStart(2, '0')}`;
      monthControlHtml = `
        <div class="ipo-month-control money-month-nav" role="group" aria-label="공모주 과거 월 선택">
          <button type="button" class="button secondary compact ipo-month-btn money-month-nav-btn money-month-nav-prev" id="ipoPrevMonthBtn" title="이전 달" aria-label="이전 달">◀</button>
          <button type="button" class="ipo-month-text money-month-text" id="ipoCurrentMonthText" title="클릭하여 원하는 년/월 직접 선택" aria-label="조회 월 선택">${ipoHistoryYear}년 ${ipoHistoryMonth}월</button>
          <input type="month" id="ipoMonthPicker" class="money-month-picker" aria-label="공모주 과거 년/월 선택" value="${pickerVal}" style="position:absolute;opacity:0;pointer-events:none;width:0;height:0;" />
          <span class="ipo-month-count" id="ipoMonthCount">(${monthCountText})</span>
          <button type="button" class="button secondary compact ipo-month-btn money-month-nav-btn money-month-nav-next" id="ipoNextMonthBtn" title="다음 달"${isCurrentOrFutureKst ? ' disabled' : ''} aria-label="다음 달">▶</button>
          <button type="button" class="button secondary compact ipo-month-btn money-month-nav-btn money-month-nav-today" id="ipoTodayMonthBtn" title="이번 달로 이동" aria-label="이번 달로 이동">이번달</button>
        </div>`;
    } else if (ipoFilterGroup === 'UPCOMING' || ipoFilterGroup === 'ACTIVE') {
      visibleIpos = marketIpos.filter(ipo => ipo.filter_group === ipoFilterGroup).sort(sortAsc);
    } else {
      visibleIpos = marketIpos.slice().sort(sortAsc);
    }

    let html = `<div class="ipo-filter-toolbar" role="group" aria-label="공모주 일정 필터">${controls}</div>`;
    if (monthControlHtml) {
      html += monthControlHtml;
    }

    const renderCard = (ipo) => {
      let cardHtml = '';
      const ipoId = ipo.ipo_id;
      const app = userApplications[ipoId] || {};
      const appliedSet = new Set(app.applied_owners || []);
      const targetList = (app.target_owners && app.target_owners.length > 0) ? app.target_owners : familyMembers;

      // Price display
      let priceText = '미정';
      if (ipo.final_offer_price) {
        priceText = `${formatMoney(ipo.final_offer_price)} 원 (확정)`;
      } else if (ipo.offer_band_low && ipo.offer_band_high) {
        priceText = `${formatMoney(ipo.offer_band_low)} ~ ${formatMoney(ipo.offer_band_high)} 원`;
      }

      // Schedules
      const subSchedule = (ipo.subscription_start && ipo.subscription_end)
        ? `${ipo.subscription_start} ~ ${ipo.subscription_end}`
        : (ipo.subscription_start || '미정');
      const forecastSchedule = (ipo.demand_forecast_start && ipo.demand_forecast_end)
        ? `${ipo.demand_forecast_start} ~ ${ipo.demand_forecast_end}`
        : '미정';
      const listingDate = ipo.actual_listing_date || ipo.expected_listing_date || '미정';
      const marketStateLabels = { UPCOMING: '청약예정', SUBSCRIPTION_OPEN: '청약중', SUBSCRIPTION_CLOSED: '청약마감', LISTING_UPCOMING: '상장예정', LISTED: '상장완료', DATE_UNKNOWN: '일정 확인 필요' };
      const userStateLabels = { NOT_APPLIED: '미신청', APPLIED: '신청완료', ALLOCATED_UNSOLD: '배정 보유', PARTIALLY_SOLD: '일부 매도', FULLY_SOLD: '매도 완료', LINK_DATA_MISSING: '연결 확인 필요' };
      const marketStateLabel = marketStateLabels[ipo.market_state] || '일정 확인 필요';
      const userStateLabel = userStateLabels[ipo.user_state] || '미신청';
      const managers = (ipo.lead_managers && ipo.lead_managers.length > 0)
        ? ipo.lead_managers.join(', ')
        : '미정';

      // Tri-state for '모두'
      const allChecked = targetList.length > 0 && targetList.every(m => appliedSet.has(m));
      const someChecked = !allChecked && targetList.some(m => appliedSet.has(m));

      // Family member checkboxes
      let memberCheckboxesHtml = '';
      targetList.forEach(member => {
        const checked = appliedSet.has(member) ? 'checked' : '';
        memberCheckboxesHtml += `
          <label class="ipo-member-checkbox-label">
            <input type="checkbox" class="ipo-member-chk" data-ipo="${escapeHtml(ipoId)}" data-member="${escapeHtml(member)}" ${checked} />
            <span>${escapeHtml(member)}</span>
          </label>`;
      });

      // Account authorization is deliberately populated from backend responses.
      // This UI never normalizes broker aliases or filters portfolio accounts.
      let applicantAccountsHtml = '';
      targetList.filter(member => appliedSet.has(member)).forEach(member => {
        applicantAccountsHtml += `
          <div class="ipo-applicant-account" data-ipo="${escapeHtml(ipoId)}" data-owner="${escapeHtml(member)}">
            <span class="ipo-applicant-account-title">${escapeHtml(member)} 청약 계좌</span>
            <select class="ipo-applicant-broker" aria-label="${escapeHtml(member)} 증권사" disabled>
              <option>증권사 불러오는 중…</option>
            </select>
            <select class="ipo-applicant-account-select" aria-label="${escapeHtml(member)} Wealth 계좌" disabled>
              <option>계좌를 선택하세요</option>
            </select>
            <button type="button" class="button secondary compact ipo-applicant-account-save" disabled>계좌 연결</button>
            <span class="ipo-applicant-account-status" aria-live="polite"></span>
            <div class="ipo-allocation-control">
              <label>배정수량 <input class="ipo-allocation-quantity" type="number" min="0" step="1" disabled /></label>
              <button type="button" class="button secondary compact ipo-allocation-save" disabled>배정 저장</button>
              <span class="ipo-allocation-summary" aria-live="polite"></span>
              <select class="ipo-sale-candidate" aria-label="매도 실현손익 후보" disabled><option value="">매도 후보 없음</option></select>
              <input class="ipo-sale-match-quantity" type="number" min="1" step="1" aria-label="연결 매도 수량" disabled />
              <button type="button" class="button secondary compact ipo-sale-link-save" disabled>매도 연결</button>
              <div class="ipo-sale-links" aria-live="polite"></div>
            </div>
          </div>`;
      });

      // Score display logic (Section 1D, Section 19)
      const scoreObj = ipo.score;
      const isSpacScore = ipo.listing_track === 'spac' || (!!scoreObj && scoreObj.status === 'NOT_APPLICABLE');
      const isCalculating = !isSpacScore && (!scoreObj || scoreObj.is_calculating || scoreObj.score === null || scoreObj.score === undefined || (scoreObj.core_missing && scoreObj.core_missing.length > 0) || (scoreObj.coverage !== undefined && scoreObj.coverage < 75));

      let scoreBoxHtml = '';
      if (isSpacScore) {
        scoreBoxHtml = `
          <div class="ipo-score-box">
            <span class="ipo-score-title">Wealth IPO Score · BETA</span>
            <strong class="ipo-score-val beta-score">별도평가</strong>
          </div>`;
      } else if (isCalculating) {
        scoreBoxHtml = `
          <div class="ipo-score-box">
            <span class="ipo-score-title">Wealth IPO Score · BETA</span>
              <strong class="ipo-score-val beta-score">점수 산정중</strong>
          </div>`;
      } else {
        const numScore = Number(scoreObj.score);
        const grade = scoreObj.grade || '—';
        const coverage = (scoreObj.coverage !== undefined && scoreObj.coverage !== null) ? `${scoreObj.coverage}%` : '';
        const statusLabel = scoreObj.status === 'PRODUCTION' ? 'v1.0' : 'v1 · BETA';
        const comps = scoreObj.component_scores || {};

        const instDemand = (comps.institutional_demand !== undefined && comps.institutional_demand !== null) ? Math.round(comps.institutional_demand) : '—';
        const supply = (comps.supply_structure !== undefined && comps.supply_structure !== null) ? Math.round(comps.supply_structure) : '—';
        const val = (comps.valuation !== undefined && comps.valuation !== null) ? Math.round(comps.valuation) : '—';
        const fund = (comps.fundamentals !== undefined && comps.fundamentals !== null) ? Math.round(comps.fundamentals) : '—';
        const marketEnv = (comps.market_environment !== undefined && comps.market_environment !== null) ? Math.round(comps.market_environment) : '—';

        scoreBoxHtml = `
          <div class="ipo-score-box" title="${scoreObj.score_as_of ? `기준시점: ${escapeHtml(scoreObj.score_as_of)}` : ''}">
            <span class="ipo-score-title">Wealth IPO Score ${escapeHtml(statusLabel)}</span>
            <div class="ipo-score-header-val">
              <strong class="ipo-score-val score-${escapeHtml(grade.toLowerCase())}">${numScore} / 100 · ${escapeHtml(grade)}</strong>
              ${coverage ? `<span class="ipo-score-coverage">신뢰도 ${escapeHtml(coverage)}</span>` : ''}
            </div>
            <div class="ipo-score-components">
              <span class="ipo-comp-pill" title="기관경쟁률/의무보유확약/공모가상단">기관수요 ${instDemand}/35</span>
              <span class="ipo-comp-pill" title="유통물량/유통시총/구주매출/3개월락업">수급구조 ${supply}/30</span>
              <span class="ipo-comp-pill" title="가격결정/상대밸류에이션">가격·가치 ${val}/15</span>
              <span class="ipo-comp-pill" title="매출성장/영업이익/부채">기업기초 ${fund}/10</span>
              <span class="ipo-comp-pill" title="최근IPO수익률/시장20일수익률">시장환경 ${marketEnv}/10</span>
            </div>
          </div>`;
      }

      cardHtml += `
        <article class="ipo-card" data-ipo-id="${escapeHtml(ipoId)}">
          <div class="ipo-card-header">
            <div class="ipo-card-title-group">
              <h3 class="ipo-company-name">${escapeHtml(ipo.company_name)}</h3>
              ${ipo.market ? `<span class="ipo-market-badge">${escapeHtml(ipo.market)}</span>` : ''}
              ${ipo.stock_code ? `<span class="ipo-code-badge">${escapeHtml(ipo.stock_code)}</span>` : ''}
            </div>
            <div class="ipo-status-badges">
              <span class="ipo-subscription-status">${escapeHtml(marketStateLabel)}</span>
              <span class="ipo-user-status">${escapeHtml(userStateLabel)}</span>
            </div>
            ${scoreBoxHtml}
          </div>

          <div class="ipo-card-body">
            <div class="ipo-info-grid">
              <div class="ipo-info-item">
                <span class="info-label">청약 일정</span>
                <span class="info-value highlight-sub">${escapeHtml(subSchedule)}</span>
              </div>
              <div class="ipo-info-item">
                <span class="info-label">공모가</span>
                <span class="info-value">${escapeHtml(priceText)}</span>
              </div>
              <div class="ipo-info-item">
                <span class="info-label">상장(예정)일</span>
                <span class="info-value">${escapeHtml(listingDate)}</span>
              </div>
              <div class="ipo-info-item">
                <span class="info-label">수요예측</span>
                <span class="info-value">${escapeHtml(forecastSchedule)}</span>
              </div>
              <div class="ipo-info-item full-row">
                <span class="info-label">주관사</span>
                <span class="info-value">${escapeHtml(managers)}</span>
              </div>
            </div>
          </div>

          <div class="ipo-card-footer">
            <div class="ipo-family-app-section">
              <div class="ipo-family-app-head">
                <span class="family-app-title">가족 청약 신청 현황</span>
                <label class="ipo-all-checkbox-label">
                  <input type="checkbox" class="ipo-all-chk" data-ipo="${escapeHtml(ipoId)}" ${allChecked ? 'checked' : ''} />
                  <span>모두</span>
                </label>
              </div>
              <div class="ipo-family-members-row">
                ${memberCheckboxesHtml}
              </div>
              <div class="ipo-applicant-accounts">${applicantAccountsHtml}</div>
            </div>
          </div>
        </article>`;
      return cardHtml;
    };

    if (visibleIpos.length === 0 && fallbackIpos.length === 0) {
      if (ipoFilterGroup === 'PAST') {
        html += `<p class="empty-text" style="padding:28px;text-align:center;">선택한 월(${ipoHistoryYear}년 ${ipoHistoryMonth}월)에 해당하는 과거 공모주 일정이 없습니다.</p>`;
      } else {
        html += '<p class="empty-text" style="padding:28px;text-align:center;">해당 조건에 맞는 공모주 일정이 없습니다.</p>';
      }
    } else {
      if (visibleIpos.length > 0) {
        html += '<div class="ipo-cards-container">';
        visibleIpos.forEach(ipo => { html += renderCard(ipo); });
        html += '</div>';
      } else if (ipoFilterGroup === 'PAST') {
        html += `<p class="empty-text" style="padding:28px;text-align:center;">선택한 월(${ipoHistoryYear}년 ${ipoHistoryMonth}월)에 해당하는 과거 공모주 일정이 없습니다.</p>`;
      }

      if (fallbackIpos.length > 0) {
        html += '<div class="ipo-fallback-heading">기타 / 일정 미확인 과거 공모주</div>';
        html += '<div class="ipo-cards-container">';
        fallbackIpos.forEach(ipo => { html += renderCard(ipo); });
        html += '</div>';
      }
    }

    wrapper.innerHTML = html;

    wrapper.querySelectorAll('.ipo-filter').forEach(button => button.addEventListener('click', () => {
      ipoFilterGroup = button.dataset.filterGroup || 'ALL';
      renderIpoList();
    }));

    if (ipoFilterGroup === 'PAST') {
      const prevBtn = wrapper.querySelector('#ipoPrevMonthBtn');
      const nextBtn = wrapper.querySelector('#ipoNextMonthBtn');
      const todayBtn = wrapper.querySelector('#ipoTodayMonthBtn');
      const monthText = wrapper.querySelector('#ipoCurrentMonthText');
      const monthPicker = wrapper.querySelector('#ipoMonthPicker');

      if (monthText && monthPicker) {
        monthText.addEventListener('click', () => {
          if (typeof monthPicker.showPicker === 'function') {
            try {
              monthPicker.showPicker();
            } catch (err) {
              monthPicker.focus();
              monthPicker.click();
            }
          } else {
            monthPicker.focus();
            monthPicker.click();
          }
        });
        monthPicker.addEventListener('change', (e) => {
          const val = e.target.value;
          if (val && /^\d{4}-\d{2}$/.test(val)) {
            const [yStr, mStr] = val.split('-');
            const y = parseInt(yStr, 10);
            const m = parseInt(mStr, 10);
            if (y >= 2000 && y <= 2100 && m >= 1 && m <= 12) {
              ipoHistoryYear = y;
              ipoHistoryMonth = m;
              renderIpoList();
            }
          }
        });
      }

      if (prevBtn) {
        prevBtn.addEventListener('click', () => {
          const shifted = shiftIpoMonth(ipoHistoryYear, ipoHistoryMonth, -1);
          ipoHistoryYear = shifted.year;
          ipoHistoryMonth = shifted.month;
          renderIpoList();
        });
      }

      if (nextBtn) {
        nextBtn.addEventListener('click', () => {
          const curKst = currentKstYearMonth();
          const shifted = shiftIpoMonth(ipoHistoryYear, ipoHistoryMonth, 1);
          if (shifted.key <= curKst.key) {
            ipoHistoryYear = shifted.year;
            ipoHistoryMonth = shifted.month;
            renderIpoList();
          }
        });
      }

      if (todayBtn) {
        todayBtn.addEventListener('click', () => {
          const curKst = currentKstYearMonth();
          ipoHistoryYear = curKst.year;
          ipoHistoryMonth = curKst.month;
          renderIpoList();
        });
      }
    }

    // Set indeterminate state on '모두' checkboxes
    wrapper.querySelectorAll('.ipo-card').forEach(card => {
      const ipoId = card.dataset.ipoId;
      const app = userApplications[ipoId] || {};
      const appliedSet = new Set(app.applied_owners || []);
      const targetList = (app.target_owners && app.target_owners.length > 0) ? app.target_owners : familyMembers;
      const allChecked = targetList.length > 0 && targetList.every(m => appliedSet.has(m));
      const someChecked = !allChecked && targetList.some(m => appliedSet.has(m));

      const allChk = card.querySelector('.ipo-all-chk');
      if (allChk) {
        allChk.indeterminate = someChecked;
      }
    });

    attachCheckboxListeners();
    hydrateApplicantAccountControls();
  }

  const resolutionMessage = (status) => ({
    MAPPED: '연결된 계좌',
    AUTO_SELECTED: '등록 계좌 자동선택',
    AMBIGUOUS_ACCOUNT: '계좌를 선택하세요',
    NO_ACCOUNT_CANDIDATE: '등록된 같은 증권사 계좌가 없습니다',
    BROKER_UNKNOWN: '증권사를 확인할 수 없습니다',
    MAPPING_CONFLICT: '기존 계좌 연결을 변경할 수 없습니다',
  }[status] || '계좌를 선택하세요');

  async function hydrateApplicantAccountControls() {
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;
    const controls = Array.from(wrapper.querySelectorAll('.ipo-applicant-account'));
    await Promise.all(controls.map(control => hydrateApplicantAccountControl(control)));
  }

  async function hydrateApplicantAccountControl(control) {
    const ipoId = control.dataset.ipo;
    const owner = control.dataset.owner;
    const brokerSelect = control.querySelector('.ipo-applicant-broker');
    const accountSelect = control.querySelector('.ipo-applicant-account-select');
    const saveButton = control.querySelector('.ipo-applicant-account-save');
    const status = control.querySelector('.ipo-applicant-account-status');
    const allocationInput = control.querySelector('.ipo-allocation-quantity');
    const allocationSave = control.querySelector('.ipo-allocation-save');
    const allocationSummary = control.querySelector('.ipo-allocation-summary');
    const saleSelect = control.querySelector('.ipo-sale-candidate');
    const saleQuantity = control.querySelector('.ipo-sale-match-quantity');
    const saleLinkSave = control.querySelector('.ipo-sale-link-save');
    const saleLinks = control.querySelector('.ipo-sale-links');
    let currentMapping = userApplications[ipoId]?.applicants?.[owner] || null;
    try {
      const brokersResponse = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/broker-options`);
      if (!brokersResponse.ok) throw new Error('broker options unavailable');
      const brokers = (await brokersResponse.json()).brokers || [];
      brokerSelect.innerHTML = brokers.length
        ? brokers.map(item => `<option value="${escapeHtml(item.broker_id)}">${escapeHtml(item.display_name)}</option>`).join('')
        : '<option value="">증권사 정보 없음</option>';
      brokerSelect.disabled = brokers.length === 0;
      if (currentMapping && brokers.some(item => item.broker_id === currentMapping.broker_id)) {
        brokerSelect.value = currentMapping.broker_id;
      }
      const reloadCandidates = async () => {
        const broker = brokerSelect.value;
        if (!broker) return;
        accountSelect.disabled = true;
        saveButton.disabled = true;
        const remap = Boolean(currentMapping && currentMapping.broker_id !== broker);
        const candidateResponse = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/account-candidates?owner=${encodeURIComponent(owner)}&broker=${encodeURIComponent(broker)}${remap ? '&remap=true' : ''}`);
        if (!candidateResponse.ok) throw new Error('account candidates unavailable');
        const result = await candidateResponse.json();
        accountSelect.innerHTML = '<option value="">계좌를 선택하세요</option>' + (result.candidates || []).map(item => {
          const label = [item.account_name, item.owner, item.account_type].filter(Boolean).join(' · ') || '등록 계좌';
          return `<option value="${escapeHtml(item.account_id)}">${escapeHtml(label)}</option>`;
        }).join('');
        const preferredId = currentMapping?.broker_id === result.broker_id ? currentMapping.account_id : result.auto_selected_account_id;
        if (preferredId) accountSelect.value = preferredId;
        accountSelect.disabled = (result.candidates || []).length === 0 || result.resolution_status === 'MAPPING_CONFLICT';
        saveButton.disabled = !accountSelect.value || result.resolution_status === 'MAPPING_CONFLICT';
        saveButton.textContent = currentMapping ? '계좌 변경' : '계좌 연결';
        status.textContent = resolutionMessage(result.resolution_status);
      };
      brokerSelect.addEventListener('change', () => reloadCandidates().catch(() => { status.textContent = '계좌 후보를 불러오지 못했습니다'; }));
      accountSelect.addEventListener('change', () => { saveButton.disabled = !accountSelect.value; });
      saveButton.addEventListener('click', async () => {
        saveButton.disabled = true;
        try {
          const isRemap = Boolean(currentMapping);
          if (isRemap && !window.confirm('현재 연결된 청약 계좌를 변경하시겠습니까?')) return;
          const endpoint = isRemap
            ? `/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/account/remap`
            : `/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/account`;
          const payload = { broker: brokerSelect.value, account_id: accountSelect.value, revision: currentRevision };
          if (isRemap) payload.expected_current_account_id = currentMapping.account_id;
          const response = await fetch(endpoint, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (!response.ok) throw new Error('account mapping rejected');
          const result = await response.json();
          currentRevision = result.revision;
          userApplications[ipoId] = userApplications[ipoId] || {};
          userApplications[ipoId].applicants = userApplications[ipoId].applicants || {};
          currentMapping = { broker_id: result.broker_id, account_id: result.account_id };
          userApplications[ipoId].applicants[owner] = currentMapping;
          saveButton.textContent = '계좌 변경';
          status.textContent = isRemap ? '계좌 변경됨' : '계좌 연결됨';
          await loadIpoSchedule();
        } catch (err) {
          status.textContent = '계좌 연결에 실패했습니다';
        } finally {
          saveButton.disabled = !accountSelect.value;
        }
      });
      const loadAllocation = async () => {
        if (!currentMapping) return;
        const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/allocation`);
        if (!response.ok) return;
        const result = await response.json();
        const allocation = result.allocation;
        allocationInput.disabled = false;
        allocationSave.disabled = false;
        if (allocation) {
          allocationInput.value = allocation.quantity;
          allocationSummary.textContent = result.has_dangling_links
            ? `매도 ${allocation.sold_quantity}주 · 잔여 ${allocation.remaining_quantity}주 · 연결된 실현손익 기록을 찾을 수 없음`
            : `매도 ${allocation.sold_quantity}주 · 잔여 ${allocation.remaining_quantity}주 · 실현손익 ${Number(allocation.realized_pnl_krw || 0).toLocaleString('ko-KR')}원`;
          saleLinks.innerHTML = (result.links || []).map(link => {
            const label = link.missing_pnl_record
              ? `${escapeHtml(link.matched_quantity)}주 · 연결된 실현손익 기록을 찾을 수 없음`
              : `${escapeHtml(link.date || '')} · ${escapeHtml(link.matched_quantity)}주 연결됨`;
            return `<div class="ipo-sale-link-row"><span>${label}</span><button type="button" class="button secondary compact ipo-sale-unlink" data-pnl-record-id="${escapeHtml(link.pnl_record_id)}">연결 해제</button></div>`;
          }).join('');
          saleLinks.querySelectorAll('.ipo-sale-unlink').forEach(button => button.addEventListener('click', async () => {
            if (!window.confirm('이 매도 기록과 공모주 배정의 연결을 해제하시겠습니까?\n실현손익 기록 자체는 삭제되지 않습니다.')) return;
            try {
              const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/allocation/links/${encodeURIComponent(button.dataset.pnlRecordId)}`, {
                method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: currentRevision }),
              });
              if (!response.ok) throw new Error('sale unlink rejected');
              const result = await response.json(); currentRevision = result.revision; await loadIpoSchedule();
            } catch (err) { allocationSummary.textContent = '매도 연결 해제에 실패했습니다'; }
          }));
        } else allocationSummary.textContent = '공모가 기준 배정수량을 입력하세요';
        const salesResponse = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/allocation/sale-candidates`);
        const sales = salesResponse.ok ? (await salesResponse.json()).candidates || [] : [];
        saleSelect.innerHTML = '<option value="">매도 후보 선택</option>' + sales.map(item => `<option value="${escapeHtml(item.pnl_record_id)}" data-available="${escapeHtml(item.available_quantity)}">${escapeHtml(item.date)} · ${escapeHtml(item.available_quantity)}주</option>`).join('');
        saleSelect.disabled = !allocation || sales.length === 0;
        saleQuantity.disabled = saleSelect.disabled;
        saleLinkSave.disabled = saleSelect.disabled;
      };
      allocationSave.addEventListener('click', async () => {
        try {
          const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/allocation`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quantity: allocationInput.value, revision: currentRevision }),
          });
          if (!response.ok) throw new Error('allocation rejected');
          const result = await response.json(); currentRevision = result.revision; await loadIpoSchedule();
        } catch (err) { allocationSummary.textContent = '배정수량 저장에 실패했습니다'; }
      });
      saleSelect.addEventListener('change', () => {
        const option = saleSelect.options[saleSelect.selectedIndex];
        saleQuantity.value = option?.dataset.available || '';
        saleQuantity.max = option?.dataset.available || '';
      });
      saleLinkSave.addEventListener('click', async () => {
        try {
          const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/allocation/links`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pnl_record_id: saleSelect.value, matched_quantity: saleQuantity.value, revision: currentRevision }),
          });
          if (!response.ok) throw new Error('sale link rejected');
          const result = await response.json(); currentRevision = result.revision; await loadIpoSchedule();
        } catch (err) { allocationSummary.textContent = '매도 연결에 실패했습니다'; }
      });
      await reloadCandidates();
      await loadAllocation();
    } catch (err) {
      if (brokerSelect) brokerSelect.innerHTML = '<option value="">증권사 정보 없음</option>';
      if (status) status.textContent = '계좌 후보를 불러오지 못했습니다';
    }
  }

  function attachCheckboxListeners() {
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;

    // Member checkbox change
    wrapper.querySelectorAll('.ipo-member-chk').forEach(chk => {
      chk.addEventListener('change', async event => {
        const ipoId = chk.dataset.ipo;
        const card = chk.closest('.ipo-card');
        const checkedMembers = [];
        card.querySelectorAll('.ipo-member-chk').forEach(c => {
          if (c.checked) checkedMembers.push(c.dataset.member);
        });

        await saveApplicationState(ipoId, checkedMembers, card);
      });
    });

    // '모두' checkbox change
    wrapper.querySelectorAll('.ipo-all-chk').forEach(allChk => {
      allChk.addEventListener('change', async event => {
        const ipoId = allChk.dataset.ipo;
        const card = allChk.closest('.ipo-card');
        const targetChecked = allChk.checked;

        const nextMembers = [];
        card.querySelectorAll('.ipo-member-chk').forEach(c => {
          c.checked = targetChecked;
          if (targetChecked) nextMembers.push(c.dataset.member);
        });
        allChk.indeterminate = false;

        await saveApplicationState(ipoId, nextMembers, card);
      });
    });
  }

  async function saveApplicationState(ipoId, appliedOwners, cardElement) {
    try {
      const res = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          applied_owners: appliedOwners,
          revision: currentRevision,
        }),
      });

      if (res.status === 409) {
        alert('다른 화면이나 기기에서 청약 신청 정보가 변경되었습니다. 최신 정보를 불러옵니다.');
        await loadIpoSchedule();
        return;
      }

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned HTTP ${res.status}`);
      }

      const data = await res.json();
      currentRevision = data.revision;
      userApplications[ipoId] = {
        ipo_id: ipoId,
        target_owners: data.target_owners,
        applied_owners: data.applied_owners,
        target_frozen_at: data.target_frozen_at,
        updated_at: data.updated_at,
        state: data.state,
        all_applied: data.all_applied,
        applicants: userApplications[ipoId]?.applicants || {},
      };

      // Update the '모두' checkbox state in UI
      const allChk = cardElement.querySelector('.ipo-all-chk');
      if (allChk) {
        allChk.checked = data.all_applied;
        allChk.indeterminate = data.state === 'some';
      }

      // Notify other modules (e.g. Calendar detail)
      window.dispatchEvent(new CustomEvent('wealth-ipo-app-updated', {
        detail: { ipo_id: ipoId, revision: data.revision, applications: userApplications },
      }));
    } catch (err) {
      console.error('Failed to update IPO application:', err);
      alert(`신청 상태 저장 실패: ${err.message}`);
      await loadIpoSchedule();
    }
  }

  // Synchronize when applications are modified in other views (e.g. Calendar)
  window.addEventListener('wealth-ipo-app-updated', async (e) => {
    const ipoPanel = document.getElementById('ipoPanel');
    if (ipoPanel && !ipoPanel.classList.contains('wealth-income-hidden')) {
      await loadIpoSchedule();
    }
  });

  document.getElementById('ipoRefreshBtn')?.addEventListener('click', refreshIpoSchedule);
  window.loadIpoSchedule = loadIpoSchedule;
  window.WealthIpoState = {
    getFilterGroup: () => ipoFilterGroup,
    setFilterGroup: (g) => { ipoFilterGroup = g; },
    getHistoryYear: () => ipoHistoryYear,
    setHistoryYear: (y) => { ipoHistoryYear = y; },
    getHistoryMonth: () => ipoHistoryMonth,
    setHistoryMonth: (m) => { ipoHistoryMonth = m; },
    isHistoryInitialized: () => ipoHistoryInitialized,
    setHistoryInitialized: (v) => { ipoHistoryInitialized = v; },
    setMarketIpos: (items) => { marketIpos = Array.isArray(items) ? items : []; },
    setUserApplications: (apps) => { userApplications = apps || {}; },
    renderIpoList,
  };
})();
