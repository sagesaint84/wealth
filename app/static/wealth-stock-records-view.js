/* General stock records presentation. Original records and cross-screen state stay caller-owned. */
(() => {
  'use strict';
  function create({ $, window, money, number, signClass, html }) {
  const { filterRecordsByPeriod, buildPreviousRecordMap } = window.WealthStockRecordsModel;

function render(records, currentRecordPeriod, currentRecordView) {
  const rawList = [...records].sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));
  const previousByRecord = buildPreviousRecordMap(rawList);
  const filtered = filterRecordsByPeriod(rawList, currentRecordPeriod);
  const unifiedStock = window.WealthUnifiedTimeseries?.renderStock;
  const useUnifiedStock = typeof unifiedStock === 'function' && $("#assetChart") && $("#recordPeriodTabs");
  const wrap = useUnifiedStock ? null : $("#assetChart");

  if (!filtered.length) {
    if (wrap) wrap.innerHTML = '<div class="empty">선택한 기간의 주식기록이 없습니다.</div>';
    $("#assetRecordList") && ($("#assetRecordList").innerHTML = "");
    $("#recordCount") && ($("#recordCount").textContent = "0개 기록");
    if (useUnifiedStock) unifiedStock();
    return;
  }

  if (currentRecordView === 'bar' || currentRecordView === 'monthly') {
    const values = filtered.map(item => Number(item.total_value_krw || 0));
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const spanVal = maxVal - (minVal * 0.8) || 1;

    const w = 900, h = 260, pad = 30;
    const hBarArea = 180;
    const barWidth = Math.max(12, Math.min(48, (w - pad * 2) / filtered.length - 8));

    let prevVal = 0;
    const bars = filtered.map((item, idx) => {
      const val = Number(item.total_value_krw || 0);
      const delta = prevVal ? val - prevVal : Number(item.day_profit_krw || 0);
      const deltaRate = prevVal ? (delta / prevVal) * 100 : 0;
      prevVal = val;
      const isGain = delta >= 0;

      const x = pad + ((w - pad * 2) * (idx + 0.5)) / Math.max(filtered.length, 1) - barWidth / 2;
      const barH = Math.max(10, ((val - minVal * 0.8) / spanVal) * (hBarArea - 25));
      const y = hBarArea - barH;

      const sign = delta >= 0 ? "+" : "";
      const deltaText = delta !== 0 ? `${sign}${number(deltaRate, 1)}%` : "-";
      const deltaColor = delta !== 0 ? (isGain ? "#ff5c77" : "#4f9dff") : "#8e9bb5";
      const shortDate = item.date ? item.date.slice(5) : ""; // MM-DD

      return `
        <g class="monthly-bar-group">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="url(#assetBarGrad)" rx="3.5" opacity="0.9">
            <title>${item.date}: ${money(val)} (변동 ${sign}${money(delta)} / ${deltaRate.toFixed(2)}%)</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" fill="#f3f5ff" font-size="10" font-weight="700" text-anchor="middle">
            ${money(val)}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 16).toFixed(1)}" fill="#c4d1eb" font-size="10.5" font-weight="700" text-anchor="middle">
            ${shortDate}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 28).toFixed(1)}" fill="${deltaColor}" font-size="9" font-weight="700" text-anchor="middle">
            ${deltaText}
          </text>
        </g>
      `;
    }).join('');

    const first = filtered[0];
    const last = filtered.at(-1);
    const totalDelta = Number(last.total_value_krw || 0) - Number(first.total_value_krw || 0);
    const totalDeltaRate = Number(first.total_value_krw || 0) ? (totalDelta / Number(first.total_value_krw || 0)) * 100 : 0;

    if (wrap) {
      wrap.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 4px 8px;font-size:12px;font-weight:700;">
          <span style="color:#c4b5fd;">📊 총 투자자산 일자별 막대그래프 (${filtered.length}개 기록)</span>
          <span class="${signClass(totalDelta)}" style="font-size:12px;">기간 변동: ${totalDelta >= 0 ? '+' : ''}${money(totalDelta)} (${totalDelta >= 0 ? '+' : ''}${number(totalDeltaRate, 2)}%)</span>
        </div>
        <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:260px;overflow:visible;">
          <defs>
            <linearGradient id="assetBarGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#a78bfa" />
              <stop offset="100%" stop-color="#6366f1" />
            </linearGradient>
          </defs>
          <line x1="${pad}" y1="${hBarArea}" x2="${w - pad}" y2="${hBarArea}" stroke="#283758" stroke-width="1.2" />
          ${bars}
        </svg>
        <div class="record-chart-meta">
          <div><span>기간 시작</span><strong>${html(first.date)}</strong><small>${money(first.total_value_krw)}</small></div>
          <div><span>최근 기록</span><strong>${html(last.date)}</strong><small>${money(last.total_value_krw)}</small></div>
          <div><span>최저 / 최고 자산</span><strong>${money(minVal)} / ${money(maxVal)}</strong><small>해당 기간 ${number(filtered.length, 0)}개 기록</small></div>
        </div>
      `;
    }
  } else {
    const values = filtered.map(item => Number(item.total_value_krw || 0));
    const profits = filtered.map(item => Number(item.day_profit_krw || 0));

    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const spanVal = maxVal - minVal || (minVal * 0.05) || 1;
    const maxAbsProfit = Math.max(...profits.map(Math.abs), 100000);

    const w = 900, h = 280, pad = 24;
    const hLineArea = 160;

    // 막대 차트와 동일하게 그리드 컬럼 중앙에 데이터 포인트와 막대 배치
    const getX = (i) => pad + ((w - pad * 2) * (i + 0.5)) / Math.max(filtered.length, 1);

    const linePoints = filtered.map((pt, i) => {
      const x = getX(i);
      const y = pad + (hLineArea - pad) * (1 - (Number(pt.total_value_krw || 0) - minVal) / spanVal);
      return { x, y, pt };
    });
    const linePath = linePoints.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

    const firstX = linePoints[0].x;
    const lastX = linePoints[linePoints.length - 1].x;
    const lineAreaPath = `${linePath} ${lastX.toFixed(1)},${hLineArea} ${firstX.toFixed(1)},${hLineArea}`;

    const hBarAreaTop = hLineArea + 25;
    const hBarAreaHeight = h - hBarAreaTop - pad;
    const zeroY = hBarAreaTop + (hBarAreaHeight / 2);

    const barWidth = Math.max(3, Math.min(32, (w - pad * 2) / filtered.length - 6));
    const bars = filtered.map((pt, i) => {
      const x = getX(i) - barWidth / 2;
      const p = Number(pt.day_profit_krw || 0);
      const isGain = p >= 0;
      const barH = Math.max(2, (Math.abs(p) / maxAbsProfit) * (hBarAreaHeight / 2 - 4));
      const y = isGain ? (zeroY - barH) : zeroY;
      const color = isGain ? '#ff5c77' : '#4f9dff';
      return `
        <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" opacity="0.85" rx="1.5">
          <title>${pt.date}: ${isGain ? '+' : ''}${money(p)}</title>
        </rect>
      `;
    }).join('');

    // 데이터가 10개 이하일 때 (일간 2개, 주간 5개 등) 각 지점에 원형 포인트와 수치 라벨 표시
    const pointCircles = filtered.length <= 10 ? linePoints.map(p => {
      const shortDate = p.pt.date ? p.pt.date.slice(5) : '';
      return `
        <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="#8e70fa" stroke="#0e162b" stroke-width="2">
          <title>${p.pt.date}: ${money(p.pt.total_value_krw)}</title>
        </circle>
        <text x="${p.x.toFixed(1)}" y="${(p.y - 7).toFixed(1)}" fill="#f3f5ff" font-size="10" font-weight="700" text-anchor="middle">
          ${money(p.pt.total_value_krw)}
        </text>
        <text x="${p.x.toFixed(1)}" y="${(hLineArea - 5).toFixed(1)}" fill="#8e9bb5" font-size="9" font-weight="600" text-anchor="middle">
          ${shortDate}
        </text>
      `;
    }).join('') : '';

    const first = filtered[0];
    const last = filtered.at(-1);

    if (wrap) {
      wrap.innerHTML = `
        <div style="display:flex;justify-content:flex-end;gap:14px;margin-bottom:8px;font-size:11px;">
          <span style="display:flex;align-items:center;gap:4px;"><i style="display:inline-block;width:12px;height:3px;background:#8e70fa;border-radius:2px;"></i> 총 자산 (선)</span>
          <span style="display:flex;align-items:center;gap:4px;"><i style="display:inline-block;width:8px;height:8px;background:#ff5c77;border-radius:2px;"></i> 가격변동 손익 (+)</span>
          <span style="display:flex;align-items:center;gap:4px;"><i style="display:inline-block;width:8px;height:8px;background:#4f9dff;border-radius:2px;"></i> 가격변동 손실 (-)</span>
        </div>
        <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="자산 기록 콤보 차트">
          <defs>
            <linearGradient id="recordComboGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#8e70fa" stop-opacity="0.28" />
              <stop offset="100%" stop-color="#8e70fa" stop-opacity="0.0" />
            </linearGradient>
          </defs>
          <line x1="${pad}" y1="${hLineArea}" x2="${w - pad}" y2="${hLineArea}" stroke="#1f2c4d" stroke-dasharray="3,3" />
          <polygon points="${lineAreaPath}" fill="url(#recordComboGrad)" />
          <polyline points="${linePath}" fill="none" stroke="#8e70fa" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" />
          ${pointCircles}
          <line x1="${pad}" y1="${zeroY}" x2="${w - pad}" y2="${zeroY}" stroke="#334673" stroke-width="1.2" />
          <text x="${pad}" y="${hLineArea + 18}" fill="#7182a6" font-size="10" font-weight="700">가격변동 손익 (PROFIT / LOSS)</text>
          <text x="${w - pad}" y="${zeroY - 4}" fill="#7182a6" font-size="9" text-anchor="end">0원</text>
          ${bars}
        </svg>
        <div class="record-chart-meta">
          <div><span>기간 시작</span><strong>${html(first.date)}</strong><small>${money(first.total_value_krw)}</small></div>
          <div><span>최근 기록</span><strong>${html(last.date)}</strong><small>${money(last.total_value_krw)}</small></div>
          <div><span>최저 / 최고 자산</span><strong>${money(minVal)} / ${money(maxVal)}</strong><small>해당 기간 ${number(filtered.length, 0)}개 기록</small></div>
        </div>
      `;
    }
  }

  const first = filtered[0];
  const last = filtered.at(-1);
  const delta = Number(last.total_value_krw || 0) - Number(first.total_value_krw || 0);
  const deltaRate = Number(first.total_value_krw || 0) ? delta / Number(first.total_value_krw || 0) * 100 : 0;
  $("#recordSummary") && ($("#recordSummary").textContent = `${money(delta)} (${deltaRate >= 0 ? "+" : ""}${number(deltaRate, 2)}%)`);
  $("#recordSummary") && ($("#recordSummary").className = signClass(delta));
  $("#recordCount") && ($("#recordCount").textContent = `${number(filtered.length, 0)}개 기록`);

  const descRecords = [...filtered].reverse();
  const listEl = $("#assetRecordList");
  if (listEl) {
    listEl.innerHTML = descRecords.map((item) => {
      const previous = previousByRecord.get(item);
      const recordChange = previous ? Number(item.total_value_krw || 0) - Number(previous.total_value_krw || 0) : null;
      const recordChangeClass = recordChange == null || recordChange === 0 ? 'record-change-neutral' : signClass(recordChange);
      const recordChangeText = recordChange == null ? '이전 기록 없음' : `${recordChange > 0 ? '+' : ''}${money(recordChange)}`;
      const dayProfit = Number(item.day_profit_krw || 0);
      return `
      <div class="record-row">
        <div class="record-row-head">
          <time datetime="${html(item.date)}">${html(item.date)}</time>
          <strong>${money(item.total_value_krw)}</strong>
        </div>
        <div class="record-row-metrics">
          <p class="record-row-change"><span>전 기록 대비</span><b class="${recordChangeClass}">${recordChangeText}</b></p>
          <p class="record-row-day-profit"><span>가격변동 손익</span><b class="${dayProfit === 0 ? 'record-change-neutral' : signClass(dayProfit)}">${dayProfit > 0 ? '+' : ''}${money(dayProfit)}</b></p>
        </div>
        <div class="record-row-meta">${number(item.holding_count, 0)}종목${item.memo || item.source ? ` · ${html(item.memo || item.source)}` : ''}</div>
        <div class="record-row-actions">
          <button class="button secondary tiny" data-record-edit="${item.id}" type="button">수정</button>
          <button class="button text danger tiny" data-record-delete="${item.id}" type="button">삭제</button>
        </div>
      </div>
    `;
    }).join("");
  }
  if (useUnifiedStock) unifiedStock();
}

    return Object.freeze({ render });
  }
  window.WealthStockRecordsView = Object.freeze({ create });
})();
