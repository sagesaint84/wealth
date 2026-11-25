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

    function renderRealizedPnlCaption(realizedView) {
      const summaryPnlSubEl = $("#summaryRealizedPnlSub");
      if (summaryPnlSubEl) {
        summaryPnlSubEl.textContent = `승률 ${number(realizedView.winRate, 1)}% · 총 ${realizedView.recordCount}건 실현${realizedView.completenessNote ? ` · ${realizedView.completenessNote}` : ''}`;
      }
    }

    function renderSummary({
      s, totalStockVal, krwStockVal, krwStockProfit, krwStockReturnRate, krwHoldingCount,
      usdStockValKrw, usdStockValUsd, usdStockProfitKrw, usdStockReturnRate, usdHoldingCount,
      realizedView, totalRealizedKrw, yearRealizedKrw, monthRealizedKrw,
      totalActualDivKrw, yearActualDivKrw, monthActualDivKrw, currYear2Digit, currMonthStr,
      dailyPnl, krwCurrency, usdCurrency, updatedAt,
    }) {
      renderRealizedPnlCaption(realizedView);

      // 2. 총 주식자산
      if ($("#totalInvestRow")) $("#totalInvestRow").style.display = "flex";
      if ($("#totalInvestLabelText")) $("#totalInvestLabelText").textContent = "총 주식자산";
      if ($("#totalValue")) $("#totalValue").textContent = money(totalStockVal);

      // 2-1. 원화 주식 카드 표시
      if ($("#krwStockRow")) $("#krwStockRow").style.display = "flex";
      if ($("#summaryKrwStockVal")) $("#summaryKrwStockVal").textContent = money(krwStockVal);
      if ($("#summaryKrwStockProfit")) {
        const kSign = krwStockProfit >= 0 ? "+" : "";
        const krSign = krwStockReturnRate >= 0 ? "+" : "";
        $("#summaryKrwStockProfit").textContent = `${kSign}${money(krwStockProfit)} (${krSign}${number(krwStockReturnRate, 2)}%)`;
        $("#summaryKrwStockProfit").style.color = krwStockProfit >= 0 ? "#f43f5e" : "#38bdf8";
      }
      if ($("#summaryKrwStockCount")) {
        $("#summaryKrwStockCount").textContent = `${krwHoldingCount}개 종목`;
      }

      // 2-2. 달러 주식 카드 표시
      if ($("#usdStockRow")) $("#usdStockRow").style.display = "flex";
      if ($("#summaryUsdStockValKrw")) $("#summaryUsdStockValKrw").textContent = money(usdStockValKrw);
      if ($("#summaryUsdStockValUsd")) {
        $("#summaryUsdStockValUsd").textContent = `$${number(usdStockValUsd, 2)} (${usdHoldingCount}개 종목)`;
      }
      if ($("#summaryUsdStockProfit")) {
        const uSign = usdStockProfitKrw >= 0 ? "+" : "";
        const urSign = usdStockReturnRate >= 0 ? "+" : "";
        $("#summaryUsdStockProfit").textContent = `${uSign}${money(usdStockProfitKrw)} (${urSign}${number(usdStockReturnRate, 2)}%)`;
        $("#summaryUsdStockProfit").style.color = usdStockProfitKrw >= 0 ? "#f43f5e" : "#38bdf8";
      }

      // 3. 주식 기대수익 (주식 평가손익) & 일간 수익
      if ($("#expectedProfitRow")) $("#expectedProfitRow").style.display = "flex";
      if ($("#profitLabelText")) $("#profitLabelText").textContent = "주식 기대수익";
      if ($("#totalProfit")) {
        $("#totalProfit").textContent = money(s.profit_krw);
      }
      const profitRateEl = $("#profitRate");
      if (profitRateEl) {
        profitRateEl.textContent = `(${s.return_rate >= 0 ? "+" : ""}${number(s.return_rate)}%)`;
      }
      // Share the existing stock-profit tone, including its zero/missing fallback.
      const totalProfitNonnegative = (s.profit_krw || 0) >= 0;
      const totalProfitColor = totalProfitNonnegative ? "#f43f5e" : "#38bdf8";
      for (const node of [$("#expectedProfitRow .wealth-profit-label"), $("#totalProfit"), profitRateEl]) {
        if (!node) continue;
        node.style.color = totalProfitColor;
        // Existing semantic rules also exclude this amount from White's neutral strong override.
        node.classList.toggle("up", totalProfitNonnegative);
        node.classList.toggle("down", !totalProfitNonnegative);
      }

      // 4. 주식 실현손익
      if ($("#realizedPnlRow")) $("#realizedPnlRow").style.display = "flex";
      if ($("#pnlLabelText")) $("#pnlLabelText").textContent = "주식 실현손익";
      if ($("#summaryRealizedPnl")) {
        $("#summaryRealizedPnl").textContent = `${totalRealizedKrw >= 0 ? "+" : ""}${money(totalRealizedKrw)}`;
        $("#summaryRealizedPnl").className = totalRealizedKrw > 0 ? 'gain up' : (totalRealizedKrw < 0 ? 'loss down' : '');
        $("#summaryRealizedPnl").style.color = totalRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
      }
      if ($("#pnlYearLabel")) $("#pnlYearLabel").textContent = `${currYear2Digit}년`;
      if ($("#summaryRealizedPnlYear")) {
        $("#summaryRealizedPnlYear").textContent = `${yearRealizedKrw >= 0 ? '+' : ''}${money(yearRealizedKrw)}`;
        $("#summaryRealizedPnlYear").className = yearRealizedKrw > 0 ? 'gain up' : (yearRealizedKrw < 0 ? 'loss down' : '');
        $("#summaryRealizedPnlYear").style.color = yearRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
      }
      if ($("#pnlMonthLabel")) $("#pnlMonthLabel").textContent = `${currMonthStr}월`;
      if ($("#summaryRealizedPnlMonth")) {
        $("#summaryRealizedPnlMonth").textContent = `${monthRealizedKrw >= 0 ? '+' : ''}${money(monthRealizedKrw)}`;
        $("#summaryRealizedPnlMonth").className = monthRealizedKrw > 0 ? 'gain up' : (monthRealizedKrw < 0 ? 'loss down' : '');
        $("#summaryRealizedPnlMonth").style.color = monthRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
      }

      // 5. 배당금 (주식 탭에서 별도 표시)
      if ($("#dividendRow")) $("#dividendRow").style.display = "flex";
      if ($("#divLabelText")) $("#divLabelText").textContent = "배당금";
      if ($("#summaryActualDividend")) {
        $("#summaryActualDividend").textContent = money(totalActualDivKrw);
      }
      if ($("#divYearLabel")) $("#divYearLabel").textContent = `${currYear2Digit}년`;
      if ($("#summaryActualDivYear")) {
        $("#summaryActualDivYear").textContent = `${yearActualDivKrw >= 0 ? '+' : ''}${money(yearActualDivKrw)}`;
      }
      if ($("#divMonthLabel")) $("#divMonthLabel").textContent = `${currMonthStr}월`;
      if ($("#summaryActualDivMonth")) {
        $("#summaryActualDivMonth").textContent = `${monthActualDivKrw >= 0 ? '+' : ''}${money(monthActualDivKrw)}`;
      }


      renderDailyPnl(dailyPnl);
      renderCurrency(krwCurrency);
      renderCurrency(usdCurrency);

      $("#updatedAt") && ($("#updatedAt").textContent = updatedAt ? `마지막 자산 반영 ${new Date(updatedAt).toLocaleString("ko-KR")}` : "아직 보유종목이 없습니다.");
      $("#accountCaption") && ($("#accountCaption").textContent = `전체 ${number(s.account_count, 0)}개 계좌`);
    }

    return Object.freeze({ renderCurrency, renderDailyPnl, renderRealizedPnlCaption, renderSummary });
  }
  window.WealthInvestmentSummaryView = Object.freeze({ create });
})();
