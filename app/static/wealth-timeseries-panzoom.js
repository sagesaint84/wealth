/* Shared horizontal pan/zoom behavior for Wealth time-series charts. */
(() => {
  'use strict';

  const STYLE_ID = 'wealthTimeseriesPanzoomStyles';
  const VIEWPORT_CLASS = 'wealth-timeseries-viewport';
  const CONTENT_CLASS = 'wealth-timeseries-content';
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
    },
  ];

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .${VIEWPORT_CLASS} {
        position: relative;
        width: 100%;
        max-width: 100%;
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
      .${VIEWPORT_CLASS}[data-panzoom-kind="ledger"] .ledger-trend-chart {
        min-width: 100%;
      }
      @media (max-width: 720px) {
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

  function installResizeHandling(state) {
    let previousClientWidth = state.viewport.clientWidth;
    const onResize = () => {
      const nextClientWidth = state.viewport.clientWidth;
      if (!nextClientWidth || nextClientWidth === previousClientWidth) return;

      if (!previousClientWidth) {
        previousClientWidth = nextClientWidth;
        applyWidth(state);
        scrollToLatest(state);
        return;
      }

      const oldScrollable = Math.max(1, state.viewport.scrollWidth - previousClientWidth);
      const ratio = clamp(state.viewport.scrollLeft / oldScrollable, 0, 1);
      previousClientWidth = nextClientWidth;
      applyWidth(state);
      requestAnimationFrame(() => {
        const nextScrollable = Math.max(0, state.viewport.scrollWidth - nextClientWidth);
        state.viewport.scrollLeft = nextScrollable * ratio;
      });
    };

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(onResize);
      observer.observe(state.viewport);
      state.resizeObserver = observer;
      return;
    }

    window.addEventListener('resize', onResize, { passive: true });
  }

  function enhance(config, target) {
    if (!target || target.dataset.wealthPanzoomEnhanced === '1') return;

    const existingViewport = target.closest(`.${VIEWPORT_CLASS}`);
    const viewport = existingViewport || document.createElement('div');
    if (!existingViewport) {
      target.parentNode.insertBefore(viewport, target);
      viewport.append(target);
    }

    const bounds = getBounds(config, target);
    const state = {
      config,
      target,
      viewport,
      scale: bounds.defaultScale,
      minScale: bounds.minScale,
      maxScale: bounds.maxScale,
      count: bounds.count,
    };

    viewport.classList.add(VIEWPORT_CLASS);
    viewport.dataset.panzoomKind = config.id;
    viewport.setAttribute('role', 'region');
    viewport.setAttribute(
      'aria-label',
      `${config.label}: 마우스 휠로 기간 확대·축소, 드래그 또는 가로 스크롤로 이동`,
    );
    target.classList.add(CONTENT_CLASS);
    target.dataset.wealthPanzoomEnhanced = '1';

    applyWidth(state);
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
