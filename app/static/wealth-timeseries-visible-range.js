/* Visible-range scaling for unified Wealth financial time-series charts. */
(() => {
  'use strict';

  const core = window.WealthTimeseriesPeriodCore;
  if (!core || window.WealthTimeseriesVisibleRange) return;

  const registry = Object.create(null);
  const installed = new WeakSet();
  const STYLE_ID = 'wealthTimeseriesVisibleRangeStyles';
  const VIEWBOX_WIDTH = 1000;
  const PLOT_LEFT = 20;
  const PLOT_RIGHT = 980;

  const finite = value => Number.isFinite(Number(value)) ? Number(value) : 0;

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

  function paddedRange(values, includeZero = false) {
    const source = values.map(finite).filter(Number.isFinite);
    if (!source.length) return { min: 0, max: 1 };
    let min = Math.min(...source);
    let max = Math.max(...source);
    if (includeZero) {
      min = Math.min(min, 0);
      max = Math.max(max, 0);
    }
    if (min === max) {
      const pad = Math.max(Math.abs(max) * 0.08, 1);
      return { min: min - pad, max: max + pad };
    }
    const pad = Math.max((max - min) * 0.08, 1);
    min -= pad;
    max += pad;
    if (includeZero) {
      min = Math.min(min, 0);
      max = Math.max(max, 0);
    }
    return { min, max };
  }

  function ticks(range, count = 5) {
    return Array.from({ length: count }, (_, index) => {
      const ratio = count <= 1 ? 0 : index / (count - 1);
      return range.max - ((range.max - range.min) * ratio);
    });
  }

  function axisHtml(range, { top, height, count = 5 } = {}) {
    const labels = ticks(range, count)
      .map(value => `<span class="wealth-unified-axis-label">${compactWon(value)}</span>`)
      .join('');
    return `<div class="wealth-unified-axis-section" style="top:${top}px;height:${height}px">${labels}</div>`;
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .wealth-unified-chart-shell.wealth-visible-state {
        grid-template-columns: 74px minmax(0, 1fr) 74px;
      }
      .wealth-unified-chart-shell.wealth-visible-state .wealth-unified-axis-label {
        transform: none;
      }
      .wealth-unified-chart-shell.wealth-visible-state .wealth-unified-axis-label:first-child {
        transform: translateY(-50%);
      }
      .wealth-unified-chart-shell.wealth-visible-state .wealth-unified-axis-label:last-child {
        transform: translateY(50%);
      }
      .wealth-unified-axis-right .wealth-unified-axis-section {
        align-items: flex-start;
        padding-left: 7px;
        padding-right: 0;
      }
      .wealth-unified-axis-right .wealth-unified-axis-section::after {
        left: 0;
        right: auto;
        border-left: 1px solid rgba(130,145,180,.28);
        border-right: 0;
      }
      .wealth-unified-axis-right .wealth-unified-axis-label::after {
        left: -8px;
        right: auto;
      }
      @media (max-width: 720px) {
        .wealth-unified-chart-shell.wealth-visible-state {
          grid-template-columns: 62px minmax(0, 1fr) 62px;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function inferStateKind(options = {}) {
    if (options.valueField === 'total_value_krw') return 'stock';
    if (options.valueField === 'net_worth') return 'networth';
    return '';
  }

  function inferFlowKind(options = {}) {
    const fields = Array.isArray(options.fields) ? options.fields : [];
    if (fields.includes('pnl_value')) return 'pnl';
    if (fields.includes('dividend_value') || fields.includes('interest_value')) return 'dividend';
    if (fields.includes('income_value') || fields.includes('expense_value')) return 'ledger';
    return '';
  }

  function wrapAggregators() {
    const aggregateState = core.aggregateState.bind(core);
    const aggregateFlow = core.aggregateFlow.bind(core);
    core.aggregateState = (records, mode, options = {}) => {
      const result = aggregateState(records, mode, options);
      const kind = inferStateKind(options);
      if (kind) registry[kind] = result;
      return result;
    };
    core.aggregateFlow = (records, mode, options = {}) => {
      const result = aggregateFlow(records, mode, options);
      const kind = inferFlowKind(options);
      if (kind) registry[kind] = result;
      return result;
    };
  }

  function bucketCenterPx(contentWidth, index, count) {
    const x = PLOT_LEFT + ((PLOT_RIGHT - PLOT_LEFT) * (index + 0.5)) / Math.max(1, count);
    return contentWidth * x / VIEWBOX_WIDTH;
  }

  function visibleBounds(viewport, count) {
    if (!count) return { start: 0, end: -1 };
    const contentWidth = Math.max(viewport.scrollWidth, viewport.clientWidth, 1);
    const startPx = viewport.scrollLeft;
    const endPx = startPx + Math.max(viewport.clientWidth, 1);
    const slotPx = contentWidth * (PLOT_RIGHT - PLOT_LEFT) / VIEWBOX_WIDTH / Math.max(1, count);
    let start = 0;
    let end = count - 1;
    while (start < count - 1 && bucketCenterPx(contentWidth, start, count) + slotPx / 2 < startPx) start += 1;
    while (end > start && bucketCenterPx(contentWidth, end, count) - slotPx / 2 > endPx) end -= 1;
    return { start, end };
  }

  function thinXAxisLabels(shell, viewport, count, mode, bounds) {
    const contentWidth = Math.max(viewport.scrollWidth, viewport.clientWidth, 1);
    const slotPx = contentWidth * (PLOT_RIGHT - PLOT_LEFT) / VIEWBOX_WIDTH / Math.max(1, count);
    const minimum = mode === '1W' ? 54 : mode === '1M' ? 42 : mode === '1Y' ? 46 : 44;
    const step = Math.max(1, Math.ceil(minimum / Math.max(slotPx, 1)));
    const labels = shell.querySelectorAll('svg text[y="262"]');
    labels.forEach((label, index) => {
      const inView = index >= bounds.start && index <= bounds.end;
      const selected = ((index - bounds.start) % step === 0) || index === bounds.end;
      label.style.visibility = inView && selected ? 'visible' : 'hidden';
    });
    shell.querySelectorAll('svg text[y="280"]').forEach(label => {
      const x = Number(label.getAttribute('x')) || 0;
      const pixel = contentWidth * x / VIEWBOX_WIDTH;
      label.style.visibility = pixel >= viewport.scrollLeft && pixel <= viewport.scrollLeft + viewport.clientWidth
        ? 'visible' : 'hidden';
    });
  }

  function clampY(value) {
    return Math.max(-500, Math.min(800, value));
  }

  function installState(shell, kind, aggregated) {
    const buckets = aggregated?.buckets || [];
    if (!buckets.length) return;
    const viewport = shell.querySelector('.wealth-unified-viewport');
    const content = shell.querySelector('.wealth-unified-content');
    const svg = shell.querySelector('svg');
    const leftAxis = shell.querySelector('.wealth-unified-axis');
    if (!viewport || !content || !svg || !leftAxis) return;

    const previousViewportWidth = Math.max(viewport.clientWidth, 1);
    const existingScale = Math.max(1, content.getBoundingClientRect().width / previousViewportWidth);
    shell.classList.add('wealth-visible-state');
    let rightAxis = shell.querySelector('.wealth-unified-axis-right');
    if (!rightAxis) {
      rightAxis = document.createElement('div');
      rightAxis.className = 'wealth-unified-axis wealth-unified-axis-right';
      shell.appendChild(rightAxis);
    }
    requestAnimationFrame(() => {
      content.style.width = `${Math.max(1, viewport.clientWidth) * existingScale}px`;
    });

    const lineTop = 18;
    const lineBottom = 160;
    const barTop = 190;
    const barBottom = 244;
    const zeroY = (barTop + barBottom) / 2;
    const barMaxH = (barBottom - barTop) / 2 - 3;
    const polyline = svg.querySelector('polyline');
    const polygon = svg.querySelector('polygon');
    const circles = [...svg.querySelectorAll('circle')];
    const bars = [...svg.querySelectorAll('rect')];

    const update = () => {
      const bounds = visibleBounds(viewport, buckets.length);
      const visible = buckets.slice(bounds.start, bounds.end + 1);
      const lineRange = paddedRange(visible.map(bucket => bucket.close), false);
      const changeAbs = Math.max(1, ...visible.map(bucket => Math.abs(finite(bucket.change)))) * 1.08;
      const changeRange = { min: -changeAbs, max: changeAbs };
      const lineY = value => clampY(lineBottom - ((finite(value) - lineRange.min) / (lineRange.max - lineRange.min)) * (lineBottom - lineTop));
      const x = index => PLOT_LEFT + ((PLOT_RIGHT - PLOT_LEFT) * (index + 0.5)) / Math.max(1, buckets.length);

      const points = buckets.map((bucket, index) => `${x(index)},${lineY(bucket.close)}`).join(' ');
      if (polyline) polyline.setAttribute('points', points);
      if (polygon) polygon.setAttribute('points', `${PLOT_LEFT},${lineBottom} ${points} ${PLOT_RIGHT},${lineBottom}`);
      circles.forEach((circle, index) => {
        if (buckets[index]) circle.setAttribute('cy', String(lineY(buckets[index].close)));
      });
      bars.forEach((bar, index) => {
        const bucket = buckets[index];
        if (!bucket) return;
        const value = finite(bucket.change);
        const h = Math.max(value === 0 ? 1 : 2, Math.min(barMaxH * 6, (Math.abs(value) / changeAbs) * barMaxH));
        bar.setAttribute('y', String(value >= 0 ? zeroY - h : zeroY));
        bar.setAttribute('height', String(h));
      });

      leftAxis.innerHTML = axisHtml(lineRange, {
        top: lineTop,
        height: lineBottom - lineTop,
        count: 4,
      });
      rightAxis.innerHTML = axisHtml(changeRange, {
        top: barTop,
        height: barBottom - barTop,
        count: 3,
      });
      thinXAxisLabels(shell, viewport, buckets.length, aggregated.mode, bounds);
    };

    installViewportWatcher(viewport, content, update);
  }

  function installFlow(shell, aggregated) {
    const buckets = aggregated?.buckets || [];
    if (!buckets.length) return;
    const viewport = shell.querySelector('.wealth-unified-viewport');
    const content = shell.querySelector('.wealth-unified-content');
    const svg = shell.querySelector('svg');
    const axis = shell.querySelector('.wealth-unified-axis');
    if (!viewport || !content || !svg || !axis) return;

    const top = 18;
    const bottom = 244;
    const bars = [...svg.querySelectorAll('.wealth-unified-flow-bar')];
    const zeroLine = svg.querySelector('line');
    const valueKeys = Object.keys(buckets.find(bucket => bucket?.values)?.values || {});
    const stacked = shell.dataset.flowStacked === 'true';

    const update = () => {
      const bounds = visibleBounds(viewport, buckets.length);
      const visible = buckets.slice(bounds.start, bounds.end + 1);
      const visibleValues = [];
      visible.forEach(bucket => {
        const values = valueKeys.map(key => finite(bucket.values?.[key]));
        if (stacked) visibleValues.push(values.reduce((sum, value) => sum + Math.max(0, value), 0), values.reduce((sum, value) => sum + Math.min(0, value), 0));
        else valueKeys.forEach(key => visibleValues.push(finite(bucket.values?.[key])));
      });
      const range = paddedRange([0, ...visibleValues], true);
      const y = value => clampY(bottom - ((finite(value) - range.min) / (range.max - range.min)) * (bottom - top));
      const zeroY = y(0);

      bars.forEach((bar, flatIndex) => {
        const bucketIndex = Number(bar.dataset.bucketIndex);
        const bucket = buckets[bucketIndex];
        if (!bucket) return;
        if (stacked) {
          const startY = y(bar.dataset.stackStart), endY = y(bar.dataset.stackEnd);
          bar.setAttribute('y', String(Math.min(startY, endY)));
          bar.setAttribute('height', String(bar.dataset.stackZero === 'true' ? 1 : Math.abs(startY - endY)));
          return;
        }
        const seriesIndex = flatIndex % Math.max(1, valueKeys.length);
        const key = valueKeys[seriesIndex];
        const value = finite(bucket.values?.[key]);
        const py = y(value);
        bar.setAttribute('y', String(Math.min(py, zeroY)));
        bar.setAttribute('height', String(Math.max(value === 0 ? 1 : 2, Math.abs(zeroY - py))));
      });
      if (zeroLine) {
        zeroLine.setAttribute('y1', String(zeroY));
        zeroLine.setAttribute('y2', String(zeroY));
      }
      axis.innerHTML = axisHtml(range, { top, height: bottom - top, count: 5 });
      thinXAxisLabels(shell, viewport, buckets.length, aggregated.mode, bounds);
    };

    installViewportWatcher(viewport, content, update);
  }

  function installViewportWatcher(viewport, content, update) {
    let frame = 0;
    const queue = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    viewport.addEventListener('scroll', queue, { passive: true });
    viewport.addEventListener('wheel', () => requestAnimationFrame(queue), { passive: true });
    window.addEventListener('resize', queue, { passive: true });
    if (typeof ResizeObserver === 'function') {
      const observer = new ResizeObserver(queue);
      observer.observe(viewport);
      observer.observe(content);
    }
    requestAnimationFrame(() => requestAnimationFrame(queue));
  }

  function installShell(shell) {
    if (!shell || installed.has(shell)) return;
    const kind = shell.dataset.unifiedKind;
    const aggregated = registry[kind];
    if (!kind || !aggregated) return;
    installed.add(shell);
    if (kind === 'stock' || kind === 'networth') installState(shell, kind, aggregated);
    else installFlow(shell, aggregated);
  }

  function scan() {
    document.querySelectorAll('.wealth-unified-chart-shell[data-unified-kind]').forEach(installShell);
  }

  wrapAggregators();
  injectStyles();

  const observer = new MutationObserver(scan);
  const start = () => {
    observer.observe(document.body, { childList: true, subtree: true });
    scan();
  };
  if (document.body) start();
  else document.addEventListener('DOMContentLoaded', start, { once: true });

  window.WealthTimeseriesVisibleRange = { scan };
})();
