/* Banking presentation only. Filtering, aggregation and derived loan models remain in wealth.js. */
(() => {
  'use strict';

  function create({ $, document, html, number, maskBrokerAccountNo, getSavingsContributions }) {
    function renderSavingPreview({ principal, preTax, tax, maturity }) {
      if ($("#prevTotalPrincipal")) $("#prevTotalPrincipal").textContent = `₩${number(principal, 0)}`;
      if ($("#prevPreTaxInterest")) $("#prevPreTaxInterest").textContent = `₩${number(preTax, 0)}`;
      if ($("#prevTaxAmount")) $("#prevTaxAmount").textContent = `₩${number(tax, 0)}`;
      if ($("#prevMaturityTotal")) $("#prevMaturityTotal").textContent = `₩${number(maturity, 0)}`;
    }

    function renderBankMinusPreview({ debt, monthlyInt, utilPercent, limitInput }) {
      const intEl = $("#bankMinusMonthlyInterest");
      const utilEl = $("#bankMinusUtilPercent");

      if (intEl) {
        if (debt > 0) {
          intEl.textContent = `₩${number(monthlyInt, 0)}`;
          intEl.style.color = "#fb7185";
        } else {
          intEl.textContent = `₩0 (대출 미사용)`;
          intEl.style.color = "#38bdf8";
        }
      }

      if (utilEl) {
        if (limitInput > 0) {
          if (debt > 0) {
            utilEl.textContent = `${utilPercent}% (사용 ₩${number(debt, 0)} / 한도 ₩${number(limitInput, 0)})`;
            utilEl.style.color = utilPercent >= 80 ? "#fb7185" : "#38bdf8";
          } else {
            utilEl.textContent = `0% (한도 ₩${number(limitInput, 0)} 전액 잔여)`;
            utilEl.style.color = "#38bdf8";
          }
        } else {
          utilEl.textContent = `한도 미설정`;
          utilEl.style.color = "#94a3b8";
        }
      }
    }

    function renderLoanPreview({ curBal, rate, monthlyInterest, monthlyPayment }) {
      if (document.getElementById('prevLoanBalance')) {
        document.getElementById('prevLoanBalance').textContent = `₩${number(curBal, 0)}`;
      }
      if (document.getElementById('prevLoanRateText')) {
        document.getElementById('prevLoanRateText').textContent = rate.toFixed(2);
      }
      if (document.getElementById('prevLoanInterest')) {
        document.getElementById('prevLoanInterest').textContent = `₩${number(monthlyInterest, 0)}`;
      }
      if (document.getElementById('prevLoanMonthlyPayment')) {
        document.getElementById('prevLoanMonthlyPayment').textContent = `₩${number(monthlyPayment, 0)}`;
      }
    }

    function renderSavings(savingsGrid, savingsRows) {
    if (!savingsRows.length) {
      window.WealthOperationFeedback.renderEmpty(savingsGrid, '등록된 예·적금 상품이 없습니다. 상단 [🏦 계좌 추가]에서 예·적금을 선택하세요.', { fullWidth: true });
    } else {
      savingsGrid.innerHTML = savingsRows.map(({ s, withdrawName, depositName, curVal, progress, maturityValue }) => {
        const isHousing = s.saving_type === 'housing' || !s.end_date;
        const typeLabel = s.saving_type === 'housing' ? '주택청약' : (s.saving_type === 'deposit' ? '정기예금' : (s.saving_type === 'installment' ? '정기적금' : '자유적금'));
        const typeClass = s.saving_type === 'housing' ? 'housing' : (s.saving_type || 'deposit');
        const dDayText = isHousing ? '만기 없음' : (s.d_day != null ? (s.d_day <= 0 ? '만기 달성' : `D-${s.d_day}`) : '자유적립');
        const dDayClass = isHousing ? 'd-day-badge' : (s.d_day != null && s.d_day <= 0 ? 'd-day-badge done' : 'd-day-badge');

        const calc = s.calc || {};
        const taxLabel = s.tax_type === 'preferential' ? '세금우대 (1.4%)' : (s.tax_type === 'tax_free' ? '비과세 (0%)' : '일반과세 (15.4%)');

        const transferInfo = isHousing
          ? (s.monthly_amount > 0 ? (s.auto_transfer_day ? `매월 ${s.auto_transfer_day}일 이체 · 월 ₩${number(s.monthly_amount, 0)}` : `월 ₩${number(s.monthly_amount, 0)} 납입`) : '자유 납입')
          : (s.saving_type === 'deposit'
              ? `예치원금: ₩${number(s.target_amount || calc.total_principal || 0, 0)}`
              : (s.auto_transfer_day ? `매월 ${s.auto_transfer_day}일 이체 · 월 ₩${number(s.monthly_amount || 0, 0)}` : `월 ₩${number(s.monthly_amount || 0, 0)}`));

        return `
          <div class="saving-card ${isHousing ? 'housing-card' : ''}" data-order-id="${html(s.id || '')}" data-order-institution="${html(s.bank_name || '기타')}" data-order-label="${html(s.product_name || '예·적금')}">
            <div class="saving-card-header">
              <div class="saving-card-title-group">
                <div class="saving-badge-row">
                  <span class="saving-type-badge ${typeClass}">${typeLabel}</span>
                  <span class="saving-owner-badge">${html(s.owner || '모두')}</span>
                  ${dDayText ? `<span class="${dDayClass}">${dDayText}</span>` : ''}
                </div>
                <h3 class="saving-product-name">${html(s.product_name)}</h3>
                <span class="saving-bank-name">${html(s.bank_name)}</span>
              </div>
              <div class="account-row-actions saving-card-actions">
                <button class="account-action-button" data-saving-edit-id="${html(s.id)}" title="수정" type="button">✎</button>
                <button class="mini-delete-button" data-saving-del-id="${html(s.id)}" title="삭제" type="button">🗑️</button>
              </div>
            </div>

            <!-- 진행률 프로그레스 바 -->
            <div class="saving-progress-wrap">
              <div class="saving-progress-meta">
                <span>${isHousing ? `불입 현황 (${s.start_date || '가입일'} ~ 만기 없음${s.elapsed_months ? ` · ${s.elapsed_months}개월 경과` : ''})` : `진행률 (${s.start_date || '가입'} ~ ${s.end_date || '만기'})`}</span>
                <strong>${isHousing ? '진행중' : `${s.progress_percent || 0}%`}</strong>
              </div>
              <div class="saving-progress-track">
                <div class="saving-progress-bar" style="width: ${progress}%;"></div>
              </div>
            </div>

            <!-- 세부 정보 그리드 -->
            <div class="saving-card-details">
              <div class="saving-detail-row">
                <span class="saving-detail-label">약정 금리</span>
                <span class="saving-detail-val" style="color:#38bdf8;">연 ${s.interest_rate}%</span>
              </div>
              <div class="saving-detail-row">
                <span class="saving-detail-label">계약 기간</span>
                <span class="saving-detail-val">${isHousing ? '자유 / 무기한' : `${s.duration_months}개월`}</span>
              </div>
              <div class="saving-detail-row" style="grid-column:1/-1;">
                <span class="saving-detail-label">납입 조건</span>
                <span class="saving-detail-val">${transferInfo}</span>
              </div>
              <div class="saving-detail-row">
                <span class="saving-detail-label">출금 통장</span>
                <span class="saving-detail-val" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${html(withdrawName)}">${html(withdrawName)}</span>
              </div>
              <div class="saving-detail-row">
                <span class="saving-detail-label">만기 입금</span>
                <span class="saving-detail-val" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${html(depositName)}">${html(depositName)}</span>
              </div>
            </div>

            <!-- 세전·세후 이자 하이라이트 박스 -->
            <div class="saving-interest-box" style="${isHousing ? 'background:rgba(56,189,248,0.06);border-color:rgba(56,189,248,0.25);' : ''}">
              <div class="saving-interest-row">
                <span style="color:#8fa0c5;">${isHousing ? '현재 누적 납입원금' : '총 불입원금'}</span>
                <span style="color:#e2e8f0;font-weight:600;">₩${number(isHousing ? curVal : (calc.total_principal || 0), 0)}</span>
              </div>
              <div class="saving-interest-row">
                <span style="color:#8fa0c5;">${isHousing ? '연간 예상 이자' : '세전 이자'}</span>
                <span style="color:#38bdf8;font-weight:600;">+₩${number(calc.pre_tax_interest || 0, 0)}</span>
              </div>
              <div class="saving-interest-row">
                <span style="color:#8fa0c5;">소득세 (${taxLabel})</span>
                <span style="color:#f43f5e;font-weight:600;">-₩${number(calc.tax_amount || 0, 0)}</span>
              </div>
              <div class="saving-interest-row maturity-row">
                <span>${isHousing ? '현재 평가액 (원금+세후이자)' : '만기 예상 실수령액'}</span>
                <span style="color:#42d5a3;font-size:14px;">₩${number(maturityValue, 0)}</span>
              </div>
            </div>
            ${getSavingsContributions()?.card(s) || ''}
          </div>
        `;
      }).join("");
    }
    }

    function renderBanks(banksWrap, bankRows) {
    if (!bankRows.length) {
      window.WealthOperationFeedback.renderEmpty(banksWrap, '등록된 자유입출금 통장이 없습니다. 상단 [🏦 계좌 추가]에서 자유입출금 통장을 선택하세요.');
    } else {
      banksWrap.innerHTML = `
        <table class="banks-table">
          <thead>
            <tr>
              <th>은행</th>
              <th>계좌 이름</th>
              <th>계좌 번호</th>
              <th>소유자</th>
              <th style="text-align:right;">잔고 (KRW)</th>
              <th>메모</th>
              <th style="text-align:center;">관리</th>
            </tr>
          </thead>
          <tbody>
            ${bankRows.map(({ b, bal, isMinus }) => {
              const formattedBal = isMinus ? `-₩${number(Math.abs(bal), 0)}` : `₩${number(bal, 0)}`;
              const balStyle = isMinus ? 'color:#fb7185;font-weight:700;' : 'color:#38bdf8;font-weight:700;';
              const minusBadge = isMinus ? '<span class="saving-type-badge loan-minus" style="font-size:10px;padding:2px 6px;margin-left:6px;vertical-align:middle;">🔴 마통</span>' : '';

              return `
                <tr data-order-id="${html(b.id || '')}" data-order-institution="${html(b.bank_name || '기타')}" data-order-label="${html(b.account_name || '통장')}" style="${isMinus ? 'background:rgba(244,63,94,0.03);' : ''}">
                  <td><strong>${html(b.bank_name)}</strong></td>
                  <td>${html(b.account_name)}${minusBadge}</td>
                  <td style="color:#8fa0c5;font-family:monospace;">${html(maskBrokerAccountNo(b.account_number) || '-')}</td>
                  <td><span class="saving-owner-badge">${html(b.owner || '모두')}</span></td>
                  <td style="text-align:right;${balStyle}">${formattedBal}</td>
                  <td style="color:#8fa0c5;font-size:11.5px;">${html(b.memo || '')}</td>
                  <td style="text-align:center;">
                    <div class="account-row-actions" style="justify-content:center;">
                      <button class="account-action-button" data-bank-edit-id="${html(b.id)}" title="통장 수정" type="button">✎</button>
                      <button class="mini-delete-button" data-bank-del-id="${html(b.id)}" title="통장 삭제" type="button">🗑️</button>
                    </div>
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      `;
    }
    }

    function renderLoans(loansGrid, loanRows, LOAN_TYPE_LABELS, REPAYMENT_TYPE_LABELS) {
    if (!loanRows.length) {
      window.WealthOperationFeedback.renderEmpty(loansGrid, '등록된 대출 또는 마이너스통장이 없습니다. 상단 [💳 대출 추가] 버튼을 눌러보세요.', { fullWidth: true });
    } else {
      loansGrid.innerHTML = loanRows.map(({ l, curBal, limitAmt, monthlyInt, monthlyPay, utilPercent, linkedAccountText, isUnusedMinus }) => {
        const typeLabel = l.is_from_bank ? "자유연동 마통" : (LOAN_TYPE_LABELS[l.loan_type] || "대출");
        const repayLabel = REPAYMENT_TYPE_LABELS[l.repayment_type] || "만기일시";
        const dDayText = l.d_day != null ? (l.d_day <= 0 ? "만기 경과" : `만기 D-${l.d_day}`) : "";
        const dDayClass = l.d_day != null && l.d_day <= 0 ? "d-day-badge done" : "d-day-badge";

        const editAttr = l.is_from_bank ? `data-bank-edit-id="${html(l.id)}"` : `data-loan-edit-id="${html(l.id)}"`;
        const delAttr = l.is_from_bank ? `data-bank-del-id="${html(l.id)}"` : `data-loan-del-id="${html(l.id)}"`;


        return `
          <div class="saving-card loan-card ${isUnusedMinus ? 'unused-minus-card' : ''}" data-order-id="${html(l.id || '')}" data-order-institution="${html(l.bank_name || '기타')}" data-order-label="${html(l.product_name || '대출')}" data-order-derived="${l.is_from_bank ? 'true' : 'false'}">
            <div class="saving-card-header">
              <div class="saving-card-title-group">
                <div class="saving-badge-row">
                  ${isUnusedMinus ? `
                    <span class="saving-type-badge loan-credit" style="background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);">🟢 자유연동 마통 (미사용)</span>
                  ` : `
                    <span class="saving-type-badge ${l.loan_type === 'minus' ? 'loan-minus' : 'loan-credit'}">${typeLabel}</span>
                  `}
                  <span class="saving-owner-badge">${html(l.owner || '모두')}</span>
                  ${dDayText ? `<span class="${dDayClass}">${dDayText}</span>` : ''}
                </div>
                <h3 class="saving-product-name">${html(l.product_name)}</h3>
                <span class="saving-bank-name">${html(l.bank_name)}</span>
              </div>
              <div class="account-row-actions saving-card-actions">
                <button class="account-action-button" ${editAttr} title="수정" type="button">✎</button>
                <button class="mini-delete-button" ${delAttr} title="삭제" type="button">🗑️</button>
              </div>
            </div>

            ${l.loan_type === 'minus' && limitAmt > 0 ? `
              <div class="saving-progress-wrap">
                <div class="saving-progress-meta">
                  <span>한도 소진율 (한도: ₩${number(limitAmt, 0)})</span>
                  <strong style="color:${utilPercent >= 80 ? '#fb7185' : '#38bdf8'};">${utilPercent}% ${isUnusedMinus ? '(전액 잔여)' : ''}</strong>
                </div>
                <div class="saving-progress-track">
                  <div class="saving-progress-bar" style="width: ${utilPercent}%; background: ${utilPercent >= 80 ? '#fb7185' : '#38bdf8'};"></div>
                </div>
              </div>
            ` : (l.is_from_bank ? `
              <div style="font-size:11px;color:#94a3b8;background:rgba(255,255,255,0.03);padding:6px 10px;border-radius:6px;margin:8px 0 4px;display:flex;justify-content:space-between;align-items:center;">
                <span>마통 한도 미설정</span>
                <button type="button" ${editAttr} style="background:none;border:none;color:#38bdf8;cursor:pointer;font-size:11px;padding:0;text-decoration:underline;">한도/금리 설정 ✎</button>
              </div>
            ` : '')}

            <div class="saving-card-details">
              <div class="saving-detail-row">
                <span class="saving-detail-label">약정 금리</span>
                <span class="saving-detail-val" style="${l.interest_rate > 0 ? (isUnusedMinus ? 'color:#38bdf8;font-weight:700;' : 'color:#fb7185;font-weight:700;') : 'color:#94a3b8;font-size:11px;'}">${l.interest_rate > 0 ? `연 ${l.interest_rate}%` : (l.is_from_bank ? '미설정 (✎ 수정)' : '-')}</span>
              </div>
              ${monthlyInt > 0 ? `
                <div class="saving-detail-row">
                  <span class="saving-detail-label">월 예상 이자</span>
                  <span class="saving-detail-val" style="color:#fb7185;font-weight:700;">₩${number(monthlyInt, 0)}</span>
                </div>
              ` : (isUnusedMinus ? `
                <div class="saving-detail-row">
                  <span class="saving-detail-label">월 예상 이자</span>
                  <span class="saving-detail-val" style="color:#38bdf8;font-weight:700;">₩0 (미발생)</span>
                </div>
              ` : '')}
              <div class="saving-detail-row">
                <span class="saving-detail-label">상환 방식</span>
                <span class="saving-detail-val">${l.is_from_bank ? '자유잔고 차감' : repayLabel}</span>
              </div>
              ${!l.is_from_bank && l.linked_account_id ? `
                <div class="saving-detail-row">
                  <span class="saving-detail-label">이자 출금 통장</span>
                  <span class="saving-detail-val" style="font-size:11px;">${html(linkedAccountText)}</span>
                </div>
              ` : ''}
              ${l.maturity_date ? `
                <div class="saving-detail-row" style="grid-column:1/-1;">
                  <span class="saving-detail-label">만기일</span>
                  <span class="saving-detail-val">${html(l.maturity_date)}</span>
                </div>
              ` : ''}
              ${l.memo ? `
                <div class="saving-detail-row" style="grid-column:1/-1;">
                  <span class="saving-detail-label">메모</span>
                  <span class="saving-detail-val" style="color:#94a3b8;font-size:11px;">${html(l.memo)}</span>
                </div>
              ` : ''}
            </div>

            ${isUnusedMinus ? `
              <div class="saving-interest-box" style="background:rgba(56,189,248,0.06);border-color:rgba(56,189,248,0.25);">
                <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
                  <span style="color:#38bdf8;font-weight:600;">현재 대출 잔액</span>
                  <span style="color:#38bdf8;font-size:15px;font-weight:700;">₩0 (대출 미사용)</span>
                </div>
                <div class="saving-interest-row" style="padding-top:4px;font-size:11px;color:#94a3b8;">
                  <span>자유통장 잔고 유지중</span>
                  <span style="color:#38bdf8;font-weight:600;">+₩${number(l.raw_balance || 0, 0)}</span>
                </div>
              </div>
            ` : `
              <div class="saving-interest-box" style="background:rgba(244,63,94,0.06);border-color:rgba(244,63,94,0.2);">
                <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
                  <span style="color:#fb7185;font-weight:600;">현재 대출 잔액 (부채)</span>
                  <span style="color:#fb7185;font-size:15px;font-weight:700;">₩${number(curBal, 0)}</span>
                </div>
                ${l.repayment_type === 'amortizing' ? `
                  <div class="saving-interest-row" style="padding-top:4px;font-size:11px;color:#94a3b8;">
                    <span>월 총 상환액 (원금+이자)</span>
                    <span>₩${number(monthlyPay, 0)}</span>
                  </div>
                ` : ''}
              </div>
            `}
          </div>
        `;
      }).join("");
    }
    }

    return Object.freeze({ renderSavings, renderBanks, renderLoans, renderSavingPreview, renderBankMinusPreview, renderLoanPreview });
  }
  window.WealthBankingView = Object.freeze({ create });
})();
