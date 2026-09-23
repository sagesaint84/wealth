/* Wealth Unified MoneyLog Calendar Module */
(() => {
  'use strict';

  const getKstToday = () => {
    const value = window.WealthIpoDate?.todayKst?.();
    if (value) return value;
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(new Date()).reduce((result, part) => {
      if (part.type !== 'literal') result[part.type] = part.value;
      return result;
    }, {});
    return `${parts.year}-${parts.month}-${parts.day}`;
  };
  const initialKst = getKstToday().split('-').map(Number);
  let currentYear = initialKst[0];
  let currentMonth = initialKst[1]; // 1-12
  let selectedDate = null;
  let hasInitializedDefaultDate = false;
  let calendarEvents = [];
  let currentOwner = '모두';
  let currentRevision = 0;
  let userApplications = {};
  let familyMembers = ['아빠', '엄마', '자녀'];

  function isDateInCurrentMonth(dateStr) {
    if (!dateStr || typeof dateStr !== 'string') return false;
    const parts = dateStr.split('-');
    if (parts.length !== 3) return false;
    return Number(parts[0]) === currentYear && Number(parts[1]) === currentMonth;
  }

  function isCalendarPanelActive() {
    const workspace = document.querySelector('.wealth-workspace');
    const calendarPanel = document.getElementById('calendarPanel');
    return workspace?.dataset.activeView === 'income'
      && calendarPanel
      && !calendarPanel.classList.contains('wealth-income-hidden');
  }

  function formatMoney(num) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    return Math.round(num).toLocaleString('ko-KR');
  }

  async function fetchApplications() {
    try {
      const res = await fetch('/api/ipo/applications');
      if (res.ok) {
        const data = await res.json();
        currentRevision = data.revision || 0;
        userApplications = data.applications || {};
        if (Array.isArray(data.family_members) && data.family_members.length > 0) {
          familyMembers = data.family_members;
        }
      }
    } catch (e) {
      console.warn('Failed to load IPO applications for calendar:', e);
    }
  }

  function getMonthDateRange(year, month) {
    const startDate = new Date(Date.UTC(year, month - 1, 1));
    const endDate = new Date(Date.UTC(year, month, 0));
    const fromStr = startDate.toISOString().slice(0, 10);
    const toStr = endDate.toISOString().slice(0, 10);
    return { fromStr, toStr, lastDay: endDate.getDate(), firstDayOfWeek: new Date(year, month - 1, 1).getDay() };
  }

  async function loadCalendar() {
    if (!hasInitializedDefaultDate) {
      hasInitializedDefaultDate = true;
      const todayStr = getKstToday();
      const [todayYear, todayMonth] = todayStr.split('-').map(Number);
      if (selectedDate === null && currentYear === todayYear && currentMonth === todayMonth) {
        selectedDate = todayStr;
      }
    }

    await fetchApplications();
    const { fromStr, toStr } = getMonthDateRange(currentYear, currentMonth);
    const label = document.getElementById('calendarCurrentMonthLabel');
    if (label) {
      label.textContent = `${currentYear}년 ${currentMonth}월`;
    }

    try {
      const ownerParam = encodeURIComponent(currentOwner || '모두');
      const res = await fetch(`/api/moneylog/calendar?from=${fromStr}&to=${toStr}&owner=${ownerParam}`);
      if (!res.ok) {
        throw new Error(`Calendar API returned HTTP ${res.status}`);
      }
      const data = await res.json();
      calendarEvents = Array.isArray(data.events) ? data.events : [];
    } catch (err) {
      console.error('Failed to load calendar events:', err);
      calendarEvents = [];
    }

    renderCalendarGrid();
    if (selectedDate && isDateInCurrentMonth(selectedDate)) {
      const dayEvents = calendarEvents.filter(ev => ev.date === selectedDate);
      renderDetailPanel(selectedDate, dayEvents);
    } else {
      const panel = document.getElementById('calendarDetailPanel');
      if (panel) panel.hidden = true;
    }
  }

  function renderCalendarGrid() {
    const wrapper = document.getElementById('calendarGridWrapper');
    if (!wrapper) return;

    const { lastDay, firstDayOfWeek } = getMonthDateRange(currentYear, currentMonth);
    const todayStr = getKstToday();

    // Group events by date string
    const eventsByDate = {};
    calendarEvents.forEach(ev => {
      const d = ev.date;
      if (!eventsByDate[d]) eventsByDate[d] = [];
      eventsByDate[d].push(ev);
    });

    const dayNames = ['일', '월', '화', '수', '목', '금', '토'];
    let html = '<div class="wealth-calendar-grid">';

    // Header
    dayNames.forEach((name, idx) => {
      const isWeekend = idx === 0 ? 'is-sun' : (idx === 6 ? 'is-sat' : '');
      html += `<div class="cal-cell cal-head-cell ${isWeekend}">${name}</div>`;
    });

    // Empty cells before day 1
    for (let i = 0; i < firstDayOfWeek; i++) {
      html += '<div class="cal-cell cal-empty-cell" aria-hidden="true"></div>';
    }

    // Days of the month
    for (let day = 1; day <= lastDay; day++) {
      const dayStr = `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayOfWeek = (firstDayOfWeek + day - 1) % 7;
      const isSun = dayOfWeek === 0 ? 'is-sun' : '';
      const isSat = dayOfWeek === 6 ? 'is-sat' : '';
      const isToday = dayStr === todayStr ? 'is-today' : '';
      const isSelected = dayStr === selectedDate ? 'is-selected' : '';
      const dayEvents = eventsByDate[dayStr] || [];

      // Summaries by category (never summing pnl, dividend, and ledger together into single net profit)
      let pnlSum = 0;
      let hasPnl = false;
      let divSum = 0;
      let hasDiv = false;
      let intSum = 0;
      let hasInt = false;
      let expSum = 0;
      let hasExp = false;
      let incSum = 0;
      let hasInc = false;
      let ipoEvents = [];

      dayEvents.forEach(ev => {
        const amt = ev.amount_krw;
        if (ev.type === 'realized_pnl' && amt !== null && amt !== undefined) {
          pnlSum += amt;
          hasPnl = true;
        } else if (ev.type === 'dividend' && amt) {
          divSum += amt;
          hasDiv = true;
        } else if (ev.type === 'interest' && amt) {
          intSum += amt;
          hasInt = true;
        } else if (ev.type === 'ledger_expense' && amt) {
          expSum += Math.abs(amt);
          hasExp = true;
        } else if (ev.type === 'ledger_income' && amt) {
          incSum += amt;
          hasInc = true;
        } else if (ev.type && ev.type.startsWith('ipo_')) {
          ipoEvents.push(ev);
        }
      });

      let badgesHtml = '';
      if (hasPnl) {
        const sign = pnlSum > 0 ? '+' : '';
        const tone = pnlSum > 0 ? 'tone-profit' : (pnlSum < 0 ? 'tone-loss' : 'tone-neutral');
        const label = pnlSum > 0 ? '수익' : (pnlSum < 0 ? '손실' : '실현손익');
        const cue = pnlSum > 0 ? '➕ ' : (pnlSum < 0 ? '➖ ' : '');
        badgesHtml += `<div class="cal-badge ${tone}" title="${label}: ${sign}${formatMoney(pnlSum)}원">${cue}${label} ${sign}${formatMoney(pnlSum)}</div>`;
      }
      if (hasDiv) {
        badgesHtml += `<div class="cal-badge tone-dividend" title="배당: +${formatMoney(divSum)}원">💰 배당 +${formatMoney(divSum)}</div>`;
      }
      if (hasInt) {
        badgesHtml += `<div class="cal-badge tone-interest" title="이자: +${formatMoney(intSum)}원">🪙 이자 +${formatMoney(intSum)}</div>`;
      }
      if (hasExp) {
        badgesHtml += `<div class="cal-badge tone-expense" title="지출: -${formatMoney(expSum)}원">🧾 지출 -${formatMoney(expSum)}</div>`;
      }
      if (hasInc) {
        badgesHtml += `<div class="cal-badge tone-income" title="수입: +${formatMoney(incSum)}원">💵 수입 +${formatMoney(incSum)}</div>`;
      }
      const ipoSubscriptions = ipoEvents.filter(ev => ev.type && ev.type.startsWith('ipo_subscription'));
      const ipoListings = ipoEvents.filter(ev => ev.type === 'ipo_listing');
      const renderIpoNames = (events, tone, icon, label) => {
        const names = [...new Map(events.map(ev => [ev.meta?.ipo_id || ev.id, ev.meta?.company_name || '공모주'])).values()];
        if (!names.length) return '';
        const visible = names.slice(0, 3).map(name => `<span class="cal-ipo-name-chip" title="${escapeHtml(name)}">${escapeHtml(name)}</span>`).join('');
        const overflow = names.length > 3 ? `<span class="cal-ipo-overflow">+${names.length - 3}</span>` : '';
        return `<div class="cal-badge ${tone}" title="${escapeHtml(label)} ${names.join(', ')}">${icon} ${visible}${overflow}</div>`;
      };
      badgesHtml += renderIpoNames(ipoSubscriptions, 'tone-ipo-subscription', '🎯', '청약');
      badgesHtml += renderIpoNames(ipoListings, 'tone-ipo-listing', '🚀', '상장');

      html += `
        <button type="button" class="cal-cell cal-day-cell ${isSun} ${isSat} ${isToday} ${isSelected}" data-date="${dayStr}">
          <span class="cal-day-number">${day}</span>
          <div class="cal-badges">${badgesHtml}</div>
        </button>`;
    }

    // Trailing empty cells
    const totalCells = firstDayOfWeek + lastDay;
    const remaining = totalCells % 7 === 0 ? 0 : 7 - (totalCells % 7);
    for (let j = 0; j < remaining; j++) {
      html += '<div class="cal-cell cal-empty-cell" aria-hidden="true"></div>';
    }

    html += `</div>
      <div class="calendar-legend" aria-label="캘린더 범례">
        <span class="calendar-legend-item tone-ipo-subscription"><i class="calendar-legend-dot"></i>청약</span>
        <span class="calendar-legend-item tone-ipo-listing"><i class="calendar-legend-dot"></i>상장</span>
        <span class="calendar-legend-item tone-profit"><i class="calendar-legend-dot"></i>수익</span>
        <span class="calendar-legend-item tone-loss"><i class="calendar-legend-dot"></i>손실</span>
        <span class="calendar-legend-item tone-dividend"><i class="calendar-legend-dot"></i>배당</span>
        <span class="calendar-legend-item tone-income"><i class="calendar-legend-dot"></i>수입</span>
        <span class="calendar-legend-item tone-expense"><i class="calendar-legend-dot"></i>지출</span>
      </div>`;
    wrapper.innerHTML = html;

    wrapper.querySelectorAll('.cal-day-cell').forEach(btn => {
      btn.addEventListener('click', () => {
        const d = btn.dataset.date;
        selectedDate = d;
        hasInitializedDefaultDate = true;
        wrapper.querySelectorAll('.cal-day-cell').forEach(b => b.classList.toggle('is-selected', b.dataset.date === d));
        const dayEvents = eventsByDate[d] || [];
        renderDetailPanel(d, dayEvents);
      });
    });
  }

  function renderDetailPanel(dateStr, events) {
    const panel = document.getElementById('calendarDetailPanel');
    const label = document.getElementById('calendarDetailDateLabel');
    const list = document.getElementById('calendarDetailList');
    if (!panel || !label || !list) return;

    panel.hidden = false;
    label.textContent = `${dateStr} 상세 내역 (${events.length}건)`;

    if (events.length === 0) {
      list.innerHTML = '<p class="empty-text" style="padding:16px;text-align:center;">이 날짜에 기록된 금융 이벤트가 없습니다.</p>';
      return;
    }

    let itemsHtml = '<ul class="calendar-event-items">';
    events.forEach(ev => {
      let icon = '📌';
      let typeLabel = ev.subtype || ev.type;
      let toneClass = '';
      let amountFormatted = '';

      if (ev.type === 'realized_pnl') {
        icon = '📈';
        typeLabel = '실현손익';
        const amt = ev.amount_krw;
        if (amt !== null && amt !== undefined) {
          const sign = amt >= 0 ? '+' : '';
          toneClass = amt >= 0 ? 'text-profit' : 'text-loss';
          amountFormatted = `${sign}${formatMoney(amt)} 원`;
        }
      } else if (ev.type === 'dividend') {
        icon = '💰';
        typeLabel = '배당금';
        toneClass = 'text-profit';
        amountFormatted = `+${formatMoney(ev.amount_krw)} 원`;
      } else if (ev.type === 'interest') {
        icon = '🪙';
        typeLabel = '이자수익';
        toneClass = 'text-profit';
        amountFormatted = `+${formatMoney(ev.amount_krw)} 원`;
      } else if (ev.type === 'ledger_expense') {
        icon = '🧾';
        typeLabel = `가계부 (${ev.subtype || '지출'})`;
        toneClass = 'text-loss';
        amountFormatted = `-${formatMoney(Math.abs(ev.amount_krw))} 원`;
      } else if (ev.type === 'ledger_income') {
        icon = '💵';
        typeLabel = `가계부 (${ev.subtype || '수입'})`;
        toneClass = 'text-profit';
        amountFormatted = `+${formatMoney(ev.amount_krw)} 원`;
      } else if (ev.type && ev.type.startsWith('ipo_')) {
        const isListing = ev.type === 'ipo_listing';
        icon = isListing ? '🚀' : '🎯';
        const ipoTypeLabels = {
          ipo_subscription_start: '청약',
          ipo_subscription: '청약',
          ipo_subscription_end: '청약',
          ipo_payment: '납입',
          ipo_refund: '환불',
          ipo_demand_start: '수요예측',
          ipo_demand_end: '수요예측',
        };
        typeLabel = isListing ? (ev.meta?.listing_status === 'actual' ? '상장' : '상장예정') : (ipoTypeLabels[ev.type] || '공모주 일정');
        toneClass = isListing ? 'text-ipo-listing' : 'text-ipo-subscription';
        amountFormatted = ev.meta?.offer_price ? `${formatMoney(ev.meta.offer_price)} 원` : '';
      }

      const metaDetails = [];
      if (ev.meta?.lead_managers && Array.isArray(ev.meta.lead_managers) && ev.meta.lead_managers.length > 0) {
        metaDetails.push(`주관사: ${ev.meta.lead_managers.join(', ')}`);
      }
      if (ev.meta?.broker) metaDetails.push(ev.meta.broker);
      if (ev.meta?.account_name) metaDetails.push(ev.meta.account_name);
      if (ev.meta?.category && !typeLabel.includes(ev.meta.category)) metaDetails.push(ev.meta.category);
      if (ev.meta?.merchant) metaDetails.push(ev.meta.merchant);
      if (ev.meta?.memo) metaDetails.push(ev.meta.memo);

      // Section 18: IPO application checkboxes in Calendar detail panel
      let ipoAppControlsHtml = '';
      if (ev.type && ev.type.startsWith('ipo_') && ev.meta?.ipo_id) {
        const ipoId = ev.meta.ipo_id;
        const app = userApplications[ipoId] || {
          applied_owners: ev.meta.applied_owners || [],
          target_owners: ev.meta.target_owners || familyMembers,
          all_applied: ev.meta.all_applied || false,
        };
        const targetList = (app.target_owners && app.target_owners.length > 0) ? app.target_owners : familyMembers;
        const appliedSet = new Set(app.applied_owners || []);

        const allChecked = targetList.length > 0 && targetList.every(m => appliedSet.has(m));
        const someChecked = !allChecked && targetList.some(m => appliedSet.has(m));

        let memberCheckboxes = '';
        targetList.forEach(m => {
          const checked = appliedSet.has(m) ? 'checked' : '';
          memberCheckboxes += `
            <label class="ipo-member-checkbox-label">
              <input type="checkbox" class="cal-ipo-member-chk" data-ipo="${escapeHtml(ipoId)}" data-member="${escapeHtml(m)}" ${checked} />
              <span>${escapeHtml(m)}</span>
            </label>`;
        });

        ipoAppControlsHtml = `
          <div class="cal-ipo-app-section" data-ipo-id="${escapeHtml(ipoId)}">
            <div class="cal-ipo-app-head">
              <span class="cal-ipo-app-title">신청 현황</span>
              <label class="ipo-all-checkbox-label">
                <input type="checkbox" class="cal-ipo-all-chk" data-ipo="${escapeHtml(ipoId)}" ${allChecked ? 'checked' : ''} />
                <span>모두</span>
              </label>
            </div>
            <div class="ipo-family-members-row">
              ${memberCheckboxes}
            </div>
          </div>`;
      }

      itemsHtml += `
        <li class="calendar-event-item" data-event-id="${escapeHtml(ev.id)}">
          <div class="event-item-main">
            <span class="event-icon">${icon}</span>
            <div class="event-body">
              <div class="event-title-row">
                <strong class="event-title">${escapeHtml(ev.title || '항목')}</strong>
                <span class="event-type-badge">${escapeHtml(typeLabel)}</span>
                <span class="event-owner-badge">${escapeHtml(ev.owner || '모두')}</span>
              </div>
              ${metaDetails.length > 0 ? `<div class="event-meta">${escapeHtml(metaDetails.join(' · '))}</div>` : ''}
              ${ipoAppControlsHtml}
            </div>
          </div>
          ${amountFormatted ? `<div class="event-amount ${toneClass}"><strong>${amountFormatted}</strong></div>` : ''}
        </li>`;
    });
    itemsHtml += '</ul>';
    list.innerHTML = itemsHtml;

    // Set indeterminate on '모두' checkboxes in detail list
    list.querySelectorAll('.cal-ipo-app-section').forEach(sec => {
      const ipoId = sec.dataset.ipoId;
      const app = userApplications[ipoId] || {};
      const appliedSet = new Set(app.applied_owners || []);
      const targetList = (app.target_owners && app.target_owners.length > 0) ? app.target_owners : familyMembers;
      const allChecked = targetList.length > 0 && targetList.every(m => appliedSet.has(m));
      const someChecked = !allChecked && targetList.some(m => appliedSet.has(m));

      const allChk = sec.querySelector('.cal-ipo-all-chk');
      if (allChk) {
        allChk.indeterminate = someChecked;
      }
    });

    attachCalendarIpoListeners(list);
  }

  function attachCalendarIpoListeners(container) {
    container.querySelectorAll('.cal-ipo-member-chk').forEach(chk => {
      chk.addEventListener('change', async () => {
        const ipoId = chk.dataset.ipo;
        const sec = chk.closest('.cal-ipo-app-section');
        const checkedMembers = [];
        sec.querySelectorAll('.cal-ipo-member-chk').forEach(c => {
          if (c.checked) checkedMembers.push(c.dataset.member);
        });
        await saveCalendarApplication(ipoId, checkedMembers);
      });
    });

    container.querySelectorAll('.cal-ipo-all-chk').forEach(allChk => {
      allChk.addEventListener('change', async () => {
        const ipoId = allChk.dataset.ipo;
        const sec = allChk.closest('.cal-ipo-app-section');
        const targetChecked = allChk.checked;
        const nextMembers = [];
        sec.querySelectorAll('.cal-ipo-member-chk').forEach(c => {
          c.checked = targetChecked;
          if (targetChecked) nextMembers.push(c.dataset.member);
        });
        allChk.indeterminate = false;
        await saveCalendarApplication(ipoId, nextMembers);
      });
    });
  }

  async function saveCalendarApplication(ipoId, appliedOwners) {
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
        alert('다른 화면이나 기기에서 청약 신청 정보가 변경되었습니다. 최신 정보를 불러온 후 다시 시도해 주세요.');
        await fetchApplications();
        if (selectedDate && isDateInCurrentMonth(selectedDate)) {
          const dayEvents = calendarEvents.filter(ev => ev.date === selectedDate);
          renderDetailPanel(selectedDate, dayEvents);
        }
        return;
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
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

      // Update in-memory calendar events
      calendarEvents.forEach(ev => {
        if (ev.meta && ev.meta.ipo_id === ipoId) {
          ev.meta.applied_owners = data.applied_owners;
          ev.meta.all_applied = data.all_applied;
          if (currentOwner === '모두') {
            ev.meta.is_applied_by_owner = data.all_applied;
          } else {
            ev.meta.is_applied_by_owner = data.applied_owners.includes(currentOwner);
          }
        }
      });

      // Rerender grid & detail
      renderCalendarGrid();
      if (selectedDate && isDateInCurrentMonth(selectedDate)) {
        const dayEvents = calendarEvents.filter(ev => ev.date === selectedDate);
        renderDetailPanel(selectedDate, dayEvents);
      }

      // Notify other tabs/modules
      window.dispatchEvent(new CustomEvent('wealth-ipo-app-updated', {
        detail: { ipo_id: ipoId, revision: data.revision, applications: userApplications },
      }));
    } catch (err) {
      console.error('Failed to save calendar IPO application:', err);
      alert(`신청 상태 저장 실패: ${err.message}`);
    }
  }

  // Cross-tab / cross-component sync
  window.addEventListener('wealth-ipo-app-updated', async () => {
    await fetchApplications();
    if (selectedDate && isDateInCurrentMonth(selectedDate)) {
      const dayEvents = calendarEvents.filter(ev => ev.date === selectedDate);
      renderDetailPanel(selectedDate, dayEvents);
    }
  });

  function closeDetailPanel() {
    const panel = document.getElementById('calendarDetailPanel');
    if (panel) panel.hidden = true;
    selectedDate = null;
    hasInitializedDefaultDate = true;
    document.querySelectorAll('.cal-day-cell.is-selected').forEach(b => b.classList.remove('is-selected'));
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

  // Navigation handlers
  document.getElementById('calendarPrevMonthBtn')?.addEventListener('click', () => {
    currentMonth -= 1;
    if (currentMonth < 1) {
      currentMonth = 12;
      currentYear -= 1;
    }
    loadCalendar();
  });

  document.getElementById('calendarNextMonthBtn')?.addEventListener('click', () => {
    currentMonth += 1;
    if (currentMonth > 12) {
      currentMonth = 1;
      currentYear += 1;
    }
    loadCalendar();
  });

  document.getElementById('calendarTodayBtn')?.addEventListener('click', () => {
    const todayStr = getKstToday();
    const [year, month] = todayStr.split('-').map(Number);
    currentYear = year;
    currentMonth = month;
    selectedDate = todayStr;
    hasInitializedDefaultDate = true;
    loadCalendar();
  });

  document.getElementById('calendarDetailCloseBtn')?.addEventListener('click', closeDetailPanel);

  window.addEventListener('wealth:owner', e => {
    const nextOwner = e.detail?.owner || '모두';
    if (nextOwner !== currentOwner) {
      currentOwner = nextOwner;
      const calendarPanel = document.getElementById('calendarPanel');
      if (calendarPanel && !calendarPanel.classList.contains('wealth-income-hidden')) {
        loadCalendar();
      }
    }
  });

  window.loadCalendar = loadCalendar;
  window.WealthCalendar = {
    getSelectedDate: () => selectedDate,
    setSelectedDate: (d) => { selectedDate = d; hasInitializedDefaultDate = true; },
    getCurrentYear: () => currentYear,
    getCurrentMonth: () => currentMonth,
    hasInitializedDefaultDate: () => hasInitializedDefaultDate,
    closeDetailPanel,
    loadCalendar,
  };
  // Layout/hash restoration runs before this module is loaded.  When it has
  // already made MoneyLog's calendar visible, perform the same lazy load the
  // normal tab activation would perform.
  if (isCalendarPanelActive()) {
    loadCalendar();
  }
})();
