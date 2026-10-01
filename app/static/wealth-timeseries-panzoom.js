/* Shared horizontal pan/zoom behavior and fixed amount axes for Wealth time-series charts. */
(() => {
  'use strict';

  const STYLE_ID = 'wealthTimeseriesPanzoomStyles';
  const SHELL_CLASS = 'wealth-timeseries-shell';
  const VIEWPORT_CLASS = 'wealth-timeseries-viewport';
  const CONTENT_CLASS = 'wealth-timeseries-content';
  const AXIS_CLASS = 'wealth-timeseries-axis';
  const ZOOM_STEP = 1.16;

  const configs = [
    {
      id: 'ledger',
      root: '#ledgerTrendContainer',
      target: '.ledger-trend-chart',
      count(target) {
        return target.querySelectorAll('.ledger-trend-col').length;
      },
      defaultVisible: 6,
      minVisible: 3,
      label: '가계부 현금흐름 추이',
      axisRange: ledgerAxisRange,
      axisGeometry(target) {
        return { top: 15, bottom: Math.max(24, target.clientHeight * 0.14) };
      },
      constrainRoot: true,
    },
    {
      id: 'stock-records',
      root: '#recordsPanel',
      target: 'svg.record-chart',
      count(target) {
        const circles = target.querySelectorAll('circle').length;
        if (circles) return circles;
        return target.querySelectorAll('rect').length;
      },
      defaultVisible: 16,
      minVisible: 5,
      label: '주식기록 추이',
      axisRange: stockAxisRange,
      axisGeometry: stockAxisGeometry,
    },
    {
      id: 'net-worth',
      root: '#wealthHistoryPlot',
      target: 'svg.wealth-history-chart',
      count(target) {
        return target.querySelectorAll('.wealth-history-point').length;
      },
      defaultVisible: 16,
      minVisible: 5,
      label: '순자산 추이',
      axisRange: netWorthAxisRange,
      axisGeometry(target) {
        return geometryFromViewBox(target, 48, 137, 250);
      },
    },
  ];

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .${SHELL_CLASS} {
        display: grid;
        grid-template-columns: 68px minmax(0, 1fr);
        align-items: start;
        gap: 8px;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        overflow: hidden;
      }
      .${VIEWPORT_CLASS} {
        position: relative;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        overflow-x: auto;
        overflow-y: hidden;
        overscroll-behavior-x: contain;
        scrollbar-gutter: stable;
        scrollbar-width: thin;
        scrollbar-color: #42547d #111a33;
        touch-action: pan-x pan-y;
        cursor: grab;
        -webkit-overflow-scrolling: touch;
      }
      .${VIEWPORT_CLASS}.is-dragging {
        cursor: grabbing;
        user-select: none;
      }
      .${VIEWPORT_CLASS}::-webkit-scrollbar {
        height: 9px;
      }
      .${VIEWPORT_CLASS}::-webkit-scrollbar-track {
        background: #111a33;
        border-radius: 999px;
      }
      .${VIEWPORT_CLASS}::-webkit-scrollbar-thumb {
        background: #42547d;
        border: 2px solid #111a33;
        border-radius: 999px;
      }
      .${VIEWPORT_CLASS}::-webkit-scrollbar-thumb:hover {
        background: #6076a8;
      }
      .${CONTENT_CLASS} {
        max-width: none !important;
        flex: 0 0 auto;
      }
      .${AXIS_CLASS} {
        position: relative;
        width: 68px;
        min-width: 68px;
        color: #8291b4;
        font-size: 10px;
        font-variant-numeric: tabular-nums;
        line-height: 1;
        user-select: none;
        pointer-events: none;
      }
      .${AXIS_CLASS}.is-empty {
        visibility: hidden;
      }
      .${AXIS_CLASS}-line {
        position: absolute;
        right: 0;
        border-right: 1px solid rgba(130, 145, 180, 0.28);
      }
      .${AXIS_CLASS}-ticks {
        position: absolute;
        left: 0;
        right: 5px;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        justify-content: space-between;
      }
      .${AXIS_CLASS}-tick {
        position: relative;
        white-space: nowrap;
        transform: translateY(-50%);
      }
      .${AXIS_CLASS}-tick:last-child {
        transform: translateY(50%);
      }
      .${AXIS_CLASS}-tick::after {
        content: '';
        position: absolute;
        right: -6px;
        top: 50%;
        width: 4px;
        border-top: 1px solid rgba(130, 145, 180, 0.34);
      }
      #ledgerTrendContainer {
        min-width: 0 !important;
        max-width: 100% !important;
        overflow: hidden;
      }
      #ledgerTrendContainer .${SHELL_CLASS},
      #ledgerTrendContainer .${VIEWPORT_CLASS} {
        min-width: 0 !important;
        max-width: 100% !important;
      }
      .${VIEWPORT_CLASS}[data-panzoom-kind="ledger"] .ledger-trend-chart {
        min-width: 100%;
      }
      @media (max-width: 720px) {
        .${SHELL_CLASS} {
          grid-template-columns: 58px minmax(0, 1fr);
          gap: 6px;
        }
        .${AXIS_CLASS} {
          width: 58px;
          min-width: 58px;
          font-size: 9px;
        }
        .${VIEWPORT_CLASS}::-webkit-scrollbar { height: 6px; }
      }
    `;
    document.head.append(style);
  }

  function getBounds(config, target) {
    const count = Math.max(1, Number(config.count(target)) || 1);
    const defaultVisible = Math.max(config.minVisible, config.defaultVisible);
    const maxScale = Math.max(1, count / Math.max(1, config.minVisible));
    return {
      count,
      minScale: 1,
      maxScale,
      defaultScale: clamp(count / defaultVisible, 1, maxScale),
    };
  }

  function contentWidth(viewport, scale) {
    return Math.max(1, viewport.clientWidth) * scale;
  }

  function applyWidth(state) {
    const width = contentWidth(state.viewport, state.scale);
    state.target.style.width = `${width}px`;
    state.target.style.minWidth = `${width}px`;
  }

  function scrollToLatest(state) {
    requestAnimationFrame(() => {
      state.viewport.scrollLeft = Math.max(0, state.viewport.scrollWidth - state.viewport.clientWidth);
    });
  }

  function setScale(state, nextScale, anchorClientX = null) {
    const oldScale = state.scale;
    const clamped = clamp(nextScale, state.minScale, state.maxScale);
    if (Math.abs(clamped - oldScale) < 0.0001) return false;

    const viewport = state.viewport;
    const rect = viewport.getBoundingClientRect();
    const anchorX = anchorClientX == null
      ? viewport.clientWidth / 2
      : clamp(anchorClientX - rect.left, 0, viewport.clientWidth);
    const oldWidth = Math.max(viewport.scrollWidth, contentWidth(viewport, oldScale));
    const logicalRatio = oldWidth > 0
      ? clamp((viewport.scrollLeft + anchorX) / oldWidth, 0, 1)
      : 1;

    state.scale = clamped;
    applyWidth(state);

    const newWidth = contentWidth(viewport, state.scale);
    viewport.scrollLeft = clamp(
      logicalRatio * newWidth - anchorX,
      0,
      Math.max(0, newWidth - viewport.clientWidth),
    );
    return true;
  }

  function installWheelZoom(state) {
    state.viewport.addEventListener('wheel', event => {
      if (Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
      const factor = event.deltaY < 0 ? ZOOM_STEP : (1 / ZOOM_STEP);
      const changed = setScale(state, state.scale * factor, event.clientX);
      // Only consume the wheel while a zoom actually occurs. At a zoom boundary
      // the browser keeps its normal vertical page scrolling behavior.
      if (changed) event.preventDefault();
    }, { passive: false });
  }

  function installMouseDrag(state) {
    let pointerId = null;
    let startX = 0;
    let startScrollLeft = 0;
    let dragged = false;

    state.viewport.addEventListener('pointerdown', event => {
      if (event.pointerType !== 'mouse' || event.button !== 0) return;
      if (event.target.closest('button, a, input, select, textarea')) return;
      pointerId = event.pointerId;
      startX = event.clientX;
      startScrollLeft = state.viewport.scrollLeft;
      dragged = false;
      state.viewport.classList.add('is-dragging');
      state.viewport.setPointerCapture?.(pointerId);
    });

    state.viewport.addEventListener('pointermove', event => {
      if (pointerId == null || event.pointerId !== pointerId) return;
      const delta = event.clientX - startX;
      if (Math.abs(delta) > 3) dragged = true;
      if (!dragged) return;
      state.viewport.scrollLeft = startScrollLeft - delta;
      event.preventDefault();
    });

    const stop = event => {
      if (pointerId == null || (event.pointerId != null && event.pointerId !== pointerId)) return;
      try { state.viewport.releasePointerCapture?.(pointerId); } catch (_) {}
      pointerId = null;
      state.viewport.classList.remove('is-dragging');
    };
    state.viewport.addEventListener('pointerup', stop);
    state.viewport.addEventListener('pointercancel', stop);
  }

  function touchDistance(touches) {
    if (!touches || touches.length < 2) return 0;
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.hypot(dx, dy);
  }

  function touchCenterX(touches) {
    return (touches[0].clientX + touches[1].clientX) / 2;
  }

  function installPinchZoom(state) {
    let pinchStartDistance = 0;
    let pinchStartScale = state.scale;

    state.viewport.addEventListener('touchstart', event => {
      if (event.touches.length !== 2) return;
      pinchStartDistance = touchDistance(event.touches);
      pinchStartScale = state.scale;
      if (pinchStartDistance > 0) event.preventDefault();
    }, { passive: false });

    state.viewport.addEventListener('touchmove', event => {
      if (event.touches.length !== 2 || pinchStartDistance <= 0) return;
      const distance = touchDistance(event.touches);
      if (distance <= 0) return;
      const ratio = distance / pinchStartDistance;
      setScale(state, pinchStartScale * ratio, touchCenterX(event.touches));
      event.preventDefault();
    }, { passive: false });

    const reset = event => {
      if (event.touches && event.touches.length >= 2) return;
      pinchStartDistance = 0;
      pinchStartScale = state.scale;
    };
    state.viewport.addEventListener('touchend', reset, { passive: true });
    state.viewport.addEventListener('touchcancel', reset, { passive: true });
  }

  function extractWonNumbers(text) {
    const values = [];
    const source = String(text || '');
    const patterns = [
      /₩\s*([+-]?[\d,.]+)/g,
      /([+-]?[\d,.]+)\s*원/g,
    ];
    for (const pattern of patterns) {
      let match;
      while ((match = pattern.exec(source))) {
        const value = Number(String(match[1]).replace(/,/g, ''));
        if (Number.isFinite(value)) values.push(value);
      }
    }
    return values;
  }

  function normalizedRange(min, max, { zeroFloor = false } = {}) {
    let lo = Number(min);
    let hi = Number(max);
    if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
    if (lo > hi) [lo, hi] = [hi, lo];
    if (zeroFloor) lo = 0;
    if (lo === hi) {
      if (hi === 0) return { min: 0, max: 1 };
      const pad = Math.max(Math.abs(hi) * 0.05, 1);
      lo = zeroFloor ? 0 : lo - pad;
      hi += pad;
    }
    return { min: lo, max: hi };
  }

  function ledgerAxisRange(target) {
    const values = [];
    target.querySelectorAll('.ledger-bar-inc[title], .ledger-bar-exp[title]').forEach(node => {
      const first = extractWonNumbers(node.getAttribute('title'))[0];
      if (Number.isFinite(first)) values.push(first);
    });
    if (!values.length) return { min: 0, max: 100000 };
    return normalizedRange(0, Math.max(100000, ...values), { zeroFloor: true });
  }

  function stockAxisRange(target) {
    const wrap = target.closest('.record-chart-wrap') || target.parentElement;
    const summary = wrap?.querySelector('.record-chart-meta div:nth-child(3) strong');
    const summaryValues = extractWonNumbers(summary?.textContent || '');
    if (summaryValues.length >= 2) {
      let lo = Math.min(...summaryValues);
      const hi = Math.max(...summaryValues);
      if (target.getAttribute('aria-label') !== '자산 기록 콤보 차트') lo *= 0.8;
      return normalizedRange(lo, hi);
    }

    const values = [];
    target.querySelectorAll('circle title, .monthly-bar-group rect title').forEach(node => {
      const first = extractWonNumbers(node.textContent)[0];
      if (Number.isFinite(first)) values.push(first);
    });
    if (!values.length) return null;
    return normalizedRange(Math.min(...values), Math.max(...values));
  }

  function netWorthAxisRange(target) {
    const values = [];
    target.querySelectorAll('.wealth-history-point circle title').forEach(node => {
      const first = extractWonNumbers(node.textContent)[0];
      if (Number.isFinite(first)) values.push(first);
    });
    if (!values.length) return null;
    return normalizedRange(Math.min(...values), Math.max(...values));
  }

  function geometryFromViewBox(target, plotTop, plotBottom, fallbackHeight) {
    const viewBox = target.viewBox?.baseVal;
    const logicalHeight = Number(viewBox?.height) || fallbackHeight;
    const renderedHeight = target.clientHeight || fallbackHeight;
    const ratio = renderedHeight / logicalHeight;
    return {
      top: plotTop * ratio,
      bottom: Math.max(0, (logicalHeight - plotBottom) * ratio),
    };
  }

  function stockAxisGeometry(target) {
    if (target.getAttribute('aria-label') === '자산 기록 콤보 차트') {
      return geometryFromViewBox(target, 24, 160, 280);
    }
    return geometryFromViewBox(target, 0, 180, 260);
  }

  function trimDecimal(value) {
    const rounded = Math.abs(value) >= 100 ? value.toFixed(0) : value.toFixed(1);
    return rounded.replace(/\.0$/, '');
  }

  function formatWonAxis(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '';
    const sign = amount < 0 ? '-' : '';
    const abs = Math.abs(amount);
    if (abs >= 1_000_000_000_000) return `${sign}₩${trimDecimal(abs / 1_000_000_000_000)}조`;
    if (abs >= 100_000_000) return `${sign}₩${trimDecimal(abs / 100_000_000)}억`;
    if (abs >= 10_000) return `${sign}₩${trimDecimal(abs / 10_000)}만`;
    return `${sign}₩${Math.round(abs).toLocaleString('ko-KR')}`;
  }

  function axisTickValues(range, count = 4) {
    if (!range) return [];
    const ticks = [];
    for (let i = 0; i < count; i += 1) {
      const ratio = i / Math.max(1, count - 1);
      ticks.push(range.max - (range.max - range.min) * ratio);
    }
    return ticks;
  }

  function renderAxis(state) {
    const range = state.config.axisRange?.(state.target) || null;
    const geometry = state.config.axisGeometry?.(state.target) || { top: 0, bottom: 0 };
    const height = Math.max(1, state.target.clientHeight || state.target.getBoundingClientRect().height || 1);
    const top = clamp(Number(geometry.top) || 0, 0, height);
    const bottom = clamp(Number(geometry.bottom) || 0, 0, Math.max(0, height - top));
    const axis = state.axis;

    axis.style.height = `${height}px`;
    axis.classList.toggle('is-empty', !range);
    if (!range) {
      axis.replaceChildren();
      return;
    }

    const ticks = axisTickValues(range);
    axis.innerHTML = `
      <div class="${AXIS_CLASS}-line" style="top:${top}px;bottom:${bottom}px"></div>
      <div class="${AXIS_CLASS}-ticks" style="top:${top}px;bottom:${bottom}px">
        ${ticks.map(value => `<span class="${AXIS_CLASS}-tick">${formatWonAxis(value)}</span>`).join('')}
      </div>
    `;
    axis.setAttribute('aria-label', `${state.config.label} 금액 축 ${formatWonAxis(range.min)} ~ ${formatWonAxis(range.max)}`);
  }

  function installResizeHandling(state) {
    let previousClientWidth = state.viewport.clientWidth;
    const handleResize = () => {
      const nextClientWidth = state.viewport.clientWidth;
      renderAxis(state);
      if (!nextClientWidth) return;
      if (!previousClientWidth) {
        previousClientWidth = nextClientWidth;
        applyWidth(state);
        renderAxis(state);
        scrollToLatest(state);
        return;
      }
      if (nextClientWidth === previousClientWidth) return;
      const oldScrollable = Math.max(1, state.viewport.scrollWidth - previousClientWidth);
      const ratio = clamp(state.viewport.scrollLeft / oldScrollable, 0, 1);
      previousClientWidth = nextClientWidth;
      applyWidth(state);
      requestAnimationFrame(() => {
        const nextScrollable = Math.max(0, state.viewport.scrollWidth - nextClientWidth);
        state.viewport.scrollLeft = nextScrollable * ratio;
      });
    };

    if (typeof ResizeObserver === 'function') {
      const observer = new ResizeObserver(handleResize);
      observer.observe(state.viewport);
      observer.observe(state.target);
      state.resizeObserver = observer;
    } else {
      window.addEventListener('resize', handleResize, { passive: true });
      state.windowResizeHandler = handleResize;
    }
  }

  function enhance(config, target) {
    if (!target || target.dataset.wealthPanzoomEnhanced === '1') return;

    const root = document.querySelector(config.root);
    if (config.constrainRoot && root) {
      root.style.minWidth = '0';
      root.style.maxWidth = '100%';
      if (root.parentElement) root.parentElement.style.minWidth = '0';
    }

    const shell = document.createElement('div');
    const axis = document.createElement('div');
    const viewport = document.createElement('div');
    shell.className = SHELL_CLASS;
    axis.className = AXIS_CLASS;
    viewport.className = VIEWPORT_CLASS;

    target.parentNode.insertBefore(shell, target);
    shell.append(axis, viewport);
    viewport.append(target);

    const bounds = getBounds(config, target);
    const state = {
      config,
      target,
      shell,
      axis,
      viewport,
      scale: bounds.defaultScale,
      minScale: bounds.minScale,
      maxScale: bounds.maxScale,
      count: bounds.count,
    };

    viewport.dataset.panzoomKind = config.id;
    viewport.setAttribute('role', 'region');
    viewport.setAttribute(
      'aria-label',
      `${config.label}: 마우스 휠로 기간 확대·축소, 드래그 또는 가로 스크롤로 이동`,
    );
    target.classList.add(CONTENT_CLASS);
    target.dataset.wealthPanzoomEnhanced = '1';

    applyWidth(state);
    renderAxis(state);
    installWheelZoom(state);
    installMouseDrag(state);
    installPinchZoom(state);
    installResizeHandling(state);
    scrollToLatest(state);
  }

  function scan() {
    for (const config of configs) {
      const root = document.querySelector(config.root);
      if (!root) continue;
      const targets = root.matches(config.target)
        ? [root]
        : [...root.querySelectorAll(config.target)];
      targets.forEach(target => enhance(config, target));
    }
  }

  let scanQueued = false;
  function queueScan() {
    if (scanQueued) return;
    scanQueued = true;
    queueMicrotask(() => {
      scanQueued = false;
      scan();
    });
  }

  injectStyles();
  scan();

  const observer = new MutationObserver(queueScan);
  observer.observe(document.body, { childList: true, subtree: true });
  window.addEventListener('wealth:timeseries-refresh', queueScan);
})();
