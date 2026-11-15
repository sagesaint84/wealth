/* Pure heatmap presentation model. Copied calculations retain their original contracts. */
(() => {
  'use strict';

const PERIOD_CAPS = {
  "1D": 10,
  "1W": 15,
  "1M": 20,
  "YTD": 50,
  "1Y": 50,
  "TOTAL": 30,
};

function getEffectiveCap(period, capSetting, items = []) {
  if (capSetting && capSetting !== "auto" && !isNaN(Number(capSetting)) && Number(capSetting) > 0) {
    return Number(capSetting);
  }

  if (items && items.length > 0) {
    let maxAbs = 0;
    items.forEach((it) => {
      let r = 0;
      const periodRates = it.period_changes || {};
      if (period === "TOTAL") {
        r = Math.abs(Number(it.rate != null ? it.rate : (it.return_rate || 0)));
      } else if (periodRates[period] != null) {
        r = Math.abs(Number(periodRates[period]));
      } else if (period === "1D") {
        r = Math.abs(Number(it.day_change_rate || 0));
      } else {
        r = Math.abs(Number(it.rate || it.day_change_rate || 0));
      }
      if (!isNaN(r) && r > maxAbs) maxAbs = r;
    });

    if (maxAbs > 0) {
      let cap = Math.ceil(maxAbs);
      if (cap < 3) cap = 3;
      else if (cap <= 25) cap = Math.ceil(maxAbs);
      else if (cap <= 60) cap = Math.ceil(cap / 5) * 5;
      else cap = Math.ceil(cap / 10) * 10;
      return Math.min(200, cap);
    }
  }

  return PERIOD_CAPS[period] || 15;
}

function getHeatmapColor(rate, maxRate = 15, theme = "kr") {
  const clamped = Math.max(-maxRate, Math.min(maxRate, rate));
  const t = Math.pow(Math.abs(clamped) / maxRate, 0.72);

  if (theme === "us") {
    if (clamped >= 0) {
      const r = Math.round(25 + (16 - 25) * t);
      const g = Math.round(45 + (190 - 45) * t);
      const b = Math.round(38 + (120 - 38) * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const r = Math.round(48 + (235 - 48) * t);
      const g = Math.round(30 + (55 - 30) * t);
      const b = Math.round(38 + (55 - 38) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  } else if (theme === "neon") {
    if (clamped >= 0) {
      const r = Math.round(40 + (170 - 40) * t);
      const g = Math.round(28 + (80 - 28) * t);
      const b = Math.round(62 + (250 - 62) * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const r = Math.round(20 + (8 - 20) * t);
      const g = Math.round(42 + (190 - 42) * t);
      const b = Math.round(60 + (220 - 60) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  } else {
    if (clamped >= 0) {
      const r = Math.round(48 + (238 - 48) * t);
      const g = Math.round(40 + (42 - 40) * t);
      const b = Math.round(52 + (68 - 52) * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const r = Math.round(35 + (35 - 35) * t);
      const g = Math.round(45 + (95 - 45) * t);
      const b = Math.round(58 + (238 - 58) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  }
}

function squarify(items, x, y, width, height) {
  if (!items.length) return [];
  const totalVal = items.reduce((s, it) => s + it.value, 0);
  if (totalVal <= 0) return [];
  const rects = [];
  const sorted = [...items].sort((a, b) => b.value - a.value);

  function layout(children, rect) {
    if (!children.length) return;
    if (children.length === 1) {
      rects.push({ ...children[0], x: rect.x, y: rect.y, w: rect.w, h: rect.h });
      return;
    }
    const isHoriz = rect.w < rect.h;
    const side = isHoriz ? rect.w : rect.h;
    let row = [];
    let rowSum = 0;
    let bestWorst = Infinity;

    for (let i = 0; i < children.length; i++) {
      const nextRow = [...row, children[i]];
      const nextSum = rowSum + children[i].value;
      const curWorst = worst(nextRow, nextSum, side, rect.total, rect.w * rect.h);
      if (row.length === 0 || curWorst <= bestWorst) {
        row = nextRow;
        rowSum = nextSum;
        bestWorst = curWorst;
      } else {
        const remaining = children.slice(i);
        const frac = rowSum / rect.total;
        if (isHoriz) {
          const rowH = rect.h * frac;
          layoutRow(row, { x: rect.x, y: rect.y, w: rect.w, h: rowH }, isHoriz);
          layout(remaining, { x: rect.x, y: rect.y + rowH, w: rect.w, h: rect.h - rowH, total: rect.total - rowSum });
        } else {
          const rowW = rect.w * frac;
          layoutRow(row, { x: rect.x, y: rect.y, w: rowW, h: rect.h }, isHoriz);
          layout(remaining, { x: rect.x + rowW, y: rect.y, w: rect.w - rowW, h: rect.h, total: rect.total - rowSum });
        }
        return;
      }
    }
    layoutRow(row, rect, isHoriz);
  }

  function worst(row, s, side, total, totalArea) {
    if (!row.length || s === 0 || side === 0) return Infinity;
    const rowArea = (s / total) * totalArea;
    const otherSide = rowArea / side;
    if (otherSide === 0) return Infinity;
    let maxRatio = 0;
    for (const item of row) {
      const itemArea = (item.value / total) * totalArea;
      const itemLen = itemArea / otherSide;
      if (itemLen === 0) return Infinity;
      const ratio = Math.max(itemLen / otherSide, otherSide / itemLen);
      if (ratio > maxRatio) maxRatio = ratio;
    }
    return maxRatio;
  }

  function layoutRow(row, rect, isHoriz) {
    if (!row.length) return;
    let offset = isHoriz ? rect.x : rect.y;
    const totalRowVal = row.reduce((s, it) => s + it.value, 0);
    for (const item of row) {
      const frac = totalRowVal > 0 ? item.value / totalRowVal : 1 / row.length;
      if (isHoriz) {
        const w = rect.w * frac;
        rects.push({ ...item, x: offset, y: rect.y, w, h: rect.h });
        offset += w;
      } else {
        const h = rect.h * frac;
        rects.push({ ...item, x: rect.x, y: offset, w: rect.w, h });
        offset += h;
      }
    }
  }

  layout(sorted, { x, y, w: width, h: height, total: totalVal });
  return rects;
}

  window.WealthHeatmapModel = Object.freeze({ PERIOD_CAPS, getEffectiveCap, getHeatmapColor, squarify });
})();
