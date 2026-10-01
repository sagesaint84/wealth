/* Non-scaled axis labels and caption spacing for unified Wealth time-series charts. */
(() => {
  'use strict';

  const core = window.WealthTimeseriesPeriodCore;
  if (!core || window.WealthTimeseriesLabelLayout) return;

  const registry = Object.create(null);
  const installed = new WeakSet();
  const STYLE_ID = 'wealthTimeseriesLabelLayoutStyles';
  const VIEWBOX_WIDTH = 1000;
  const PLOT_LEFT = 20;
  const PLOT_RIGHT = 980;

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

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .wealth-unified-content { position: relative; }
      .wealth-unified-content svg text[y="262"],
      .wealth-unified-content svg text[y="280"] { display: none !important; }
      .wealth-timeseries-html-xaxis {
        position: absolute;
        inset: 0;
        pointer-events: none;
        overflow: visible;
        z-index: 3;
        font-variant-numeric: tabular-nums;
      }
      .wealth-timeseries-html-xlabel,
      .wealth-timeseries-html-year {
        position: absolute;
        transform: translateX(-50%);
        white-space: nowrap;
        text-align: center;
        line-height: 1;
        user-select: none;
      }
      .wealth-timeseries-html-xlabel {
        top: 252px;
        color: #9aacd2;
        font-size: 10px;
      }
      .wealth-timeseries-html-year {
        top: 271px;
        color: #6f82ad;
        font-size: 9px;
        font-weight: 700;
      }
      .wealth-unified-chart-shell.wealth-visible-state {
        grid-template-columns: 92px minmax(0, 1fr) 92px !important;
      }
      .wealth-unified-chart-shell.wealth-visible-state > .wealth-unified-axis {
        width: 92px !important;
        min-width: 92px !important;
      }
      .wealth-unified-chart-shell.wealth-visible-state .wealth-unified-axis-caption {
        white-space: nowrap !important;
        max-width: none !important;
        line-height: 1 !important;
        font-size: 8.5px !important;
        padding: 2px 3px;
        border-radius: 4px;
        background: rgba(11, 19, 40, .94);
        z-index: 4;
      }
      .wealth-unified-chart-shell.wealth-visible-state .wealth-unified-axis-right .wealth-unified-axis-caption {
        left: 6px !important;
        right: auto !important;
        transform: translateY(-110%);
      }
      .wealth-unified-chart-shell.wealth-visible-state > .wealth-unified-axis:not(.wealth-unified-axis-right) .wealth-unified-axis-caption {
        right: 6px !important;
      }
      @media (max-width: 720px) {
        .wealth-unified-chart-shell.wealth-visible-state {
          grid-template-columns: 72px minmax(0, 1fr) 72px !important;
        }
        .wealth-unified-chart-shell.wealth-visible-state > .wealth-unified-axis {
          width: 72px !important;
          min-width: 72px !important;
        }
        .wealth-unified-chart-shell.wealth-visible-state .wealth-unified-axis-caption {
          font-size: 7.5px !important;
        }
        .wealth-timeseries-html-xlabel { font-size: 9px; }
      }
    `;
    document.head.appendChild(style);
  }

  function contentWidth(content, viewport) {
    return Math.max(content.getBoundingClientRect().width, viewport.scrollWidth, viewport.clientWidth, 1);
  }

  function bucketCenterPx(width, index, count) {
    const x = PLOT_LEFT + ((PLOT_RIGHT - PLOT_LEFT) * (index + 0.5)) / Math.max(1, count);
    return width * x / VIEWBOX_WIDTH;
  }

  function visibleBounds(viewport, content, count) {
    if (!count) return { start: 0, end: -1 };
    const width = contentWidth(content, viewport);
    const slot = width * (PLOT_RIGHT - PLOT_LEFT) / VIEWBOX_WIDTH / Math.max(1, count);
    const left = viewport.scrollLeft;
    const right = left + Math.max(viewport.clientWidth, 1);
    let start = 0;
    let end = count - 1;
    while (start < count - 1 && bucketCenterPx(width, start, count) + slot / 2 < left) start += 1;
    while (end > start && bucketCenterPx(width, end, count) - slot / 2 > right) end -= 1;
    return { start, end };
  }

  function minimumSpacing(mode) {
    if (mode === '1W') return 76;
    if (mode === '1M') return 68;
    if (mode === '1Y') return 72;
    return 64;
  }

  function selectedIndices(viewport, content, buckets, mode) {
    const count = buckets.length;
    const width = contentWidth(content, viewport);
    const bounds = visibleBounds(viewport, content, count);
    const slot = width * (PLOT_RIGHT - PLOT_LEFT) / VIEWBOX_WIDTH / Math.max(1, count);
    const step = Math.max(1, Math.ceil(minimumSpacing(mode) / Math.max(slot, 1)));
    const selected = [];
    for (let index = bounds.start; index <= bounds.end; index += step) selected.push(index);
    if (selected.length && selected.at(-1) !== bounds.end) {
      const previous = selected.at(-1);
      const gap = bucketCenterPx(width, bounds.end, count) - bucketCenterPx(width, previous, count);
      if (gap >= minimumSpacing(mode) * 0.72) selected.push(bounds.end);
    }
    if (!selected.length && bounds.end >= bounds.start) selected.push(bounds.start);
    return { selected, bounds, width };
  }

  function ensureOverlay(content) {
    let overlay = content.querySelector(':scope > .wealth-timeseries-html-xaxis');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'wealth-timeseries-html-xaxis';
      overlay.setAttribute('aria-hidden', 'true');
      content.appendChild(overlay);
    }
    return overlay;
  }

  function renderLabels(shell, aggregated) {
    const buckets = aggregated?.buckets || [];
    if (!buckets.length) return;
    const viewport = shell.querySelector('.wealth-unified-viewport');
    const content = shell.querySelector('.wealth-unified-content');
    if (!viewport || !content) return;
    const overlay = ensureOverlay(content);

    const update = () => {
      const { selected, bounds, width } = selectedIndices(viewport, content, buckets, aggregated.mode);
      overlay.replaceChildren();
      selected.forEach(index => {
        const bucket = buckets[index];
        if (!bucket) return;
        const center = bucketCenterPx(width, index, buckets.length);
        const label = document.createElement('span');
        label.className = 'wealth-timeseries-html-xlabel';
        label.style.left = `${center}px`;
        label.textContent = bucket.label || '';
        overlay.appendChild(label);

        const showYear = aggregated.mode !== '1Y'
          && (index === bounds.start || bucket.yearMarker);
        if (showYear && bucket.year) {
          const year = document.createElement('span');
          year.className = 'wealth-timeseries-html-year';
          year.style.left = `${center}px`;
          year.textContent = `${bucket.year}년`;
          overlay.appendChild(year);
        }
      });
    };

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
    renderLabels(shell, aggregated);
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

  window.WealthTimeseriesLabelLayout = { scan };
})();
