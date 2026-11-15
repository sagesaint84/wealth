/* Heatmap card DOM presentation, selectively integrated from the existing M100 View. */
(() => {
  'use strict';

  function create({ document, $, html }) {
    function renderCardMode(container, cards, onCardSelect) {
      if (!container) return;

      container.style.height = "auto";
      container.style.position = "static";

      const grid = document.createElement("div");
      grid.className = "heatmap-cards-grid";

      cards.forEach((cardData) => {
        const card = document.createElement("div");
        card.className = "heatmap-card-item";
        card.setAttribute("role", "button");
        card.tabIndex = 0;
        card.setAttribute("aria-label", `${cardData.name} 보유종목 보기`);
        card.style.cssText = `background-color:${cardData.backgroundColor};border:1px solid rgba(255,255,255,0.16);cursor:pointer;padding:12px 14px;border-radius:10px;transition:all 0.16s ease;box-shadow:0 2px 6px rgba(0,0,0,0.25);`;

        const heading = document.createElement("div");
        heading.style.cssText = "display:flex;justify-content:space-between;align-items:flex-start;gap:8px;";
        const name = document.createElement("strong");
        name.style.cssText = "font-size:13.5px;font-weight:700;color:#ffffff;text-shadow:0 1px 3px rgba(0,0,0,0.55);";
        name.textContent = cardData.name == null ? "" : String(cardData.name);
        const weight = document.createElement("span");
        weight.style.cssText = "font-size:11.5px;color:rgba(255,255,255,0.8);font-weight:600;";
        weight.textContent = cardData.weightText;
        heading.append(name, weight);

        const details = document.createElement("div");
        details.style.cssText = "display:flex;justify-content:space-between;align-items:baseline;margin-top:8px;";
        const value = document.createElement("small");
        value.style.cssText = "font-size:11.5px;color:rgba(255,255,255,0.85);";
        value.textContent = cardData.valueText;
        const rate = document.createElement("b");
        rate.style.cssText = "font-size:14px;font-weight:800;color:#ffffff;text-shadow:0 1px 4px rgba(0,0,0,0.7);";
        rate.textContent = cardData.rateText;
        details.append(value, rate);

        card.append(heading, details);
        card.addEventListener("click", () => onCardSelect(cardData.name));
        card.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          onCardSelect(cardData.name);
        });
        grid.appendChild(card);
      });

      container.textContent = "";
      container.appendChild(grid);
    }

function renderLegend({ cap, theme, maxCap, periodLabel }) {
  const legLeft = $("#legendCapLeft");
  const legRight = $("#legendCapRight");
  const legBar = $("#legendBar");
  const legText = $("#legendText");
  const tipNote = $("#heatmapTipNote");
  const capSel = document.getElementById("heatmapCapSelect");

  if (capSel) {
    const autoOpt = capSel.querySelector("option[value='auto']");
    if (autoOpt) autoOpt.textContent = `범위: 자동 (±${cap}%)`;
    if (maxCap && capSel.value !== maxCap) capSel.value = maxCap;
  }

  if (legLeft) legLeft.textContent = `-${cap}%`;
  if (legRight) legRight.textContent = `+${cap}%`;
  if (legBar) legBar.className = `legend-bar theme-${theme}`;
  if (legText) {
    if (theme === "us") legText.textContent = "하락(Red) ← 0 → 상승(Green)";
    else if (theme === "neon") legText.textContent = "하락(Cyan) ← 0 → 상승(Violet)";
    else legText.textContent = "하락(Blue) ← 0 → 상승(Red)";
  }
  if (tipNote) tipNote.textContent = `면적 = 포지션 규모 · 색 = ${periodLabel} 손익률 (범위 ±${cap}%) · 선택하면 보유종목 탭에서 검색`;
}

function renderTreemap(container, tiles, height) {
  if (!tiles.length) {
    container.innerHTML = '<div class="empty">평가금액이 있는 보유종목이 없습니다.</div>';
    return;
  }
  container.style.position = "relative";
  container.style.height = height + "px";
  container.innerHTML = tiles.map((tile) => {
    const { isTiny, isSmall, isMed, rateText } = tile;
    let inner = "";
    if (isTiny) {
      inner = `<span class="tile-tiny-dot"></span>`;
    } else if (isSmall) {
      inner = `<span class="tile-name small">${html(tile.name)}</span><span class="tile-rate small">${rateText}</span>`;
    } else if (isMed) {
      inner = `<strong class="tile-name med">${html(tile.name)}</strong><span class="tile-rate med">${rateText}</span>`;
    } else {
      inner = `<strong class="tile-name">${html(tile.name)}</strong><span class="tile-rate">${rateText}</span>`;
    }


    return `<div class="heatmap-tile" role="button" tabindex="0" aria-label="${html(tile.name)} 보유종목 보기" data-symbol="${html(tile.name)}" data-info="${tile.infoStr}" style="left:${tile.left}px;top:${tile.top}px;width:${tile.width}px;height:${tile.height}px;background-color:${tile.color};"><div class="heatmap-tile-inner">${inner}</div></div>`;
  }).join("");
}

function renderTooltip(tooltipEl, display, position) {
  if (!display) {
    tooltipEl.style.display = "none";
    return;
  }
  tooltipEl.innerHTML = `
        <div class="heatmap-tooltip-title">
          <strong>${html(display.name)}</strong>
          <span>${html(display.code)} · ${html(display.market)}</span>
        </div>
        <div class="heatmap-tooltip-row">
          <span class="label">포지션 규모:</span>
          <span class="val">${html(display.valueText)} (${html(display.weightText)}%)</span>
        </div>
        <div class="heatmap-tooltip-row">
          <span class="label">${html(display.periodLabel)}:</span>
          <span class="val" style="color:${display.rateColor};font-weight:700;">${display.sign}${html(display.selectedRateText)}%</span>
        </div>
        <div class="heatmap-tooltip-row">
          <span class="label">누적 수익률:</span>
          <span class="val" style="color:${display.totalRateColor};font-weight:700;">${display.totalSign}${html(display.totalRateText)}% (${display.profitSign}${html(display.profitText)})</span>
        </div>
      `;
  tooltipEl.style.display = "block";
  tooltipEl.style.left = position.left;
  tooltipEl.style.top = position.top;
}

    return { renderCardMode, renderLegend, renderTreemap, renderTooltip };
  }

  window.WealthHeatmapView = { create };
})();
