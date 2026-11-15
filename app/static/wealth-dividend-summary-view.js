(() => {
  'use strict';

  function renderTexts(texts) {
    Object.entries(texts).forEach(([id, text]) => {
      const node = document.getElementById(id);
      if (node) node.textContent = text;
    });
  }

  function renderActual({ $, texts, periodLabel }) {
    renderTexts(texts);
    const title = $('#dividendChartTitle');
    if (title) title.textContent = '📊 ' + periodLabel + ' 실제 배당금 입금 추이';

    const chartWrap = $('#dividendBarChartWrap');
    if (chartWrap && !window.WealthUnifiedTimeseries?.renderDividend) {
      chartWrap.textContent = '배당 차트를 불러오는 중…';
    }
  }

  function renderEstimatedChart({
    $, html, money, chartBars, w, h, pad, hBarArea, barWidth, axisEndX, monthLabelY, countLabelY,
  }) {
    const bars = chartBars.map(({ m, idx, val, x, y, barH, isSelected, itemCount, labelX, valueLabelY }) => {
      const topText = val > 0 ? money(val) : "-";
      const barFill = isSelected ? "url(#divBarGradActive)" : (val > 0 ? "url(#divBarGrad)" : "#1c263d");

      return `
        <g class="dividend-bar-group" data-month="${m}" data-bucket-index="${idx}" tabindex="0" role="img" aria-label="${m}월 예상 배당금 ${html(money(val))}">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${barFill}" rx="4" opacity="0.95">
            <title>${m}월 예상 배당금: ${money(val)} (${itemCount}개 종목)</title>
          </rect>
          <text x="${labelX.toFixed(1)}" y="${valueLabelY.toFixed(1)}" fill="${val > 0 ? '#f3f5ff' : '#64748b'}" font-size="9.5" font-weight="700" text-anchor="middle">
            ${topText}
          </text>
          <text x="${labelX.toFixed(1)}" y="${monthLabelY.toFixed(1)}" fill="${isSelected ? '#c4b5fd' : '#94a3b8'}" font-size="11" font-weight="${isSelected ? '700' : '600'}" text-anchor="middle">
            ${m}월
          </text>
          <text x="${labelX.toFixed(1)}" y="${countLabelY.toFixed(1)}" fill="${itemCount > 0 ? '#8e70fa' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
            ${itemCount > 0 ? itemCount + '종목' : '-'}
          </text>
        </g>
      `;
    }).join('');

    const chartWrap = $("#dividendBarChartWrap");
    if (chartWrap) {
      chartWrap.innerHTML = `
        <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:240px;overflow:visible;">
          <defs>
            <linearGradient id="divBarGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#a78bfa" />
              <stop offset="100%" stop-color="#6366f1" />
            </linearGradient>
            <linearGradient id="divBarGradActive" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#38bdf8" />
              <stop offset="100%" stop-color="#818cf8" />
            </linearGradient>
          </defs>
          <line x1="${pad}" y1="${hBarArea}" x2="${axisEndX}" y2="${hBarArea}" stroke="#283758" stroke-width="1.2" />
          ${bars}
        </svg>
      `;
    }
  }

  window.WealthDividendSummaryView = { renderTexts, renderActual, renderEstimatedChart };
})();
