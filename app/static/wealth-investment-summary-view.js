(() => {
  "use strict";

  function create({ $, money, number }) {
    function renderCurrency({ currency, marketValue, stockValue, cash }) {
      const prefix = currency.toLowerCase();
      const value = $(`#${prefix}Value`);
      if (value) value.textContent = money(marketValue, currency);
      const caption = $(`#${prefix}Caption`);
      if (caption) caption.textContent = `주식 평가 ${money(stockValue, currency)}`;
      const cashBadge = $(`#${prefix}CashBadge`);
      if (cashBadge) cashBadge.textContent = `(예수금 ${money(cash, currency)})`;
    }

    function renderDailyPnl({ profit, rate, partial, date }) {
      const profitEl = $("#dayProfitVal");
      if (profitEl) {
        profitEl.title = '당일 가격변동 손익 ÷ 총 주식자산';
        if (profit === null) {
          profitEl.textContent = '일 수익 — (—)';
          profitEl.style.color = "#94a3b8";
        } else {
          const rateText = rate === null ? '—' : `${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%`;
          const sign = profit >= 0 ? "+" : "";
          const note = partial ? ' · 일부 종목 기준 없음' : '';
          profitEl.textContent = `일 수익 ${sign}${money(profit)} (${rateText})${note}`;
          profitEl.style.color = profit >= 0 ? "#f43f5e" : "#38bdf8";
        }
      }
      const caption = $("#dayCaption");
      if (caption) {
        caption.textContent = date ? `${date} 기록 기준` : '기록 기준 없음';
        caption.title = '일 수익은 시장 session 가격변동 손익이며 전 기록 대비 평가액 변화와 다릅니다.';
      }
    }

    return Object.freeze({ renderCurrency, renderDailyPnl });
  }
  window.WealthInvestmentSummaryView = Object.freeze({ create });
})();
