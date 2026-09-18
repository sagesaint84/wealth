/* Wealth IPO Subsystem Frontend Module */
(() => {
  'use strict';

  let currentRevision = 0;
  let familyMembers = ['아빠', '엄마', '자녀'];
  let userApplications = {};
  let marketIpos = [];

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

  function renderIpoList() {
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;

    if (marketIpos.length === 0) {
      wrapper.innerHTML = '<p class="empty-text" style="padding:32px;text-align:center;">등록된 공모주 일정이 없습니다.</p>';
      return;
    }

    let html = '<div class="ipo-cards-container">';
    marketIpos.forEach(ipo => {
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

      // Score display logic (Section 1D, Section 19)
      const scoreObj = ipo.score;
      const isCalculating = !scoreObj || scoreObj.is_calculating || scoreObj.score === null || scoreObj.score === undefined || (scoreObj.core_missing && scoreObj.core_missing.length > 0) || (scoreObj.coverage !== undefined && scoreObj.coverage < 75);

      let scoreBoxHtml = '';
      if (isCalculating) {
        scoreBoxHtml = `
          <div class="ipo-score-box">
            <span class="ipo-score-title">Wealth IPO Score · BETA</span>
            <strong class="ipo-score-val beta-score">산정중</strong>
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

      html += `
        <article class="ipo-card" data-ipo-id="${escapeHtml(ipoId)}">
          <div class="ipo-card-header">
            <div class="ipo-card-title-group">
              <h3 class="ipo-company-name">${escapeHtml(ipo.company_name)}</h3>
              ${ipo.market ? `<span class="ipo-market-badge">${escapeHtml(ipo.market)}</span>` : ''}
              ${ipo.stock_code ? `<span class="ipo-code-badge">${escapeHtml(ipo.stock_code)}</span>` : ''}
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
            </div>
          </div>
        </article>`;
    });
    html += '</div>';
    wrapper.innerHTML = html;

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

  document.getElementById('ipoRefreshBtn')?.addEventListener('click', loadIpoSchedule);
  window.loadIpoSchedule = loadIpoSchedule;
})();
