(() => {
  "use strict";

  function create(app) {
    let currentPnlSortField = 'date';
    let currentPnlSortOrder = 'desc'; // 'asc' | 'desc'
    let currentDivSortField = 'date';
    let currentDivSortOrder = 'desc';

    let isSubmittingDividend = false;
    async function saveActualDividendRecord() {
      if (isSubmittingDividend) return;
      const form = document.getElementById("dividendRecordForm");
      if (!form) return;
      const rId = form.dataset.recordId;
      const dateVal = (form.querySelector("[name='date']")?.value || "").trim();
      const ownerVal = (form.querySelector("[name='owner']")?.value || "모두").trim();
      const brokerVal = (form.querySelector("[name='broker']")?.value || "").trim();
      const accountNameVal = (form.querySelector("[name='account_name']")?.value || "").trim();
      let codeVal = (form.querySelector("[name='code']")?.value || "").trim().toUpperCase();
      const nameVal = (form.querySelector("[name='name']")?.value || "").trim();
      let currVal = (form.querySelector("[name='currency']")?.value || "KRW").toUpperCase();
      const amtInput = form.querySelector("[name='amount']");
      const amtVal = Number(amtInput?.value || 0);
      const fxVal = Number(form.querySelector("[name='fx_rate']")?.value || 1385.0);
      let amtKrwVal = Number(form.querySelector("[name='amount_krw']")?.value || 0);
      if (!amtKrwVal && amtVal) {
        amtKrwVal = currVal === "USD" ? Math.round(amtVal * fxVal) : Math.round(amtVal);
      }
      const memoVal = (form.querySelector("[name='memo']")?.value || "").trim();

      if (!dateVal) {
        app.toast("입금일을 선택해 주세요.", true);
        return;
      }
      if (!nameVal && !codeVal) {
        app.toast("종목명 또는 종목코드를 입력해 주세요.", true);
        return;
      }
      if (!codeVal && nameVal) {
        try {
          const searchRes = await app.api(`/api/stock-search?q=${encodeURIComponent(nameVal)}`);
          if (searchRes && searchRes.code) {
            codeVal = searchRes.code;
            if (form.querySelector("[name='code']")) form.querySelector("[name='code']").value = codeVal;
            if (searchRes.currency && form.querySelector("[name='currency']")) {
              form.querySelector("[name='currency']").value = searchRes.currency;
              currVal = searchRes.currency;
            }
          }
        } catch (e) {}
      }
      if (!amtVal && (amtInput?.value === '' || amtInput?.value == null)) {
        app.toast("배당금(입금액)을 입력해 주세요.", true);
        return;
      }

      const payload = {
        date: dateVal,
        owner: ownerVal,
        broker: brokerVal,
        account_name: accountNameVal,
        code: codeVal,
        name: nameVal || codeVal,
        currency: currVal,
        amount: amtVal,
        fx_rate: fxVal,
        amount_krw: amtKrwVal,
        memo: memoVal,
      };

      Object.assign(payload, dividendRecordTaxInputs(form));

      // 현재 스크롤 위치 저장
      const savedScrollY = window.scrollY || window.pageYOffset || 0;
      const divDetailWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
      const savedTableScroll = divDetailWrap ? divDetailWrap.scrollTop : 0;

      isSubmittingDividend = true;
      try {
        const url = rId ? `/api/actual-dividends/${rId}` : "/api/actual-dividends";
        const method = rId ? "PUT" : "POST";
        const res = await app.api(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        document.getElementById("dividendRecordDialog")?.close();
        app.toast(res.message || "배당금이 저장되었습니다.");
        await window.loadActualDividends(app.currentOwner, selectedDividendYear);
        await app.updateOverviewCardsAllTime(app.currentOwner);
        if (typeof loadDividends === 'function') await loadDividends(app.currentOwner);

        // 스크롤 위치 복원
        window.scrollTo({ top: savedScrollY, behavior: "instant" });
        requestAnimationFrame(() => {
          window.scrollTo({ top: savedScrollY, behavior: "instant" });
          const newWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
          if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
        });
      } catch (err) {
        app.toast(err.message, true);
      } finally {
        isSubmittingDividend = false;
      }
    }

    let currentDividendMode = 'actual'; // 'estimated' | 'actual'
    let dividendData = null;
    let dividendDataOwner = null;
    let dividendDataEpoch = -1;
    let actualDividendData = null;
    const _initDivKst = getKstYearMonth();
    let selectedDividendMonth = _initDivKst.month;
    let selectedDividendYear = String(_initDivKst.year);

    function syncIncomeMonthNavUI(prefix, year, month) {
      const textEl = document.getElementById(prefix + "CurrentMonthText");
      const pickerEl = document.getElementById(prefix + "MonthPicker");
      const selEl = document.getElementById(prefix + "YearSelect");
      if (year === 'all') {
        if (textEl) textEl.textContent = "전체 기간";
      } else {
        const y = year || getKstYearMonth().year;
        const m = month || getKstYearMonth().month;
        if (textEl) textEl.textContent = `${y}년 ${m}월`;
        if (pickerEl) pickerEl.value = `${y}-${String(m).padStart(2, '0')}`;
        if (selEl && selEl.value !== String(y)) selEl.value = String(y);
      }
    }

    function syncDividendMonthNavUI() {
      syncIncomeMonthNavUI('dividend', selectedDividendYear, selectedDividendMonth);
    }

    function setSelectedDividendPeriod(year, month) {
      window.WealthUnifiedTimeseries?.clearDetail('dividend', {render:false});
      selectedDividendYear = String(year);
      selectedDividendMonth = month !== null && month !== undefined ? Number(month) : null;
      syncDividendMonthNavUI();
    }

    function normalizeMonthlyDividendSchedule(monthlySchedule) {
      if (Array.isArray(monthlySchedule)) return monthlySchedule;
      if (!monthlySchedule || typeof monthlySchedule !== "object") return [];

      return Object.entries(monthlySchedule)
        .map(([key, value]) => {
          const item = value && typeof value === "object" && !Array.isArray(value) ? value : {};
          const itemMonth = Number(item.month);
          const keyMonth = Number(key);
          return {
            ...item,
            month: Number.isFinite(itemMonth) ? itemMonth : (Number.isFinite(keyMonth) ? keyMonth : 0),
            items: Array.isArray(item.items) ? item.items : [],
          };
        })
        .sort((left, right) => left.month - right.month);
    }

    function beginIncomeRead(loader, panel) {
      if (globalThis.WealthStartup?.visible(panel) === false) {
        globalThis.WealthStartup.count('inactive_skipped');
        return null;
      }
      return (loader.generation || 0) + 1;
    }

    function isCurrentIncomeRead(loader, generation, owner, panel, isCurrentScope) {
      if (generation === loader.generation && owner === app.currentOwner && isCurrentScope()
          && globalThis.WealthStartup?.visible(panel) !== false) return true;
      globalThis.WealthStartup?.count('stale_ignored');
      return false;
    }

    async function loadDividends(owner = app.currentOwner, {reuse = false} = {}) {
      if (currentDividendMode !== 'estimated') return;
      const generation = beginIncomeRead(loadDividends, 'dividendPanel');
      if (generation === null || owner !== app.currentOwner) return;
      if (reuse && dividendData && dividendDataOwner === owner && dividendDataEpoch === app.startupReadEpoch) {
        window.renderDividends(dividendData);
        return dividendData;
      }
      // A failed explicit refresh must not leave an older success marked reusable.
      if (!reuse) dividendDataEpoch = -1;
      const readEpoch = app.startupReadEpoch;
      loadDividends.generation = generation;
      try {
        const res = await app.api(`/api/dividends?owner=${encodeURIComponent(owner)}`);
        if (!isCurrentIncomeRead(loadDividends, generation, owner, 'dividendPanel',
          () => readEpoch === app.startupReadEpoch && currentDividendMode === 'estimated')) return;
        dividendData = res;
        dividendDataOwner = owner;
        dividendDataEpoch = readEpoch;
        if (currentDividendMode === 'estimated') {
          window.renderDividends(res);
        }
      } catch (err) {
        console.error("배당 정보를 불러오지 못했습니다.", err);
      }
    }

    // A navigation hands its freshly fetched full-history response to the visible
    // summary/filter consumer. Ordinary reloads never consult this transient value.
    function preparedActualDividendResponse(prepared, owner, year) {
      if (!prepared || prepared.error || !prepared.response || prepared.owner !== owner
          || owner !== app.currentOwner || year !== selectedDividendYear || currentDividendMode !== 'actual'
          || prepared.readEpoch !== app.startupReadEpoch
          || prepared.scope !== window.WealthUnifiedTimeseries?.dividendScopeKey()) return null;
      return prepared.response;
    }

    async function loadActualDividends(owner = app.currentOwner, year = selectedDividendYear, preparedDividend = null) {
      if (currentDividendMode !== 'actual') return;
      const generation = beginIncomeRead(loadActualDividends, 'dividendPanel');
      if (generation === null) return;
      loadActualDividends.generation = generation;
      try {
        const res = preparedActualDividendResponse(preparedDividend, owner, year)
          ?? await app.api(`/api/actual-dividends?owner=${encodeURIComponent(owner)}&year=${encodeURIComponent(year || '')}`);
        if (!isCurrentIncomeRead(loadActualDividends, generation, owner, 'dividendPanel',
          () => year === selectedDividendYear && currentDividendMode === 'actual')) return;
        actualDividendData = res;
        if (currentDividendMode === 'actual') {
          renderActualDividends(res);
        }
        updateDividendYearOptions(res?.available_years || []);
      } catch (err) {
        console.error("실제 배당 정보를 불러오지 못했습니다.", err);
      }
    }

    function updateDividendYearOptions(years) {
      const sel = document.getElementById("dividendYearSelect");
      if (!sel) return;
      const currentVal = selectedDividendYear;
      const allYears = Array.from(new Set([new Date().getFullYear().toString(), ...years])).sort().reverse();

      const opts = allYears.map(y => `<option value="${y}">${y}년</option>`);
      opts.push('<option value="all">전체 기간</option>');
      sel.innerHTML = opts.join('');
      if (allYears.includes(currentVal) || currentVal === 'all') {
        sel.value = currentVal;
      }
    }

    function renderDividends(data) {
      if (document.getElementById('divMonthlyAvgSub')) document.getElementById('divMonthlyAvgSub').textContent = '연간 배당금 ÷ 12개월';
      if (!data) return;
      syncDividendMonthNavUI();
      const fxUsd = (app.dashboard?.fx_rates?.USD) || 1385.0;

      window.WealthDividendSummaryView.renderTexts({
        divCardLabel1: "연간 예상 배당금",
        divCardLabel2: "포트폴리오 배당수익률",
        divCardLabel3: "월평균 예상 배당금",
        divCardLabel4: "배당 지급 종목 수",
        dividendChartTitle: "📊 1월 ~ 12월 월별 예상 배당금 추이",
      });

      // 1. 상단 4대 요약 카드
      const schedule = normalizeMonthlyDividendSchedule(data.monthly_schedule);
      const scheduleTotal = schedule.reduce((sum, item) => sum + Number(item.total_krw || 0), 0);
      const totalAnnual = Number(data.total_annual_dividend_krw ?? scheduleTotal ?? 0) || scheduleTotal;
      const totalAnnualUsd = fxUsd > 0 ? (totalAnnual / fxUsd) : 0;
      const yieldRate = Number(data.portfolio_yield || 0);
      const monthlyAvg = Number(data.monthly_avg_dividend_krw ?? (totalAnnual / 12)) || (totalAnnual / 12);
      const payingCount = Number(data.dividend_paying_count ?? (data.holding_dividends || []).filter(item => Number(item.annual_payout_krw || 0) > 0).length) || 0;
      let totalHoldings = (app.dashboard?.holdings || []).length;
      if (app.currentOwner !== '모두') {
        totalHoldings = (app.dashboard?.holdings || []).filter(h => (h.owner || '모두') === app.currentOwner).length;
      }

      app.$("#divTotalAnnual") && (app.$("#divTotalAnnual").textContent = app.money(totalAnnual));
      app.$("#divTotalAnnualUsd") && (app.$("#divTotalAnnualUsd").textContent = `$${app.number(totalAnnualUsd, 2)} 환산 포함`);
      app.$("#divYield") && (app.$("#divYield").textContent = `${app.number(yieldRate, 2)}%`);
      app.$("#divYieldSub") && (app.$("#divYieldSub").textContent = "총 평가금액 대비");
      app.$("#divMonthlyAvg") && (app.$("#divMonthlyAvg").textContent = app.money(monthlyAvg));
      app.$("#divPayingCount") && (app.$("#divPayingCount").textContent = `${payingCount}개`);
      app.$("#divTotalHoldings") && (app.$("#divTotalHoldings").textContent = `전체 ${totalHoldings}개 종목 중`);

      // 핵심 요약 패널의 예상 연간 배당금 갱신
      app.$("#summaryEstimatedDividend") && (app.$("#summaryEstimatedDividend").textContent = `예상 연간 배당금 ${app.money(totalAnnual)} (${app.number(yieldRate, 2)}%)`);

      // 2. 1월~12월 월별 막대그래프 (SVG Bar Chart)
      const maxMonthly = Math.max(...schedule.map(s => Number(s.total_krw || 0)), 1);

      const w = 900, h = 240, pad = 30;
      const hBarArea = 170;
      const barWidth = 44;

      const chartBars = schedule.map((item, idx) => {
        const m = item.month;
        const val = Number(item.total_krw || 0);
        const x = pad + ((w - pad * 2) * (idx + 0.5)) / 12 - barWidth / 2;
        const barH = val > 0 ? Math.max(8, (val / maxMonthly) * (hBarArea - 25)) : 2;
        const y = hBarArea - barH;
        const isSelected = selectedDividendMonth === m;

        const itemCount = (item.items || []).length;
        return {
          m, idx, val, x, y, barH, isSelected, itemCount,
          labelX: x + barWidth / 2, valueLabelY: y - 6,
        };
      });

      window.WealthDividendSummaryView.renderEstimatedChart({
        $: app.$, html: app.html, money: app.money, chartBars, w, h, pad, hBarArea, barWidth,
        axisEndX: w - pad, monthLabelY: hBarArea + 16, countLabelY: hBarArea + 28,
      });

      attachEstimatedDividendTooltip(data);

      renderMonthlyDividendDetail(selectedDividendMonth);
    }

    function attachEstimatedDividendTooltip(data = dividendData) {
      if (currentDividendMode !== 'estimated' || !data) return;
      const host = document.getElementById('dividendBarChartWrap');
      if (!host) return;
      const year = selectedDividendYear && !['all', '전체'].includes(selectedDividendYear) ? selectedDividendYear : getKstYearMonth().year;
      window.WealthUnifiedTimeseries?.installAmountTooltip(host,
        normalizeMonthlyDividendSchedule(data.monthly_schedule).map(item => ({key:`${year}-${String(item.month).padStart(2, '0')}`, total:item.total_krw})),
        bucket => [['예상 배당', bucket.total]]);
    }

    function renderMonthlyDividendDetail(month = null) {
      const container = app.$("#dividendMonthlyDetail");
      if (!container || !dividendData) return;
      const detailMoney = window.WealthFormat.createCurrencyFormatter('KRW', app.money);

      const schedule = normalizeMonthlyDividendSchedule(dividendData.monthly_schedule);
      let title = "전체 배당 지급 종목 (연간 기준)";
      let items = [];

      if (month && month >= 1 && month <= 12) {
        const monthData = schedule.find(s => s.month === month);
        title = `📅 ${month}월 예상 배당 지급 종목 (${(monthData?.items || []).length}개 종목 · 합계 ${detailMoney(monthData?.total_krw || 0)})`;
        items = monthData?.items || [];
      } else {
        title = `📅 전체 배당 지급 종목 (${(dividendData.holding_dividends || []).filter(h => h.annual_payout_krw > 0).length}개 종목 · 연간 합계 ${detailMoney(dividendData.total_annual_dividend_krw || 0)})`;
        items = (dividendData.holding_dividends || []).filter(h => h.annual_payout_krw > 0).map(h => ({
          code: h.code,
          name: h.name,
          quantity: h.quantity,
          currency: h.currency,
          payout_krw: h.annual_payout_krw,
          payout_orig: h.annual_payout_orig,
          div_yield: h.div_yield,
          months: h.payout_months,
        }));
      }

      window.WealthActualDividendDetailView.renderEstimated({ container, title, items, month, html: app.html, money: detailMoney, number: app.number });
    }

    function renderActualDividends(data) {
      globalThis.WealthStartup?.count('render');
      if (!data) return;
      syncDividendMonthNavUI();
      const isAllYears = (selectedDividendYear === "all" || selectedDividendYear === "전체");

      const allRecords = (data.records || []).filter(r =>
        (isAllYears || String(r.date || '').startsWith(`${selectedDividendYear}-`))
        && (app.currentOwner === '모두' || (r.owner || '모두') === app.currentOwner)
        && r.income_type !== 'account_interest' && r.income_kind !== 'interest');
      let filteredRecords = allRecords;
      if (!isAllYears && selectedDividendMonth) {
        filteredRecords = allRecords.filter(r => String(r.date || '').startsWith(`${selectedDividendYear}-${String(selectedDividendMonth).padStart(2, '0')}`));
      }
      const periodLabel = isAllYears ? '전체 기간' : `${selectedDividendYear}년`;
      const monthLabel = !isAllYears && selectedDividendMonth ? `${selectedDividendMonth}월` : '';
      const totalActual = filteredRecords.reduce((sum, r) => sum + Number(r.amount_krw || 0), 0);
      const annualActual = allRecords.reduce((sum, r) => sum + Number(r.amount_krw || 0), 0);
      const grossAnnual = allRecords.reduce((sum, r) => sum + Number(r.tax_estimate?.gross_amount_krw ?? r.amount_krw ?? 0), 0);
      const hasEstimates = allRecords.some(r => !r.tax_estimate || r.tax_estimate.estimated);
      const texts = {
        divCardLabel1: `${periodLabel} ${monthLabel} 실제 수령 배당금`,
        divCardLabel2: `${periodLabel} 총 세전 배당금`,
        divCardLabel3: `${periodLabel} 누적 실제 수령 배당금`,
        divCardLabel4: `${monthLabel || periodLabel} 수령 종목 / 건수`,
        divTotalAnnual: app.money(totalActual), divTotalAnnualUsd: '실제 입금액 기준',
        divYield: app.money(grossAnnual), divYieldSub: hasEstimates ? '일부 예상값 포함' : '저장된 세전 금액 기준',
        divMonthlyAvg: app.money(annualActual), divMonthlyAvgSub: `${periodLabel} 전체 입금 합계`,
        divPayingCount: `${new Set(filteredRecords.map(r => r.code || r.name).filter(Boolean)).size}종목`,
        divTotalHoldings: `총 ${filteredRecords.length}건 입금`,
      };
      window.WealthDividendSummaryView.renderActual({ $: app.$, texts, periodLabel });

      renderActualDividendDetail(selectedDividendMonth, window.WealthUnifiedTimeseries?.getDetail('dividend') || null);
    }

    function renderActualDividendDetail(month = null, bucketDetail = null) {
      if (bucketDetail) month = bucketDetail.key;
      const container = app.$("#dividendMonthlyDetail");
      if (!container || (!actualDividendData && !bucketDetail)) return;
      const detailMoney = window.WealthFormat.createCurrencyFormatter('KRW', app.money);

      const records = bucketDetail?.items || [
        ...(actualDividendData?.records || []).map(record => ({...record, income_kind: 'dividend'})),
        ...(actualDividendData?.interest_records || []).map(record => ({...record, income_kind: 'interest'})),
      ];
      let title = "전체 실제 배당금 입금 내역";
      let items = [];

      if (bucketDetail) {
        items = [...records];
      } else if (month && month >= 1 && month <= 12) {
        const monthStr = String(month).padStart(2, '0');
        items = records.filter(r => {
          if (!r.date) return false;
          const parts = r.date.split('-');
          if (parts.length < 2) return false;
          const rYear = parts[0];
          const rMonth = parts[1];
          if (selectedDividendYear && selectedDividendYear !== 'all') {
            return rYear === String(selectedDividendYear) && rMonth === monthStr;
          }
          return rMonth === monthStr;
        });
        const sumKrw = items.reduce((acc, cur) => acc + Number(cur.amount_krw || 0), 0);
        const yrPrefix = (selectedDividendYear && selectedDividendYear !== 'all') ? `${selectedDividendYear}년 ` : '';
        title = `📅 ${yrPrefix}${month}월 실제 배당금 입금 내역 (${items.length}건 · 합계 <span style="color:#f43f5e;">${detailMoney(sumKrw)}</span>)`;
      } else {
        items = [...records];
        const sumKrw = items.reduce((acc, cur) => acc + Number(cur.amount_krw || 0), 0);
        title = `📅 전체 실제 배당금 입금 내역 (${items.length}건 · 합계 <span style="color:#f43f5e;">${detailMoney(sumKrw)}</span>)`;
      }

      const dividendCount = items.filter(item => item.income_kind !== 'interest').length;
      const interestCount = items.length - dividendCount;
      const sumKrw = items.reduce((sum, item) => sum + Number(item.amount_krw || 0), 0);
      const period = bucketDetail?.key ? window.WealthUnifiedTimeseries.bucketHeading(bucketDetail.key, bucketDetail.mode)
        : month ? `${selectedDividendYear && selectedDividendYear !== 'all' ? `${selectedDividendYear}년 ` : ''}${month}월` : '전체';
      title = `📅 ${period} 실제 배당·이자 내역 (배당 ${dividendCount}건 · 이자 ${interestCount}건 · 합계 ${detailMoney(sumKrw)})`;

      // 배당금 내역 컬럼 정렬 (보유종목과 동일 UX)
      items.sort((a, b) => {
        let valA, valB;
        if (currentDivSortField === 'date') {
          valA = a.date || '';
          valB = b.date || '';
          return currentDivSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else if (currentDivSortField === 'owner') {
          valA = a.owner || '모두';
          valB = b.owner || '모두';
          return currentDivSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else if (currentDivSortField === 'name') {
          valA = a.name || a.code || '';
          valB = b.name || b.code || '';
          return currentDivSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else if (currentDivSortField === 'amount') {
          valA = Number(a.amount || 0);
          valB = Number(b.amount || 0);
          return currentDivSortOrder === 'asc' ? valA - valB : valB - valA;
        } else if (currentDivSortField === 'amount_krw') {
          valA = Number(a.amount_krw || 0);
          valB = Number(b.amount_krw || 0);
          return currentDivSortOrder === 'asc' ? valA - valB : valB - valA;
        }
        return 0;
      });

      window.WealthActualDividendDetailView.render({
        container, title, items, month, hasBucketDetail: Boolean(bucketDetail),
        currentDivSortField, currentDivSortOrder, html: app.html, money: detailMoney, number: app.number,
      });
    }

    async function fetchHistoricalFxRate(dateStr) {
      if (!dateStr) return (app.dashboard?.fx_rates?.USD) || 1385.0;
      try {
        const res = await app.api(`/api/historical-fx?date=${encodeURIComponent(dateStr)}`);
        return Number(res.rate || (app.dashboard?.fx_rates?.USD) || 1385.0);
      } catch (e) {
        return (app.dashboard?.fx_rates?.USD) || 1385.0;
      }
    }

    async function openDividendRecordDialog(record = null) {
      const dlg = document.getElementById("dividendRecordDialog");
      const form = document.getElementById("dividendRecordForm");
      if (!dlg || !form) return;

      form.reset();
      form.dataset.recordId = record ? record.id : "";
      app.$("#dividendDialogTitle") && (app.$("#dividendDialogTitle").textContent = record ? "실제 배당금 수정" : "실제 배당금 추가");

      // ACCOUNTS 섹션의 등록된 계좌 목록 드롭다운 및 데이터리스트 채우기
      const accounts = app.dashboard?.accounts || [];
      const acctSel = app.$("#dividendAccountSelect");
      if (acctSel) {
        acctSel.innerHTML = '<option value="">-- 직접 입력 또는 등록된 계좌 선택 --</option>' +
          accounts.map(a => `
        <option value="${app.html(a.id)}" data-broker="${app.html(a.broker)}" data-name="${app.html(a.name)}" data-owner="${app.html(a.owner || '모두')}">
          [${app.html(a.broker)}] ${app.html(a.name)} (${app.html(a.owner || '모두')})
        </option>
      `).join('');

        const matchedAcct = accounts.find(a => record?.account_id && a.id === record.account_id)
          || accounts.find(a => record?.destination_account_id && a.id === record.destination_account_id)
          || accounts.find(a => record?.broker && a.broker === record.broker && record?.account_name && a.name === record.account_name);
        acctSel.value = matchedAcct ? matchedAcct.id : "";
      }

      const acctDatalist = app.$("#divAccountDatalist");
      if (acctDatalist) {
        const uniqueNames = [...new Set(accounts.map(a => a.name).filter(Boolean))];
        acctDatalist.innerHTML = uniqueNames.map(name => `<option value="${app.html(name)}"></option>`).join('');
      }

      app.populateStockDatalists();
      app.attachStockAutoFill("dividendRecordForm", updateDivFormFields);
      app.setupAutoAdvancingDateInput("#divSplitDateWrap");

      const today = new Date().toISOString().slice(0, 10);
      const targetDate = record ? record.date : today;

      const dateEl = form.querySelector("[name='date']");
      const ownerEl = form.querySelector("[name='owner']");
      const brokerEl = form.querySelector("[name='broker']");
      const accEl = form.querySelector("[name='account_name']");
      const codeEl = form.querySelector("[name='code']");
      const nameEl = form.querySelector("[name='name']");
      const currEl = form.querySelector("[name='currency']");
      const amtEl = form.querySelector("[name='amount']");
      const fxEl = form.querySelector("[name='fx_rate']");
      const amtKrwEl = form.querySelector("[name='amount_krw']");
      const memoEl = form.querySelector("[name='memo']");

      if (dateEl) dateEl.value = targetDate;
      document.getElementById("divSplitDateWrap")?._syncFromNative?.();
      if (ownerEl) ownerEl.value = record ? (record.owner || "모두") : (app.currentOwner !== "모두" ? app.currentOwner : "모두");
      if (brokerEl) brokerEl.value = record ? (record.broker || "") : "";
      if (accEl) accEl.value = record ? (record.account_name || "") : "";
      if (codeEl) codeEl.value = record ? record.code : "";
      if (nameEl) nameEl.value = record ? record.name : "";
      if (currEl) currEl.value = record ? record.currency : "KRW";
      if (amtEl) amtEl.value = record ? record.amount : "";
      if (amtKrwEl) amtKrwEl.value = record ? record.amount_krw : "";
      if (memoEl) memoEl.value = record ? (record.memo || "") : "";

      for (const field of ['capital_dividend_mode', 'gross_amount', 'tax', 'estimated_tax_rate', 'capital_exempt_amount', 'high_dividend_amount']) {
        const input = form.elements.namedItem(field);
        if (input) input.value = field === 'capital_dividend_mode' ? (record?.high_dividend_mode === 'MANUAL_ON' ? 'HIGH_DIVIDEND' : record?.[field] || 'AUTO')
          : record?.[field] == null ? '' : field === 'estimated_tax_rate' ? record[field] * 100 : record[field];
      }
      form._taxRecord = record;
      ++dividendTaxPreviewRevision;
      if (!form.dataset.taxEstimateBound) {
        form.dataset.taxEstimateBound = 'true';
        form.addEventListener('input', scheduleDividendTaxPreview);
        form.addEventListener('change', scheduleDividendTaxPreview);
      }

      if (record && record.fx_rate) {
        if (fxEl) fxEl.value = record.fx_rate;
      } else {
        const historicalFx = await fetchHistoricalFxRate(targetDate);
        if (fxEl) fxEl.value = historicalFx;
      }

      // 날짜 변경 시 해당 일자의 과거 환율 자동 조회
      if (dateEl && !dateEl.dataset.fxBound) {
        dateEl.dataset.fxBound = "true";
        dateEl.addEventListener("change", async () => {
          if (form.currency.value === "USD") {
            const rate = await fetchHistoricalFxRate(dateEl.value);
            if (form.fx_rate) form.fx_rate.value = rate;
            updateDivFormFields();
          }
        });
      }

      updateDivFormFields();
      dlg.showModal();
      scheduleDividendTaxPreview();
    }

    let dividendTaxPreviewTimer = null;
    let dividendTaxPreviewRevision = 0;
    function dividendRecordTaxInputs(form) {
      const selected = form.elements.namedItem('capital_dividend_mode')?.value || 'AUTO';
      const values = {capital_dividend_mode: selected === 'HIGH_DIVIDEND' ? 'MANUAL_OFF' : selected,
        high_dividend_mode: selected === 'HIGH_DIVIDEND' ? 'MANUAL_ON' : 'MANUAL_OFF'};
      for (const key of ['gross_amount', 'tax', 'estimated_tax_rate', 'capital_exempt_amount', 'high_dividend_amount']) {
        const value = form.elements.namedItem(key)?.value;
        values[key] = value == null || value === '' ? null : Number(value) / (key === 'estimated_tax_rate' ? 100 : 1);
      }
      return values;
    }
    function scheduleDividendTaxPreview() {
      clearTimeout(dividendTaxPreviewTimer);
      const revision = ++dividendTaxPreviewRevision;
      const form = document.getElementById('dividendRecordForm');
      const output = document.getElementById('divRecordTaxPreview');
      if (!form || !output) return;
      output.textContent = '예상 금액 계산 중…';
      dividendTaxPreviewTimer = setTimeout(async () => {
        const values = Object.fromEntries(new FormData(form));
        const payload = {...values, ...dividendRecordTaxInputs(form), amount: Number(values.amount || 0),
          fee: form._taxRecord?.fee ?? 0, fx_rate: Number(values.fx_rate || 1),
          ...(form._taxRecord?.event_identity ? {event_identity: form._taxRecord.event_identity} : {})};
        try {
          const result = await app.api('/api/actual-dividends/estimate', {method:'POST',
            headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
          if (revision !== dividendTaxPreviewRevision || !form.closest('dialog')?.open) return;
          const fmt = value => Number(value).toLocaleString('ko-KR', {maximumFractionDigits:values.currency === 'USD' ? 2 : 0});
          output.textContent = `${result.tax_type_label} · ${result.estimated ? '예상 ' : ''}세전 ${fmt(result.gross_amount)} / 세금 ${fmt(result.tax)} ${values.currency} · 자산관리용 추정${result.high_dividend_qualification?.status === 'official_qualified' ? ` · 공식 고배당기업 근거 (${result.high_dividend_qualification.business_year ?? '연도 미확인'} 사업연도)` : result.high_dividend_selected ? ' · 공식 자격 미확인' : ''}`;
        } catch (_) {
          if (revision === dividendTaxPreviewRevision) output.textContent = '예상 계산을 불러오지 못했습니다. 실제 입금액은 그대로 저장할 수 있습니다.';
        }
      }, 350);
    }

    function updateDivFormFields() {
      const form = document.getElementById("dividendRecordForm");
      if (!form) return;
      const isUsd = form.currency.value === "USD";
      const fxField = document.getElementById("fxRateField");
      const krwField = document.getElementById("amountKrwField");
      if (fxField) fxField.style.display = isUsd ? "flex" : "none";
      if (krwField) krwField.style.display = isUsd ? "flex" : "none";

      const amt = Number(form.amount.value || 0);
      const fx = Number(form.fx_rate.value || (app.dashboard?.fx_rates?.USD) || 1385.0);
      const original = form._taxRecord;
      if (original && Number(original.amount) === amt && original.currency === form.currency.value
          && (!isUsd || Number(original.fx_rate) === fx)) {
        form.amount_krw.value = original.amount_krw;
        return;
      }
      if (isUsd) {
        form.amount_krw.value = Math.round(amt * fx);
      } else {
        form.amount_krw.value = Math.round(amt);
      }
    }

    // ── 16. 주식 매도 실현손익 관리 (Realized PnL) ──────────────────────────────
    let pnlData = null;
    const _initPnlKst = getKstYearMonth();
    let selectedPnlMonth = _initPnlKst.month;
    let selectedPnlYear = String(_initPnlKst.year);
    let currentPnlTradeType = "all"; // 'all' | 'ipo'

    function syncPnlMonthNavUI() {
      syncIncomeMonthNavUI('pnl', selectedPnlYear, selectedPnlMonth);
    }

    function setSelectedPnlPeriod(year, month) {
      window.WealthUnifiedTimeseries?.clearDetail('pnl', {render:false});
      selectedPnlYear = String(year);
      selectedPnlMonth = month !== null && month !== undefined ? Number(month) : null;
      syncPnlMonthNavUI();
    }

    async function loadRealizedPnl(owner = app.currentOwner, year = selectedPnlYear, tradeType = currentPnlTradeType) {
      const generation = beginIncomeRead(loadRealizedPnl, 'realizedPnlPanel');
      if (generation === null) return;
      loadRealizedPnl.generation = generation;
      try {
        const res = await app.api(`/api/realized-pnl?owner=${encodeURIComponent(owner)}&year=${encodeURIComponent(year || '')}&trade_type=${encodeURIComponent(tradeType || 'all')}`);
        if (!isCurrentIncomeRead(loadRealizedPnl, generation, owner, 'realizedPnlPanel',
          () => year === selectedPnlYear && tradeType === currentPnlTradeType)) return;
        pnlData = res;
        window.renderRealizedPnl(res);
        updatePnlYearOptions(res?.available_years || []);

        // 실현손익 내 부동산 매도 기록을 부동산 탭 원장과 즉시 연동
        if (res?.records) {
          const registeredNames = (app.realEstateFeature.rawRealEstates || []).map(r => (r.name || '').trim()).filter(n => n.length >= 2);
          const reKw = /부동산|아파트|오피스텔|빌라|주택|단지|상가|토지|건물|원룸|분양권|재개발/i;
          const reRecords = res.records.filter(r =>
            r.asset_type === 'real_estate' || r.code === 'REAL_ESTATE' || r.broker === '부동산' ||
            (r.name && (r.name.includes('[부동산]') || r.name.includes('부동산') || registeredNames.some(rn => r.name.includes(rn)) || reKw.test(r.name)))
          );
          if (reRecords.length > 0) {
            app.renderRealEstate(app.realEstateFeature.rawRealEstates, app.currentOwner, null);
          }
        }
      } catch (err) {
        console.error("매도 실현손익을 불러오지 못했습니다.", err);
      }
    }

    function updatePnlYearOptions(years) {
      const sel = document.getElementById("pnlYearSelect");
      if (!sel) return;
      const currentVal = selectedPnlYear;
      const allYears = Array.from(new Set([new Date().getFullYear().toString(), ...years])).sort().reverse();

      const opts = allYears.map(y => `<option value="${y}">${y}년</option>`);
      opts.push('<option value="all">전체 기간</option>');
      sel.innerHTML = opts.join('');
      if (allYears.includes(currentVal) || currentVal === 'all') {
        sel.value = currentVal;
      }
    }

    function renderRealizedPnl(data) {
      globalThis.WealthStartup?.count('render');
      if (!data) return;
      syncPnlMonthNavUI();

      const allRecords = data.records || [];
      const records = allRecords.filter(r => {
        const at = String(r.asset_type || '').toLowerCase();
        const c = String(r.code || '').toUpperCase();
        const b = String(r.broker || '').trim();
        const n = String(r.name || '');
        return at !== 'real_estate' && c !== 'REAL_ESTATE' && b !== '부동산' && !n.startsWith('[부동산]') && !r.re_id && !r.real_estate_name;
      });

      const isAllYears = (selectedPnlYear === "all" || selectedPnlYear === "전체");
      let filteredRecords = records;
      if (!isAllYears && selectedPnlMonth && selectedPnlMonth >= 1 && selectedPnlMonth <= 12) {
        const mStr = String(selectedPnlMonth).padStart(2, '0');
        filteredRecords = records.filter(r => {
          const clean = String(r.date || '').replaceAll('-', '');
          const rYear = clean.slice(0, 4);
          const rMonth = clean.slice(4, 6);
          if (selectedPnlYear) return rYear === String(selectedPnlYear) && rMonth === mStr;
          return rMonth === mStr;
        });
      }

      const pnlView = app.buildRealizedPnlDisplaySummary(data, filteredRecords, isAllYears);
      const totalPnl = pnlView.totalPnlKrw;
      const winRecords = filteredRecords.filter(r => {
        const pnlVal = app.finiteRealizedPnlNumber(r.pnl_krw);
        const nativePnl = app.finiteRealizedPnlNumber(r.pnl);
        const s = nativePnl === null ? pnlVal : nativePnl;
        return s !== null && s > 0;
      });
      const lossRecords = filteredRecords.filter(r => {
        const pnlVal = app.finiteRealizedPnlNumber(r.pnl_krw);
        const nativePnl = app.finiteRealizedPnlNumber(r.pnl);
        const s = nativePnl === null ? pnlVal : nativePnl;
        return s !== null && s < 0;
      });
      const totalWin = isAllYears ? Number(data.total_win_krw || 0) : winRecords.reduce((acc, r) => acc + (app.finiteRealizedPnlNumber(r.pnl_krw) || 0), 0);
      const winCount = isAllYears ? Number(data.win_count || 0) : winRecords.length;
      const totalLoss = isAllYears ? Number(data.total_loss_krw || 0) : lossRecords.reduce((acc, r) => acc + (app.finiteRealizedPnlNumber(r.pnl_krw) || 0), 0);
      const lossCount = isAllYears ? Number(data.loss_count || 0) : lossRecords.length;
      const classifiedCount = winCount + lossCount;
      const winRate = isAllYears ? Number(data.win_rate || 0) : (classifiedCount ? (winCount / classifiedCount * 100) : 0);
      const recordCount = filteredRecords.length;

      // 1. 4대 요약 카드
      window.WealthRealizedPnlView.renderSummary({ $: app.$, money: app.money, number: app.number, totalPnl, recordCount, completenessNote: pnlView.completenessNote, totalWin, winCount, totalLoss, lossCount, winRate });

      // 2. 양방향 막대그래프 (SVG Bar Chart)
      const w = 900, h = 240, pad = 30;
      const zeroY = 120; // 0원 기준선 중앙
      const maxBarH = 80;

      let bars = "";

      if (isAllYears) {
        const yearlySchedule = data.yearly_schedule || [];
        const maxAbsPnl = Math.max(
          ...yearlySchedule.map(s => Math.abs(Number(s.total_krw || 0))),
          100000
        );
        const numYears = Math.max(yearlySchedule.length, 1);
        const barWidth = Math.min(64, Math.max(36, (w - pad * 2) / numYears - 28));

        bars = yearlySchedule.map((item, idx) => {
          const yr = String(item.year);
          const val = Number(item.total_krw || 0);
          const x = pad + ((w - pad * 2) * (idx + 0.5)) / numYears - barWidth / 2;
          const itemCount = (item.items || []).length;

          let barH = 2, y = zeroY - 1;
          let barFill = "#1c263d";
          let textY = zeroY - 8;

          if (val > 0) {
            barH = Math.max(6, (val / maxAbsPnl) * maxBarH);
            y = zeroY - barH;
            barFill = "url(#pnlGainBarGrad)";
            textY = y - 6;
          } else if (val < 0) {
            barH = Math.max(6, (Math.abs(val) / maxAbsPnl) * maxBarH);
            y = zeroY;
            barFill = "url(#pnlLossBarGrad)";
            textY = y + barH + 12;
          }

          const topText = val !== 0 ? `${val > 0 ? '+' : ''}${app.money(val)}` : '-';
          const textColor = val > 0 ? '#f43f5e' : (val < 0 ? '#38bdf8' : '#64748b');

          return `
        <g class="pnl-bar-group" data-year="${yr}" style="cursor:pointer;">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${barFill}" rx="4" opacity="0.95">
            <title>${yr}년 실현손익: ${app.money(val)} (${itemCount}건) - 클릭시 해당 연도 보기</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${textY.toFixed(1)}" fill="${textColor}" font-size="10" font-weight="700" text-anchor="middle">
            ${topText}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="215" fill="#cbd5e1" font-size="11.5" font-weight="700" text-anchor="middle">
            ${yr}년
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="228" fill="${itemCount > 0 ? '#fbbf24' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
            ${itemCount > 0 ? itemCount + '건' : '-'}
          </text>
        </g>
      `;
        }).join('');
      } else {
        const schedule = data.monthly_schedule || [];
        const maxAbsPnl = Math.max(
          ...schedule.map(s => Math.abs(Number(s.total_krw || 0))),
          100000
        );
        const barWidth = 44;

        bars = schedule.map((item, idx) => {
          const m = item.month;
          const val = Number(item.total_krw || 0);
          const x = pad + ((w - pad * 2) * (idx + 0.5)) / 12 - barWidth / 2;
          const isSelected = selectedPnlMonth === m;
          const itemCount = (item.items || []).length;

          let barH = 2, y = zeroY - 1;
          let barFill = "#1c263d";
          let textY = zeroY - 8;

          if (val > 0) {
            barH = Math.max(6, (val / maxAbsPnl) * maxBarH);
            y = zeroY - barH;
            barFill = isSelected ? "url(#pnlGainBarGradActive)" : "url(#pnlGainBarGrad)";
            textY = y - 6;
          } else if (val < 0) {
            barH = Math.max(6, (Math.abs(val) / maxAbsPnl) * maxBarH);
            y = zeroY;
            barFill = isSelected ? "url(#pnlLossBarGradActive)" : "url(#pnlLossBarGrad)";
            textY = y + barH + 12;
          }

          const topText = val !== 0 ? `${val > 0 ? '+' : ''}${app.money(val)}` : '-';
          const textColor = val > 0 ? '#f43f5e' : (val < 0 ? '#38bdf8' : '#64748b');

          return `
        <g class="pnl-bar-group" data-month="${m}" style="cursor:pointer;">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${barFill}" rx="4" opacity="0.95">
            <title>${m}월 실현손익: ${app.money(val)} (${itemCount}건)</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${textY.toFixed(1)}" fill="${textColor}" font-size="9.5" font-weight="700" text-anchor="middle">
            ${topText}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="215" fill="${isSelected ? '#f59e0b' : '#94a3b8'}" font-size="11" font-weight="${isSelected ? '700' : '600'}" text-anchor="middle">
            ${m}월
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="228" fill="${itemCount > 0 ? '#fbbf24' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
            ${itemCount > 0 ? itemCount + '건' : '-'}
          </text>
        </g>
      `;
        }).join('');
      }

      const chartWrap = app.$("#pnlBarChartWrap");
      if (chartWrap && !window.WealthUnifiedTimeseries?.renderPnl) {
        window.WealthRealizedPnlView.renderLegacyChart(chartWrap, { w, h, pad, zeroY, bars });
      }

      renderPnlMonthlyDetail(selectedPnlMonth, window.WealthUnifiedTimeseries?.getDetail('pnl') || null);
    }

    function formatOptionalTossWtsFxDisplay(record, value, formatter) {
      return record?.source === 'toss_wts' && value == null ? '—' : formatter(value);
    }

    function formatOptionalRealizedPnlValue(value, formatter) {
      const parsed = app.finiteRealizedPnlNumber(value);
      return parsed === null ? '—' : formatter(parsed);
    }

    function renderPnlMonthlyDetail(month = null, bucketDetail = null) {
      if (bucketDetail) month = bucketDetail.key;
      const container = app.$("#pnlMonthlyDetail");
      if (!container || (!pnlData && !bucketDetail)) return;

      const allRecords = bucketDetail?.items || pnlData.records || [];
      const records = allRecords.filter(r => {
        const at = String(r.asset_type || '').toLowerCase();
        const c = String(r.code || '').toUpperCase();
        const b = String(r.broker || '').trim();
        const n = String(r.name || '');
        return at !== 'real_estate' && c !== 'REAL_ESTATE' && b !== '부동산' && !n.startsWith('[부동산]') && !r.re_id && !r.real_estate_name;
      });
      let title = "전체 매도 실현손익 내역";
      let items = [];

      if (bucketDetail) {
        items = [...records];
        const itemSummary = app.buildRealizedPnlDisplaySummary({}, items, false);
        const period = bucketDetail.key ? window.WealthUnifiedTimeseries.bucketHeading(bucketDetail.key, bucketDetail.mode) : '전체';
        title = `📅 ${period} 매도 실현손익 내역 (${items.length}건 · 합계 ${itemSummary.totalPnlKrw > 0 ? '+' : ''}${app.money(itemSummary.totalPnlKrw)}${itemSummary.completenessNote ? ` · ${itemSummary.completenessNote}` : ''})`;
      } else if (month && month >= 1 && month <= 12) {
        const monthStr = String(month).padStart(2, '0');
        items = records.filter(r => {
          const clean = String(r.date || '').replaceAll('-', '');
          const rYear = clean.slice(0, 4);
          const rMonth = clean.slice(4, 6);
          if (selectedPnlYear && selectedPnlYear !== 'all') {
            return rYear === String(selectedPnlYear) && rMonth === monthStr;
          }
          return rMonth === monthStr;
        });
        const itemSummary = app.buildRealizedPnlDisplaySummary({}, items, false);
        const yrPrefix = (selectedPnlYear && selectedPnlYear !== 'all') ? `${selectedPnlYear}년 ` : '';
        title = `📅 ${yrPrefix}${month}월 매도 실현손익 내역 (${items.length}건 · 합계 ${itemSummary.totalPnlKrw > 0 ? '+' : ''}${app.money(itemSummary.totalPnlKrw)}${itemSummary.completenessNote ? ` · ${itemSummary.completenessNote}` : ''})`;
      } else {
        items = [...records];
        const itemSummary = app.buildRealizedPnlDisplaySummary({}, items, false);
        title = `📅 전체 매도 실현손익 내역 (${items.length}건 · 총합 ${itemSummary.totalPnlKrw > 0 ? '+' : ''}${app.money(itemSummary.totalPnlKrw)}${itemSummary.completenessNote ? ` · ${itemSummary.completenessNote}` : ''})`;
      }



      // 매도 실현손익 내역 컬럼 정렬 (보유종목과 동일 UX)
      items.sort((a, b) => {
        let valA, valB;
        if (currentPnlSortField === 'date') {
          valA = a.date || '';
          valB = b.date || '';
          return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else if (currentPnlSortField === 'owner') {
          valA = a.owner || '모두';
          valB = b.owner || '모두';
          return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else if (currentPnlSortField === 'name') {
          valA = a.name || a.code || '';
          valB = b.name || b.code || '';
          return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else if (currentPnlSortField === 'is_ipo') {
          valA = a.is_ipo ? '1' : (a.asset_type === 'real_estate' ? '2' : '0');
          valB = b.is_ipo ? '1' : (b.asset_type === 'real_estate' ? '2' : '0');
          return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else if (currentPnlSortField === 'pnl') {
          valA = Number(a.pnl || 0);
          valB = Number(b.pnl || 0);
          return currentPnlSortOrder === 'asc' ? valA - valB : valB - valA;
        } else if (currentPnlSortField === 'pnl_krw') {
          valA = app.finiteRealizedPnlNumber(a.pnl_krw);
          valB = app.finiteRealizedPnlNumber(b.pnl_krw);
          if (valA === null || valB === null) {
            if (valA === valB) return 0;
            return valA === null ? 1 : -1;
          }
          return currentPnlSortOrder === 'asc' ? valA - valB : valB - valA;
        }
        return 0;
      });

      window.WealthRealizedPnlView.renderMonthlyDetail({
        container, title, items, month, hasBucketDetail: Boolean(bucketDetail),
        currentPnlSortField, currentPnlSortOrder, html: app.html, money: app.money, number: app.number,
        finiteRealizedPnlNumber: app.finiteRealizedPnlNumber, formatOptionalRealizedPnlValue, formatOptionalTossWtsFxDisplay,
      });
    }

    function calcPnlReProfit() {
      const form = document.getElementById("pnlRecordForm");
      if (!form) return;
      const purch = Number(form.re_purchase_price?.value || 0);
      const sell = Number(form.re_sell_price?.value || 0);
      const exp = Number(form.re_expenses?.value || 0);
      const pnl = sell - purch - exp;

      const pnlInput = form.pnl;
      const pnlKrwInput = form.pnl_krw;
      if (pnlInput && (sell > 0 || purch > 0)) pnlInput.value = pnl;
      if (pnlKrwInput && (sell > 0 || purch > 0)) pnlKrwInput.value = pnl;

      const formulaEl = document.getElementById("pnlReCalcFormula");
      if (formulaEl) {
        formulaEl.textContent = `양도가 ₩${app.number(sell, 0)} - 취득가 ₩${app.number(purch, 0)} - 필요경비 ₩${app.number(exp, 0)} = ₩${app.number(pnl, 0)}`;
      }
    }


    function onSelectPnlRealEstate() {
      const form = document.getElementById("pnlRecordForm");
      const sel = document.getElementById("pnlRealEstateSelect");
      if (!form || !sel) return;
      const reId = sel.value;
      if (!reId) return;

      const list = app.realEstateFeature.rawRealEstates || app.rawDashboard?.real_estates || [];
      const target = list.find(r => r.id === reId);
      if (!target) return;

      if (form.name) form.name.value = target.name || "";
      if (form.owner && target.owner) form.owner.value = target.owner;
      const purchPrice = Number(target.purchase_price || target.acquisition_price || target.current_price || 0);
      if (form.re_purchase_price) {
        form.re_purchase_price.value = purchPrice;
        if (typeof app.updateKoreanCurrencyHint === 'function') app.updateKoreanCurrencyHint(form.re_purchase_price);
      }
      calcPnlReProfit();
    }


    function togglePnlAssetTypeFields() {
      const form = document.getElementById("pnlRecordForm");
      if (!form) return;
      const assetType = document.getElementById("pnlAssetTypeSelect")?.value || "stock";
      const isIpo = (assetType === "ipo");

      const brokerWrap = document.getElementById("pnlBrokerWrap");
      const acctNameWrap = document.getElementById("pnlAccountNameWrap");
      const codeWrap = document.getElementById("pnlCodeWrap");
      const acctSelWrap = document.getElementById("pnlAccountSelectWrap");
      const ipoWrap = document.getElementById("pnlIpoWrap");
      const currWrap = document.getElementById("pnlCurrencyWrap");
      const nameLabel = document.getElementById("pnlNameLabelText");

      if (brokerWrap) brokerWrap.style.display = "block";
      if (acctNameWrap) acctNameWrap.style.display = "block";
      if (codeWrap) codeWrap.style.display = "block";
      if (acctSelWrap) acctSelWrap.style.display = "block";
      if (currWrap) currWrap.style.display = "block";
      if (ipoWrap) ipoWrap.style.display = isIpo ? "none" : "block";
      if (nameLabel) nameLabel.textContent = isIpo ? "공모주 종목명" : "종목명";

      const nameInput = form.querySelector("[name='name']");
      const codeInput = form.querySelector("[name='code']");
      if (nameInput) {
        nameInput.placeholder = isIpo ? "예: 아이엠바이오로직스, 한패스, 리센스메디컬 (종목명 입력 시 자동 검색)" : "예: 삼성전자, 현대차, NVDA";
      }
      if (codeInput) {
        codeInput.placeholder = isIpo ? "예: 394420 (공모주명 입력 시 자동 완성)" : "예: 005930 (종목명 입력 시 자동 완성)";
      }

      const isIpoEl = form.querySelector("[name='is_ipo']");
      if (isIpoEl) isIpoEl.value = isIpo ? "true" : "false";
    }


    async function openPnlRecordDialog(record = null) {
      const dlg = document.getElementById("pnlRecordDialog");
      const form = document.getElementById("pnlRecordForm");
      if (!dlg || !form) return;

      form.reset();
      form.dataset.recordId = record ? record.id : "";
      app.$("#pnlDialogTitle") && (app.$("#pnlDialogTitle").textContent = record ? "매도 실현손익 수정" : "매도 실현손익 추가");

      const assetTypeEl = document.getElementById("pnlAssetTypeSelect");
      if (assetTypeEl) {
        if (record) {
          assetTypeEl.value = record.asset_type || (record.is_ipo ? "ipo" : "stock");
        } else {
          assetTypeEl.value = (currentPnlTradeType === "ipo") ? "ipo" : "stock";
        }
      }
      togglePnlAssetTypeFields();

      // ACCOUNTS 섹션의 등록된 계좌 목록 드롭다운 및 데이터리스트 채우기
      const accounts = app.dashboard?.accounts || [];
      const acctSel = app.$("#pnlAccountSelect");
      if (acctSel) {
        acctSel.innerHTML = '<option value="">-- 직접 입력 또는 등록된 계좌 선택 --</option>' +
          accounts.map(a => `
        <option value="${app.html(a.id)}" data-broker="${app.html(a.broker)}" data-name="${app.html(a.name)}" data-owner="${app.html(a.owner || '모두')}">
          [${app.html(a.broker)}] ${app.html(a.name)} (${app.html(a.owner || '모두')})
        </option>
      `).join('');

        const matchedAcct = accounts.find(a => record?.account_id && a.id === record.account_id)
          || accounts.find(a => record?.destination_account_id && a.id === record.destination_account_id)
          || accounts.find(a => record?.broker && a.broker === record.broker && record?.account_name && a.name === record.account_name);
        acctSel.value = matchedAcct ? matchedAcct.id : "";
      }

      const acctDatalist = app.$("#pnlAccountDatalist");
      if (acctDatalist) {
        const uniqueNames = [...new Set(accounts.map(a => a.name).filter(Boolean))];
        acctDatalist.innerHTML = uniqueNames.map(name => `<option value="${app.html(name)}"></option>`).join('');
      }

      app.populateStockDatalists();
      app.attachStockAutoFill("pnlRecordForm", updatePnlFormFields);
      app.setupAutoAdvancingDateInput("#pnlSplitDateWrap");

      const today = new Date().toISOString().slice(0, 10);
      let targetDate = record ? record.date : today;
      if (typeof targetDate === 'string' && /^\d{8}$/.test(targetDate.trim())) {
        const s = targetDate.trim();
        targetDate = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}`;
      }

      const dateEl = form.querySelector("[name='date']");
      const ownerEl = form.querySelector("[name='owner']");
      const brokerEl = form.querySelector("[name='broker']");
      const accEl = form.querySelector("[name='account_name']");
      const codeEl = form.querySelector("[name='code']");
      const nameEl = form.querySelector("[name='name']");
      const currEl = form.querySelector("[name='currency']");
      const pnlEl = form.querySelector("[name='pnl']");
      const fxEl = form.querySelector("[name='fx_rate']");
      const pnlKrwEl = form.querySelector("[name='pnl_krw']");
      const isIpoEl = form.querySelector("[name='is_ipo']");
      const memoEl = form.querySelector("[name='memo']");

      if (dateEl) dateEl.value = targetDate;
      document.getElementById("pnlSplitDateWrap")?._syncFromNative?.();
      if (ownerEl) ownerEl.value = record ? (record.owner || "모두") : (app.currentOwner !== "모두" ? app.currentOwner : "모두");
      if (brokerEl) brokerEl.value = record ? (record.broker || "") : "";
      if (accEl) accEl.value = record ? (record.account_name || "") : "";
      if (codeEl) codeEl.value = record ? record.code : "";
      if (nameEl) nameEl.value = record ? record.name : "";
      if (currEl) currEl.value = record ? record.currency : "KRW";
      if (pnlEl) pnlEl.value = record ? record.pnl : "";
      if (pnlKrwEl) pnlKrwEl.value = record ? record.pnl_krw : "";
      if (isIpoEl) {
        if (record) {
          isIpoEl.value = record.is_ipo ? "true" : "false";
        } else {
          isIpoEl.value = (currentPnlTradeType === "ipo") ? "true" : "false";
        }
      }
      if (memoEl) memoEl.value = record ? (record.memo || "") : "";

      if (record && record.fx_rate) {
        if (fxEl) fxEl.value = record.fx_rate;
      } else {
        const historicalFx = await fetchHistoricalFxRate(targetDate);
        if (fxEl) fxEl.value = historicalFx;
      }

      // 날짜 변경 시 해당 일자의 과거 환율 자동 조회
      if (dateEl && !dateEl.dataset.fxBound) {
        dateEl.dataset.fxBound = "true";
        dateEl.addEventListener("change", async () => {
          if (form.currency.value === "USD") {
            const rate = await fetchHistoricalFxRate(dateEl.value);
            if (form.fx_rate) form.fx_rate.value = rate;
            updatePnlFormFields();
          }
        });
      }

      updatePnlFormFields();
      calcPnlReProfit();
      dlg.showModal();
    }

    function updatePnlFormFields() {
      const form = document.getElementById("pnlRecordForm");
      if (!form) return;
      const isUsd = form.currency.value === "USD";
      const fxField = document.getElementById("pnlFxRateField");
      const krwField = document.getElementById("pnlAmountKrwField");
      if (fxField) fxField.style.display = isUsd ? "flex" : "none";
      if (krwField) krwField.style.display = isUsd ? "flex" : "none";

      const pnl = Number(form.pnl.value || 0);
      const fx = Number(form.fx_rate.value || (app.dashboard?.fx_rates?.USD) || 1385.0);
      if (isUsd) {
        form.pnl_krw.value = Math.round(pnl * fx);
      } else {
        form.pnl_krw.value = Math.round(pnl);
      }
    }

    // 실현손익 단건 등록 폼 이벤트
    let isSubmittingPnl = false;
    async function saveRealizedPnlRecord() {
      if (isSubmittingPnl) return;
      const form = document.getElementById("pnlRecordForm");
      if (!form) return;
      const rId = form.dataset.recordId;
      const dateVal = (form.querySelector("[name='date']")?.value || "").trim();
      const ownerVal = (form.querySelector("[name='owner']")?.value || "모두").trim();
      const brokerVal = (form.querySelector("[name='broker']")?.value || "").trim();
      const accountNameVal = (form.querySelector("[name='account_name']")?.value || "").trim();
      let codeVal = (form.querySelector("[name='code']")?.value || "").trim().toUpperCase();
      const nameVal = (form.querySelector("[name='name']")?.value || "").trim();
      let currVal = (form.querySelector("[name='currency']")?.value || "KRW").toUpperCase();
      const pnlInputStr = form.querySelector("[name='pnl']")?.value;
      let pnlVal = Number(pnlInputStr || 0);
      const fxVal = Number(form.querySelector("[name='fx_rate']")?.value || 1385.0);
      let pnlKrwVal = Number(form.querySelector("[name='pnl_krw']")?.value || 0);
      if (!pnlKrwVal && pnlVal) {
        pnlKrwVal = currVal === "USD" ? Math.round(pnlVal * fxVal) : Math.round(pnlVal);
      }

      let assetTypeVal = form.querySelector("[name='asset_type']")?.value || "stock";
      const isIpoVal = (assetTypeVal === "ipo") || (form.querySelector("[name='is_ipo']")?.value === "true");
      const isRealEstate = (assetTypeVal === "real_estate");
      const memoVal = (form.querySelector("[name='memo']")?.value || "").trim();

      let purchVal = Number(form.querySelector("[name='re_purchase_price']")?.value || 0);
      let sellVal = Number(form.querySelector("[name='re_sell_price']")?.value || 0);
      let expVal = Number(form.querySelector("[name='re_expenses']")?.value || 0);

      if (isRealEstate && sellVal > 0 && purchVal > 0 && (!pnlVal || pnlVal === 0)) {
        pnlVal = Math.round(sellVal - purchVal - expVal);
        pnlKrwVal = pnlVal;
      }

      if (!dateVal) {
        app.toast("매도일을 선택해 주세요.", true);
        return;
      }
      if (isRealEstate) {
        if (!nameVal) {
          app.toast("부동산 명칭을 입력해 주세요.", true);
          return;
        }
        codeVal = "REAL_ESTATE";
        currVal = "KRW";
      } else {
        if (!nameVal && !codeVal) {
          app.toast("종목명 또는 종목코드를 입력해 주세요.", true);
          return;
        }
        if (!codeVal && nameVal) {
          try {
            const searchRes = await app.api(`/api/stock-search?q=${encodeURIComponent(nameVal)}`);
            if (searchRes && searchRes.code) {
              codeVal = searchRes.code;
              if (form.querySelector("[name='code']")) form.querySelector("[name='code']").value = codeVal;
              if (searchRes.currency && form.querySelector("[name='currency']")) {
                form.querySelector("[name='currency']").value = searchRes.currency;
                currVal = searchRes.currency;
              }
            }
          } catch (e) {}
        }
      }

      if (pnlInputStr === '' || pnlInputStr == null) {
        app.toast("실현손익을 입력해 주세요.", true);
        return;
      }

      const payload = {
        date: dateVal,
        owner: ownerVal,
        broker: isRealEstate ? "부동산" : brokerVal,
        account_name: isRealEstate ? "부동산 자산" : accountNameVal,
        code: codeVal,
        name: nameVal || codeVal,
        asset_type: assetTypeVal,
        currency: currVal,
        pnl: pnlVal,
        fx_rate: fxVal,
        fx_pnl_krw: 0,
        pnl_krw: pnlKrwVal,
        is_ipo: isIpoVal,
        memo: memoVal,
      };

      if (isRealEstate) {
        payload.purchase_price = purchVal;
        payload.sell_price = sellVal;
        payload.expenses = expVal;
        payload.real_estate_name = nameVal;
      }

      // 현재 스크롤 위치 저장 (윈도우 스크롤 및 세부 테이블 스크롤)
      const savedScrollY = window.scrollY || window.pageYOffset || 0;
      const pnlDetailWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
      const savedTableScroll = pnlDetailWrap ? pnlDetailWrap.scrollTop : 0;

      isSubmittingPnl = true;
      try {
        const url = rId ? `/api/realized-pnl/${rId}` : "/api/realized-pnl";
        const method = rId ? "PUT" : "POST";
        const res = await app.api(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        document.getElementById("pnlRecordDialog")?.close();
        app.toast(res.message || "매도 실현손익이 저장되었습니다.");
        await app.loadDashboard();
        await loadRealizedPnl(app.currentOwner, selectedPnlYear, currentPnlTradeType);
        app.renderRealEstateWithOwner(app.currentOwner);
        await app.updateOverviewCardsAllTime(app.currentOwner);

        // 스크롤 위치 완벽 복원
        window.scrollTo({ top: savedScrollY, behavior: "instant" });
        requestAnimationFrame(() => {
          window.scrollTo({ top: savedScrollY, behavior: "instant" });
          const newWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
          if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
        });
      } catch (err) {
        app.toast(err.message, true);
      } finally {
        isSubmittingPnl = false;
      }
    }

    function bindMonthNavigation({ prefix, getYear, getMonth, setPeriod, sync, beforeSelect, beforePeriodChange, refresh }) {
      window.WealthIncomeMonthNavigation.bind({
        prefix, getKstYearMonth, shiftYearMonth, parseYearMonth,
        getYear, getMonth, beforeSelect,
        onMonthSelected: async (year, month) => {
          beforePeriodChange?.();
          const yearChanged = String(year) !== String(getYear());
          setPeriod(String(year), month);
          sync();
          await refresh(yearChanged);
        },
      });
    }

    function initPnlMonthNavListeners() {
      bindMonthNavigation({
        prefix: 'pnl',
        getYear: () => selectedPnlYear,
        getMonth: () => selectedPnlMonth,
        setPeriod: (year, month) => { selectedPnlYear = year; selectedPnlMonth = month; },
        sync: syncPnlMonthNavUI,
        beforeSelect: () => window.WealthUnifiedTimeseries?.clearDetail('pnl', {render:false}),
        refresh: async yearChanged => {
          if (yearChanged || !pnlData) {
            await loadRealizedPnl(app.currentOwner, selectedPnlYear, currentPnlTradeType);
          } else {
            window.renderRealizedPnl(pnlData);
          }
        },
      });
    }

    function initDividendMonthNavListeners() {
      bindMonthNavigation({
        prefix: 'dividend',
        getYear: () => selectedDividendYear,
        getMonth: () => selectedDividendMonth,
        setPeriod: (year, month) => { selectedDividendYear = year; selectedDividendMonth = month; },
        sync: syncDividendMonthNavUI,
        beforePeriodChange: () => window.WealthUnifiedTimeseries?.clearDetail('dividend', {render:false}),
        refresh: async yearChanged => {
          if (currentDividendMode === 'actual') {
            if (yearChanged || !actualDividendData) {
              await window.loadActualDividends(app.currentOwner, selectedDividendYear);
            } else {
              renderActualDividends(actualDividendData);
            }
          } else {
            await loadDividends(app.currentOwner, {reuse:true});
          }
        },
      });
    }

    function sortPnlDetail(pnlTh) {
      const sortField = pnlTh.dataset.pnlSort;
      if (currentPnlSortField === sortField) {
        currentPnlSortOrder = currentPnlSortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        currentPnlSortField = sortField;
        currentPnlSortOrder = (sortField === 'name' || sortField === 'owner') ? 'asc' : 'desc';
      }
      renderPnlMonthlyDetail(selectedPnlMonth, window.WealthUnifiedTimeseries?.getDetail('pnl') || null);
    }

    function sortDividendDetail(divTh) {
      const sortField = divTh.dataset.divSort;
      if (currentDivSortField === sortField) {
        currentDivSortOrder = currentDivSortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        currentDivSortField = sortField;
        currentDivSortOrder = (sortField === 'name' || sortField === 'owner') ? 'asc' : 'desc';
      }
      renderActualDividendDetail(selectedDividendMonth, window.WealthUnifiedTimeseries?.getDetail('dividend') || null);
    }

    function refreshDividends(divRefreshBtn) {
      app.action(divRefreshBtn, () => app.api("/api/refresh-prices", { method: "POST" }), async () => {
        await app.loadDashboard();
        await app.loadMarkets();
        await loadDividends(app.currentOwner);
      });
    }

    function switchDividendMode(divModeTab) {
      document.querySelectorAll('#dividendModeTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
      divModeTab.classList.add('active');
      currentDividendMode = divModeTab.dataset.divMode || 'actual';
      const refreshBtn = app.$("#refreshDividendBtn");
      const addBtn = app.$("#addDividendBtn");
      const importBtn = app.$("#importDividendBtn");
      const clearBtn = app.$("#clearAllDividendBtn");
      const incomeSection = app.$("#tossWtsIncomeSection");
      if (incomeSection) {
        incomeSection.style.display = currentDividendMode === 'actual' ? 'flex' : 'none';
      }
      // A mode change supersedes an in-flight actual-chart navigation, too.
      // Estimated mode can activate immediately; actual mode keeps its controls
      // available while preparing a scoped unified frame.
      void app.setIncomeTab('dividend', {updateHash:false});

      if (currentDividendMode === 'estimated') {
        if (refreshBtn) refreshBtn.style.display = 'inline-block';
        if (addBtn) addBtn.style.display = 'none';
        if (importBtn) importBtn.style.display = 'none';
        if (clearBtn) clearBtn.style.display = 'none';
        void loadDividends(app.currentOwner, {reuse:true});
      } else {
        if (refreshBtn) refreshBtn.style.display = 'none';
        if (addBtn) addBtn.style.display = 'inline-block';
        if (importBtn) importBtn.style.display = 'inline-block';
        if (clearBtn) clearBtn.style.display = 'inline-block';
        if (actualDividendData) {
          renderActualDividends(actualDividendData);
          void window.WealthUnifiedTimeseries?.renderDividend?.();
        } else {
          window.loadActualDividends(app.currentOwner);
        }
      }
    }

    function submitDividend(e) {
      e.preventDefault();
      if (typeof saveActualDividendRecord === 'function') {
        saveActualDividendRecord();
      }
    }

    function submitPnl(e) {
      e.preventDefault();
      if (typeof saveRealizedPnlRecord === 'function') {
        saveRealizedPnlRecord();
      }
    }

    function addDividend() {
      window.openDividendRecordDialog();
    }

    function openDividendImport() {
      const dlg = document.getElementById("dividendImportDialog");
      if (dlg) dlg.showModal();
    }

    async function refreshClearedIncome(kind) {
      window.WealthUnifiedTimeseries?.clearDetail(kind, {render:false});
      if (kind === 'pnl') {
        await loadRealizedPnl(app.currentOwner, selectedPnlYear, currentPnlTradeType);
      } else {
        await window.loadActualDividends(app.currentOwner, selectedDividendYear);
      }
      await app.loadDashboard();
      await app.updateOverviewCardsAllTime(app.currentOwner);
      window.dispatchEvent(new CustomEvent('wealth:income-view'));
    }

    function clearDividends() {
      if (confirm("정말로 모든 실제 배당금 기록을 일괄 삭제하시겠습니까?\n삭제된 내역은 복구할 수 없습니다.")) {
        const btn = app.$("#clearAllDividendBtn");
        app.action(btn, () => app.api("/api/actual-dividends/clear", { method: "POST" }),
          () => refreshClearedIncome('dividend'));
      }
    }

    function editDividend(editActualDivBtn) {
      const rId = editActualDivBtn.dataset.id;
      const rec = (window.WealthUnifiedTimeseries?.getDetail('dividend')?.items || actualDividendData?.records || []).find(r => r.id === rId && r.income_kind !== 'interest');
      if (rec) window.openDividendRecordDialog(rec);
    }

    async function deleteDividend(delActualDivBtn) {
      const rId = delActualDivBtn.dataset.id;
      const rec = (window.WealthUnifiedTimeseries?.getDetail('dividend')?.items || actualDividendData?.records || []).find(r => r.id === rId && r.income_kind !== 'interest');
      const label = rec ? `${rec.date} ${rec.name} (${app.money(rec.amount_krw)})` : '배당 기록';
      if (!confirm(`'${label}' 배당 내역을 삭제할까요?`)) return;
      const savedScrollY = window.scrollY || window.pageYOffset || 0;
      const divDetailWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
      const savedTableScroll = divDetailWrap ? divDetailWrap.scrollTop : 0;
      try {
        const res = await app.api(`/api/actual-dividends/${rId}`, { method: 'DELETE' });
        app.toast(res.message || '삭제되었습니다.');
        await window.loadActualDividends(app.currentOwner);
        await app.updateOverviewCardsAllTime(app.currentOwner);
        window.scrollTo({ top: savedScrollY, behavior: "instant" });
        requestAnimationFrame(() => {
          window.scrollTo({ top: savedScrollY, behavior: "instant" });
          const newWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
          if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
        });
      } catch (err) {
        app.toast(err.message, true);
      }
    }

    function selectDividendBar(divBar) {
      window.WealthUnifiedTimeseries?.clearDetail('dividend', {render:false});
      if (divBar.dataset.year) {
        const yr = divBar.dataset.year;
        selectedDividendYear = yr;
        selectedDividendMonth = null;
        const yearSelect = app.$("#dividendYearSelect");
        if (yearSelect) yearSelect.value = yr;
        window.loadActualDividends(app.currentOwner, yr);
        return true;
      }
      if (divBar.dataset.month) {
        const m = Number(divBar.dataset.month);
        selectedDividendMonth = m;
        syncDividendMonthNavUI();
        if (currentDividendMode === 'estimated') {
          if (dividendData) window.renderDividends(dividendData);
        } else {
          if (actualDividendData) renderActualDividends(actualDividendData);
        }
        return true;
      }
    }

    function clearDividendMonth() {
      if (window.WealthUnifiedTimeseries?.getDetail('dividend')) {
        window.WealthUnifiedTimeseries.clearDetail('dividend');
        return;
      }
      selectedDividendMonth = null;
      if (currentDividendMode === 'estimated') {
        if (dividendData) window.renderDividends(dividendData);
      } else {
        if (actualDividendData) renderActualDividends(actualDividendData);
      }
    }

    function selectPnlType(pnlTab) {
      document.querySelectorAll('#pnlTradeTypeTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
      pnlTab.classList.add('active');
      currentPnlTradeType = pnlTab.dataset.tradeType || 'all';
      loadRealizedPnl(app.currentOwner, selectedPnlYear, currentPnlTradeType);
    }

    function addPnl() {
      window.openPnlRecordDialog();
    }

    function openPnlImport() {
      const dlg = document.getElementById("pnlImportDialog");
      if (dlg) dlg.showModal();
    }

    function clearPnl() {
      if (confirm("정말로 모든 매도 실현손익 기록을 일괄 삭제하시겠습니까?\n삭제된 내역은 복구할 수 없습니다.")) {
        const btn = app.$("#clearAllPnlBtn");
        app.action(btn, () => app.api("/api/realized-pnl/clear", { method: "POST" }),
          () => refreshClearedIncome('pnl'));
      }
    }

    function editPnl(editPnlBtn) {
      const rId = editPnlBtn.dataset.id;
      const rec = (window.WealthUnifiedTimeseries?.getDetail('pnl')?.items || pnlData?.records || []).find(r => r.id === rId);
      if (rec) window.openPnlRecordDialog(rec);
    }

    async function deletePnl(delPnlBtn) {
      const rId = delPnlBtn.dataset.id;
      const rec = (window.WealthUnifiedTimeseries?.getDetail('pnl')?.items || pnlData?.records || []).find(r => r.id === rId);
      const label = rec ? `${rec.date} ${rec.name} (${app.money(rec.pnl_krw)})` : '손익 기록';
      if (!confirm(`'${label}' 매도 실현손익 내역을 삭제할까요?`)) return;
      const savedScrollY = window.scrollY || window.pageYOffset || 0;
      const pnlDetailWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
      const savedTableScroll = pnlDetailWrap ? pnlDetailWrap.scrollTop : 0;
      try {
        const res = await app.api(`/api/realized-pnl/${rId}`, { method: 'DELETE' });
        app.toast(res.message || '삭제되었습니다.');
        await app.loadDashboard();
        await loadRealizedPnl(app.currentOwner, selectedPnlYear, currentPnlTradeType);
        app.renderRealEstateWithOwner(app.currentOwner);
        await app.updateOverviewCardsAllTime(app.currentOwner);
        window.scrollTo({ top: savedScrollY, behavior: "instant" });
        requestAnimationFrame(() => {
          window.scrollTo({ top: savedScrollY, behavior: "instant" });
          const newWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
          if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
        });
      } catch (err) {
        app.toast(err.message, true);
      }
    }

    function selectPnlBar(pnlBar) {
      window.WealthUnifiedTimeseries?.clearDetail('pnl', {render:false});
      if (pnlBar.dataset.year) {
        const yr = pnlBar.dataset.year;
        selectedPnlYear = yr;
        selectedPnlMonth = null;
        const yearSelect = app.$("#pnlYearSelect");
        if (yearSelect) yearSelect.value = yr;
        loadRealizedPnl(app.currentOwner, yr, currentPnlTradeType);
        return true;
      }
      if (pnlBar.dataset.month) {
        const m = Number(pnlBar.dataset.month);
        selectedPnlMonth = m;
        syncPnlMonthNavUI();
        if (pnlData) window.renderRealizedPnl(pnlData);
        return true;
      }
    }

    function clearPnlMonth() {
      if (window.WealthUnifiedTimeseries?.getDetail('pnl')) {
        window.WealthUnifiedTimeseries.clearDetail('pnl');
        return;
      }
      selectedPnlMonth = null;
      if (pnlData) window.renderRealizedPnl(pnlData);
    }

    function bindAccountSelects() {
      app.$("#pnlAccountSelect")?.addEventListener("change", (e) => {
        const sel = e.target;
        const form = app.$("#pnlRecordForm");
        if (!form || !sel) return;
        const opt = sel.selectedOptions[0];
        if (opt && opt.value) {
          const brokerInput = form.querySelector("[name='broker']");
          const accInput = form.querySelector("[name='account_name']");
          const ownerSelect = form.querySelector("[name='owner']");
          if (opt.dataset.broker && brokerInput) brokerInput.value = opt.dataset.broker;
          if (opt.dataset.name && accInput) accInput.value = opt.dataset.name;
          if (opt.dataset.owner && ownerSelect) ownerSelect.value = opt.dataset.owner;
        }
      });

      // 배당금 추가/수정 팝업 내 등록된 계좌 선택 시 자동 채움
      app.$("#dividendAccountSelect")?.addEventListener("change", (e) => {
        const sel = e.target;
        const form = app.$("#dividendRecordForm");
        if (!form || !sel) return;
        const opt = sel.selectedOptions[0];
        if (opt && opt.value) {
          const brokerInput = form.querySelector("[name='broker']");
          const accInput = form.querySelector("[name='account_name']");
          const ownerSelect = form.querySelector("[name='owner']");
          if (opt.dataset.broker && brokerInput) brokerInput.value = opt.dataset.broker;
          if (opt.dataset.name && accInput) accInput.value = opt.dataset.name;
          if (opt.dataset.owner && ownerSelect) ownerSelect.value = opt.dataset.owner;
        }
      });
    }

    function bindDividendImport() {
      const divImportForm = document.getElementById("dividendImportForm");
      if (divImportForm) {
        divImportForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fileInput = document.getElementById("divImportFileInput");
          if (!fileInput || !fileInput.files.length) {
            app.toast("가져올 엑셀 또는 CSV 파일을 선택하세요.", true);
            return;
          }
          const formData = new FormData();
          formData.append("file", fileInput.files[0]);

          try {
            const res = await app.api("/api/import-dividends", {
              method: "POST",
              body: formData,
            });
            divImportForm.closest("dialog")?.close();
            fileInput.value = "";
            app.toast(res.message || "배당금 내역을 성공적으로 가져왔습니다.");
            await window.loadActualDividends(app.currentOwner);
            await app.updateOverviewCardsAllTime(app.currentOwner);
          } catch (err) {
            app.toast(err.message || "배당 파일 처리 실패", true);
          }
        });
      }
    }

    function bindEstimatedTooltip() {
      window.addEventListener('wealth:unified-ready', () => attachEstimatedDividendTooltip());
    }

    function bindRecordForms() {
      document.querySelector("#pnlRecordForm [name='code']")?.addEventListener("input", (e) => {
        const form = document.getElementById("pnlRecordForm");
        if (!form) return;
        const val = e.target.value.trim().toUpperCase();
        const match = (app.dashboard?.holdings || []).find(h => h.code.toUpperCase() === val || h.name === val);
        if (match) {
          const nameEl = form.querySelector("[name='name']");
          const currEl = form.querySelector("[name='currency']");
          if (nameEl) nameEl.value = match.name;
          if (currEl) currEl.value = match.currency || "KRW";
          if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
        }
      });

      document.querySelector("#pnlRecordForm [name='currency']")?.addEventListener("change", () => {
        if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
      });
      document.querySelector("#pnlRecordForm [name='pnl']")?.addEventListener("input", () => {
        if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
      });
      document.querySelector("#pnlRecordForm [name='fx_rate']")?.addEventListener("input", () => {
        if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
      });

      // 실현손익 파일 가져오기 폼 이벤트
      const pnlImportForm = document.getElementById("pnlImportForm");
      if (pnlImportForm) {
        pnlImportForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fileInput = document.getElementById("pnlImportFileInput");
          if (!fileInput || !fileInput.files.length) {
            app.toast("가져올 엑셀 또는 CSV 파일을 선택하세요.", true);
            return;
          }
          const formData = new FormData();
          formData.append("file", fileInput.files[0]);

          try {
            const res = await app.api("/api/import-realized-pnl", {
              method: "POST",
              body: formData,
            });
            pnlImportForm.closest("dialog")?.close();
            fileInput.value = "";
            app.toast(res.message || "실현손익 내역을 성공적으로 가져왔습니다.");
            await loadRealizedPnl(app.currentOwner, selectedPnlYear, currentPnlTradeType);
            await app.updateOverviewCardsAllTime(app.currentOwner);
          } catch (err) {
            app.toast(err.message || "실현손익 파일 처리 실패", true);
          }
        });
      }

      // 배당 연도 셀렉트 변경 이벤트
      document.getElementById("dividendYearSelect")?.addEventListener("change", (e) => {
        window.WealthUnifiedTimeseries?.clearDetail('dividend', {render:false});
        selectedDividendYear = e.target.value;
        selectedDividendMonth = null;
        window.loadActualDividends(app.currentOwner, selectedDividendYear);
      });

      // 실현손익 연도 셀렉트 변경 이벤트
      document.getElementById("pnlYearSelect")?.addEventListener("change", (e) => {
        window.WealthUnifiedTimeseries?.clearDetail('pnl', {render:false});
        selectedPnlYear = e.target.value;
        selectedPnlMonth = null;
        loadRealizedPnl(app.currentOwner, selectedPnlYear, currentPnlTradeType);
      });
    }

    return {
      publicActions: {
        saveActualDividendRecord,
        syncDividendMonthNavUI,
        normalizeMonthlyDividendSchedule,
        loadDividends,
        preparedActualDividendResponse,
        loadActualDividends,
        updateDividendYearOptions,
        renderDividends,
        attachEstimatedDividendTooltip,
        renderMonthlyDividendDetail,
        renderActualDividends,
        renderActualDividendDetail,
        fetchHistoricalFxRate,
        openDividendRecordDialog,
        dividendRecordTaxInputs,
        scheduleDividendTaxPreview,
        updateDivFormFields,
        syncPnlMonthNavUI,
        loadRealizedPnl,
        updatePnlYearOptions,
        renderRealizedPnl,
        formatOptionalTossWtsFxDisplay,
        formatOptionalRealizedPnlValue,
        renderPnlMonthlyDetail,
        calcPnlReProfit,
        onSelectPnlRealEstate,
        togglePnlAssetTypeFields,
        openPnlRecordDialog,
        updatePnlFormFields,
        saveRealizedPnlRecord,
        initPnlMonthNavListeners,
        initDividendMonthNavListeners,
        setSelectedDividendPeriod,
        setSelectedPnlPeriod,
      },
      actions: {
        sortPnlDetail,
        sortDividendDetail,
        refreshDividends,
        switchDividendMode,
        submitDividend,
        submitPnl,
        addDividend,
        openDividendImport,
        clearDividends,
        refreshClearedIncome,
        editDividend,
        deleteDividend,
        selectDividendBar,
        clearDividendMonth,
        selectPnlType,
        addPnl,
        openPnlImport,
        clearPnl,
        editPnl,
        deletePnl,
        selectPnlBar,
        clearPnlMonth,
        bindAccountSelects,
        bindDividendImport,
        bindEstimatedTooltip,
        bindRecordForms,
      },
      legacyState: {
        get actualDividendData() { return actualDividendData; },
        set actualDividendData(value) { actualDividendData = value; },
        get currentDividendMode() { return currentDividendMode; },
        set currentDividendMode(value) { currentDividendMode = value; },
        get currentPnlTradeType() { return currentPnlTradeType; },
        set currentPnlTradeType(value) { currentPnlTradeType = value; },
        get dividendData() { return dividendData; },
        set dividendData(value) { dividendData = value; },
        get pnlData() { return pnlData; },
        set pnlData(value) { pnlData = value; },
        get selectedDividendMonth() { return selectedDividendMonth; },
        set selectedDividendMonth(value) { selectedDividendMonth = value; },
        get selectedDividendYear() { return selectedDividendYear; },
        set selectedDividendYear(value) { selectedDividendYear = value; },
        get selectedPnlMonth() { return selectedPnlMonth; },
        set selectedPnlMonth(value) { selectedPnlMonth = value; },
        get selectedPnlYear() { return selectedPnlYear; },
        set selectedPnlYear(value) { selectedPnlYear = value; },
      },
    };
  }

  window.WealthIncomeFeatureController = { create };
})();
