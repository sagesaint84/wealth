/* Pure donut geometry and presentation. Data policy, DOM and events belong to callers. */
(() => {
  'use strict';

  // Sizes are caller-defined: no filtering, coercion, normalization or clamping here.
  const segments = (items, sizeOf) => {
    let cursor = 0;
    return items.map((item, index) => {
      const start = cursor;
      cursor += sizeOf(item, index);
      return { ...item, start, end: cursor };
    });
  };

  const hitTest = (items, { x, y, innerRadius, outerRadius,
    includeInner = true, includeOuter = true }) => {
    const distance = Math.hypot(x, y);
    if (!Number.isFinite(distance)
      || (includeInner ? distance < innerRadius : distance <= innerRadius)
      || (includeOuter ? distance > outerRadius : distance >= outerRadius)) return null;
    // CSS conic-gradient starts at twelve o'clock and proceeds clockwise.
    const percent = ((Math.atan2(y, x) * 180 / Math.PI + 450) % 360) / 3.6;
    return items.find(item => percent >= item.start && percent < item.end)?.key || null;
  };

  const conicGradient = (items, { activeKey = null, emptyBackground,
    maxEnd = null, inactiveAlpha = '80' }) => {
    const stops = items.map(item => `${item.color}${activeKey && activeKey !== item.key ? inactiveAlpha : ''} ${item.start}% ${maxEnd === null ? item.end : Math.min(item.end, maxEnd)}%`);
    return stops.length ? `conic-gradient(${stops.join(',')})` : emptyBackground;
  };

  // Shared presentation for home and portfolio; callers own ratios and colors.
  const bind = (donut, items, { legend, root = donut, onSelect } = {}) => {
    const rows = [...(legend?.querySelectorAll('[data-donut-key]') || [])];
    const activate = key => {
      const item = items.find(item => item.key === key);
      if (item?.colorKey) donut.dataset.colorKey = item.colorKey;
      else delete donut.dataset.colorKey;
      donut.style.background = conicGradient(items, { activeKey: key, emptyBackground: 'var(--line)' });
      donut.classList.toggle('has-donut-hover', Boolean(key));
      root.classList.toggle('has-donut-hover', Boolean(key));
      rows.forEach(row => row.classList.toggle('is-donut-active', row.dataset.donutKey === key));
    };
    const keyAt = event => {
      const rect = donut.getBoundingClientRect(), outer = Math.min(rect.width, rect.height) / 2;
      const inset = parseFloat(getComputedStyle(donut, '::after').top);
      return hitTest(items, { x: event.clientX - rect.left - rect.width / 2,
        y: event.clientY - rect.top - rect.height / 2,
        innerRadius: Math.max(0, outer - (Number.isFinite(inset) ? inset : 24)), outerRadius: outer });
    };
    const select = key => { const item = items.find(item => item.key === key); if (item) onSelect?.(item); };
    donut.onpointermove = event => activate(keyAt(event));
    donut.onpointerleave = () => activate(null);
    donut.onclick = event => select(keyAt(event));
    rows.forEach(row => {
      row.onpointerenter = row.onfocus = () => activate(row.dataset.donutKey);
      row.onpointerleave = row.onblur = () => activate(null);
      row.onkeydown = event => {
        if (onSelect && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault(); select(row.dataset.donutKey);
        }
      };
    });
    activate(null);
  };

  window.WealthDonutChart = Object.freeze({ segments, hitTest, conicGradient, bind });
  // Retain the hit-test compatibility entry point used by existing callers.
  window.WealthDonutHitTest = hitTest;
})();
