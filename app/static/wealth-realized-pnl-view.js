(() => {
  'use strict';

  function renderSummary({ $, money, number, totalPnl, recordCount, completenessNote, totalWin, winCount, totalLoss, lossCount, winRate }) {
    const totalEl = $("#pnlTotal");
    if (totalEl) {
      totalEl.textContent = `${totalPnl > 0 ? '+' : ''}${money(totalPnl)}`;
      totalEl.className = `div-card-val ${totalPnl > 0 ? 'gain' : (totalPnl < 0 ? 'loss' : '')}`;
    }
    $("#pnlTotalCount") && ($("#pnlTotalCount").textContent = `총 ${recordCount}건 매도${completenessNote ? ` · ${completenessNote}` : ''}`);

    $("#pnlTotalWin") && ($("#pnlTotalWin").textContent = `+${money(totalWin)}`);
    $("#pnlWinCount") && ($("#pnlWinCount").textContent = `${winCount}건 실현`);

    $("#pnlTotalLoss") && ($("#pnlTotalLoss").textContent = `${money(totalLoss)}`);
    $("#pnlLossCount") && ($("#pnlLossCount").textContent = `${lossCount}건 실현`);

    const winRateEl = $("#pnlWinRate");
    if (winRateEl) {
      winRateEl.textContent = `${number(winRate, 1)}%`;
      winRateEl.className = `div-card-val ${winRate >= 50 ? 'gain' : ''}`;
    }
  }

  function renderLegacyChart(chartWrap, { w, h, pad, zeroY, bars }) {
    chartWrap.innerHTML = `
      <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:240px;overflow:visible;">
        <defs>
          <linearGradient id="pnlGainBarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#fb7185" />
            <stop offset="100%" stop-color="#e11d48" />
          </linearGradient>
          <linearGradient id="pnlGainBarGradActive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#f43f5e" />
            <stop offset="100%" stop-color="#fda4af" />
          </linearGradient>
          <linearGradient id="pnlLossBarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#0284c7" />
            <stop offset="100%" stop-color="#0369a1" />
          </linearGradient>
          <linearGradient id="pnlLossBarGradActive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#38bdf8" />
            <stop offset="100%" stop-color="#7dd3fc" />
          </linearGradient>
        </defs>
        <!-- 0원 기준 중심선 -->
        <line x1="${pad}" y1="${zeroY}" x2="${w - pad}" y2="${zeroY}" stroke="#334155" stroke-dasharray="3 3" stroke-width="1.2" />
        <line x1="${pad}" y1="200" x2="${w - pad}" y2="200" stroke="#1e293b" stroke-width="1" />
        ${bars}
      </svg>
    `;
  }

  function renderMonthlyDetail({
    container, title, items, month, hasBucketDetail, currentPnlSortField, currentPnlSortOrder,
    html, money, number, finiteRealizedPnlNumber, formatOptionalRealizedPnlValue, formatOptionalTossWtsFxDisplay,
  }) {
    if (!items.length) {
      container.innerHTML = `
        <div class="div-detail-header">
          ${title}
          ${month ? `<button type="button" class="button text compact" id="clearPnlMonthBtn" style="font-size:11px;margin-left:auto;">✕ ${hasBucketDetail ? '선택 해제' : '전체 보기'}</button>` : ''}
        </div>
        <div class="empty" style="padding:16px;">
          등록된 매도 실현손익 내역이 없습니다. 상단의 <strong>[➕ 손익 추가]</strong> 또는 <strong>[📂 가져오기]</strong> 버튼으로 매도 기록을 등록해보세요.
        </div>
      `;
      return;
    }

    const rowsHtml = items.map(item => {
      const isUsd = item.currency === 'USD';
      const pnlVal = finiteRealizedPnlNumber(item.pnl_krw);
      const nativePnlVal = finiteRealizedPnlNumber(item.pnl);
      const signValue = pnlVal === null ? nativePnlVal : pnlVal;
      const krwPnlDisplay = formatOptionalRealizedPnlValue(item.pnl_krw, value => `${value > 0 ? '+' : ''}${money(value)}`);
      const colorClass = signValue > 0 ? 'pnl-gain-val' : (signValue < 0 ? 'pnl-loss-val' : 'pnl-zero-val');
      const origText = isUsd ? `${Number(item.pnl) > 0 ? '+' : ''}$${number(item.pnl, 2)}` : '';
      const fxPnlVal = finiteRealizedPnlNumber(item.fx_pnl_krw);
      const wtsFxPnlUnavailable = item.source === 'toss_wts' && item.fx_pnl_krw == null;
      const wtsFxPnlZero = item.source === 'toss_wts' && item.fx_pnl_krw === 0;
      const fxPnlDisplay = formatOptionalTossWtsFxDisplay(item, item.fx_pnl_krw, value => `${Number(value) > 0 ? '+' : ''}${money(value)}`);
      const fxPnlInfo = (isUsd && (wtsFxPnlUnavailable || wtsFxPnlZero || (fxPnlVal !== null && fxPnlVal !== 0))) ? `<br><small style="color:#c4b5fd;">환차손익 ${fxPnlDisplay}</small>` : '';
      const fxRateDisplay = formatOptionalRealizedPnlValue(item.fx_rate, value => `${number(value, 1)}원`);
      const fxInfo = isUsd ? `<br><small style="color:#8da0c7;">환율 ${fxRateDisplay}</small>${fxPnlInfo}` : '';

      let typeBadge = '<span class="td-normal-badge">일반거래</span>';
      if (item.asset_type === 'real_estate' || item.code === 'REAL_ESTATE') {
        typeBadge = '<span class="saving-type-badge badge-sold" style="background:rgba(245,158,11,0.18);color:#f59e0b;border:1px solid rgba(245,158,11,0.35);font-size:11px;padding:2px 6px;border-radius:4px;font-weight:700;">🏷️ 부동산</span>';
      } else if (item.is_ipo) {
        typeBadge = '<span class="td-ipo-badge">📦 공모주</span>';
      }

      return `
        <tr>
          <td class="center td-date">${html(item.date)}</td>
          <td class="center"><span class="td-owner-badge">${html(item.owner || '모두')}</span></td>
          <td class="td-stock-col">
            <strong class="td-stock-name">${html(item.name || item.code)}</strong>
            <div class="td-stock-code">${html(item.code || '')}</div>
          </td>
          <td class="center">
            ${typeBadge}
          </td>
          <td class="center"><span class="td-currency">${html(item.currency || 'KRW')}</span></td>
          <td class="num td-orig-amt">${isUsd ? origText : krwPnlDisplay}${fxInfo}</td>
          <td class="num ${colorClass}" style="font-size:13.5px;font-weight:700;">${krwPnlDisplay}</td>
          <td class="td-memo">${html(item.memo || '-')}</td>
          <td class="center" style="white-space:nowrap;">
            <div class="account-row-actions" style="justify-content:center;">
              <button class="account-action-button edit-pnl-btn" data-id="${html(String(item.id))}" title="손익 수정" type="button">✎</button>
              <button class="account-action-button mini-delete-button delete-pnl-btn" data-id="${html(String(item.id))}" title="손익 삭제" type="button">🗑️</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <div class="div-detail-header">
        ${title}
        ${month ? `<button type="button" class="button text compact" id="clearPnlMonthBtn" style="font-size:11px;margin-left:auto;">✕ ${hasBucketDetail ? '선택 해제' : '전체 보기'}</button>` : ''}
      </div>
      <div class="detail-table-wrap">
        <table class="detail-table">
          <thead>
            <tr>
              <th class="center sortable-th ${currentPnlSortField === 'date' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="date" style="width:95px;">매도일 <span class="sort-icon"></span></th>
              <th class="center sortable-th ${currentPnlSortField === 'owner' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="owner" style="width:75px;">소유자 <span class="sort-icon"></span></th>
              <th class="sortable-th ${currentPnlSortField === 'name' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="name">종목명 (코드) <span class="sort-icon"></span></th>
              <th class="center sortable-th ${currentPnlSortField === 'is_ipo' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="is_ipo" style="width:85px;">유형 <span class="sort-icon"></span></th>
              <th class="center" style="width:60px;">통화</th>
              <th class="sortable-th ${currentPnlSortField === 'pnl' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="pnl" style="text-align:right;width:115px;">실현손익 <span class="sort-icon"></span></th>
              <th class="sortable-th ${currentPnlSortField === 'pnl_krw' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="pnl_krw" style="text-align:right;width:125px;">원화 환산손익 <span class="sort-icon"></span></th>
              <th>메모 / 계좌</th>
              <th class="center" style="width:65px;">관리</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;
  }

  window.WealthRealizedPnlView = { renderSummary, renderLegacyChart, renderMonthlyDetail };
})();
