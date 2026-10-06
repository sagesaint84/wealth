/* Unified period/bucketing controls for Wealth financial time-series charts. */
(() => {
  'use strict';

  const core = window.WealthTimeseriesPeriodCore;
  if (!core) {
    console.error('WealthTimeseriesPeriodCore is required.');
    return;
  }

  const { MODES, aggregateState, aggregateFlow } = core;
  const MODE_ORDER = [MODES.DAY, MODES.WEEK, MODES.MONTH, MODES.YEAR, MODES.ALL];
  const MODE_LABEL = {
    [MODES.DAY]: '일간',
    [MODES.WEEK]: '주간',
    [MODES.MONTH]: '월간',
    [MODES.YEAR]: '연간',
    [MODES.ALL]: '전체',
  };
  const DEFAULT_VISIBLE = {
    [MODES.DAY]: 30,
    [MODES.WEEK]: 20,
    [MODES.MONTH]: 18,
    [MODES.YEAR]: 8,
  };
  const MIN_VISIBLE = {
    [MODES.DAY]: 7,
    [MODES.WEEK]: 6,
    [MODES.MONTH]: 4,
    [MODES.YEAR]: 3,
  };
  const STYLE_ID = 'wealthUnifiedTimeseriesStyles';
  const ZOOM_STEP = 1.16;
  const EPSILON = 0.002;

  const modes = {
    stock: MODES.DAY,
    networth: MODES.DAY,
    pnl: MODES.MONTH,
    dividend: MODES.MONTH,
    ledger: MODES.MONTH,
  };

  const cache = {
    networth: [],
    pnl: { key: '', raw: [] },
    dividend: { key: '', dividend: [], interest: [] },
    ledgerTransactions: new Map(),
    ledgerMonthly: new Map(),
    ledgerOwner: '',
  };

  const renderQueued = new Set();
  const pendingVisiblePanZoom = new WeakMap();
  let pnlRenderGeneration = 0;
  let dividendRenderGeneration = 0;
  let internalNetWorthClick = false;
  let netWorthCapturePending = false;
  let ledgerLoadingOlder = false;

  const html = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
  const finite = value => Number.isFinite(Number(value)) ? Number(value) : 0;

  function currentOwnerValue() {
    try {
      return typeof currentOwner !== 'undefined' && currentOwner ? currentOwner : '모두';
    } catch (_) {
      return '모두';
    }
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .wealth-unified-periods {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        padding: 3px;
        border: 1px solid #26385f;
        border-radius: 10px;
        background: #0f1830;
        flex-wrap: wrap;
      }
      .wealth-unified-periods .heatmap-tab { min-width: 42px; }
      .wealth-unified-chart-shell {
        display: grid;
        grid-template-columns: 74px minmax(0, 1fr);
        gap: 8px;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        overflow: hidden;
      }
      .wealth-unified-axis {
        position: relative;
        width: 74px;
        min-width: 74px;
        height: 292px;
        color: #8291b4;
        font-size: 10px;
        font-variant-numeric: tabular-nums;
        user-select: none;
        pointer-events: none;
      }
      .wealth-unified-axis-section {
        position: absolute;
        left: 0;
        right: 0;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        align-items: flex-end;
        padding-right: 7px;
        box-sizing: border-box;
      }
      .wealth-unified-axis-section::after {
        content: '';
        position: absolute;
        right: 0;
        top: 0;
        bottom: 0;
        border-right: 1px solid rgba(130,145,180,.28);
      }
      .wealth-unified-axis-label {
        position: relative;
        white-space: nowrap;
        transform: translateY(-50%);
      }
      .wealth-unified-axis-label:last-child { transform: translateY(50%); }
      .wealth-unified-axis-label::after {
        content: '';
        position: absolute;
        right: -8px;
        top: 50%;
        width: 5px;
        border-top: 1px solid rgba(130,145,180,.38);
      }
      .wealth-unified-axis-caption {
        position: absolute;
        right: 8px;
        color: #7182a6;
        font-size: 9px;
        font-weight: 700;
      }
      .wealth-unified-viewport {
        position: relative;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-width: thin;
        scrollbar-color: #42547d #111a33;
        scrollbar-gutter: stable;
        overscroll-behavior-x: contain;
        cursor: grab;
        touch-action: pan-x pan-y;
        -webkit-overflow-scrolling: touch;
      }
      .wealth-unified-viewport.is-dragging {
        cursor: grabbing;
        user-select: none;
      }
      .wealth-unified-viewport::-webkit-scrollbar { height: 9px; }
      .wealth-unified-viewport::-webkit-scrollbar-track {
        background: #111a33;
        border-radius: 999px;
      }
      .wealth-unified-viewport::-webkit-scrollbar-thumb {
        background: #42547d;
        border: 2px solid #111a33;
        border-radius: 999px;
      }
      .wealth-unified-content {
        min-width: 100%;
        height: 292px;
        transform-origin: left center;
      }
      .wealth-unified-chart {
        display: block;
        width: 100%;
        height: 292px;
        overflow: visible;
      }
      .wealth-unified-flow-bar.is-clickable { cursor: pointer; }
      .wealth-unified-flow-bar.is-clickable:hover { opacity: .78; }
      .wealth-unified-empty {
        padding: 42px 12px;
        text-align: center;
        color: #8291b4;
        font-size: 12px;
      }
      #assetChart, #pnlBarChartWrap, #dividendBarChartWrap, #ledgerTrendContainer, #wealthHistoryPlot {
        min-width: 0;
        max-width: 100%;
      }
      @media (max-width: 720px) {
        .wealth-unified-chart-shell { grid-template-columns: 62px minmax(0, 1fr); gap: 5px; }
        .wealth-unified-axis { width: 62px; min-width: 62px; font-size: 9px; }
        .wealth-unified-viewport::-webkit-scrollbar { height: 6px; }
      }
    `;
    document.head.append(style);
  }

  function trim(value) {
    const digits = Math.abs(value) >= 100 ? 0 : (Math.abs(value) >= 10 ? 1 : 2);
    return Number(value.toFixed(digits)).toLocaleString('ko-KR');
  }

  function compactWon(value) {
    const amount = Number(value) || 0;
    const abs = Math.abs(amount);
    if (abs >= 1e12) return `₩${trim(amount / 1e12)}조`;
    if (abs >= 1e8) return `₩${trim(amount / 1e8)}억`;
    if (abs >= 1e4) return `₩${trim(amount / 1e4)}만`;
    return `₩${Math.round(amount).toLocaleString('ko-KR')}`;
  }

  function niceRange(minValue, maxValue, includeZero = false) {
    let min = Number(minValue);
    let max = Number(maxValue);
    if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 1 };
    if (includeZero) {
      min = Math.min(min, 0);
      max = Math.max(max, 0);
    }
    if (min === max) {
      const pad = Math.max(Math.abs(max) * 0.08, 1);
      min -= pad;
      max += pad;
    }
    return { min, max };
  }

  function ticks(range, count = 5) {
    return Array.from({ length: count }, (_, index) => {
      const ratio = count === 1 ? 0 : index / (count - 1);
      return range.max - ((range.max - range.min) * ratio);
    });
  }

  function axisHtml(sections) {
    return sections.map(section => {
      const labels = ticks(section.range, section.count || 5)
        .map(value => `<span class="wealth-unified-axis-label">${compactWon(value)}</span>`)
        .join('');
      return `<div class="wealth-unified-axis-section" style="top:${section.top}px;height:${section.height}px">${labels}</div>${section.caption ? `<span class="wealth-unified-axis-caption" style="top:${section.captionTop}px">${html(section.caption)}</span>` : ''}`;
    }).join('');
  }

  function ensureInjectedControls(kind, anchor, mode = modes[kind]) {
    if (!anchor) return null;
    let controls = anchor.querySelector(`.wealth-unified-periods[data-kind="${kind}"]`);
    if (!controls) {
      controls = document.createElement('div');
      controls.className = 'wealth-unified-periods heatmap-period-tabs';
      controls.dataset.kind = kind;
      controls.setAttribute('role', 'group');
      controls.setAttribute('aria-label', '차트 집계 간격');
      controls.innerHTML = MODE_ORDER.map(value => `<button type="button" class="heatmap-tab" data-unified-period="${value}">${MODE_LABEL[value]}</button>`).join('');
      anchor.appendChild(controls);
    }
    controls.querySelectorAll('[data-unified-period]').forEach(button => {
      button.classList.toggle('active', button.dataset.unifiedPeriod === mode);
    });
    return controls;
  }

  function adoptExistingControls(kind, controls, mode = modes[kind]) {
    if (!controls) return;
    controls.classList.add('wealth-unified-periods');
    controls.dataset.kind = kind;
    controls.querySelectorAll('[data-period]').forEach(button => {
      button.dataset.unifiedPeriod = button.dataset.period;
      button.classList.toggle('active', button.dataset.period === mode);
    });
  }

  function initialScale(bucketCount, resolvedMode) {
    const visible = DEFAULT_VISIBLE[resolvedMode] || 16;
    return Math.max(1, bucketCount / Math.max(1, visible));
  }

  function maxScale(bucketCount, resolvedMode) {
    const visible = MIN_VISIBLE[resolvedMode] || 4;
    return Math.max(1, bucketCount / Math.max(1, visible));
  }

  function installPanZoom(viewport, content, state, onNeedOlder = null) {
    const apply = () => {
      const width = Math.max(1, viewport.clientWidth) * state.scale;
      content.style.width = `${Math.max(1, width)}px`;
    };

    const setScale = (next, clientX = null) => {
      const previous = state.scale;
      const clamped = Math.max(1, Math.min(state.maxScale, next));
      if (Math.abs(clamped - previous) < EPSILON) return false;
      const rect = viewport.getBoundingClientRect();
      const anchor = clientX == null
        ? viewport.clientWidth / 2
        : Math.max(0, Math.min(viewport.clientWidth, clientX - rect.left));
      const oldWidth = Math.max(viewport.scrollWidth, viewport.clientWidth * previous);
      const ratio = oldWidth > 0
        ? Math.max(0, Math.min(1, (viewport.scrollLeft + anchor) / oldWidth))
        : 1;
      state.scale = clamped;
      apply();
      const newWidth = Math.max(viewport.clientWidth, viewport.clientWidth * state.scale);
      viewport.scrollLeft = Math.max(
        0,
        Math.min(newWidth - viewport.clientWidth, ratio * newWidth - anchor),
      );
      return true;
    };

    const initializeVisibleWidth = () => {
      if (!viewport.clientWidth) return false;
      apply();
      viewport.scrollLeft = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
      return true;
    };
    if (viewport.clientWidth) {
      initializeVisibleWidth();
    } else {
      const observer = new ResizeObserver(() => {
        if (!viewport.isConnected) {
          observer.disconnect();
          pendingVisiblePanZoom.delete(viewport);
          return;
        }
        if (initializeVisibleWidth()) {
          observer.disconnect();
          pendingVisiblePanZoom.delete(viewport);
        }
      });
      pendingVisiblePanZoom.set(viewport, () => {
        if (initializeVisibleWidth()) {
          observer.disconnect();
          pendingVisiblePanZoom.delete(viewport);
        }
      });
      observer.observe(viewport);
    }

    viewport.addEventListener('wheel', event => {
      if (Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
      const factor = event.deltaY < 0 ? ZOOM_STEP : (1 / ZOOM_STEP);
      const changed = setScale(state.scale * factor, event.clientX);
      if (changed) {
        event.preventDefault();
        return;
      }
      if (event.deltaY > 0 && state.scale <= 1 + EPSILON && typeof onNeedOlder === 'function') {
        const accepted = onNeedOlder();
        if (accepted !== false) event.preventDefault();
      }
    }, { passive: false });

    let pointerId = null;
    let startX = 0;
    let startScrollLeft = 0;
    viewport.addEventListener('pointerdown', event => {
      if (event.pointerType !== 'mouse' || event.button !== 0) return;
      pointerId = event.pointerId;
      startX = event.clientX;
      startScrollLeft = viewport.scrollLeft;
      viewport.classList.add('is-dragging');
      viewport.setPointerCapture?.(pointerId);
    });
    viewport.addEventListener('pointermove', event => {
      if (pointerId == null || event.pointerId !== pointerId) return;
      viewport.scrollLeft = startScrollLeft - (event.clientX - startX);
      event.preventDefault();
    });
    const stopDrag = event => {
      if (pointerId == null || (event.pointerId != null && event.pointerId !== pointerId)) return;
      try { viewport.releasePointerCapture?.(pointerId); } catch (_) {}
      pointerId = null;
      viewport.classList.remove('is-dragging');
    };
    viewport.addEventListener('pointerup', stopDrag);
    viewport.addEventListener('pointercancel', stopDrag);

    let pinchDistance = 0;
    let pinchScale = state.scale;
    const distance = touches => Math.hypot(
      touches[0].clientX - touches[1].clientX,
      touches[0].clientY - touches[1].clientY,
    );
    viewport.addEventListener('touchstart', event => {
      if (event.touches.length !== 2) return;
      pinchDistance = distance(event.touches);
      pinchScale = state.scale;
      event.preventDefault();
    }, { passive: false });
    viewport.addEventListener('touchmove', event => {
      if (event.touches.length !== 2 || !pinchDistance) return;
      const centerX = (event.touches[0].clientX + event.touches[1].clientX) / 2;
      setScale(pinchScale * (distance(event.touches) / pinchDistance), centerX);
      event.preventDefault();
    }, { passive: false });
    viewport.addEventListener('touchend', event => {
      if (event.touches.length < 2) pinchDistance = 0;
    }, { passive: true });
  }

  function yearText(bucket, index, mode) {
    if (mode === MODES.YEAR) return '';
    if (!bucket.yearMarker && index !== 0) return '';
    return `${bucket.year}년`;
  }

  function renderStateChart(host, aggregated, options = {}) {
    if (!host) return;
    const buckets = aggregated?.buckets || [];
    if (!buckets.length) {
      host.innerHTML = '<div class="wealth-unified-empty">표시할 기록이 없습니다.</div>';
      return;
    }

    const closes = buckets.map(item => finite(item.close));
    const changes = buckets.map(item => finite(item.change));
    const lineRange = niceRange(Math.min(...closes), Math.max(...closes));
    const changeAbs = Math.max(1, ...changes.map(value => Math.abs(value)));
    const changeRange = { min: -changeAbs, max: changeAbs };
    const width = 1000;
    const height = 292;
    const left = 20;
    const right = 980;
    const lineTop = 18;
    const lineBottom = 160;
    const barTop = 190;
    const barBottom = 244;
    const zeroY = (barTop + barBottom) / 2;
    const x = index => left + ((right - left) * (index + 0.5)) / Math.max(1, buckets.length);
    const lineY = value => lineBottom - ((value - lineRange.min) / (lineRange.max - lineRange.min)) * (lineBottom - lineTop);
    const barMaxH = (barBottom - barTop) / 2 - 3;
    const barWidth = Math.max(4, Math.min(24, ((right - left) / Math.max(1, buckets.length)) * 0.5));

    const points = buckets.map((bucket, index) => `${x(index)},${lineY(bucket.close)}`).join(' ');
    const area = `${left},${lineBottom} ${points} ${right},${lineBottom}`;
    const bars = buckets.map((bucket, index) => {
      const value = finite(bucket.change);
      const h = Math.max(value === 0 ? 1 : 2, (Math.abs(value) / changeAbs) * barMaxH);
      const y = value >= 0 ? zeroY - h : zeroY;
      const fill = value >= 0 ? '#f05268' : '#438ee6';
      return `<rect x="${x(index) - barWidth / 2}" y="${y}" width="${barWidth}" height="${h}" rx="1.5" fill="${fill}" opacity=".94"><title>${html(bucket.label)} · 변화 ${compactWon(value)}</title></rect>`;
    }).join('');
    const labels = buckets.map((bucket, index) => {
      const marker = yearText(bucket, index, aggregated.mode);
      return `<text x="${x(index)}" y="262" fill="#9aacd2" font-size="10" text-anchor="middle">${html(bucket.label)}</text>${marker ? `<text x="${x(index)}" y="280" fill="#6f82ad" font-size="9" font-weight="700" text-anchor="middle">${html(marker)}</text>` : ''}`;
    }).join('');
    const dots = buckets.map((bucket, index) => `<circle cx="${x(index)}" cy="${lineY(bucket.close)}" r="2.8" fill="#9b8afb"><title>${html(bucket.label)} · ${compactWon(bucket.close)}</title></circle>`).join('');

    host.innerHTML = `<div class="wealth-unified-chart-shell" data-unified-kind="${html(options.kind || '')}"><div class="wealth-unified-axis">${axisHtml([
      { range: lineRange, top: lineTop, height: lineBottom - lineTop, count: 4 },
      { range: changeRange, top: barTop, height: barBottom - barTop, count: 3, caption: options.changeLabel || '변화', captionTop: barTop - 13 },
    ])}</div><div class="wealth-unified-viewport"><div class="wealth-unified-content"><svg class="wealth-unified-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${html(options.ariaLabel || '금액 추이 차트')}"><line x1="${left}" y1="${lineBottom}" x2="${right}" y2="${lineBottom}" stroke="#293858" opacity=".6"/><line x1="${left}" y1="${zeroY}" x2="${right}" y2="${zeroY}" stroke="#334673" opacity=".85"/><polygon points="${area}" fill="#8e70fa" opacity=".10"/><polyline points="${points}" fill="none" stroke="#8e70fa" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${dots}${bars}${labels}</svg></div></div></div>`;

    const viewport = host.querySelector('.wealth-unified-viewport');
    const content = host.querySelector('.wealth-unified-content');
    installPanZoom(viewport, content, {
      mode: aggregated.mode,
      bucketCount: buckets.length,
      scale: initialScale(buckets.length, aggregated.mode),
      maxScale: maxScale(buckets.length, aggregated.mode),
    }, options.onNeedOlder || null);
  }

  function renderFlowChart(host, aggregated, series, options = {}) {
    if (!host) return;
    const buckets = aggregated?.buckets || [];
    if (!buckets.length) {
      host.innerHTML = '<div class="wealth-unified-empty">표시할 기록이 없습니다.</div>';
      return;
    }

    const values = [];
    buckets.forEach(bucket => series.forEach(item => values.push(finite(bucket.values?.[item.key]))));
    const range = niceRange(Math.min(0, ...values), Math.max(0, ...values), true);
    const width = 1000;
    const height = 292;
    const left = 20;
    const right = 980;
    const top = 18;
    const bottom = 244;
    const y = value => bottom - ((value - range.min) / (range.max - range.min)) * (bottom - top);
    const zeroY = y(0);
    const slot = (right - left) / Math.max(1, buckets.length);
    const groupWidth = Math.min(34, slot * 0.72);
    const barWidth = Math.max(2, groupWidth / Math.max(1, series.length));

    const bars = buckets.map((bucket, index) => {
      const cx = left + slot * (index + 0.5);
      return series.map((item, seriesIndex) => {
        const value = finite(bucket.values?.[item.key]);
        const py = y(value);
        const rectY = Math.min(py, zeroY);
        const rectH = Math.max(value === 0 ? 1 : 2, Math.abs(zeroY - py));
        const startX = cx - (barWidth * series.length) / 2;
        const fill = value < 0 ? (item.negativeColor || '#438ee6') : (item.color || '#43d982');
        const clickable = typeof options.onBucketClick === 'function';
        return `<rect class="wealth-unified-flow-bar${clickable ? ' is-clickable' : ''}" data-bucket-index="${index}" x="${startX + seriesIndex * barWidth}" y="${rectY}" width="${Math.max(1, barWidth - 1)}" height="${rectH}" rx="1.5" fill="${fill}" opacity=".95"><title>${html(bucket.label)} · ${html(item.label)} ${compactWon(value)}</title></rect>`;
      }).join('');
    }).join('');

    const labels = buckets.map((bucket, index) => {
      const cx = left + slot * (index + 0.5);
      const marker = yearText(bucket, index, aggregated.mode);
      return `<text x="${cx}" y="262" fill="#9aacd2" font-size="10" text-anchor="middle">${html(bucket.label)}</text>${marker ? `<text x="${cx}" y="280" fill="#6f82ad" font-size="9" font-weight="700" text-anchor="middle">${html(marker)}</text>` : ''}`;
    }).join('');

    host.innerHTML = `<div class="wealth-unified-chart-shell" data-unified-kind="${html(options.kind || '')}"><div class="wealth-unified-axis">${axisHtml([{ range, top, height: bottom - top, count: 5 }])}</div><div class="wealth-unified-viewport"><div class="wealth-unified-content"><svg class="wealth-unified-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${html(options.ariaLabel || '금액 막대 차트')}"><line x1="${left}" y1="${zeroY}" x2="${right}" y2="${zeroY}" stroke="#334673" opacity=".9"/>${bars}${labels}</svg></div></div></div>`;

    if (typeof options.onBucketClick === 'function') {
      host.querySelectorAll('.wealth-unified-flow-bar[data-bucket-index]').forEach(node => {
        node.addEventListener('click', event => {
          const index = Number(event.currentTarget.dataset.bucketIndex);
          const bucket = buckets[index];
          if (bucket) options.onBucketClick(bucket, aggregated.mode);
        });
      });
    }

    const viewport = host.querySelector('.wealth-unified-viewport');
    const content = host.querySelector('.wealth-unified-content');
    installPanZoom(viewport, content, {
      mode: aggregated.mode,
      bucketCount: buckets.length,
      scale: initialScale(buckets.length, aggregated.mode),
      maxScale: maxScale(buckets.length, aggregated.mode),
    }, options.onNeedOlder || null);
  }

  function stockSource() {
    try {
      return Array.isArray(assetRecords) ? assetRecords : [];
    } catch (_) {
      return [];
    }
  }

  function renderStock() {
    if (document.getElementById('recordsPanel')?.classList.contains('is-tax-view')) return;
    const host = document.getElementById('assetChart');
    const controls = document.getElementById('recordPeriodTabs');
    if (!host || !controls) return;
    adoptExistingControls('stock', controls);
    const source = stockSource();
    const aggregated = aggregateState(source, modes.stock, {
      valueField: 'total_value_krw',
      changeField: 'day_profit_krw',
    });
    renderStateChart(host, aggregated, {
      kind: 'stock',
      ariaLabel: '주식기록 자산 및 기간별 가격변동 손익',
      changeLabel: `${MODE_LABEL[aggregated.mode]} 가격변동`,
    });
  }

  function captureNetWorthFromLegacy() {
    const plot = document.getElementById('wealthHistoryPlot');
    if (!plot) return false;
    const records = [];
    plot.querySelectorAll('.wealth-history-point[data-history-date]').forEach(point => {
      const date = point.dataset.historyDate;
      const title = point.querySelector('title')?.textContent || '';
      const match = title.match(/순자산\s*([+-]?[\d,]+)원/);
      if (!date || !match) return;
      records.push({ date, net_worth: Number(match[1].replace(/,/g, '')) });
    });
    if (!records.length) return false;
    cache.networth = records.sort((a, b) => a.date.localeCompare(b.date));
    return true;
  }

  function ensureNetWorthSource() {
    const panel = document.querySelector('.wealth-history');
    const controls = panel?.querySelector('.wealth-periods');
    const plot = document.getElementById('wealthHistoryPlot');
    if (!panel || !controls || !plot) return false;
    if (cache.networth.length) {
      adoptExistingControls('networth', controls);
      return true;
    }
    if (netWorthCapturePending) return false;
    const allButton = controls.querySelector('[data-period="ALL"]');
    if (!allButton) return false;
    netWorthCapturePending = true;
    internalNetWorthClick = true;
    allButton.click();
    internalNetWorthClick = false;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      captureNetWorthFromLegacy();
      adoptExistingControls('networth', controls);
      netWorthCapturePending = false;
      renderNetWorth();
    }));
    return false;
  }

  function renderNetWorth() {
    if (!ensureNetWorthSource()) return;
    const host = document.getElementById('wealthHistoryPlot');
    const aggregated = aggregateState(cache.networth, modes.networth, {
      valueField: 'net_worth',
    });
    renderStateChart(host, aggregated, {
      kind: 'networth',
      ariaLabel: '순자산 및 기간별 변화량',
      changeLabel: `${MODE_LABEL[aggregated.mode]} 순자산 변화`,
    });
  }

  function activePnlTradeType() {
    return document.querySelector('#pnlTradeTypeTabs .heatmap-tab.active')?.dataset.tradeType || 'all';
  }

  function activeBroker(selectId) {
    return document.getElementById(selectId)?.value || 'all';
  }

  const pnlPending = new Map();
  const dividendPending = new Map();

  async function pnlSource() {
    const owner = currentOwnerValue();
    const tradeType = activePnlTradeType();
    const key = `${owner}|${tradeType}`;
    let data = cache.pnl;
    if (data.key !== key) {
      if (!pnlPending.has(key)) {
        const pending = api(`/api/realized-pnl?owner=${encodeURIComponent(owner)}&year=all&trade_type=${encodeURIComponent(tradeType)}`)
          .then(response => ({ key, raw: Array.isArray(response?.records) ? response.records : [] }))
          .finally(() => pnlPending.delete(key));
        pnlPending.set(key, pending);
      }
      data = await pnlPending.get(key);
      if (owner === currentOwnerValue() && tradeType === activePnlTradeType()) cache.pnl = data;
    }
    const broker = activeBroker('pnlBrokerFilter');
    if (broker === 'all') return data.raw;
    return data.raw.filter(record => {
      const label = String(record?.broker || '').trim();
      return broker === '__unassigned__' ? !label : label === broker;
    });
  }

  async function renderPnl() {
    const host = document.getElementById('pnlBarChartWrap');
    const header = host?.closest('.dividend-chart-section')?.querySelector('.dividend-chart-header');
    if (!host || !header || typeof api !== 'function') return;
    ensureInjectedControls('pnl', header);
    const owner = currentOwnerValue();
    const generation = ++pnlRenderGeneration;
    try {
      const source = await pnlSource();
      if (generation !== pnlRenderGeneration || owner !== currentOwnerValue()) return;
      const rows = source.map(record => ({ ...record, pnl_value: finite(record?.pnl_krw) }));
      const aggregated = aggregateFlow(rows, modes.pnl, { fields: ['pnl_value'] });
      renderFlowChart(host, aggregated, [
        { key: 'pnl_value', label: '실현손익', color: '#f05268', negativeColor: '#438ee6' },
      ], {
        kind: 'pnl',
        ariaLabel: '기간별 실현손익',
        onBucketClick: (bucket, resolvedMode) => {
          if (resolvedMode !== MODES.MONTH || typeof renderPnlMonthlyDetail !== 'function') return;
          const month = Number(bucket.key.slice(5, 7));
          try { selectedPnlMonth = month; } catch (_) {}
          renderPnlMonthlyDetail(month);
        },
      });
      const title = document.getElementById('pnlChartTitle');
      if (title) title.textContent = `📊 ${MODE_LABEL[aggregated.mode]} 실현손익 추이`;
    } catch (error) {
      console.error('실현손익 공통 차트 오류:', error);
    }
  }

  function dividendMode() {
    return document.querySelector('#dividendModeTabs .heatmap-tab.active')?.dataset.divMode || 'actual';
  }

  async function dividendSource() {
    const owner = currentOwnerValue();
    const key = owner;
    let data = cache.dividend;
    if (data.key !== key) {
      if (!dividendPending.has(key)) {
        const pending = api(`/api/actual-dividends?owner=${encodeURIComponent(owner)}&year=all`)
          .then(response => ({
            key,
            dividend: Array.isArray(response?.records) ? response.records : [],
            interest: Array.isArray(response?.interest_records) ? response.interest_records : [],
          })).finally(() => dividendPending.delete(key));
        dividendPending.set(key, pending);
      }
      data = await dividendPending.get(key);
      if (owner === currentOwnerValue()) cache.dividend = data;
    }
    const broker = activeBroker('dividendBrokerFilter');
    const filterBroker = rows => broker === 'all' ? rows : rows.filter(record => {
      const label = String(record?.broker || '').trim();
      return broker === '__unassigned__' ? !label : label === broker;
    });
    return {
      dividend: filterBroker(data.dividend),
      interest: filterBroker(data.interest),
    };
  }

  async function renderDividend() {
    const host = document.getElementById('dividendBarChartWrap');
    const header = host?.closest('.dividend-chart-section')?.querySelector('.dividend-chart-header');
    if (!host || !header || typeof api !== 'function') return;
    const controls = ensureInjectedControls('dividend', header);
    if (dividendMode() !== 'actual') {
      if (controls) controls.hidden = true;
      return;
    }
    if (controls) controls.hidden = false;
    const owner = currentOwnerValue();
    const generation = ++dividendRenderGeneration;
    try {
      const source = await dividendSource();
      if (generation !== dividendRenderGeneration || owner !== currentOwnerValue() || dividendMode() !== 'actual') return;
      const rows = [
        ...source.dividend.map(record => ({ ...record, dividend_value: finite(record?.amount_krw), interest_value: 0 })),
        ...source.interest.map(record => ({ ...record, dividend_value: 0, interest_value: finite(record?.amount_krw) })),
      ];
      const aggregated = aggregateFlow(rows, modes.dividend, { fields: ['dividend_value', 'interest_value'] });
      renderFlowChart(host, aggregated, [
        { key: 'dividend_value', label: '배당', color: '#fb7185' },
        { key: 'interest_value', label: '이자', color: '#f6b84a' },
      ], {
        kind: 'dividend',
        ariaLabel: '기간별 실제 배당 및 이자',
        onBucketClick: (bucket, resolvedMode) => {
          if (resolvedMode !== MODES.MONTH || typeof renderActualDividendDetail !== 'function') return;
          const month = Number(bucket.key.slice(5, 7));
          try { selectedDividendMonth = month; } catch (_) {}
          renderActualDividendDetail(month);
        },
      });
      const title = document.getElementById('dividendChartTitle');
      if (title) title.textContent = `📊 ${MODE_LABEL[aggregated.mode]} 실제 배당·이자 추이`;
      return true;
    } catch (error) {
      console.error('배당·이자 공통 차트 오류:', error);
      return false;
    }
  }

  function monthKey(year, month) {
    return `${Number(year)}-${String(Number(month)).padStart(2, '0')}`;
  }

  function shiftMonthKey(key, delta) {
    const [yearTextValue, monthTextValue] = String(key).split('-');
    let year = Number(yearTextValue);
    let month = Number(monthTextValue) + delta;
    while (month < 1) { month += 12; year -= 1; }
    while (month > 12) { month -= 12; year += 1; }
    return monthKey(year, month);
  }

  function seedLedgerMonthly() {
    const owner = currentOwnerValue();
    if (cache.ledgerOwner !== owner) {
      cache.ledgerOwner = owner;
      cache.ledgerTransactions.clear();
      cache.ledgerMonthly.clear();
    }
    try {
      const trend = typeof rawLedgerData !== 'undefined' && Array.isArray(rawLedgerData?.monthly_trend)
        ? rawLedgerData.monthly_trend : [];
      trend.forEach(row => {
        const key = monthKey(row.year, row.month);
        cache.ledgerMonthly.set(key, {
          date: `${key}-01`,
          income_value: finite(row.income),
          expense_value: finite(row.expense),
        });
      });
    } catch (_) {}
  }

  async function fetchLedgerMonth(key, includeTransactions = false) {
    const owner = currentOwnerValue();
    const [year, month] = key.split('-').map(Number);
    const response = await api(`/api/ledger?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&owner=${encodeURIComponent(owner)}`);
    (Array.isArray(response?.monthly_trend) ? response.monthly_trend : []).forEach(row => {
      const rowKey = monthKey(row.year, row.month);
      cache.ledgerMonthly.set(rowKey, {
        date: `${rowKey}-01`,
        income_value: finite(row.income),
        expense_value: finite(row.expense),
      });
    });
    if (includeTransactions) {
      cache.ledgerTransactions.set(key, Array.isArray(response?.transactions) ? response.transactions : []);
    }
  }

  function currentLedgerMonthKey() {
    try {
      return monthKey(currentLedgerYear, currentLedgerMonth);
    } catch (_) {
      const now = new Date();
      return monthKey(now.getFullYear(), now.getMonth() + 1);
    }
  }

  async function ensureLedgerTransactionMonths(count = 6) {
    seedLedgerMonthly();
    const end = currentLedgerMonthKey();
    const keys = Array.from({ length: count }, (_, index) => shiftMonthKey(end, -(count - 1 - index)));
    const missing = keys.filter(key => !cache.ledgerTransactions.has(key));
    for (const key of missing) await fetchLedgerMonth(key, true);
  }

  function ledgerTransactionRows() {
    return [...cache.ledgerTransactions.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .flatMap(([, rows]) => rows)
      .filter(record => record?.type === 'income' || record?.type === 'expense')
      .map(record => ({
        date: String(record.date || ''),
        income_value: record.type === 'income' ? finite(record.amount) : 0,
        expense_value: record.type === 'expense' ? finite(record.amount) : 0,
      }));
  }

  function ledgerMonthlyRows() {
    seedLedgerMonthly();
    return [...cache.ledgerMonthly.values()].sort((a, b) => a.date.localeCompare(b.date));
  }

  async function extendLedgerHistory() {
    if (ledgerLoadingOlder || typeof api !== 'function') return false;
    ledgerLoadingOlder = true;
    try {
      seedLedgerMonthly();
      const usingTransactions = modes.ledger === MODES.DAY || modes.ledger === MODES.WEEK;
      const keys = usingTransactions
        ? [...cache.ledgerTransactions.keys()].sort()
        : [...cache.ledgerMonthly.keys()].sort();
      const earliest = keys[0] || currentLedgerMonthKey();
      const previousEnd = shiftMonthKey(earliest, -1);
      if (usingTransactions) {
        const older = Array.from({ length: 6 }, (_, index) => shiftMonthKey(previousEnd, -(5 - index)));
        for (const key of older) {
          if (!cache.ledgerTransactions.has(key)) await fetchLedgerMonth(key, true);
        }
      } else {
        await fetchLedgerMonth(previousEnd, false);
      }
      await renderLedger();
      return true;
    } catch (error) {
      console.error('가계부 공통 차트 과거 데이터 확장 오류:', error);
      return false;
    } finally {
      ledgerLoadingOlder = false;
    }
  }

  async function renderLedger() {
    const host = document.getElementById('ledgerTrendContainer');
    const panel = host?.closest('.ledger-sub-panel');
    if (!host || !panel || typeof api !== 'function') return;
    let controlAnchor = panel.querySelector('.wealth-unified-ledger-controls');
    if (!controlAnchor) {
      controlAnchor = document.createElement('div');
      controlAnchor.className = 'wealth-unified-ledger-controls';
      const heading = panel.querySelector('h3');
      if (heading?.parentElement) heading.parentElement.appendChild(controlAnchor);
      else panel.prepend(controlAnchor);
    }
    ensureInjectedControls('ledger', controlAnchor);
    try {
      let rows;
      if (modes.ledger === MODES.DAY || modes.ledger === MODES.WEEK) {
        if (!cache.ledgerTransactions.size) await ensureLedgerTransactionMonths(6);
        rows = ledgerTransactionRows();
      } else {
        rows = ledgerMonthlyRows();
      }
      const aggregated = aggregateFlow(rows, modes.ledger, { fields: ['income_value', 'expense_value'] });
      renderFlowChart(host, aggregated, [
        { key: 'income_value', label: '수입', color: '#42dc88' },
        { key: 'expense_value', label: '지출', color: '#ef476f' },
      ], {
        kind: 'ledger',
        ariaLabel: '기간별 가계부 수입 지출',
        onNeedOlder: extendLedgerHistory,
      });
      const title = panel.querySelector('h3');
      if (title) title.textContent = `${MODE_LABEL[aggregated.mode]} 현금흐름 추이`;
    } catch (error) {
      console.error('가계부 공통 차트 오류:', error);
    }
  }

  function queue(kind) {
    if (renderQueued.has(kind)) return;
    renderQueued.add(kind);
    requestAnimationFrame(() => {
      renderQueued.delete(kind);
      if (kind === 'stock') renderStock();
      if (kind === 'networth') renderNetWorth();
      if (kind === 'pnl') void renderPnl();
      if (kind === 'dividend') void renderDividend();
      if (kind === 'ledger') void renderLedger();
    });
  }

  function handlePeriodClick(event) {
    if (internalNetWorthClick) return;
    const existing = event.target?.closest?.('#recordPeriodTabs [data-period], .wealth-history .wealth-periods [data-period]');
    const injected = event.target?.closest?.('.wealth-unified-periods [data-unified-period]');
    const button = existing || injected;
    if (!button) return;
    const controls = button.closest('.wealth-unified-periods, #recordPeriodTabs, .wealth-history .wealth-periods');
    let kind = controls?.dataset?.kind;
    if (!kind && controls?.id === 'recordPeriodTabs') kind = 'stock';
    if (!kind && controls?.classList?.contains('wealth-periods')) kind = 'networth';
    if (!kind) return;
    const mode = button.dataset.unifiedPeriod || button.dataset.period;
    if (!MODE_ORDER.includes(mode)) return;

    if (existing) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
    modes[kind] = mode;
    controls.querySelectorAll('[data-period], [data-unified-period]').forEach(item => {
      const value = item.dataset.unifiedPeriod || item.dataset.period;
      item.classList.toggle('active', value === mode);
    });
    if (kind === 'ledger' && (mode === MODES.DAY || mode === MODES.WEEK)) {
      void ensureLedgerTransactionMonths(6).then(() => queue('ledger'));
    } else {
      queue(kind);
    }
  }

  function handleExternalChange(event) {
    const target = event.target;
    if (!target) return;
    if (target.id === 'pnlBrokerFilter') queue('pnl');
    if (target.id === 'dividendBrokerFilter') queue('dividend');
  }

  function handleExternalClick(event) {
    if (event.target?.closest?.('#pnlTradeTypeTabs [data-trade-type]')) {
      cache.pnl.key = '';
      setTimeout(() => queue('pnl'), 0);
    }
    if (event.target?.closest?.('#dividendModeTabs [data-div-mode]')) {
      setTimeout(() => queue('dividend'), 0);
    }
    if (event.target?.closest?.('.family-tab')) {
      cache.pnl.key = '';
      cache.dividend.key = '';
      cache.ledgerOwner = '';
      setTimeout(() => ['pnl', 'dividend', 'ledger'].forEach(queue), 0);
    }
  }

  function hostNeedsUnified(hostId) {
    const host = document.getElementById(hostId);
    if (!host) return false;
    const child = host.firstElementChild;
    return !child?.classList?.contains('wealth-unified-chart-shell')
      && !child?.classList?.contains('wealth-unified-empty');
  }

  function refreshVisiblePanZoom(hostId) {
    const viewport = document.getElementById(hostId)?.querySelector('.wealth-unified-viewport');
    if (viewport) pendingVisiblePanZoom.get(viewport)?.();
  }

  function installObserver() {
    const observer = new MutationObserver(() => {
      if (!document.getElementById('recordsPanel')?.classList.contains('is-tax-view') && hostNeedsUnified('assetChart')) queue('stock');
      if (!netWorthCapturePending && hostNeedsUnified('wealthHistoryPlot')) queue('networth');
      if (hostNeedsUnified('pnlBarChartWrap')) queue('pnl');
      if (dividendMode() === 'actual' && hostNeedsUnified('dividendBarChartWrap')) queue('dividend');
      if (hostNeedsUnified('ledgerTrendContainer')) queue('ledger');
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function install() {
    injectStyles();
    document.addEventListener('click', handlePeriodClick, true);
    document.addEventListener('change', handleExternalChange, true);
    document.addEventListener('click', handleExternalClick, false);
    installObserver();
    ['stock', 'networth', 'pnl', 'dividend', 'ledger'].forEach(queue);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();

  window.WealthUnifiedTimeseries = {
    modes,
    renderStock,
    renderNetWorth,
    renderPnl,
    renderDividend,
    refreshVisiblePanZoom,
    renderLedger,
    extendLedgerHistory,
  };
  window.dispatchEvent(new Event('wealth:unified-ready'));
})();
