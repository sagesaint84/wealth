/* Insurance/pension presentation only. Tax calculations and national history validation stay caller-owned. */
(() => {
  'use strict';
  function create({ html, number }) {
    function pensionYearRow({ yYear, yDep, yDeductible, ySaved }) {
      return `
          <div style="display:flex;justify-content:space-between;align-items:center;padding:3px 6px;border-radius:4px;font-size:11.5px;margin-bottom:3px;">
            <span><strong>${html(yYear)}년:</strong> 입금 ₩${number(yDep, 0)}</span>
            <span>➔ ${yDeductible ? `<strong style="color:#4ade80;">소유자 합산 절세 ₩${number(ySaved, 0)}</strong>` : '<span style="color:#34d399;font-weight:600;">비공제 (₩0)</span>'}</span>
          </div>
        `;
    }

    function pensionCard({ a, isTaxDeductible, badgeClass, typeLabel, statusLabel, dep, rate, totalTarget, ownerCurrent, refund, yearlyHistoryHtml }) {
      return `
      <div class="saving-card" style="border:1px solid ${isTaxDeductible ? 'rgba(56,189,248,0.35)' : 'rgba(16,185,129,0.35)'};">
        <div class="saving-card-header">
          <div class="saving-card-title-group">
            <div class="saving-badge-row">
              <span class="insurance-type-badge ${badgeClass}" style="${isTaxDeductible ? 'background:rgba(56,189,248,0.15);color:#38bdf8;' : 'background:rgba(16,185,129,0.15);color:#34d399;'}">${typeLabel}</span>
              <span class="payment-status-badge ${badgeClass}" style="${isTaxDeductible ? 'background:rgba(56,189,248,0.15);color:#38bdf8;' : 'background:rgba(16,185,129,0.15);color:#34d399;'}">${statusLabel}</span>
              <span class="saving-owner-badge">${html(a.owner || '모두')}</span>
            </div>
            <h3 class="saving-product-name">${html(a.name)}</h3>
            <span class="saving-bank-name">${html(a.broker)}</span>
          </div>
          <div class="account-row-actions saving-card-actions">
            <button class="account-action-button" data-account-edit-id="${a.id}" title="계좌 정보 수정" type="button">✎</button>
          </div>
        </div>

        <div class="saving-card-details">
          <div class="saving-detail-row">
            <span class="saving-detail-label">올해 납입액</span>
            <span class="saving-detail-val" style="color:#38bdf8;font-weight:700;">₩${number(dep, 0)}</span>
          </div>
          <div class="saving-detail-row">
            <span class="saving-detail-label">연간 납입한도</span>
            <span class="saving-detail-val">₩18,000,000</span>
          </div>
          <div class="saving-detail-row" style="grid-column:1/-1;">
            <span class="saving-detail-label">세액공제 한도</span>
            <span class="saving-detail-val">${isTaxDeductible ? `연금저축 600만 · 소유자 합산 900만 (소득구간 ${rate}%)` : '<span style="color:#34d399;">비공제 (원금 비과세 인출 대상)</span>'}</span>
          </div>
        </div>

        <div class="saving-interest-box" style="background:${isTaxDeductible ? 'rgba(56,189,248,0.08)' : 'rgba(16,185,129,0.08)'};border-color:${isTaxDeductible ? 'rgba(56,189,248,0.35)' : 'rgba(16,185,129,0.35)'};margin-top:8px;">
          <div class="saving-interest-row">
            <span style="color:${isTaxDeductible ? '#38bdf8' : '#34d399'};">소유자 합산 세액공제 대상</span>
            <span style="color:#e2e8f0;font-weight:600;">₩${number(totalTarget, 0)}${ownerCurrent.isaDeductionTarget > 0 ? ` (ISA 전환 추가 ₩${number(ownerCurrent.isaDeductionTarget, 0)})` : ''}</span>
          </div>
          <div class="saving-interest-row maturity-row" style="border-top:1px dashed ${isTaxDeductible ? 'rgba(56,189,248,0.3)' : 'rgba(16,185,129,0.3)'};padding-top:4px;margin-top:4px;">
            <span style="color:${isTaxDeductible ? '#38bdf8' : '#34d399'};">소유자 합산 예상 세금 절감(환급)액</span>
            <span style="color:#4ade80;font-size:14px;font-weight:700;">${isTaxDeductible ? `+₩${number(refund, 0)} (${rate}%)` : '₩0 (원금 100% 비과세 인출)'}</span>
          </div>
        </div>

        ${yearlyHistoryHtml}
      </div>
    `;
    }

    function umbrellaYearRow({ yYear, yDep, yDeductible, ySaved }) {
      return `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:3px 6px;border-radius:4px;font-size:11.5px;margin-bottom:3px;">
            <span><strong>${html(yYear)}년:</strong> 입금 ₩${number(yDep, 0)}</span>
            <span>➔ ${yDeductible ? `<strong style="color:#4ade80;">소득공제 절세 ₩${number(ySaved, 0)}</strong>` : '<span style="color:#34d399;font-weight:600;">비공제 (₩0)</span>'}</span>
          </div>
        `;
    }

    function productStart({ ins, isYU, typeKey, typeLabel, statusKey, statusLabel, periodText, yuTaxBox }) {
      return `
      <div class="saving-card ${isYU ? 'yellow-umbrella-card' : ''}">
        <div class="saving-card-header">
          <div class="saving-card-title-group">
            <div class="saving-badge-row">
              <span class="insurance-type-badge ${typeKey}">${typeLabel}</span>
              <span class="payment-status-badge ${statusKey}">${statusLabel}</span>
              <span class="saving-owner-badge">${html(ins.owner || '모두')}</span>
            </div>
            <h3 class="saving-product-name">${html(ins.product_name)}</h3>
            <span class="saving-bank-name">${html(ins.company_name)}</span>
          </div>
          <div class="account-row-actions saving-card-actions">
            <button class="account-action-button" data-insurance-edit-id="${ins.id}" title="수정" type="button">✎</button>
            <button class="mini-delete-button" data-insurance-del-id="${ins.id}" title="삭제" type="button">🗑️</button>
          </div>
        </div>

        <div class="saving-card-details">
          <div class="saving-detail-row">
            <span class="saving-detail-label">월 납입액</span>
            <span class="saving-detail-val" style="color:#38bdf8;">₩${number(ins.monthly_premium || 0, 0)}</span>
          </div>
          <div class="saving-detail-row">
            <span class="saving-detail-label">누적 납입액</span>
            <span class="saving-detail-val">₩${number(ins.total_paid_amount || 0, 0)}</span>
          </div>
          <div class="saving-detail-row" style="grid-column:1/-1;">
            <span class="saving-detail-label">계약 기간</span>
            <span class="saving-detail-val">${html(periodText)}</span>
          </div>
          ${ins.memo ? `
            <div class="saving-detail-row" style="grid-column:1/-1;">
              <span class="saving-detail-label">메모</span>
              <span class="saving-detail-val" style="color:#94a3b8;font-size:11px;">${html(ins.memo)}</span>
            </div>
          ` : ''}
        </div>

        ${yuTaxBox}
        `;
    }

    function productEnd({ ins, isYU }) {
      return `

        ${(ins.payout_type === 'monthly_pension' || (Number(ins.monthly_payout) || 0) > 0) ? `
          <div class="saving-interest-box" style="margin-top:10px;background:rgba(56,189,248,0.06);border-color:rgba(56,189,248,0.35);">
            <div class="saving-interest-row">
              <span style="color:#7dd3fc;">💎 월 예상 수령액</span>
              <span style="color:#38bdf8;font-weight:700;font-size:13.5px;">월 ₩${number(ins.monthly_payout || 0, 0)}</span>
            </div>
            <div class="saving-interest-row maturity-row" style="border-top:1px dashed rgba(56,189,248,0.3);padding-top:5px;margin-top:5px;">
              <span style="color:#e2e8f0;">총자산 환산액 (${ins.payout_duration_years || 20}년)</span>
              <span style="color:#4ade80;font-size:14.5px;font-weight:800;">₩${number(ins.expected_amount || ins.converted_total_asset || 0, 0)}</span>
            </div>
          </div>
        ` : `
          <div class="saving-interest-box" style="margin-top:${isYU ? '6px' : '10px'};">
            <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
              <span>예상 수령액 / 해약환급금</span>
              <span style="color:#42d5a3;font-size:14px;">₩${number(ins.expected_amount || 0, 0)}</span>
            </div>
          </div>
        `}
      </div>
    `;
    }

    function productCard(start, nationalHistoryMarkup, end) { return start + nationalHistoryMarkup + end; }

    function bindFormInputs({ $, insForm, updateYellowUmbrellaFields, updatePensionPayoutFields }) {
      const handleInsuranceFormChange = () => {
        updateYellowUmbrellaFields();
        updatePensionPayoutFields();
      };
      insForm.addEventListener("input", handleInsuranceFormChange);
      insForm.addEventListener("change", handleInsuranceFormChange);

      $("#insuranceTypeSelect")?.addEventListener("change", (e) => {
        if (e.target.value === "national_pension") {
          const pRadio = $("#payoutTypeMonthlyPension");
          if (pRadio) pRadio.checked = true;
          const compInput = insForm.querySelector("[name='company_name']");
          if (compInput && !compInput.value.trim()) compInput.value = "국민연금공단";
          const prodInput = insForm.querySelector("[name='product_name']");
          if (prodInput && !prodInput.value.trim()) prodInput.value = "국민연금 (노령연금)";
          updatePensionPayoutFields();
        }
      });
    }

    return Object.freeze({ bindFormInputs, productStart, productEnd, productCard, pensionYearRow, pensionCard, umbrellaYearRow });
  }
  window.WealthInsuranceView = Object.freeze({ create });
})();
