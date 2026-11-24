(() => {
  "use strict";

  function create(app) {
    let rawInsuranceAccounts = [];

    const INSURANCE_TYPE_LABELS = {
      protection: "보장성보험",
      savings: "저축성보험",
      national_pension: "국민연금",
      yellow_umbrella: "노란우산공제",
      irp: "개인연금 / IRP",
      etc: "기타 공제",
    };

    const PAYMENT_STATUS_LABELS = {
      paying: "납입중",
      completed: "납입완료",
      deferred: "거치중",
    };

    function renderAssetTaxInformation() {
      const panel=document.getElementById('catPanelTax');if(!panel)return;
      let information=panel.querySelector('#assetTaxInformation');
      if(!information){
        information=document.createElement('div');information.id='assetTaxInformation';
        panel.prepend(information);
      }
      // This renderer owns product information only, not the independent tax tools.
      information.replaceChildren();
      const intro=document.createElement('p');intro.className='dialog-description';
      intro.textContent='소득공제와 세액공제는 서로 다른 제도입니다. 확인된 입력과 기존 계산 화면을 구분하여 확인하세요. 이 화면은 세금을 새로 계산하지 않습니다.';information.append(intro);
      const accounts=(app.rawDashboard?.accounts||[]).filter(item=>app.isTaxAdvantagedAccount(item));
      const insurances=rawInsuranceAccounts.filter(item=>['national_pension','yellow_umbrella','pension','irp'].includes(item.insurance_type));
      [...insurances,...accounts].filter(item=>app.currentOwner==='모두'||(item.owner||'모두')===app.currentOwner).forEach(item=>{
        const card=document.createElement('article');card.className='np-tax-card';
        const title=document.createElement('h3');title.textContent=item.product_name||item.name||'연금 상품';card.append(title);
        const text=document.createElement('p');
        const national=item.insurance_type==='national_pension', umbrella=item.insurance_type==='yellow_umbrella';
        text.textContent=national?'국민연금: 연금보험료 소득공제. 실제 본인 인정액과 해당 연도 과세표준이 필요합니다.':umbrella?'노란우산: 소득공제. 기존 소유자별 공제 한도·세금 계산을 유지합니다.':'연금저축·IRP: 세액공제. 국민연금 소득공제와 합산하지 않습니다. ISA는 별도 비과세·분리과세 제도입니다.';card.append(text);
        if(!national){
          const note=document.createElement('p');
          note.textContent=`공제 설정: ${item.tax_deductible===false?'비공제':item.tax_deductible===true?'공제 대상 설정':'확인 필요'} · 연간 납입 참고값 ${item.annual_deposit==null?'미확인':app.number(item.annual_deposit,0)+'원'}`;card.append(note);
          (item.yearly_contributions||[]).forEach(row=>{const line=document.createElement('p');line.textContent=`${row.year}년 납부액 ${row.deposit==null?'미확인':app.number(row.deposit,0)+'원'} · ${row.is_deductible===false?'비공제':'개별 인정 한도·신고 자료 확인 필요'}`;card.append(line);});
        }
        if(national){
          const button=document.createElement('button');button.type='button';button.className='button secondary compact';
          button.dataset.nationalAnalysisId=item.id;button.textContent='가입유형·세금·수익 분석';card.append(button);
          (item.national_pension_analysis?.tax_years||[]).forEach(row=>{
            const note=document.createElement('p');note.textContent=`${row.year}년 · 인정 공제액 ${row.allowed_deduction==null?'미확인':app.number(row.allowed_deduction,0)+'원'} · ${row.source==='tax_return'&&row.verified?'신고 자료 확인':'신고 확인 미완료'}`;card.append(note);
          });
        }
        information.append(card);
      });
      if(!information.querySelector('article')){const empty=document.createElement('p');empty.textContent='등록된 연금·공제 상품이 없습니다.';information.append(empty);}
    }

    function nationalPensionHistoryMarkup(ins) {
      const records = Array.isArray(ins.yearly_contributions) ? ins.yearly_contributions : [];
      const malformed = (ins.yearly_contributions != null && !Array.isArray(ins.yearly_contributions)) ||
        records.some(row => !row || !/^\d{4}$/.test(String(row.year)) || Number(row.year) < 1988 || Number(row.year) > new Date().getFullYear() || !Number.isFinite(row.deposit) || row.deposit < 0) ||
        new Set(records.map(row => String(row.year))).size !== records.length;
      if (malformed) return '<p class="np-history">등록 납부 이력 형식을 확인해 주세요. 합계는 산정하지 않았습니다.</p>';
      const byYear = new Map(records.map(row => [String(row.year), row.deposit]));
      const currentYear = new Date().getFullYear();
      const firstYear = Math.min(2013, ...records.map(row => Number(row.year)).filter(year => year >= 1988 && year <= currentYear));
      const total = records.reduce((sum, row) => sum + (Number.isFinite(row.deposit) && row.deposit >= 0 ? row.deposit : 0), 0);
      const paid = Number(ins.total_paid_amount);
      const difference = Number.isFinite(paid) ? total - paid : null;
      const rows = [];
      for (let year = currentYear; year >= firstYear; year--) {
        const amount = byYear.get(String(year));
        const text = !byYear.has(String(year)) ? '미확인' : amount === 0 ? '납부 없음 (0원)' : `₩${app.number(amount, 0)}`;
        rows.push(`<div class="np-history-line"><span>${year}년</span><span>${text}</span></div>`);
      }
      return `<div class="np-card-actions">
    <button type="button" class="button secondary compact" data-national-history-id="${app.html(ins.id)}">납부 이력 편집</button>
    <button type="button" class="button secondary compact" data-national-analysis-id="${app.html(ins.id)}">가입유형·세금·수익 분석</button>
    <button type="button" class="button secondary compact" data-national-import-id="${app.html(ins.id)}">📄 국민연금 자료 가져오기 · PDF·사진</button>
    </div><details class="np-history"><summary>연도별 실제 납부 이력 · ${records.length}건</summary>
    <p>입력 이력 합계 ₩${app.number(total, 0)} · 기존 누적납입액 ₩${app.number(ins.total_paid_amount || 0, 0)}</p>
    <p>${difference === null ? '기존 누적납입액 확인 필요' : difference === 0 ? '기존 누적납입액과 일치' : `입력 이력과 누적납입액 차이 ₩${app.number(difference, 0)} (자동 변경 없음)`}</p>
    <p>미확인은 미입력 연도입니다. 첫해·당해연도 금액은 확인한 부분 납부액 그대로 기록합니다.</p>
    <div class="np-history-list">${rows.join('')}</div></details>`;
    }

    let nationalPensionHistoryItem = null;
    let nationalPensionHistoryOriginal = [];
    let nationalPensionRowCounter = 0;
    let nationalPensionHistorySaving = false;
    function addNationalPensionHistoryRow(record = {}) {
      const list = document.getElementById('nationalPensionYearlyList');
      const id = ++nationalPensionRowCounter;
      const row = document.createElement('div'); row.className = 'np-history-edit-row';
      row.innerHTML = `<label for="npYear${id}">연도<input id="npYear${id}" data-np-year type="number" min="1988" max="${new Date().getFullYear()}" step="1" placeholder="2013"></label>
    <label for="npAmount${id}">실제 납부액<input id="npAmount${id}" data-np-amount type="number" min="0" step="any" data-korean-currency placeholder="미확인: 비워 두기"></label>
    <button type="button" class="button secondary compact" aria-label="납부 이력 행 삭제">삭제</button>`;
      row.querySelector('[data-np-year]').value = record.year ?? '';
      row.querySelector('[data-np-amount]').value = record.deposit ?? '';
      row.querySelector('button').onclick = () => { if (confirm('이 연도의 납부 이력을 삭제할까요? 저장 전까지 실제 기록은 유지됩니다.')) row.remove(); };
      list.append(row);
      app.refreshDialogKoreanHints(document.getElementById('nationalPensionHistoryDialog'));
    }
    function openNationalPensionHistory(ins, { showImport = false } = {}) {
      if (!ins?.id) { app.toast('상품을 먼저 저장해 주세요.'); return; }
      if (nationalPensionHistorySaving) { app.toast('납부 이력 저장이 진행 중입니다. 잠시 후 다시 열어 주세요.'); return; }
      nationalPensionHistoryItem = ins;
      nationalPensionHistoryOriginal = structuredClone(ins.yearly_contributions || []);
      nationalPensionRowCounter = 0;
      document.getElementById('nationalPensionYearlyList').replaceChildren();
      nationalPensionHistoryOriginal.forEach(addNationalPensionHistoryRow);
      document.getElementById('nationalPensionHistoryNotice').textContent = `기존 누적납입액 ₩${app.number(ins.total_paid_amount || 0, 0)}는 이력 저장으로 변경되지 않습니다. 연금 개시일은 납부 종료일로 사용하지 않습니다.`;
      document.getElementById('nationalPensionHistoryDialog').showModal();
      window.WealthNationalPension?.open(ins);
      window.WealthPensionImport?.open(ins, { showPanel: showImport });
    }
    function readNationalPensionHistoryRows() {
      const result = [], years = new Set(), currentYear = new Date().getFullYear();
      document.querySelectorAll('#nationalPensionYearlyList .np-history-edit-row').forEach(row => {
        const year = row.querySelector('[data-np-year]').value.trim();
        const raw = row.querySelector('[data-np-amount]').value.trim();
        if (!year && !raw) return;
        const amount = Number(raw);
        if (!/^\d{4}$/.test(year) || Number(year) < 1988 || Number(year) > currentYear || years.has(year)) throw new Error('1988년부터 당해연도까지 중복 없는 연도를 입력하세요.');
        if (!raw || !Number.isFinite(amount) || amount < 0) throw new Error('실제 납부액을 입력하세요. 납부 없음은 0원, 미확인은 행을 추가하지 않습니다.');
        years.add(year); result.push({year, deposit: amount});
      });
      return result;
    }

    function hasUnsavedNationalPensionHistory() {
      return JSON.stringify(readNationalPensionHistoryRows()) !== JSON.stringify(nationalPensionHistoryOriginal);
    }

    const insuranceView = window.WealthInsuranceView.create({ html: app.html, number: app.number });

    function renderInsurance(insuranceList, owner = '모두') {
      rawInsuranceAccounts = insuranceList || [];
      renderInsuranceWithOwner(owner);
    }

    function renderInsuranceWithOwner(owner = '모두') {
      if(app.currentAccountCategory==='tax')renderAssetTaxInformation();
      const o = owner || app.currentOwner || '모두';
      const filtered = window.WealthDashboardOwnerModel.selectOwnedAccounts(rawInsuranceAccounts, o);

      const totalMonthly = filtered.reduce((sum, i) => sum + (Number(i.monthly_premium) || 0), 0);
      const totalPaid = filtered.reduce((sum, i) => sum + (Number(i.total_paid_amount) || 0), 0);
      const totalExpected = filtered.reduce((sum, i) => sum + (Number(i.expected_amount) || 0), 0);

      if (app.$("#totalInsuranceMonthlyVal")) app.$("#totalInsuranceMonthlyVal").textContent = `₩${app.number(totalMonthly, 0)}`;
      if (app.$("#totalInsurancePaidVal")) app.$("#totalInsurancePaidVal").textContent = `₩${app.number(totalPaid, 0)}`;
      if (app.$("#totalInsuranceExpectedVal")) app.$("#totalInsuranceExpectedVal").textContent = `₩${app.number(totalExpected, 0)}`;


      const grid = app.$("#insuranceGrid");
      if (!grid) return;

      // 상단 절세 요약 배너 업데이트
      let totalCumulativeYuTaxSaved = 0;
      const yuTaxSaved = filtered.filter(i => (i.insurance_type === 'yellow_umbrella' || (i.product_name || '').includes('노란우산'))).reduce((sum, i) => {
        const monthly = Number(i.monthly_premium) || 0;
        const bracket = i.income_bracket || '40m_to_100m';
        const rate = Number(i.marginal_tax_rate) || 26.4;
        const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
        const limit = limits[bracket] || 3000000;
        const deduction = Math.min(monthly * 12, limit);
        const saved = Math.floor(deduction * (rate / 100));

        // 누적 절세액 합산
        const yuList = Array.isArray(i.yearly_contributions) ? i.yearly_contributions : [];
        if (yuList.length > 0) {
          yuList.forEach(y => {
            const isDed = y.is_deductible !== false && String(y.is_deductible) !== 'false';
            if (isDed) {
              totalCumulativeYuTaxSaved += Math.floor(Math.min(Number(y.deposit || 0), limit) * (rate / 100));
            }
          });
        } else {
          totalCumulativeYuTaxSaved += saved;
        }

        return sum + saved;
      }, 0);

      // 증권 계좌 연금/IRP 절세액 합산
      const secAccounts = (app.dashboard?.accounts || []).filter(a => o === '모두' || (a.owner || '모두') === o);
      const pensionTaxBenefits = app.calculateOwnerYearPensionTaxBenefits(secAccounts);
      const pensionTaxSaved = pensionTaxBenefits.current.taxSaved;
      const totalCumulativePensionTaxSaved = pensionTaxBenefits.cumulative.taxSaved;

      const grandTotalTax = yuTaxSaved + pensionTaxSaved;
      const grandCumulativeTax = totalCumulativeYuTaxSaved + totalCumulativePensionTaxSaved;
      if (app.$("#grandTotalTaxBenefitVal")) {
        if (grandCumulativeTax > grandTotalTax) {
          app.$("#grandTotalTaxBenefitVal").innerHTML = `₩${app.number(grandTotalTax, 0)} <span style="font-size:12px;color:#a78bfa;font-weight:600;">(누적 ₩${app.number(grandCumulativeTax, 0)})</span>`;
        } else {
          app.$("#grandTotalTaxBenefitVal").textContent = `₩${app.number(grandTotalTax, 0)}`;
        }
      }

      // 증권 계좌 연금저축 & IRP 카드 생성
      const secPensionAccounts = (app.dashboard?.accounts || []).filter(a => {
        if (o !== '모두' && (a.owner || '모두') !== o) return false;
        return app.isTaxAdvantagedAccount(a) && app.getTaxCategory(a) !== 'isa';
      });

      const pensionCardsHtml = secPensionAccounts.map(a => {
        const aType = app.getTaxCategory(a);
        const isTaxDeductible = app.isAccountTaxDeductible(a);
        const dep = Number(a.annual_deposit) || 0;
        const rate = a.income_level === 'high' ? 13.2 : 16.5;
        const ownerKey = String(a.owner || '모두');
        const ownerCurrent = pensionTaxBenefits.current.byOwner[ownerKey] || { eligibleContribution: 0, isaDeductionTarget: 0, taxSaved: 0 };
        const ownerCumulative = pensionTaxBenefits.cumulative.byOwner[ownerKey] || { taxSaved: 0 };
        const totalTarget = ownerCurrent.eligibleContribution + ownerCurrent.isaDeductionTarget;
        const refund = ownerCurrent.taxSaved;

        const typeLabel = aType === 'pension_savings' ? '연금저축' : '개인형 IRP';
        const badgeClass = isTaxDeductible ? 'pension' : 'non-deductible';
        const statusLabel = isTaxDeductible ? '세액공제 신청' : '세액공제 제외(비공제)';

        const yearlyContributions = Array.isArray(a.yearly_contributions) ? a.yearly_contributions : [];
        let yearlyHistoryHtml = '';

        if (yearlyContributions.length > 0) {
          const yearlyRows = yearlyContributions.map(yc => {
            const yYear = String(yc.year || '').trim();
            const yDep = Number(yc.deposit || 0);
            const yDeductible = isTaxDeductible && app.isContributionTaxDeductible(yc.is_deductible);
            const ownerYear = pensionTaxBenefits.cumulative.byOwnerYear[`${ownerKey}\u0000${yYear}`] || { taxSaved: 0 };
            const ySaved = yDeductible ? ownerYear.taxSaved : 0;

            return insuranceView.pensionYearRow({ yYear, yDep, yDeductible, ySaved });
          }).join('');

          yearlyHistoryHtml = `
        <div class="insurance-yearly-history" style="margin-top:10px;padding:8px 10px;border:1px solid ${isTaxDeductible ? 'rgba(56,189,248,0.25)' : 'rgba(16,185,129,0.25)'};border-radius:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-size:11.5px;">
            <span style="font-weight:700;color:${isTaxDeductible ? '#38bdf8' : '#34d399'};">📅 연도별 절세 이력</span>
            <span style="font-weight:700;color:#4ade80;font-size:12px;">소유자 합산 누적: ₩${app.number(ownerCumulative.taxSaved, 0)}</span>
          </div>
          ${yearlyRows}
        </div>
      `;
        }

        return insuranceView.pensionCard({ a, isTaxDeductible, badgeClass, typeLabel, statusLabel, dep, rate, totalTarget, ownerCurrent, refund, yearlyHistoryHtml });
      }).join('');

      const insuranceCardsHtml = filtered.map(ins => {
        const typeKey = ins.insurance_type || 'protection';
        const typeLabel = INSURANCE_TYPE_LABELS[typeKey] || '보험/공제';
        const statusKey = ins.payment_status || 'paying';
        const statusLabel = PAYMENT_STATUS_LABELS[statusKey] || '납입중';

        const periodText = typeKey === 'national_pension'
          ? `가입 ${ins.start_date || '미지정'} · 연금개시 예정 ${ins.maturity_date || '미지정'}`
          : (ins.start_date || ins.maturity_date)
          ? `${ins.start_date || '가입'} ~ ${ins.maturity_date || '만기'}`
          : '기간 미지정';

        const isYU = typeKey === 'yellow_umbrella' || (ins.product_name || '').includes('노란우산');
        let yuTaxBox = '';
        let yuYearlyRowsHtml = '';
        if (isYU) {
          const monthly = Number(ins.monthly_premium) || 0;
          const bracket = ins.income_bracket || '40m_to_100m';
          const rate = Number(ins.marginal_tax_rate) || 26.4;
          const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
          const limit = limits[bracket] || 3000000;
          const deduction = Math.min(monthly * 12, limit);
          const taxSaved = Math.floor(deduction * (rate / 100));

          const yuYearlyList = Array.isArray(ins.yearly_contributions) ? ins.yearly_contributions : [];
          let yuCumulativeSaved = 0;

          if (yuYearlyList.length > 0) {
            const rows = yuYearlyList.map(yc => {
              const yYear = String(yc.year || '').trim();
              const yDep = Number(yc.deposit || 0);
              const yDeductible = yc.is_deductible !== false && String(yc.is_deductible) !== 'false';
              const yTarget = yDeductible ? Math.min(yDep, limit) : 0;
              const ySaved = yDeductible ? Math.floor(yTarget * (rate / 100)) : 0;
              if (yDeductible) yuCumulativeSaved += ySaved;

              return insuranceView.umbrellaYearRow({ yYear, yDep, yDeductible, ySaved });
            }).join('');

            yuYearlyRowsHtml = `
          <div class="insurance-yearly-history" style="margin-top:10px;padding:8px 10px;border:1px solid rgba(234,179,8,0.3);border-radius:6px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-size:11.5px;">
              <span style="font-weight:700;color:#facc15;">📅 연도별 소득공제 이력</span>
              <span style="font-weight:700;color:#4ade80;font-size:12px;">누적 절세액: ₩${app.number(yuCumulativeSaved, 0)}</span>
            </div>
            ${rows}
          </div>
        `;
          } else {
            yuCumulativeSaved = taxSaved;
          }

          yuTaxBox = `
        <div class="saving-interest-box" style="background:rgba(234,179,8,0.08);border-color:rgba(234,179,8,0.35);margin-top:8px;">
          <div class="saving-interest-row">
            <span style="color:#facc15;">연간 소득공제 대상</span>
            <span class="saving-detail-val" style="font-weight:600;">₩${app.number(deduction, 0)} (한도 ₩${app.number(limit, 0)})</span>
          </div>
          <div class="saving-interest-row maturity-row" style="border-top:1px dashed rgba(234,179,8,0.3);padding-top:4px;margin-top:4px;">
            <span style="color:#facc15;">예상 세금 절감(환급)액</span>
            <span style="color:#4ade80;font-size:14px;font-weight:700;">+₩${app.number(taxSaved, 0)} (${rate}%)</span>
          </div>
        </div>
        ${yuYearlyRowsHtml}
      `;
        }

        return insuranceView.productCard(insuranceView.productStart({ ins, isYU, typeKey, typeLabel, statusKey, statusLabel, periodText, yuTaxBox }), typeKey === 'national_pension' ? nationalPensionHistoryMarkup(ins) : '', insuranceView.productEnd({ ins, isYU }));
      }).join('');

      grid.innerHTML = (pensionCardsHtml + insuranceCardsHtml) || '<div class="empty">등록된 보험/연금 상품이 없습니다.</div>';
    }

    function updatePensionPayoutFields() {
      const isPension = app.$("#payoutTypeMonthlyPension")?.checked;
      const lumpSumGroup = app.$("#lumpSumAmountGroup");
      const pensionGroup = app.$("#pensionPayoutGroup");

      if (lumpSumGroup) lumpSumGroup.style.display = isPension ? "none" : "block";
      if (pensionGroup) pensionGroup.style.display = isPension ? "block" : "none";

      if (isPension) {
        const monthly = Number(app.$("#pensionMonthlyPayout")?.value) || 0;
        const years = Number(app.$("#pensionDurationSelect")?.value) || 20;
        const totalMonths = Math.round(years * 12);
        const converted = Math.round(monthly * totalMonths);

        if (app.$("#pensionDurationText")) {
          app.$("#pensionDurationText").textContent = `${years}년 (${totalMonths}개월)`;
        }
        if (app.$("#pensionConvertedTotalText")) {
          app.$("#pensionConvertedTotalText").textContent = `₩${app.number(converted, 0)}`;
        }
        // 일시금 필드에도 동기화하여 안전자산 및 호환성 보장
        if (app.$("#insuranceExpectedAmount")) {
          app.$("#insuranceExpectedAmount").value = converted > 0 ? converted : "";
        }
      }
    }

    let yuCurrentYearlyList = [];

    function renderYuYearlyFormRows(form = document.getElementById("insuranceAccountForm")) {
      const container = form?.querySelector("#yuYearlyList");
      if (!container) return;

      const bracket = form.querySelector("#yuIncomeBracket")?.value || "40m_to_100m";
      const rate = Number(form.querySelector("#yuMarginalRate")?.value) || 26.4;
      const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
      const maxLimit = limits[bracket] || 3000000;

      let cumulativeSaved = 0;

      const rows = yuCurrentYearlyList.map((yc, idx) => {
        const yr = yc.year || (2024 - idx);
        const dep = Number(yc.deposit || 0);
        const ded = yc.is_deductible !== false && String(yc.is_deductible) !== "false";
        const target = ded ? Math.min(dep, maxLimit) : 0;
        const saved = ded ? Math.floor(target * (rate / 100)) : 0;
        if (ded) cumulativeSaved += saved;
        return { idx, yr, dep, ded, saved };
      });
      app.accountYearlyView.renderYellowUmbrella(form, container, rows, cumulativeSaved);
    }

    function updateYellowUmbrellaFields() {
      const type = app.$("#insuranceTypeSelect")?.value;
      const taxGroup = app.$("#yellowUmbrellaTaxGroup");
      const isYU = type === "yellow_umbrella";
      if (taxGroup) taxGroup.style.display = isYU ? "block" : "none";

      if (isYU) {
        const monthly = Number(app.$("#insuranceAccountForm [name='monthly_premium']")?.value) || 0;
        const bracket = app.$("#yuIncomeBracket")?.value || "40m_to_100m";
        const rate = Number(app.$("#yuMarginalRate")?.value) || 26.4;

        const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
        const maxLimit = limits[bracket] || 3000000;
        const annualPaid = monthly * 12;
        const deduction = Math.min(annualPaid, maxLimit);
        const taxSaved = Math.floor(deduction * (rate / 100));

        if (app.$("#yuDeductionAmountText")) app.$("#yuDeductionAmountText").textContent = `₩${app.number(deduction, 0)} (한도 ₩${app.number(maxLimit, 0)})`;
        if (app.$("#yuTaxSavedText")) app.$("#yuTaxSavedText").textContent = `₩${app.number(taxSaved, 0)} (${rate}%)`;

        renderYuYearlyFormRows(app.$("#insuranceAccountForm"));
      }
    }

    function openInsuranceAccountDialog(item = null) {
      const dialog = app.$("#insuranceAccountDialog");
      const form = app.$("#insuranceAccountForm");
      if (!dialog || !form) return;
      form.reset();
      form.querySelector("[name='id']").value = item ? item.id : "";
      if (app.$("#insuranceAccountDialogTitle")) {
        app.$("#insuranceAccountDialogTitle").textContent = item ? "보험 / 연금 / 공제 상품 수정" : "보험 / 연금 / 공제 상품 추가";
      }
      if (item) {
        const initial = window.WealthInsuranceFormModel.editValues(item);
        for (const [name, value] of Object.entries(initial.fields)) {
          form.querySelector(`[name='${name}']`).value = value;
        }

        const isMonthlyPension = item.payout_type === "monthly_pension" || (Number(item.monthly_payout) || 0) > 0 || item.insurance_type === "national_pension";
        if (isMonthlyPension) {
          if (app.$("#payoutTypeMonthlyPension")) app.$("#payoutTypeMonthlyPension").checked = true;
          if (app.$("#pensionMonthlyPayout")) app.$("#pensionMonthlyPayout").value = initial.monthlyPayout;
          if (app.$("#pensionDurationSelect")) app.$("#pensionDurationSelect").value = initial.payoutDuration;
        } else {
          if (app.$("#payoutTypeLumpSum")) app.$("#payoutTypeLumpSum").checked = true;
        }

        for (const [name, value] of Object.entries(initial.datesAndMemo)) {
          form.querySelector(`[name='${name}']`).value = value;
        }

        yuCurrentYearlyList = Array.isArray(item.yearly_contributions)
          ? JSON.parse(JSON.stringify(item.yearly_contributions))
          : [];
      } else {
        form.querySelector("[name='owner']").value = app.currentOwner !== "모두" ? app.currentOwner : "모두";
        if (app.$("#payoutTypeLumpSum")) app.$("#payoutTypeLumpSum").checked = true;
        if (app.$("#pensionDurationSelect")) app.$("#pensionDurationSelect").value = "20";
        yuCurrentYearlyList = [];
      }
      updateYellowUmbrellaFields();
      updatePensionPayoutFields();
      renderYuYearlyFormRows(form);
      dialog.querySelector('[data-np-edit-entry]')?.remove();
      if(item?.id&&item.insurance_type==='national_pension'){
        const initial=JSON.stringify([...new FormData(form).entries()]);
        const entry=document.createElement('button');entry.type='button';entry.className='button secondary compact';
        entry.dataset.npEditEntry='';entry.textContent='가입유형·세금·수익 분석 / 자료 가져오기';
        entry.onclick=()=>{
          if(JSON.stringify([...new FormData(form).entries()])!==initial){app.toast('수정 중인 기본 정보를 먼저 저장하거나 취소해 주세요.',true);return;}
          app.closeDialog('insuranceAccountDialog');openNationalPensionHistory(item);
        };
        form.append(entry);
      }
      app.refreshDialogKoreanHints(dialog);
      dialog.showModal();
    }

    function bindForm(bindSecuritiesYearlyForm) {
      const insForm = app.$("#insuranceAccountForm");
      if (insForm) {
        insuranceView.bindFormInputs({ $: app.$, insForm, updateYellowUmbrellaFields, updatePensionPayoutFields });

        insForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(insForm);
          const pType = fd.get("payout_type") || "lump_sum";
          const mPayout = Number(fd.get("monthly_payout")) || 0;
          const pYears = Number(fd.get("payout_duration_years")) || 20;
          const convertedTotal = Math.round(mPayout * 12 * pYears);

          const yu_yearly_contributions = [];
          document.querySelectorAll("#yuYearlyList .yu-yearly-row").forEach(row => {
            const yr = (row.querySelector(".yu-yearly-year")?.value || "").trim();
            const dep = Number(row.querySelector(".yu-yearly-deposit")?.value) || 0;
            const ded = row.querySelector(".yu-yearly-deductible")?.value === "true";
            if (yr) {
              yu_yearly_contributions.push({ year: yr, deposit: dep, is_deductible: ded });
            }
          });

          const payload = {
            id: fd.get("id") || undefined,
            insurance_type: fd.get("insurance_type") || "protection",
            owner: fd.get("owner") || "모두",
            company_name: fd.get("company_name") || "",
            product_name: fd.get("product_name") || "",
            payment_status: fd.get("payment_status") || "paying",
            income_bracket: fd.get("income_bracket") || "40m_to_100m",
            marginal_tax_rate: Number(fd.get("marginal_tax_rate")) || 26.4,
            monthly_premium: Number(fd.get("monthly_premium")) || 0,
            total_paid_amount: Number(fd.get("total_paid_amount")) || 0,
            expected_amount: pType === "monthly_pension" ? convertedTotal : (Number(fd.get("expected_amount")) || 0),
            payout_type: pType,
            monthly_payout: mPayout,
            payout_duration_years: pYears,
            converted_total_asset: pType === "monthly_pension" ? convertedTotal : (Number(fd.get("expected_amount")) || 0),
            start_date: fd.get("start_date") || "",
            maturity_date: fd.get("maturity_date") || "",
            memo: fd.get("memo") || "",
            yearly_contributions: yu_yearly_contributions,
          };

          try {
            await app.api("/api/insurance-accounts", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            app.toast("보험/연금/공제 상품이 저장되었습니다.");
            app.closeDialog("insuranceAccountDialog");
            await app.loadDashboard();
          } catch (err) {
            app.toast(err.message || "보험/연금 상품 저장 실패", true);
          }
        });

        bindSecuritiesYearlyForm();

        // 노란우산공제 연도별 이력 관리 이벤트
        document.getElementById("addYuYearlyBtn")?.addEventListener("click", () => {
          const years = yuCurrentYearlyList.map(y => Number(y.year) || 2024);
          const nextYr = years.length > 0 ? Math.min(...years) - 1 : 2024;
          yuCurrentYearlyList.push({ year: nextYr, deposit: 2400000, is_deductible: true });
          renderYuYearlyFormRows();
        });

        const handleYuYearlyRowChange = (e) => {
          const row = e.target.closest(".yu-yearly-row");
          if (!row) return;
          const idx = Number(row.dataset.index);
          if (yuCurrentYearlyList[idx]) {
            yuCurrentYearlyList[idx].year = row.querySelector(".yu-yearly-year")?.value || "";
            yuCurrentYearlyList[idx].deposit = Number(row.querySelector(".yu-yearly-deposit")?.value) || 0;
            yuCurrentYearlyList[idx].is_deductible = row.querySelector(".yu-yearly-deductible")?.value === "true";
            renderYuYearlyFormRows();
          }
        };
        document.getElementById("yuYearlyList")?.addEventListener("change", handleYuYearlyRowChange);

        document.getElementById("yuYearlyList")?.addEventListener("click", (e) => {
          const delBtn = e.target.closest(".yu-yearly-del-btn");
          if (!delBtn) return;
          const idx = Number(delBtn.dataset.index);
          if (!isNaN(idx)) {
            yuCurrentYearlyList.splice(idx, 1);
            renderYuYearlyFormRows();
          }
        });
      }
    }

    function bindPensionHistory() {
      document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('addNationalPensionYear')?.addEventListener('click', () => addNationalPensionHistoryRow());
        document.getElementById('nationalPensionHistoryForm')?.addEventListener('submit', async event => {
          event.preventDefault();
          if (nationalPensionHistorySaving) return;
          const item = nationalPensionHistoryItem;
          const notice = document.getElementById('nationalPensionHistoryNotice');
          const button = event.target.querySelector('[type=submit]');
          try {
            const records = readNationalPensionHistoryRows(); button.disabled = true; nationalPensionHistorySaving = true;
            const result = await app.api(`/api/insurance-accounts/${encodeURIComponent(item.id)}/yearly-contributions`, {
              method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({yearly_contributions:records, expected_history:nationalPensionHistoryOriginal})});
            // Apply only history; enriched valuation and the owner's original totals stay unchanged.
            item.yearly_contributions = result.insurance.yearly_contributions;
            renderInsuranceWithOwner(app.currentOwner);
            app.closeDialog('nationalPensionHistoryDialog'); app.toast('국민연금 납부 이력이 저장되었습니다.');
          } catch (error) { notice.textContent = error.message; app.toast(error.message, true); }
          finally { button.disabled = false; nationalPensionHistorySaving = false; }
        });
      });
    }

    function openNationalPensionTool(analysisButton, importButton) {
      const id=analysisButton?.dataset.nationalAnalysisId||importButton.dataset.nationalImportId;
      const item=rawInsuranceAccounts.find(row=>row.id===id&&row.insurance_type==='national_pension');
      if (!item) return;
      openNationalPensionHistory(item, { showImport: Boolean(importButton) });
      if (!importButton) document.getElementById('npAnalysisPanel')?.scrollIntoView({block:'start'});
    }

    function openNationalPensionHistoryFromRow(historyButton) {
      const item = rawInsuranceAccounts.find(item => item.id === historyButton.dataset.nationalHistoryId && item.insurance_type === 'national_pension');
      if (item) openNationalPensionHistory(item);
    }

    function editInsuranceAccount(insEditBtn) {
      const iid = insEditBtn.dataset.insuranceEditId;
      const ins = rawInsuranceAccounts.find(i => i.id === iid);
      if (ins) openInsuranceAccountDialog(ins);
    }

    async function deleteInsuranceAccount(insDelBtn) {
      const iid = insDelBtn.dataset.insuranceDelId;
      if (confirm('이 보험/연금 상품을 삭제하시겠습니까?')) {
        try {
          await app.api(`/api/insurance-accounts/${iid}`, { method: 'DELETE' });
          app.toast('보험/연금 상품이 삭제되었습니다.');
          await app.loadDashboard();
        } catch (err) {
          app.toast(err.message || '삭제 실패', true);
        }
      }
    }

    return {
      publicActions: {
        renderAssetTaxInformation,
        nationalPensionHistoryMarkup,
        addNationalPensionHistoryRow,
        openNationalPensionHistory,
        readNationalPensionHistoryRows,
        hasUnsavedNationalPensionHistory,
        renderInsurance,
        renderInsuranceWithOwner,
        updatePensionPayoutFields,
        renderYuYearlyFormRows,
        updateYellowUmbrellaFields,
        openInsuranceAccountDialog,
      },
      actions: {
        bindForm,
        bindPensionHistory,
        openNationalPensionTool,
        openNationalPensionHistoryFromRow,
        editInsuranceAccount,
        deleteInsuranceAccount,
      },
      get rawInsuranceAccounts() { return rawInsuranceAccounts; },
    };
  }

  window.WealthInsurancePensionFeatureController = { create };
})();
