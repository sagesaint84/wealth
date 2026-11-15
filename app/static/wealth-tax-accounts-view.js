/* Tax accounts presentation only. Matching, filters, calculations and sort state stay in wealth.js. */
(() => {
  'use strict';
  function create({ html, number, signClass, holdingRows }) {
    function emptyAccounts({ o }) {
      return `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;color:#94a3b8;text-align:center;">
        <span style="font-size:32px;margin-bottom:8px;">🌿</span>
        <strong style="font-size:15px;color:#cbd5e1;margin-bottom:4px;">${o === '모두' ? '절세계좌(IRP·연금저축·ISA)' : `[${o}] 절세계좌`}에 보유종목이 없습니다.</strong>
        <p style="font-size:12px;margin:0;">계좌 관리에서 IRP, 연금저축, 중개형 ISA 계좌를 등록하고 종목을 추가해보세요.</p>
      </div>
    `;
    }

    function emptyFilter({ filterTitle }) {
      return `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:260px;color:#94a3b8;text-align:center;">
        <span style="font-size:32px;margin-bottom:8px;">🔍</span>
        <strong style="font-size:15px;color:#cbd5e1;margin-bottom:6px;">${filterTitle}에 등록된 보유종목이 없습니다.</strong>
        <p style="font-size:12px;margin:10px 0 12px;color:#64748b;">좌측 카드에서 다른 절세계좌를 선택하시거나 전체보기를 눌러주세요.</p>
        <button type="button" class="button secondary compact" style="cursor:pointer;" onclick="currentTaxAccountFilter='all';renderTaxAccountHoldings(currentOwner);">🌿 절세계좌 전체 보기</button>
      </div>
    `;
    }

    function cashRow({ cashAccountLabel, currentFilterCash }) {
      return `
        <tr class="tax-cash-table-row" style="background:rgba(56,189,248,0.06);border-bottom:1px solid rgba(56,189,248,0.25);">
          <td class="holding-name-cell" style="text-align:left;">
            <strong style="color:#38bdf8;font-size:13px;display:flex;align-items:center;gap:6px;">
              💵 예수금 (현금 잔고)
            </strong>
            <small style="color:#7dd3fc;">미투자 현금 잔액</small>
          </td>
          <td style="text-align:left;">
            <span class="sector-badge" style="background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);">현금·예수금</span>
          </td>
          <td class="holding-accounts" style="text-align:left;">
            <span class="holding-account-detail" style="background:rgba(56,189,248,0.12);border-color:rgba(56,189,248,0.3);color:#7dd3fc;font-weight:600;">
              ${html(cashAccountLabel)} ₩${number(currentFilterCash, 0)}
            </span>
          </td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="text-align:right;"><strong style="color:#38bdf8;font-size:13.5px;font-weight:700;">₩${number(currentFilterCash, 0)}</strong></td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="text-align:center;color:#64748b;">-</td>
        </tr>
      `;
    }

    function emptyStocksWithCash({ currentFilterCash }) {
      return `
        <tr style="text-align:center;color:#94a3b8;">
          <td colspan="9" style="padding:28px 14px;text-align:center;color:#94a3b8;">
            <div style="font-size:13px;color:#cbd5e1;font-weight:600;margin-bottom:4px;">보유 중인 주식 종목이 없습니다.</div>
            <div style="font-size:11.5px;color:#64748b;">예수금 ₩${number(currentFilterCash, 0)}이 안전하게 보관되어 있습니다.</div>
          </td>
        </tr>
      `;
    }

    function holdingsTable({ taxHoldingSortField, taxHoldingSortOrder, cashRowHtml, emptyStockNotice, holdingRowsData }) {
      const trsHtml = holdingRowsData.map(({ item, accounts }) =>
        renderHoldingRow(item, accounts.map(renderAccountDetail).join(""))
      ).join("");
      return `
      <div class="table-wrap tax-table-wrap">
        <table class="tax-holdings-table">
          <thead>
            <tr>
              <th data-tax-sort="name" class="sortable-th ${taxHoldingSortField === 'name' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="text-align:left;">종목 <span class="sort-icon"></span></th>
              <th data-tax-sort="sector" class="sortable-th ${taxHoldingSortField === 'sector' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="text-align:left;">섹터 <span class="sort-icon"></span></th>
              <th style="text-align:left;">보유계좌</th>
              <th data-tax-sort="quantity" class="sortable-th ${taxHoldingSortField === 'quantity' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">수량 <span class="sort-icon"></span></th>
              <th data-tax-sort="market_value_krw" class="sortable-th ${taxHoldingSortField === 'market_value_krw' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">평가금액 <span class="sort-icon"></span></th>
              <th data-tax-sort="profit_krw" class="sortable-th ${taxHoldingSortField === 'profit_krw' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">평가손익 <span class="sort-icon"></span></th>
              <th data-tax-sort="return_rate" class="sortable-th ${taxHoldingSortField === 'return_rate' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">수익률 <span class="sort-icon"></span></th>
              <th data-tax-sort="day_change_rate" class="sortable-th ${taxHoldingSortField === 'day_change_rate' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">등락률 <span class="sort-icon"></span></th>
              <th style="text-align:center;">차트</th>
            </tr>
          </thead>
          <tbody id="taxHoldingsBody">${cashRowHtml}${emptyStockNotice}${trsHtml}</tbody>
        </table>
      </div>
    `;
    }

    function allTaxBenefit({ allCumulativeTaxSaved, icon = "💎" }) {
      return `
      <span style="color:#c4b5fd;background:rgba(167,139,250,0.14);border:1px solid rgba(167,139,250,0.3);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;">
        ${icon} 누적 절세액: <strong style="color:#ddd6fe;font-size:12.5px;">₩${number(allCumulativeTaxSaved, 0)}</strong>
      </span>
    `;
    }

    function irpTaxBenefit({ irpCumulativeTaxSaved }) {
      return allTaxBenefit({ allCumulativeTaxSaved: irpCumulativeTaxSaved, icon: "🛡️" });
    }

    function pensionTaxBenefit({ pensionCumulativeTaxSaved }) {
      return `
      <span style="color:#34d399;background:rgba(52,211,153,0.14);border:1px solid rgba(52,211,153,0.3);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;">
        💎 누적 절세액: <strong style="color:#a7f3d0;font-size:12.5px;">₩${number(pensionCumulativeTaxSaved, 0)}</strong>
      </span>
    `;
    }

    function isaTaxBenefit() {
      return `
      <span style="color:#38bdf8;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.25);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
        🔄 ISA 혜택: 비과세 200~400만 + 9.9% 분리과세
      </span>
    `;
    }

    function accountIsaBenefit() {
      return `
          <span style="color:#38bdf8;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.25);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
            🔄 ISA 비과세 200~400만 + 9.9% 분리과세
          </span>
        `;
    }

    function accountTaxBenefit({ targetTaxSaved }) {
      return `
          <span style="color:#c4b5fd;background:rgba(167,139,250,0.16);border:1px solid rgba(167,139,250,0.35);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;">
            💎 소유자 합산 누적 절세액: <strong style="color:#ddd6fe;font-size:12.5px;">₩${number(targetTaxSaved, 0)}</strong>
          </span>
        `;
    }

    function accountNonDeductibleBenefit() {
      return `
          <span style="color:#34d399;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.25);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
            🌱 비공제 계좌: 원금 인출 시 비과세
          </span>
        `;
    }

    function accountZeroBenefit() {
      return `
          <span style="color:#94a3b8;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
            누적 절세액: ₩0
          </span>
        `;
    }

    function chartTaxBenefit(benefit) {
      switch (benefit?.kind) {
        case 'all': return allTaxBenefit({ allCumulativeTaxSaved: benefit.amount });
        case 'irp': return irpTaxBenefit({ irpCumulativeTaxSaved: benefit.amount });
        case 'pension': return pensionTaxBenefit({ pensionCumulativeTaxSaved: benefit.amount });
        case 'isa': return isaTaxBenefit();
        case 'accountIsa': return accountIsaBenefit();
        case 'account': return accountTaxBenefit({ targetTaxSaved: benefit.amount });
        case 'nonDeductible': return accountNonDeductibleBenefit();
        case 'zero': return accountZeroBenefit();
        default: return '';
      }
    }

    function chartContent(container, { filterTitle, sortedGroups, filterSubtitle, filteredTotalMarket, filteredStats, currentFilterCash, taxBenefit, holdingsHtml }) {
      container.innerHTML = `
    <div class="tax-table-header" style="display:flex;justify-content:space-between;align-items:center;padding:2px 4px 10px;border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:8px;flex-wrap:wrap;gap:8px;">
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="tax-filter-title" style="font-size:13.5px;font-weight:700;">${filterTitle} (${sortedGroups.length}개 종목)</span>
        <span style="font-size:11px;color:#94a3b8;">${filterSubtitle}</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;font-size:12px;flex-wrap:wrap;">
        <span style="color:#94a3b8;">총 자산: <strong style="font-size:14px;font-weight:800;">₩${number(filteredTotalMarket, 0)}</strong></span>
        <span style="color:#94a3b8;">(주식 <strong style="font-weight:600;">₩${number(filteredStats.market, 0)}</strong> · <strong style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(currentFilterCash, 0)}</strong>)</span>
        <span class="${signClass(filteredStats.profit)}" style="font-weight:700;">
          ${filteredStats.profit >= 0 ? '+' : ''}₩${number(filteredStats.profit, 0)} (${filteredStats.profit >= 0 ? '+' : ''}${number(filteredStats.profitRate, 2)}%)
        </span>
        ${chartTaxBenefit(taxBenefit)}
      </div>
    </div>
    ${holdingsHtml}
  `;
    }

    function allCard({ isAllActive, taxHoldings, taxAccounts, allTotalMarket, allStats, allCash, allCumulativeTaxSaved }) {
      return `
    <div class="tax-card record-row ${isAllActive ? 'active-tax-card' : ''}" data-tax-filter="all">
      <div class="tax-card-head" style="margin-bottom:6px;">
        <div class="tax-card-heading">
          <span style="font-size:16px;">🌿</span>
          <strong class="tax-card-title" style="font-size:13.5px;font-weight:700;">절세계좌 전체</strong>
          ${isAllActive ? '<span class="tax-card-selected" style="font-size:10px;padding:2px 6px;border-radius:4px;background:#8b5cf6;color:#fff;font-weight:800;">선택</span>' : ''}
        </div>
        <span class="tax-card-count" style="font-size:11px;color:#94a3b8;background:rgba(255,255,255,0.06);padding:2px 7px;border-radius:4px;">
          ${taxHoldings.length}종목 · ${taxAccounts.length}계좌
        </span>
      </div>

      <!-- 절세계좌 총액 -->
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px;">
        <span style="font-size:11.5px;color:#94a3b8;">절세계좌 총 자산</span>
        <strong class="tax-card-val" style="font-size:16px;font-weight:800;letter-spacing:-0.3px;">
          ₩${number(allTotalMarket, 0)}
        </strong>
      </div>

      <!-- 자산 구성: 주식 + 예수금 -->
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 7px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(allStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(allCash, 0)}</span>
      </div>

      <!-- 수익금액 및 수익률 -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익금액 / 수익률</span>
        <strong class="${signClass(allStats.profit)}" style="font-size:12.5px;font-weight:700;">
          ${allStats.profit >= 0 ? '+' : ''}₩${number(allStats.profit, 0)} (${allStats.profit >= 0 ? '+' : ''}${number(allStats.profitRate, 2)}%)
        </strong>
      </div>

      <!-- 절세금액 누적 -->
      <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 9px;background:rgba(167,139,250,0.12);border:1px solid rgba(167,139,250,0.25);border-radius:6px;font-size:11.5px;">
        <span style="color:#c4b5fd;font-weight:600;">💎 절세금액 누적</span>
        <strong style="color:#a78bfa;font-weight:800;font-size:13px;">
          ₩${number(allCumulativeTaxSaved, 0)}
        </strong>
      </div>
    </div>
  `;
    }

    function isaCard({ isIsaActive, isaHoldings, isaAccounts, isaTotalMarket, isaStats, isaCash }) {
      return `
    <div class="tax-card record-row ${isIsaActive ? 'active-tax-card' : ''}" data-tax-filter="isa">
      <div class="tax-card-head" style="margin-bottom:5px;">
        <div class="tax-card-heading">
          <span style="font-size:15px;">🔄</span>
          <strong class="tax-card-title" style="font-size:13px;font-weight:700;">중개형 ISA</strong>
          ${isIsaActive ? '<span class="tax-card-selected" style="font-size:10px;padding:2px 6px;border-radius:4px;background:#38bdf8;color:#0f172a;font-weight:800;">선택</span>' : ''}
        </div>
        <span class="tax-card-count" style="font-size:11px;color:#38bdf8;background:rgba(56,189,248,0.12);padding:2px 6px;border-radius:4px;font-weight:600;">
          ${isaHoldings.length}종목 · ${isaAccounts.length}계좌
        </span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;">
        <span style="font-size:11.5px;color:#94a3b8;">총 자산</span>
        <strong class="tax-card-val" style="font-size:14.5px;font-weight:800;">₩${number(isaTotalMarket, 0)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(isaStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(isaCash, 0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익 / 수익률</span>
        <span class="${signClass(isaStats.profit)}" style="font-size:12px;font-weight:700;">
          ${isaStats.profit >= 0 ? '+' : ''}₩${number(isaStats.profit, 0)} (${isaStats.profit >= 0 ? '+' : ''}${number(isaStats.profitRate, 2)}%)
        </span>
      </div>
      <div style="font-size:11px;color:#7dd3fc;background:rgba(56,189,248,0.08);padding:4px 8px;border-radius:5px;display:flex;justify-content:space-between;">
        <span>절세 혜택</span>
        <span>비과세 200~400만 + 9.9% 분리과세</span>
      </div>
    </div>
  `;
    }

    function irpCard({ isIrpActive, irpHoldings, irpAccounts, irpTotalMarket, irpStats, irpCash, irpCumulativeTaxSaved }) {
      return `
    <div class="tax-card record-row ${isIrpActive ? 'active-tax-card' : ''}" data-tax-filter="irp">
      <div class="tax-card-head" style="margin-bottom:5px;">
        <div class="tax-card-heading">
          <span style="font-size:15px;">🛡️</span>
          <strong class="tax-card-title" style="font-size:13px;font-weight:700;">개인형 IRP</strong>
          ${isIrpActive ? '<span class="tax-card-selected" style="font-size:10px;padding:2px 6px;border-radius:4px;background:#a78bfa;color:#0f172a;font-weight:800;">선택</span>' : ''}
        </div>
        <span class="tax-card-count" style="font-size:11px;color:#c4b5fd;background:rgba(167,139,250,0.15);padding:2px 6px;border-radius:4px;font-weight:600;">
          ${irpHoldings.length}종목 · ${irpAccounts.length}계좌
        </span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;">
        <span style="font-size:11.5px;color:#94a3b8;">총 자산</span>
        <strong class="tax-card-val" style="font-size:14.5px;font-weight:800;">₩${number(irpTotalMarket, 0)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(irpStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(irpCash, 0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익 / 수익률</span>
        <span class="${signClass(irpStats.profit)}" style="font-size:12px;font-weight:700;">
          ${irpStats.profit >= 0 ? '+' : ''}₩${number(irpStats.profit, 0)} (${irpStats.profit >= 0 ? '+' : ''}${number(irpStats.profitRate, 2)}%)
        </span>
      </div>
      <div style="font-size:11px;color:#ddd6fe;background:rgba(167,139,250,0.08);padding:4px 8px;border-radius:5px;display:flex;justify-content:space-between;">
        <span>누적 절세액</span>
        <strong style="color:#c4b5fd;">₩${number(irpCumulativeTaxSaved, 0)}</strong>
      </div>
    </div>
  `;
    }

    function pensionCard({ isPensionActive, pensionHoldings, pensionAccounts, pensionTotalMarket, pensionStats, pensionCash, pensionCumulativeTaxSaved }) {
      return `
    <div class="tax-card record-row ${isPensionActive ? 'active-tax-card' : ''}" data-tax-filter="pension_savings">
      <div class="tax-card-head" style="margin-bottom:5px;">
        <div class="tax-card-heading">
          <span style="font-size:15px;">💎</span>
          <strong class="tax-card-title" style="font-size:13px;font-weight:700;">연금저축</strong>
          ${isPensionActive ? '<span class="tax-card-selected" style="font-size:10px;padding:2px 6px;border-radius:4px;background:#34d399;color:#0f172a;font-weight:800;">선택</span>' : ''}
        </div>
        <span class="tax-card-count" style="font-size:11px;color:#34d399;background:rgba(52,211,153,0.15);padding:2px 6px;border-radius:4px;font-weight:600;">
          ${pensionHoldings.length}종목 · ${pensionAccounts.length}계좌
        </span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;">
        <span style="font-size:11.5px;color:#94a3b8;">총 자산</span>
        <strong class="tax-card-val" style="font-size:14.5px;font-weight:800;">₩${number(pensionTotalMarket, 0)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(pensionStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(pensionCash, 0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익 / 수익률</span>
        <span class="${signClass(pensionStats.profit)}" style="font-size:12px;font-weight:700;">
          ${pensionStats.profit >= 0 ? '+' : ''}₩${number(pensionStats.profit, 0)} (${pensionStats.profit >= 0 ? '+' : ''}${number(pensionStats.profitRate, 2)}%)
        </span>
      </div>
      <div style="font-size:11px;color:#a7f3d0;background:rgba(16,185,129,0.08);padding:4px 8px;border-radius:5px;display:flex;justify-content:space-between;">
        <span>누적 절세액</span>
        <strong style="color:#34d399;">₩${number(pensionCumulativeTaxSaved, 0)}</strong>
      </div>
    </div>
  `;
    }

    function isaAccountTaxRow() {
      return `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px;color:#7dd3fc;background:rgba(56,189,248,0.08);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span>절세 혜택</span>
          <span style="color:#38bdf8;font-weight:600;">비과세 200~400만</span>
        </div>
      `;
    }

    function deductibleAccountTaxRow({ acctSavedTax }) {
      return `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#ddd6fe;background:rgba(167,139,250,0.09);border:1px solid rgba(167,139,250,0.22);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span style="color:#c4b5fd;font-weight:600;">💎 소유자 합산 누적 절세액</span>
          <strong style="color:#ddd6fe;font-size:12px;font-weight:800;">₩${number(acctSavedTax, 0)}</strong>
        </div>
      `;
    }

    function nonDeductibleAccountTaxRow() {
      return `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px;color:#a7f3d0;background:rgba(16,185,129,0.07);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span>절세 분류</span>
          <span style="color:#34d399;">비공제 (원금인출 비과세)</span>
        </div>
      `;
    }

    function zeroAccountTaxRow() {
      return `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px;color:#94a3b8;background:rgba(255,255,255,0.04);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span>소유자 합산 누적 절세액</span>
          <span style="color:#cbd5e1;">₩0</span>
        </div>
      `;
    }

    function accountCard({ isAcctActive, acct, typeBadge, acctTotalMarket, acctStats, acctHoldings, acctCash, taxSavedRowHtml }) {
      return `
      <div class="tax-card record-row ${isAcctActive ? 'active-tax-card' : ''}" data-tax-filter="acc_${acct.id}" style="padding:9px 12px !important;margin-bottom:6px;">
        <div class="tax-card-head">
          <div class="tax-card-heading">
            <strong class="tax-card-title" title="${html(acct.name)}" style="font-size:12.5px;">${html(acct.name)}</strong>
            ${isAcctActive ? '<span class="tax-card-selected" style="font-size:9.5px;padding:1px 5px;border-radius:3px;background:#a78bfa;color:#0f172a;font-weight:800;">선택</span>' : ''}
          </div>
          <div class="tax-card-actions">
            ${typeBadge}
            <button class="account-action-button" data-account-edit-id="${acct.id}" title="계좌 정보 및 예수금 수정" type="button" style="padding:1px 5px;font-size:11px;line-height:1;border-radius:4px;cursor:pointer;">✎</button>
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:baseline;font-size:11.5px;color:#94a3b8;margin-top:3px;">
          <span>${html(acct.broker)} [${html(acct.owner || '모두')}]</span>
          <strong class="tax-card-val" style="font-size:13.5px;font-weight:800;">₩${number(acctTotalMarket, 0)}</strong>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-top:4px;">
          <span style="color:#cbd5e1;">주식 ₩${number(acctStats.market, 0)} (${acctHoldings.length}종목)</span>
          <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(acctCash, 0)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;margin-top:4px;padding-top:2px;">
          <span>평가손익</span>
          <span class="${signClass(acctStats.profit)}" style="font-weight:700;">${acctStats.profit >= 0 ? '+' : ''}₩${number(acctStats.profit, 0)} (${acctStats.profit >= 0 ? '+' : ''}${number(acctStats.profitRate, 2)}%)</span>
        </div>
        ${taxSavedRowHtml}
      </div>
    `;
    }

    function cardList(container, { all, isa, irp, pension, accountCards }) {
      if (!accountCards.length) {
        container.innerHTML = emptyAccountList();
        return;
      }

      const allCardHtml = allCard(all);
      const isaCardHtml = isaCard(isa);
      const irpCardHtml = irpCard(irp);
      const pensionCardHtml = pensionCard(pension);
      const accountCardsHtml = accountCards.map(card => {
        const { cat, isDed, acctSavedTax, taxRow } = card;
        const typeBadge = cat === 'isa' ? isaTypeBadge()
          : cat === 'irp' ? irpTypeBadge({ isDed }) : pensionTypeBadge({ isDed });
        const taxSavedRowHtml = taxRow === 'isa' ? isaAccountTaxRow()
          : taxRow === 'deductible' ? deductibleAccountTaxRow({ acctSavedTax })
          : taxRow === 'nonDeductible' ? nonDeductibleAccountTaxRow() : zeroAccountTaxRow();
        return accountCard({ ...card, typeBadge, taxSavedRowHtml });
      }).join('');

      container.innerHTML = `
    ${allCardHtml}
    <div style="display:flex;flex-direction:column;gap:8px;">
      ${isaCardHtml}
      ${irpCardHtml}
      ${pensionCardHtml}
    </div>
    <div style="font-size:11px;color:#94a3b8;font-weight:700;margin:12px 0 6px 2px;letter-spacing:0.3px;display:flex;justify-content:space-between;align-items:center;">
      <span>계좌별 상세 (${accountCards.length}개)</span>
      <span style="font-size:10px;color:#64748b;">클릭하여 단일 계좌 조회</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:4px;">
      ${accountCardsHtml}
    </div>
  `;
    }

    function isaTypeBadge() {
      return '<span style="color:#38bdf8;background:rgba(56,189,248,0.12);padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;">ISA 비과세</span>';
    }

    function irpTypeBadge({ isDed }) {
      return `<span style="color:${isDed ? '#c4b5fd' : '#34d399'};background:${isDed ? 'rgba(167,139,250,0.15)' : 'rgba(16,185,129,0.15)'};padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;">IRP ${isDed ? '공제' : '비공제'}</span>`;
    }

    function pensionTypeBadge({ isDed }) {
      return `<span style="color:${isDed ? '#38bdf8' : '#34d399'};background:${isDed ? 'rgba(56,189,248,0.12)' : 'rgba(16,185,129,0.12)'};padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;">연금저축 ${isDed ? '공제' : '비공제'}</span>`;
    }
    function renderAccountDetail(detail) { return holdingRows.renderAccountDetail(detail, 'tax'); }
    function renderHoldingRow(item, accounts) { return holdingRows.renderRow(item, { accounts, variant: 'tax' }); }
    function emptyAccountList() {
      return '<div style="color:#94a3b8;font-size:12px;padding:8px;">등록된 절세계좌가 없습니다.</div>';
    }
    return Object.freeze({ emptyAccountList, emptyAccounts, emptyFilter, cashRow, emptyStocksWithCash, holdingsTable, allTaxBenefit, irpTaxBenefit, pensionTaxBenefit, isaTaxBenefit, accountIsaBenefit, accountTaxBenefit, accountNonDeductibleBenefit, accountZeroBenefit, chartContent, allCard, isaCard, irpCard, pensionCard, isaAccountTaxRow, deductibleAccountTaxRow, nonDeductibleAccountTaxRow, zeroAccountTaxRow, accountCard, cardList, isaTypeBadge, irpTypeBadge, pensionTypeBadge, renderAccountDetail, renderHoldingRow });
  }
  window.WealthTaxAccountsView = Object.freeze({ create });
})();
