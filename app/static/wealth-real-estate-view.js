/* Real estate presentation only. Ownership, valuations, loans and sold-record matching remain caller-owned. */
(() => {
  'use strict';
  function create({ $, html, number }) {
    function updateSummary({ o, totalREVal, ownList, rentalList, totalPurchaseVal, totalTenantDeposit, totalProfit, totalProfitRate, totalREDebt, totalLinkedLoanBalance, totalLandlordDeposit, totalSoldPnl, totalSoldPurch, soldProfitRate, filteredSold, filtered, leaseList, currentRealEstateSubtab }) {
  if ($("#totalRealEstateVal")) $("#totalRealEstateVal").textContent = `₩${number(totalREVal, 0)}`;
  if ($("#totalRealEstateCountSub")) {
    const isShare = o !== '모두' ? ` (${o} 지분 반영)` : '';
    $("#totalRealEstateCountSub").textContent = `보유: ${ownList.length + rentalList.length}건 (자가 ${ownList.length} · 임대 ${rentalList.length})${isShare}`;
  }
  if ($("#totalPurchaseVal")) $("#totalPurchaseVal").textContent = `₩${number(totalPurchaseVal, 0)}`;
  if ($("#totalTenantDepositSub")) {
    $("#totalTenantDepositSub").textContent = `임차 전세보증금: ₩${number(totalTenantDeposit, 0)}`;
  }
  if ($("#totalRealEstateProfitVal")) {
    const pSign = totalProfit >= 0 ? "+" : "";
    $("#totalRealEstateProfitVal").textContent = `${pSign}₩${number(totalProfit, 0)}`;
    $("#totalRealEstateProfitVal").style.color = totalProfit >= 0 ? "#42d5a3" : "#f43f5e";
  }
  if ($("#totalRealEstateRateSub")) {
    const rSign = Number(totalProfitRate) >= 0 ? "+" : "";
    $("#totalRealEstateRateSub").textContent = `수익률: ${rSign}${totalProfitRate}%`;
  }
  if ($("#totalRealEstateDebtVal")) $("#totalRealEstateDebtVal").textContent = `₩${number(totalREDebt, 0)}`;
  if ($("#totalRealEstateDebtSub")) {
    $("#totalRealEstateDebtSub").textContent = `담보·전세대출: ₩${number(totalLinkedLoanBalance, 0)} · 임대보증금: ₩${number(totalLandlordDeposit, 0)}`;
  }

  // 🏷️ 상단 5번째 요약 카드: 부동산 실현손익
  if ($("#totalRealEstateRealizedVal")) {
    const sSign = totalSoldPnl >= 0 ? "+" : "";
    $("#totalRealEstateRealizedVal").textContent = `${sSign}₩${number(totalSoldPnl, 0)}`;
    $("#totalRealEstateRealizedVal").style.color = totalSoldPnl > 0 ? "#42d5a3" : (totalSoldPnl < 0 ? "#f43f5e" : "#f59e0b");
  }
  if ($("#totalRealEstateRealizedSub")) {
    const rateText = totalSoldPurch > 0 ? ` (수익률: ${Number(soldProfitRate) >= 0 ? '+' : ''}${soldProfitRate}%)` : '';
    $("#totalRealEstateRealizedSub").textContent = `매도: ${filteredSold.length}건${rateText}`;
  }

  // 5개 서브탭 카운트 업데이트
  if ($("#reAllCount")) $("#reAllCount").textContent = filtered.length;
  if ($("#reOwnCount")) $("#reOwnCount").textContent = ownList.length;
  if ($("#reRentalCount")) $("#reRentalCount").textContent = rentalList.length;
  if ($("#reLeaseCount")) $("#reLeaseCount").textContent = leaseList.length;
  if ($("#reSoldCount")) $("#reSoldCount").textContent = filteredSold.length;

  // 매도 탭 활성화 시 [➕ 매도 기록 추가] 버튼 노출
  const directBtn = $("#btnDirectAddSoldRe");
  if (directBtn) {
    directBtn.style.display = currentRealEstateSubtab === 'sold' ? 'inline-flex' : 'none';
  }

    }

    function emptySold() {
      return `
        <div class="empty" style="grid-column:1/-1;padding:32px 16px;text-align:center;">
          <p style="font-size:15px;color:#f8fafc;font-weight:700;margin-bottom:6px;">🏷️ 기록된 부동산 매도 내역이 없습니다.</p>
          <p style="font-size:12px;color:#94a3b8;margin-bottom:14px;">보유 부동산 카드의 [🏢] 버튼을 누르거나, 우측 상단의 [➕ 매도 기록 추가] 버튼으로 등록할 수 있습니다.</p>
          <button type="button" class="button secondary compact" onclick="openDirectAddSoldReDialog()" style="font-size:12px;color:#f59e0b;border-color:rgba(245,158,11,0.4);">➕ 매도 기록 직접 추가</button>
        </div>
      `;
    }

    function soldCard({ sold, ownerBadgeText, titleName, purch, isPartial, rawPurch, sell, rawSell, exp, rawExp, profitColor, profitSign, pnl, profitRate }) {
      return `
        <div class="saving-card real-estate-card badge-sold">
          <div class="saving-card-header">
            <div class="saving-card-title-group">
              <div class="saving-badge-row">
                <span class="saving-type-badge badge-sold" style="background:rgba(245,158,11,0.18);color:#f59e0b;border:1px solid rgba(245,158,11,0.35);font-weight:700;">🏷️ 매도 완료</span>
                <span class="saving-owner-badge" title="${html(sold.owner || '')}">${html(ownerBadgeText)}</span>
                <span class="d-day-badge">📅 매도일: ${html(sold.date || '-')}</span>
              </div>
              <h3 class="saving-product-name" style="font-size:15px;margin-top:2px;">${html(titleName)}</h3>
              <span class="saving-bank-name">${html(sold.address || sold.memo || '-')}</span>
            </div>
            <div class="account-row-actions saving-card-actions">
              <button class="account-action-button" data-sold-re-edit="${sold.id}" title="매도 기록 수정" type="button" style="color:#38bdf8;font-size:13px;">✎</button>
              <button class="mini-delete-button" data-sold-re-del="${sold.id}" title="매도 기록 삭제" type="button" style="color:#f43f5e;font-size:13px;">🗑️</button>
            </div>
          </div>

          <div class="saving-card-details">
            <div class="saving-detail-row">
              <span class="saving-detail-label">취득가 (매수가)</span>
              <span class="saving-detail-val">${purch > 0 ? `₩${number(purch, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawPurch, 0)})</small>` : ''}` : '-'}</span>
            </div>
            <div class="saving-detail-row">
              <span class="saving-detail-label">양도가 (매도가)</span>
              <span class="saving-detail-val" style="color:#38bdf8;font-size:13px;font-weight:700;">${sell > 0 ? `₩${number(sell, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawSell, 0)})</small>` : ''}` : '-'}</span>
            </div>
            ${exp > 0 ? `
              <div class="saving-detail-row">
                <span class="saving-detail-label">필요경비 (공제)</span>
                <span class="saving-detail-val" style="color:#fb7185;">-₩${number(exp, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawExp, 0)})</small>` : ''}</span>
              </div>
            ` : ''}
            <div class="saving-detail-row sold-profit-row" style="grid-column:1/-1;padding:8px 10px;border-radius:8px;margin-top:2px;">
              <span class="saving-detail-label" style="font-weight:700;">실현손익 (양도차익)</span>
              <span class="saving-detail-val" style="color:${profitColor};font-size:14px;font-weight:800;">
                ${profitSign}₩${number(pnl, 0)} ${profitRate != null ? `(${profitSign}${profitRate}%)` : ''}
              </span>
            </div>
            ${sold.memo ? `
              <div class="saving-detail-row" style="grid-column:1/-1;">
                <span class="saving-detail-label">비고 / 메모</span>
                <span class="saving-detail-val" style="color:#94a3b8;font-size:11.5px;white-space:normal;word-break:break-word;">${html(sold.memo)}</span>
              </div>
            ` : ''}
          </div>
        </div>
      `;
    }

    function propertyCard({ re, typeBadgeClass, typeLabel, ownerBadgeText, dDayText, titleHtml, pType, naverLandUrl, cleanSearchKeyword, isPartial, o, purch, rawPurch, curr, rawCurr, profitColor, profitSign, profit, profitRate, dep, rawDep, rent, pyungText, connectedLoanItems, linkedLoanTotalBal, linkedLoanTotalInterest, netEquity }) {
      return `
      <div class="saving-card real-estate-card ${typeBadgeClass}">
        <div class="saving-card-header">
          <div class="saving-card-title-group">
            <div class="saving-badge-row">
              <span class="saving-type-badge ${typeBadgeClass}">${typeLabel}</span>
              <span class="saving-owner-badge" title="${html(re.owner || '')}">${html(ownerBadgeText)}</span>
              ${dDayText ? `<span class="d-day-badge">${dDayText}</span>` : ''}
            </div>
            <h3 class="saving-product-name">${titleHtml}</h3>
            <span class="saving-bank-name">${html(re.address || '-')}</span>
          </div>
          <div class="account-row-actions saving-card-actions">
            ${pType !== 'lease' ? `<button class="account-action-button" data-re-refresh-kb-id="${re.id}" title="KB부동산 공식 시세로 즉시 갱신" type="button" style="color:#facc15;font-size:12px;">🔄</button>` : ''}
            <a href="${naverLandUrl}" target="_blank" rel="noopener" class="account-action-button" title="네이버 부동산 '${cleanSearchKeyword}' 시세 확인" style="text-decoration:none;display:inline-flex;align-items:center;font-size:12px;">🔍</a>
            ${pType !== 'lease' ? `<button class="account-action-button" data-re-sell-id="${re.id}" title="부동산 매각 및 실현손익 기록" type="button" style="color:#f59e0b;font-size:12px;">🏢</button>` : ''}
            <button class="account-action-button" data-re-edit-id="${re.id}" title="수정" type="button">✎</button>
            <button class="mini-delete-button" data-re-del-id="${re.id}" title="삭제" type="button">🗑️</button>
          </div>
        </div>

        <div class="saving-card-details">
          ${pType !== 'lease' ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 매수가` : '매수가 (취득가)'}</span>
              <span class="saving-detail-val">₩${number(purch, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawPurch, 0)})</small>` : ''}</span>
            </div>
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 현재 시세` : '현재 시세'}</span>
              <span class="saving-detail-val" style="color:#38bdf8;font-size:13px;">₩${number(curr, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawCurr, 0)})</small>` : ''}</span>
            </div>
            <div class="saving-detail-row" style="grid-column:1/-1;">
              <span class="saving-detail-label">시세 차익 (수익률)</span>
              <span class="saving-detail-val" style="color:${profitColor};font-weight:700;">${profitSign}₩${number(profit, 0)} (${profitSign}${profitRate}%)</span>
            </div>
          ` : `
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 임차 보증금` : '임차 전세보증금'}</span>
              <span class="saving-detail-val" style="color:#38bdf8;font-size:13px;">₩${number(dep, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawDep, 0)})</small>` : ''}</span>
            </div>
            ${rent > 0 ? `
              <div class="saving-detail-row">
                <span class="saving-detail-label">월세 지출</span>
                <span class="saving-detail-val" style="color:#fb7185;">-₩${number(rent, 0)}</span>
              </div>
            ` : '<div class="saving-detail-row"><span class="saving-detail-label">계약 형태</span><span class="saving-detail-val">올전세</span></div>'}
          `}

          ${pType === 'rental' ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 임대 전세금` : '임대 전세금 (부채)'}</span>
              <span class="saving-detail-val" style="color:#fb7185;font-weight:700;">-₩${number(dep, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawDep, 0)})</small>` : ''}</span>
            </div>
            ${rent > 0 ? `
              <div class="saving-detail-row">
                <span class="saving-detail-label">월세 수입</span>
                <span class="saving-detail-val" style="color:#42d5a3;font-weight:700;">+₩${number(rent, 0)}</span>
              </div>
            ` : '<div class="saving-detail-row"><span class="saving-detail-label">임대 형태</span><span class="saving-detail-val">전세 임대</span></div>'}
          ` : ''}

          ${re.exclusive_area > 0 ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">전용면적</span>
              <span class="saving-detail-val">${re.exclusive_area}㎡${pyungText}</span>
            </div>
          ` : ''}

          ${re.contract_date ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">취득/계약일</span>
              <span class="saving-detail-val">${html(re.contract_date)}</span>
            </div>
          ` : ''}

          ${re.expiry_date ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">만기일</span>
              <span class="saving-detail-val">${html(re.expiry_date)}</span>
            </div>
          ` : ''}

          ${connectedLoanItems.length > 0 ? `
            <div class="saving-detail-row" style="grid-column:1/-1;background:rgba(244,63,94,0.06);padding:6px 8px;border-radius:6px;margin-top:2px;">
              <span class="saving-detail-label" style="color:#fb7185;">연결 대출 (${connectedLoanItems.length}건)</span>
              <span class="saving-detail-val" style="color:#fb7185;font-size:12px;">잔액: -₩${number(linkedLoanTotalBal, 0)} (월이자: ₩${number(linkedLoanTotalInterest, 0)})</span>
            </div>
          ` : ''}

          ${re.memo ? `
            <div class="saving-detail-row" style="grid-column:1/-1;">
              <span class="saving-detail-label">메모</span>
              <span class="saving-detail-val" style="color:#94a3b8;font-size:11px;">${html(re.memo)}</span>
            </div>
          ` : ''}

          ${pType !== 'lease' ? `
            <div style="grid-column:1/-1;margin-top:8px;padding-top:8px;border-top:1px dashed rgba(255,255,255,0.08);display:flex;justify-content:flex-end;">
              <button class="button secondary compact" data-re-sell-id="${re.id}" type="button" style="font-size:11px;padding:4px 10px;color:#f59e0b;border-color:rgba(245,158,11,0.4);background:rgba(245,158,11,0.08);font-weight:600;">
                🏢 매각/실현손익 기록
              </button>
            </div>
          ` : ''}
        </div>

        <div class="saving-interest-box" style="background:rgba(59,130,246,0.08);border-color:rgba(59,130,246,0.25);">
          <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
            <span style="color:#93c5fd;font-weight:600;">${isPartial ? `${o} 순에퀴티(순자산)` : '부동산 순에퀴티(순자산)'}</span>
            <span style="color:#60a5fa;font-size:15px;font-weight:700;">₩${number(netEquity, 0)}</span>
          </div>
        </div>
      </div>
    `;
    }

    function emptyProperties() { return '<div class="empty" style="grid-column:1/-1;">등록된 부동산 자산이 없습니다. 상단 [🏠 부동산 추가] 버튼을 눌러보세요.</div>'; }

    function title({ re }) { return re.dong_ho
      ? `${html(re.name)} <span style="font-size:12.5px;font-weight:normal;opacity:0.85;">(${html(re.dong_ho)})</span>`
      : html(re.name); }
    function updateFormTypeFields() {
      const pType = $("#reTypeSelect")?.value || "own";
      const isLease = pType === "lease";
      const isRental = pType === "rental";

      const purchLabel = $("#rePurchasePriceLabel");
      const currLabel = $("#reCurrentPriceLabel");
      const depLabel = $("#reDepositLabel");
      const rentLabel = $("#reMonthlyRentLabel");
      const depHint = $("#reDepositHint");

      if (purchLabel) purchLabel.style.display = isLease ? "none" : "";
      if (currLabel) currLabel.style.display = isLease ? "none" : "";
      if (depLabel) depLabel.style.display = (isRental || isLease) ? "" : "none";
      if (rentLabel) rentLabel.style.display = (isRental || isLease) ? "" : "none";

      if (depHint) {
        depHint.textContent = isRental ? "세입자에게 받은 전세보증금 (추후 상환할 부채)" : "집주인에게 맡긴 전세보증금 (만기 시 돌려받을 내 자산)";
      }
    }

    function showJointOwnershipFields(isJoint) {
      const singleWrap = $("#reSingleOwnerWrap");
      const jointWrap = $("#reJointOwnershipWrap");
      if (singleWrap) singleWrap.style.display = isJoint ? "none" : "block";
      if (jointWrap) jointWrap.style.display = isJoint ? "block" : "none";
    }

    function bindFormInputs({ updateRealEstateTypeFields, calcRealEstatePreview }) {
      $("#reTypeSelect")?.addEventListener("change", updateRealEstateTypeFields);
      ["rePurchasePrice", "reCurrentPrice", "reDepositAmount", "reLinkedLoansSelect"].forEach(id => {
        document.getElementById(id)?.addEventListener("input", calcRealEstatePreview);
        document.getElementById(id)?.addEventListener("change", calcRealEstatePreview);
      });
    }

    return Object.freeze({ updateFormTypeFields, showJointOwnershipFields, bindFormInputs, updateSummary, emptySold, soldCard, propertyCard, emptyProperties, title });
  }
  window.WealthRealEstateView = Object.freeze({ create });
})();
