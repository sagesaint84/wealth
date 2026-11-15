/* Stock price/volume Dialog View. Original request and SVG calculations are preserved. */
(() => {
  'use strict';

  function create({ $, api, money, number, signClass, html, document }) {
let currentStockChartCode = '';
let currentStockChartName = '';
let currentStockChartPrice = 0;
let currentStockChartCurrency = 'KRW';
let currentStockChartPeriod = '1M'; // '1D' | '1W' | '1M' | '1Y'

async function openStockChart(code, name, price, currency = 'KRW') {
  currentStockChartCode = code;
  currentStockChartName = name || code;
  currentStockChartPrice = Number(price || 0);
  currentStockChartCurrency = currency || 'KRW';

  const dlg = $("#stockChartDialog");
  if (!dlg) return;

  $("#stockChartTitle").textContent = currentStockChartName;
  $("#stockChartCode").textContent = `${currentStockChartCode} · ${currentStockChartCurrency}`;
  $("#stockChartPrice").textContent = money(currentStockChartPrice, currentStockChartCurrency);
  $("#stockChartChange").textContent = "데이터 조회 중…";
  if (!['1D', '1W', '1M', '1Y'].includes(currentStockChartPeriod)) {
    currentStockChartPeriod = '1M';
  }

  window.WealthApplyPeriodButtonSelection(document.querySelectorAll('#stockChartPeriodTabs .heatmap-tab'), currentStockChartPeriod);

  dlg.showModal();
  await loadStockChartData();
}

async function loadStockChartData() {
  const container = $("#stockChartContainer");
  if (!container) return;
  container.innerHTML = '<div class="empty">차트 데이터를 불러오는 중입니다…</div>';

  try {
    const res = await api(`/api/stock-chart/${encodeURIComponent(currentStockChartCode)}?period=${currentStockChartPeriod}`);
    const candles = res?.candles || [];
    if (!candles.length) {
      container.innerHTML = '<div class="empty">조회 가능한 캔들 차트 데이터가 없습니다.</div>';
      return;
    }

    const prices = candles.map(c => c.close);
    const volumes = candles.map(c => c.volume || 0);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const maxVol = Math.max(...volumes, 1);
    const spanPrice = maxPrice - minPrice || (minPrice * 0.02) || 1;

    const w = 680, h = 260, pad = 20;
    const hPriceArea = 170;
    const hVolTop = hPriceArea + 20;
    const hVolArea = h - hVolTop - 15;

    const pricePoints = candles.map((c, idx) => {
      const x = pad + ((w - pad * 2) * idx) / Math.max(candles.length - 1, 1);
      const y = pad + (hPriceArea - pad) * (1 - (c.close - minPrice) / spanPrice);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const pricePath = pricePoints.join(" ");
    const priceAreaPath = `${pricePath} ${(w - pad)},${hPriceArea} ${pad},${hPriceArea}`;

    const barWidth = Math.max(1.5, Math.min(14, (w - pad * 2) / candles.length - 1.5));
    const volBars = candles.map((c, idx) => {
      const x = pad + ((w - pad * 2) * idx) / Math.max(candles.length - 1, 1) - barWidth / 2;
      const volH = Math.max(2, (c.volume / maxVol) * hVolArea);
      const y = h - 15 - volH;
      const isUp = idx === 0 ? true : (c.close >= candles[idx - 1].close);
      const color = isUp ? '#ff5c77' : '#4f9dff';
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${volH.toFixed(1)}" fill="${color}" opacity="0.75" rx="1" />`;
    }).join('');

    const first = candles[0];
    const last = candles[candles.length - 1];
    const diff = last.close - first.close;
    const diffRate = first.close > 0 ? (diff / first.close) * 100 : 0;
    const isGain = diff >= 0;

    $("#stockChartPrice").textContent = money(last.close, currentStockChartCurrency);
    $("#stockChartChange").textContent = `${isGain ? "+" : ""}${money(diff, currentStockChartCurrency)} (${isGain ? "+" : ""}${number(diffRate, 2)}%)`;
    $("#stockChartChange").className = `sub-rate ${signClass(diff)}`;

    let countLabel = `${candles.length}개 거래일`;
    if (currentStockChartPeriod === "1D") countLabel = `${candles.length}개 5분봉 (장중)`;
    else if (currentStockChartPeriod === "1W") countLabel = `${candles.length}개 60분봉 (1주)`;

    container.innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:260px;overflow:visible;">
        <defs>
          <linearGradient id="stockPriceGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#8e70fa" stop-opacity="0.32" />
            <stop offset="100%" stop-color="#8e70fa" stop-opacity="0.0" />
          </linearGradient>
        </defs>
        <polygon points="${priceAreaPath}" fill="url(#stockPriceGrad)" />
        <polyline points="${pricePath}" fill="none" stroke="#8e70fa" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        <text x="${pad}" y="${pad + 4}" fill="#7182a6" font-size="10">최고 ${money(maxPrice, currentStockChartCurrency)}</text>
        <text x="${pad}" y="${hPriceArea - 4}" fill="#7182a6" font-size="10">최저 ${money(minPrice, currentStockChartCurrency)}</text>

        <line x1="${pad}" y1="${hVolTop - 5}" x2="${w - pad}" y2="${hVolTop - 5}" stroke="#1f2c4d" stroke-dasharray="2,2" />
        <text x="${pad}" y="${hVolTop + 8}" fill="#7182a6" font-size="9" font-weight="700">거래량 (VOLUME)</text>
        ${volBars}
      </svg>
      <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:#7182a6;">
        <span>${first.date}</span>
        <span>${countLabel}</span>
        <span>${last.date}</span>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="empty">차트 로드 실패: ${html(err.message)}</div>`;
  }
}

    async function setPeriod(chartTab) {
    document.querySelectorAll('#stockChartPeriodTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
    chartTab.classList.add('active');
    currentStockChartPeriod = chartTab.dataset.period || '1M';
    await loadStockChartData();
    }

    return Object.freeze({ openStockChart, setPeriod });
  }

  window.WealthStockChartView = Object.freeze({ create });
})();
