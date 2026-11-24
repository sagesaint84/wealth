(() => {
  "use strict";

  function create(app) {
    let rawRealEstates = [];
    let rawSoldRealEstates = [];
    let currentRealEstateSubtab = 'all'; // 'all' | 'own' | 'rental' | 'lease' | 'sold'

    const PROPERTY_TYPE_LABELS = {
      own: "🏠 자가",
      rental: "🏢 임대",
      lease: "🔑 임차",
      sold: "🏷️ 매도",
    };

    const realEstateView = window.WealthRealEstateView.create({ $: app.$, html: app.html, number: app.number });

    function renderRealEstate(reList, owner = '모두', soldList = null) {
      rawRealEstates = reList || [];

      // 모든 가용 원천에서 매도 부동산 후보군 통합 수집 및 정밀 감지
      const allCandidateRecords = [
        ...(soldList || []),
        ...((app.rawDashboard && app.rawDashboard.sold_real_estates) || []),
        ...((app.rawDashboard && app.rawDashboard.realized_pnl_records) || []),
        ...((app.pnlData && app.pnlData.records) || [])
      ];
      const registeredNames = (rawRealEstates || []).map(r => (r.name || '').trim()).filter(n => n.length >= 2);
      const reKw = /부동산|아파트|오피스텔|빌라|주택|단지|상가|토지|건물|원룸|분양권|재개발/i;

      const map = new Map();
      allCandidateRecords.forEach(r => {
        if (!r || !r.id) return;
        const name = r.name || '';
        const memo = r.memo || '';
        const isRe = r.asset_type === 'real_estate' || r.code === 'REAL_ESTATE' || r.broker === '부동산' ||
          name.includes('[부동산]') || name.includes('부동산') ||
          registeredNames.some(rn => name.includes(rn)) ||
          reKw.test(name) || (memo && reKw.test(memo) && r.asset_type !== 'stock');
        if (isRe) {
          map.set(r.id, r);
        }
      });
      rawSoldRealEstates = Array.from(map.values()).sort((a, b) => (b.date || '').localeCompare(a.date || ''));
      renderRealEstateWithOwner(owner);
    }

    function renderRealEstateWithOwner(owner = '모두') {
      const o = owner || app.currentOwner || '모두';
      const filtered = [];

      rawRealEstates.forEach(r => {
        const ownerships = (r.ownerships && r.ownerships.length)
          ? r.ownerships
          : [{ owner: r.owner || '모두', ratio: 100 }];

        let share = 1.0;
        if (o !== '모두') {
          let matched = ownerships.find(x => x.owner === o);
          if (!matched && r.owner && r.owner.includes(o)) {
            const m = r.owner.match(new RegExp(`${o}\\s*([0-9.]+)%`));
            if (m) {
              share = parseFloat(m[1]) / 100;
            } else {
              share = 0.5;
            }
          } else if (matched && matched.ratio > 0) {
            share = (matched.ratio || 100) / 100;
          } else {
            return;
          }
        }
        const clone = Object.assign({}, r, { _shareRatio: share });
        filtered.push(clone);
      });

      // 매도 부동산 목록 소유자 필터링
      const filteredSold = [];
      rawSoldRealEstates.forEach(s => {
        let share = 1.0;
        if (o !== '모두') {
          const ownerships = (s.ownerships && s.ownerships.length)
            ? s.ownerships
            : [{ owner: s.owner || '모두', ratio: 100 }];
          let matched = ownerships.find(x => x.owner === o);
          if (!matched && s.owner && s.owner.includes(o)) {
            const m = s.owner.match(new RegExp(`${o}\\s*([0-9.]+)%`));
            if (m) {
              share = parseFloat(m[1]) / 100;
            } else {
              share = 0.5;
            }
          } else if (matched && matched.ratio > 0) {
            share = (matched.ratio || 100) / 100;
          } else if (s.owner === o) {
            share = 1.0;
          } else {
            return;
          }
        }
        const clone = Object.assign({}, s, { _shareRatio: share });
        filteredSold.push(clone);
      });

      const ownList = filtered.filter(r => (r.property_type || 'own') === 'own');
      const rentalList = filtered.filter(r => r.property_type === 'rental');
      const leaseList = filtered.filter(r => r.property_type === 'lease');

      const totalREVal = ownList.concat(rentalList).reduce((sum, r) => sum + ((Number(r.current_price) || 0) * (r._shareRatio || 1.0)), 0);
      const totalPurchaseVal = ownList.concat(rentalList).reduce((sum, r) => sum + ((Number(r.purchase_price) || 0) * (r._shareRatio || 1.0)), 0);
      const totalProfit = totalPurchaseVal > 0 ? (totalREVal - totalPurchaseVal) : 0;
      const totalProfitRate = totalPurchaseVal > 0 ? ((totalProfit / totalPurchaseVal) * 100).toFixed(1) : "0.0";

      const totalTenantDeposit = leaseList.reduce((sum, r) => sum + ((Number(r.deposit_amount) || 0) * (r._shareRatio || 1.0)), 0);
      const totalLandlordDeposit = rentalList.reduce((sum, r) => sum + ((Number(r.deposit_amount) || 0) * (r._shareRatio || 1.0)), 0);

      let totalLinkedLoanBalance = 0;
      const loanMap = new Map();
      app.rawLoanAccounts.forEach(l => loanMap.set(l.id, l));

      filtered.forEach(r => {
        (r.linked_loan_ids || []).forEach(lid => {
          const l = loanMap.get(lid);
          if (l) totalLinkedLoanBalance += ((Number(l.current_balance) || 0) * (r._shareRatio || 1.0));
        });
      });

      const totalREDebt = totalLandlordDeposit + totalLinkedLoanBalance;

      // 매도 부동산 총 실현손익, 양도가, 취득가 계산
      const totalSoldPnl = filteredSold.reduce((sum, s) => sum + ((Number(s.pnl_krw != null ? s.pnl_krw : s.pnl) || 0) * (s._shareRatio || 1.0)), 0);
      const totalSoldPurch = filteredSold.reduce((sum, s) => sum + ((Number(s.purchase_price) || 0) * (s._shareRatio || 1.0)), 0);
      const totalSoldSell = filteredSold.reduce((sum, s) => sum + ((Number(s.sell_price) || 0) * (s._shareRatio || 1.0)), 0);
      const soldProfitRate = totalSoldPurch > 0 ? ((totalSoldPnl / totalSoldPurch) * 100).toFixed(1) : "0.0";

      realEstateView.updateSummary({ o, totalREVal, ownList, rentalList, totalPurchaseVal, totalTenantDeposit, totalProfit, totalProfitRate, totalREDebt, totalLinkedLoanBalance, totalLandlordDeposit, totalSoldPnl, totalSoldPurch, soldProfitRate, filteredSold, filtered, leaseList, currentRealEstateSubtab });

      let displayList = filtered;
      if (currentRealEstateSubtab === 'own') {
        displayList = ownList;
      } else if (currentRealEstateSubtab === 'rental') {
        displayList = rentalList;
      } else if (currentRealEstateSubtab === 'lease') {
        displayList = leaseList;
      } else if (currentRealEstateSubtab === 'sold') {
        displayList = filteredSold;
      }

      const grid = app.$("#realEstateGrid");
      if (!grid) return;

      if (currentRealEstateSubtab === 'sold') {
        if (!filteredSold.length) {
          grid.innerHTML = realEstateView.emptySold();
          return;
        }

        grid.innerHTML = filteredSold.map(sold => {
          const shareRatio = sold._shareRatio || 1.0;
          const isPartial = shareRatio < 0.999;
          const rawPurch = Number(sold.purchase_price) || 0;
          const rawSell = Number(sold.sell_price) || 0;
          const rawExp = Number(sold.expenses) || 0;
          const rawPnl = Number(sold.pnl_krw != null ? sold.pnl_krw : sold.pnl) || 0;

          const purch = isPartial ? rawPurch * shareRatio : rawPurch;
          const sell = isPartial ? rawSell * shareRatio : rawSell;
          const exp = isPartial ? rawExp * shareRatio : rawExp;
          const pnl = isPartial ? rawPnl * shareRatio : rawPnl;

          const profitSign = pnl >= 0 ? "+" : "";
          const profitColor = pnl > 0 ? "#42d5a3" : (pnl < 0 ? "#f43f5e" : "#94a3b8");
          const profitRate = purch > 0 ? ((pnl / purch) * 100).toFixed(1) : null;

          const titleName = sold.clean_name || (sold.name || '부동산').replace('[부동산]', '').trim() || '부동산 매도';
          const ownerBadgeText = sold.is_joint_ownership
            ? (isPartial ? `🤝 ${o} ${(shareRatio * 100).toFixed(0)}% (공동명의)` : `🤝 ${sold.owner}`)
            : (sold.owner || '모두');

          return realEstateView.soldCard({ sold, ownerBadgeText, titleName, purch, isPartial, rawPurch, sell, rawSell, exp, rawExp, profitColor, profitSign, pnl, profitRate });
        }).join("");
        return;
      }

      if (!displayList.length) {
        grid.innerHTML = realEstateView.emptyProperties();
        return;
      }

      const today = new Date();
      today.setHours(0, 0, 0, 0);

      grid.innerHTML = displayList.map(re => {
        const pType = re.property_type || 'own';
        const typeLabel = PROPERTY_TYPE_LABELS[pType] || "부동산";
        const typeBadgeClass = pType === 'own' ? 'badge-own' : (pType === 'rental' ? 'badge-rental' : 'badge-lease');
        const shareRatio = re._shareRatio || 1.0;
        const isPartial = shareRatio < 0.999;

        const rawPurch = Number(re.purchase_price || 0);
        const rawCurr = Number(re.current_price || 0);
        const rawDep = Number(re.deposit_amount || 0);
        const rawRent = Number(re.monthly_rent || 0);

        const purch = isPartial ? rawPurch * shareRatio : rawPurch;
        const curr = isPartial ? rawCurr * shareRatio : rawCurr;
        const dep = isPartial ? rawDep * shareRatio : rawDep;
        const rent = isPartial ? rawRent * shareRatio : rawRent;

        const profit = (pType !== 'lease' && purch > 0) ? (curr - purch) : 0;
        const profitRate = (pType !== 'lease' && purch > 0) ? ((profit / purch) * 100).toFixed(1) : "0.0";
        const profitSign = profit >= 0 ? "+" : "";
        const profitColor = profit >= 0 ? "#42d5a3" : "#f43f5e";

        let dDayText = "";
        if (re.expiry_date) {
          try {
            const expDt = new Date(re.expiry_date.substring(0, 10));
            const diffDays = Math.round((expDt - today) / (1000 * 60 * 60 * 24));
            dDayText = diffDays <= 0 ? "만기 경과" : `만기 D-${diffDays}`;
          } catch (e) {}
        }

        const connectedLoanItems = (re.linked_loan_ids || []).map(lid => loanMap.get(lid)).filter(Boolean);
        const linkedLoanTotalBal = connectedLoanItems.reduce((acc, l) => acc + Number(l.current_balance || 0) * shareRatio, 0);
        const linkedLoanTotalInterest = connectedLoanItems.reduce((acc, l) => acc + (Number(l.monthly_interest) || Number(l.calc?.monthly_interest) || 0) * shareRatio, 0);

        let netEquity = 0;
        if (pType === 'own') {
          netEquity = curr - linkedLoanTotalBal;
        } else if (pType === 'rental') {
          netEquity = curr - (dep + linkedLoanTotalBal);
        } else {
          netEquity = dep - linkedLoanTotalBal;
        }

        const pyungText = re.exclusive_area > 0 ? ` (약 ${(re.exclusive_area / 3.3058).toFixed(1)}평)` : '';

        // 네이버 부동산 검색 링크: 동·호수를 제외한 깨끗한 단지명으로 검색
        const cleanSearchKeyword = (re.name || '').replace(/\s*\d+[-~_동호].*$/i, '').trim() || re.name || re.address || '';
        const naverLandUrl = `https://m.land.naver.com/search/result/${encodeURIComponent(cleanSearchKeyword)}`;

        // 카드 타이틀에 동·호수 결합 표시
        const titleHtml = realEstateView.title({ re });

        // 소유자 배지 라벨
        const ownerBadgeText = re.is_joint_ownership
          ? (isPartial ? `🤝 ${o} ${(shareRatio * 100).toFixed(0)}% (공동명의)` : `🤝 ${re.owner}`)
          : (re.owner || '모두');

        return realEstateView.propertyCard({ re, typeBadgeClass, typeLabel, ownerBadgeText, dDayText, titleHtml, pType, naverLandUrl, cleanSearchKeyword, isPartial, o, purch, rawPurch, curr, rawCurr, profitColor, profitSign, profit, profitRate, dep, rawDep, rent, pyungText, connectedLoanItems, linkedLoanTotalBal, linkedLoanTotalInterest, netEquity });
      }).join("");
    }

    function calcRealEstatePreview() {
      const pType = app.$("#reTypeSelect")?.value || "own";
      const purch = Number(app.$("#rePurchasePrice")?.value || 0);
      const curr = Number(app.$("#reCurrentPrice")?.value || 0);
      const dep = Number(app.$("#reDepositAmount")?.value || 0);

      const selectedLoanId = app.$("#reLinkedLoansSelect")?.value || "";
      let loanBal = 0;
      if (selectedLoanId) {
        const l = app.rawLoanAccounts.find(x => x.id === selectedLoanId);
        if (l) loanBal = Number(l.current_balance || 0);
      }

      let netEquity = 0;
      let profit = 0;
      let profitRate = "0.0";

      if (pType === 'own') {
        netEquity = curr - loanBal;
        if (purch > 0) {
          profit = curr - purch;
          profitRate = ((profit / purch) * 100).toFixed(1);
        }
      } else if (pType === 'rental') {
        netEquity = curr - (dep + loanBal);
        if (purch > 0) {
          profit = curr - purch;
          profitRate = ((profit / purch) * 100).toFixed(1);
        }
      } else {
        netEquity = dep - loanBal;
      }

      if (app.$("#rePreviewEquity")) app.$("#rePreviewEquity").textContent = `₩${app.number(netEquity, 0)}`;
      if (app.$("#rePreviewProfitWrap")) {
        app.$("#rePreviewProfitWrap").style.display = pType !== 'lease' ? "block" : "none";
        if (pType !== 'lease') {
          const pSign = profit >= 0 ? "+" : "";
          if (app.$("#rePreviewProfit")) {
            app.$("#rePreviewProfit").textContent = `${pSign}₩${app.number(profit, 0)} (${pSign}${profitRate}%)`;
            app.$("#rePreviewProfit").style.color = profit >= 0 ? "#42d5a3" : "#f43f5e";
          }
        }
      }
    }

    function updateRealEstateTypeFields() {
      realEstateView.updateFormTypeFields();

      calcRealEstatePreview();
    }

    function renderJointOwnershipRows(ownerships = []) {
      const container = app.$("#reJointRows");
      if (!container) return;
      const members = (typeof familyMembers !== 'undefined' && familyMembers && familyMembers.length)
        ? familyMembers
        : ['아빠', '엄마', '자녀'];

      const rows = (ownerships && ownerships.length) ? ownerships : [
        { owner: members[0] || '아빠', ratio: 50 },
        { owner: members[1] || '엄마', ratio: 50 }
      ];

      container.innerHTML = rows.map(r => `
    <div class="re-joint-row" style="display:flex;align-items:center;gap:8px;">
      <select class="re-joint-owner-select" style="flex:1;">
        ${members.map(m => `<option value="${m}" ${m === r.owner ? 'selected' : ''}>${m}</option>`).join('')}
      </select>
      <div style="display:flex;align-items:center;gap:4px;width:110px;">
        <input type="number" class="re-joint-ratio-input" value="${r.ratio}" min="1" max="100" step="1" style="width:70px;text-align:right;" />
        <span style="font-size:12px;color:#94a3b8;">%</span>
      </div>
      <button type="button" class="mini-delete-button re-joint-del-btn" title="삭제" style="padding:2px 6px;">×</button>
    </div>
  `).join('');

      updateJointTotalRatio();
    }

    function updateJointTotalRatio() {
      const inputs = document.querySelectorAll('.re-joint-ratio-input');
      let sum = 0;
      inputs.forEach(inp => sum += Number(inp.value || 0));
      const totalEl = app.$("#reJointTotalRatio");
      if (totalEl) {
        totalEl.textContent = `지분율 합계: ${sum}%`;
        totalEl.style.color = sum === 100 ? "#38bdf8" : "#fb7185";
      }
    }

    function openRealEstateDialog(reItem = null) {
      const dialog = app.$("#realEstateDialog");
      const form = app.$("#realEstateForm");
      if (!dialog || !form) return;
      form.reset();
      form.querySelector("[name='id']").value = reItem ? reItem.id : "";

      if (app.$("#realEstateDialogTitle")) {
        app.$("#realEstateDialogTitle").textContent = reItem ? "부동산 자산 수정" : "부동산 자산 추가";
      }

      const loanSelect = app.$("#reLinkedLoansSelect");
      if (loanSelect) {
        let opts = '<option value="">-- 연결 대출 없음 --</option>';
        app.rawLoanAccounts.forEach(l => {
          const typeStr = app.loanTypeLabels[l.loan_type] || "대출";
          opts += `<option value="${l.id}">${l.bank_name} - ${l.product_name} (${typeStr}, 잔액 ₩${app.number(l.current_balance, 0)})</option>`;
        });
        loanSelect.innerHTML = opts;
      }

      const isJoint = Boolean(reItem?.is_joint_ownership);
      const jointCheck = app.$("#reIsJointCheck");
      if (jointCheck) jointCheck.checked = isJoint;

      realEstateView.showJointOwnershipFields(isJoint);

      renderJointOwnershipRows(reItem?.ownerships || []);

      if (reItem) {
        form.querySelector("[name='property_type']").value = reItem.property_type || "own";
        form.querySelector("[name='owner']").value = reItem.ownerships?.[0]?.owner || reItem.owner || "모두";
        form.querySelector("[name='name']").value = reItem.name || "";
        form.querySelector("[name='dong_ho']").value = reItem.dong_ho || "";
        form.querySelector("[name='address']").value = reItem.address || "";
        form.querySelector("[name='purchase_price']").value = reItem.purchase_price || "";
        form.querySelector("[name='current_price']").value = reItem.current_price || "";
        form.querySelector("[name='deposit_amount']").value = reItem.deposit_amount || "";
        form.querySelector("[name='monthly_rent']").value = reItem.monthly_rent || "";
        form.querySelector("[name='contract_date']").value = reItem.contract_date || "";
        form.querySelector("[name='expiry_date']").value = reItem.expiry_date || "";
        form.querySelector("[name='exclusive_area']").value = reItem.exclusive_area || "";
        form.querySelector("[name='memo']").value = reItem.memo || "";
        form.querySelector("[name='kb_complex_no']").value = reItem.kb_complex_no || "";

        const linkedIds = reItem.linked_loan_ids || [];
        if (loanSelect) loanSelect.value = linkedIds[0] || "";
      } else {
        form.querySelector("[name='owner']").value = app.currentOwner !== "모두" ? app.currentOwner : "모두";
        form.querySelector("[name='kb_complex_no']").value = "";
      }

      const kbBox = app.$("#reKbResultBox");
      if (kbBox) kbBox.style.display = "none";

      updateRealEstateTypeFields();
      app.refreshDialogKoreanHints(dialog);
      dialog.showModal();
    }

    let currentKbTypes = [];

    async function fetchKbMarketPrice() {
      const nameInput = app.$("#reNameInput");
      const areaInput = app.$("#reExclusiveArea");
      const complexNoInput = app.$("#reKbComplexNo");
      const btn = app.$("#reFetchKbBtn");
      const resultBox = app.$("#reKbResultBox");
      const resultDetail = app.$("#reKbResultDetail");
      const typeSelectWrap = app.$("#reKbTypeSelectWrap");
      const typeSelect = app.$("#reKbTypeSelect");

      const name = (nameInput?.value || "").trim();
      if (!name) {
        alert("단지명(아파트명)을 먼저 입력해 주세요.");
        nameInput?.focus();
        return;
      }

      const area = Number(areaInput?.value || 0);
      const complexNo = (complexNoInput?.value || "").trim();

      if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳ 조회 중...";
      }

      try {
        const res = await app.api(`/api/real-estates/kb-price?name=${encodeURIComponent(name)}&area=${area}&complex_no=${encodeURIComponent(complexNo)}`);
        if (!res.ok) {
          alert(res.message || "KB시세를 찾을 수 없습니다.");
          return;
        }

        if (complexNoInput) complexNoInput.value = res.complex_no;
        currentKbTypes = res.types || [];

        const matched = res.matched;
        if (resultBox) resultBox.style.display = "block";

        if (matched) {
          if (resultDetail) {
            resultDetail.innerHTML = `
          <strong>단지</strong>: ${app.html(res.complex_info?.name || name)}\x20
          <span style="color:#facc15;">[${app.html(matched.type_display)}]</span><br/>
          <strong>KB 매매 일반평균가</strong>: <span style="font-size:13px;font-weight:700;color:#38bdf8;">₩${app.number(matched.deal_avg, 0)}</span><br/>
          <small style="color:#94a3b8;">하한가 ₩${app.number(matched.deal_low, 0)} ~ 상한가 ₩${app.number(matched.deal_high, 0)} · 전세 ₩${app.number(matched.lease_avg, 0)}</small>
        `;
          }
          // 현재 시세에 자동 적용
          const currInput = app.$("#reCurrentPrice");
          if (currInput && (!currInput.value || Number(currInput.value) === 0 || confirm(`조회된 KB 일반평균가(₩${app.number(matched.deal_avg, 0)})를 현재 시세에 적용할까요?`))) {
            currInput.value = matched.deal_avg;
            app.updateKoreanCurrencyHint(currInput);
            calcRealEstatePreview();
          }
        }

        // 평형 선택 드롭다운 구성
        if (typeSelect && currentKbTypes.length > 1) {
          typeSelect.innerHTML = currentKbTypes.map((t, idx) => `
        <option value="${idx}" ${t === matched ? 'selected' : ''}>
          ${t.type_display} - 일반가 ₩${app.number(t.deal_avg, 0)}
        </option>
      `).join('');
          if (typeSelectWrap) typeSelectWrap.style.display = "block";
        } else if (typeSelectWrap) {
          typeSelectWrap.style.display = "none";
        }

      } catch (err) {
        alert("KB시세 조회 실패: " + (err.message || err));
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "🔍 KB시세 조회";
        }
      }
    }

    // ── 부동산 매각 및 실현손익 기록 다이얼로그 제어 ─────────────────────────
    function openRealEstateSellDialog(reItem, editPnlItem = null) {
      const dlg = document.getElementById("realEstateSellDialog");
      if (!dlg) return;

      const titleEl = document.getElementById("reSellDialogTitle");
      const targetIdEl = document.getElementById("reSellTargetId");
      const editPnlIdEl = document.getElementById("reSellEditPnlId");
      const nameEl = document.getElementById("reSellName");
      const addressEl = document.getElementById("reSellAddress");
      const ownerEl = document.getElementById("reSellOwner");
      const dateEl = document.getElementById("reSellDate");
      const purchEl = document.getElementById("reSellPurchasePrice");
      const priceEl = document.getElementById("reSellPrice");
      const expEl = document.getElementById("reSellExpenses");
      const memoEl = document.getElementById("reSellMemo");
      const removeEl = document.getElementById("reSellRemoveFromAssets");
      const removeWrap = document.getElementById("reSellRemoveFromAssetsWrap");
      const submitBtn = document.getElementById("reSellSubmitBtn");

      // 가족 소유자 목록 옵션 갱신
      if (ownerEl) {
        const familyMembers = (app.rawDashboard && app.rawDashboard.family_members) || ['아빠', '엄마'];
        const opts = ['모두', ...familyMembers];
        ownerEl.innerHTML = Array.from(new Set(opts)).map(m => `<option value="${m}">${m}</option>`).join('');
      }

      if (editPnlItem) {
        // 1) 기존 매도 기록 수정 모드
        if (titleEl) titleEl.textContent = "🏢 부동산 매도 기록 수정";
        if (submitBtn) submitBtn.textContent = "매도 기록 수정 완료";
        if (targetIdEl) targetIdEl.value = "";
        if (editPnlIdEl) editPnlIdEl.value = editPnlItem.id || "";
        if (nameEl) {
          nameEl.value = editPnlItem.clean_name || (editPnlItem.name || '').replace('[부동산]', '').trim() || "";
          nameEl.readOnly = false;
          nameEl.style.background = "";
          nameEl.style.color = "";
        }
        if (addressEl) addressEl.value = editPnlItem.address || "";
        if (ownerEl) ownerEl.value = editPnlItem.owner || "모두";
        if (dateEl) dateEl.value = editPnlItem.date || new Date().toISOString().slice(0, 10);
        if (purchEl) {
          purchEl.value = editPnlItem.purchase_price || 0;
          purchEl.readOnly = false;
          purchEl.style.background = "";
          purchEl.style.color = "";
        }
        if (priceEl) priceEl.value = editPnlItem.sell_price || 0;
        if (expEl) expEl.value = editPnlItem.expenses || 0;
        if (memoEl) memoEl.value = editPnlItem.memo || "";
        if (removeWrap) removeWrap.style.display = "none";
      } else if (reItem) {
        // 2) 보유 부동산 매각 모드
        if (titleEl) titleEl.textContent = "🏢 부동산 매각 및 실현손익 기록";
        if (submitBtn) submitBtn.textContent = "실현손익에 기록";
        if (targetIdEl) targetIdEl.value = reItem.id || "";
        if (editPnlIdEl) editPnlIdEl.value = "";
        if (nameEl) {
          nameEl.value = reItem.name || "부동산";
          nameEl.readOnly = true;
          nameEl.style.background = "rgba(255,255,255,0.05)";
          nameEl.style.color = "#94a3b8";
        }
        if (addressEl) addressEl.value = reItem.address || "";
        if (ownerEl) ownerEl.value = reItem.owner || "모두";
        if (dateEl) dateEl.value = new Date().toISOString().slice(0, 10);
        if (purchEl) {
          purchEl.value = reItem.purchase_price || 0;
          purchEl.readOnly = true;
          purchEl.style.background = "rgba(255,255,255,0.05)";
          purchEl.style.color = "#94a3b8";
        }
        if (priceEl) priceEl.value = reItem.current_price || reItem.purchase_price || "";
        if (expEl) expEl.value = 0;
        if (memoEl) memoEl.value = "";
        if (removeWrap) removeWrap.style.display = "block";
        if (removeEl) removeEl.checked = true;
      } else {
        // 3) 직접 매도 기록 추가 모드
        if (titleEl) titleEl.textContent = "🏢 부동산 매도 기록 직접 추가";
        if (submitBtn) submitBtn.textContent = "매도 기록 등록";
        if (targetIdEl) targetIdEl.value = "direct";
        if (editPnlIdEl) editPnlIdEl.value = "";
        if (nameEl) {
          nameEl.value = "";
          nameEl.readOnly = false;
          nameEl.style.background = "";
          nameEl.style.color = "";
        }
        if (addressEl) addressEl.value = "";
        if (ownerEl) ownerEl.value = app.currentOwner || "모두";
        if (dateEl) dateEl.value = new Date().toISOString().slice(0, 10);
        if (purchEl) {
          purchEl.value = "";
          purchEl.readOnly = false;
          purchEl.style.background = "";
          purchEl.style.color = "";
        }
        if (priceEl) priceEl.value = "";
        if (expEl) expEl.value = 0;
        if (memoEl) memoEl.value = "";
        if (removeWrap) removeWrap.style.display = "none";
      }

      // 한글 통화 힌트 업데이트
      if (purchEl && typeof app.updateKoreanCurrencyHint === 'function') app.updateKoreanCurrencyHint(purchEl);
      if (priceEl && typeof app.updateKoreanCurrencyHint === 'function') app.updateKoreanCurrencyHint(priceEl);
      if (expEl && typeof app.updateKoreanCurrencyHint === 'function') app.updateKoreanCurrencyHint(expEl);

      calcRealEstateSellProfit();
      dlg.showModal();
    }


    function openDirectAddSoldReDialog() {
      openRealEstateSellDialog(null, null);
    }


    function calcRealEstateSellProfit() {
      const purch = Number(document.getElementById("reSellPurchasePrice")?.value || 0);
      const sell = Number(document.getElementById("reSellPrice")?.value || 0);
      const exp = Number(document.getElementById("reSellExpenses")?.value || 0);
      const pnl = sell - purch - exp;

      const pnlEl = document.getElementById("reSellPnlPreview");
      const formulaEl = document.getElementById("reSellCalcFormula");

      if (pnlEl) {
        const sign = pnl >= 0 ? "+" : "";
        pnlEl.textContent = `${sign}₩${app.number(pnl, 0)}`;
        pnlEl.style.color = pnl > 0 ? "#42d5a3" : (pnl < 0 ? "#f43f5e" : "#38bdf8");
      }
      if (formulaEl) {
        formulaEl.textContent = `양도가 ₩${app.number(sell, 0)} - 취득가 ₩${app.number(purch, 0)} - 필요경비 ₩${app.number(exp, 0)}`;
      }
    }


    async function submitRealEstateSell() {
      const reId = document.getElementById("reSellTargetId")?.value;
      const editPnlId = document.getElementById("reSellEditPnlId")?.value;

      const name = document.getElementById("reSellName")?.value?.trim() || "부동산";
      const address = document.getElementById("reSellAddress")?.value?.trim() || "";
      const owner = document.getElementById("reSellOwner")?.value || "모두";
      const sellPrice = Number(document.getElementById("reSellPrice")?.value || 0);
      const purchPrice = Number(document.getElementById("reSellPurchasePrice")?.value || 0);
      const sellDate = document.getElementById("reSellDate")?.value;
      const expenses = Number(document.getElementById("reSellExpenses")?.value || 0);
      const memo = document.getElementById("reSellMemo")?.value?.trim() || "";
      const removeFromAssets = document.getElementById("reSellRemoveFromAssets")?.checked ?? true;

      if (sellPrice <= 0) {
        alert("매도가액(양도가)을 올바르게 입력해 주세요.");
        return;
      }

      try {
        if (editPnlId) {
          // 1) 기존 매도 기록 수정
          const pnlKrw = Math.round(sellPrice - purchPrice - expenses);
          await app.api(`/api/realized-pnl/${editPnlId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: `[부동산] ${name}`,
              code: "REAL_ESTATE",
              asset_type: "real_estate",
              date: sellDate,
              currency: "KRW",
              pnl: pnlKrw,
              pnl_krw: pnlKrw,
              owner: owner,
              memo: memo || `매도가 ₩${app.number(sellPrice, 0)}, 매수가 ₩${app.number(purchPrice, 0)}, 필요경비 ₩${app.number(expenses, 0)}`,
              real_estate_name: name,
              purchase_price: purchPrice,
              sell_price: sellPrice,
              expenses: expenses,
              address: address,
            }),
          });
          app.toast("부동산 매도 기록이 수정되었습니다.");
        } else {
          // 2) 신규 매각 기록 (보유 부동산 매각 or 직접 매도 추가)
          const targetEndpoint = (reId && reId !== "direct") ? `/api/real-estates/${reId}/sell` : `/api/real-estates/direct/sell`;
          const res = await app.api(targetEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: name,
              owner: owner,
              purchase_price: purchPrice,
              sell_price: sellPrice,
              sell_date: sellDate,
              expenses: expenses,
              address: address,
              remove_from_assets: (reId && reId !== "direct") ? removeFromAssets : false,
              memo: memo,
            }),
          });
          app.toast(res.message || "부동산 매각 실현손익이 기록되었습니다.");
        }

        document.getElementById("realEstateSellDialog")?.close();
        await app.loadDashboard();
        await app.loadRealizedPnl(app.currentOwner);
      } catch (err) {
        alert(`부동산 매각 처리 오류: ${err.message}`);
      }
    }

    function bindForm() {
      const reForm = app.$("#realEstateForm");
      if (reForm) {
        reForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(reForm);
          const linkedLoanId = fd.get("linked_loan_ids");
          const linkedLoanIds = linkedLoanId ? [linkedLoanId] : [];

          const isJoint = Boolean(document.getElementById("reIsJointCheck")?.checked);
          const ownerships = [];
          if (isJoint) {
            document.querySelectorAll("#reJointRows .re-joint-row").forEach(row => {
              const mOwner = row.querySelector(".re-joint-owner-select")?.value;
              const mRatio = Number(row.querySelector(".re-joint-ratio-input")?.value || 0);
              if (mOwner && mRatio > 0) {
                ownerships.push({ owner: mOwner, ratio: mRatio });
              }
            });
          }

          const payload = {
            id: fd.get("id") || undefined,
            property_type: fd.get("property_type") || "own",
            owner: fd.get("owner") || "모두",
            name: fd.get("name") || "",
            dong_ho: fd.get("dong_ho") || "",
            address: fd.get("address") || "",
            is_joint_ownership: isJoint,
            ownerships: ownerships,
            purchase_price: Number(fd.get("purchase_price")) || 0,
            current_price: Number(fd.get("current_price")) || 0,
            deposit_amount: Number(fd.get("deposit_amount")) || 0,
            monthly_rent: Number(fd.get("monthly_rent")) || 0,
            contract_date: fd.get("contract_date") || "",
            expiry_date: fd.get("expiry_date") || "",
            exclusive_area: Number(fd.get("exclusive_area")) || 0,
            kb_complex_no: fd.get("kb_complex_no") || "",
            linked_loan_ids: linkedLoanIds,
            memo: fd.get("memo") || "",
          };

          try {
            await app.api("/api/real-estates", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            app.toast("부동산 자산 정보가 저장되었습니다.");
            app.closeDialog("realEstateDialog");
            await app.loadDashboard();
          } catch (err) {
            app.toast(err.message || "부동산 자산 저장 실패", true);
          }
        });

        realEstateView.bindFormInputs({ updateRealEstateTypeFields, calcRealEstatePreview });

        // KB시세 조회 버튼 리스너
        document.getElementById("reFetchKbBtn")?.addEventListener("click", fetchKbMarketPrice);

        // KB시세 적용 버튼 리스너
        document.getElementById("reApplyKbPriceBtn")?.addEventListener("click", () => {
          const typeSelect = document.getElementById("reKbTypeSelect");
          const currInput = document.getElementById("reCurrentPrice");
          if (typeSelect && currentKbTypes.length && currInput) {
            const selectedIdx = Number(typeSelect.value || 0);
            const selType = currentKbTypes[selectedIdx];
            if (selType && selType.deal_avg > 0) {
              currInput.value = selType.deal_avg;
              app.updateKoreanCurrencyHint(currInput);
              calcRealEstatePreview();
              app.toast(`KB시세(₩${app.number(selType.deal_avg, 0)})가 현재 시세에 적용되었습니다.`);
            }
          }
        });

        // KB 평형 선택 변경 리스너
        document.getElementById("reKbTypeSelect")?.addEventListener("change", (e) => {
          const idx = Number(e.target.value || 0);
          const selType = currentKbTypes[idx];
          const resultDetail = document.getElementById("reKbResultDetail");
          const name = document.getElementById("reNameInput")?.value || "";
          if (selType && resultDetail) {
            resultDetail.innerHTML = `
          <strong>단지</strong>: ${app.html(name)}\x20
          <span style="color:#facc15;">[${app.html(selType.type_display)}]</span><br/>
          <strong>KB 매매 일반평균가</strong>: <span style="font-size:13px;font-weight:700;color:#38bdf8;">₩${app.number(selType.deal_avg, 0)}</span><br/>
          <small style="color:#94a3b8;">하한가 ₩${app.number(selType.deal_low, 0)} ~ 상한가 ₩${app.number(selType.deal_high, 0)} · 전세 ₩${app.number(selType.lease_avg, 0)}</small>
        `;
          }
        });

        // 공동명의 체크박스 토글 리스너
        document.getElementById("reIsJointCheck")?.addEventListener("change", (e) => {
          const checked = e.target.checked;
          const singleWrap = document.getElementById("reSingleOwnerWrap");
          const jointWrap = document.getElementById("reJointOwnershipWrap");
          if (singleWrap) singleWrap.style.display = checked ? "none" : "block";
          if (jointWrap) jointWrap.style.display = checked ? "block" : "none";
          if (checked) {
            const rows = document.querySelectorAll("#reJointRows .re-joint-row");
            if (!rows.length) renderJointOwnershipRows();
          }
        });

        // 공동명의 행 추가 버튼 리스너
        document.getElementById("reAddJointRowBtn")?.addEventListener("click", () => {
          const container = document.getElementById("reJointRows");
          if (!container) return;
          const members = (typeof familyMembers !== 'undefined' && familyMembers && familyMembers.length)
            ? familyMembers
            : ['아빠', '엄마', '자녀'];
          const div = document.createElement("div");
          div.className = "re-joint-row";
          div.style.cssText = "display:flex;align-items:center;gap:8px;";
          div.innerHTML = `
        <select class="re-joint-owner-select" style="flex:1;">
          ${members.map(m => `<option value="${m}">${m}</option>`).join('')}
        </select>
        <div style="display:flex;align-items:center;gap:4px;width:110px;">
          <input type="number" class="re-joint-ratio-input" value="50" min="1" max="100" step="1" style="width:70px;text-align:right;" />
          <span style="font-size:12px;color:#94a3b8;">%</span>
        </div>
        <button type="button" class="mini-delete-button re-joint-del-btn" title="삭제" style="padding:2px 6px;">×</button>
      `;
          container.appendChild(div);
          updateJointTotalRatio();
        });

        // 공동명의 행 삭제 및 지분율 입력 이벤트 위임
        document.getElementById("reJointRows")?.addEventListener("click", (e) => {
          if (e.target.closest(".re-joint-del-btn")) {
            e.target.closest(".re-joint-row")?.remove();
            updateJointTotalRatio();
          }
        });
        document.getElementById("reJointRows")?.addEventListener("input", (e) => {
          if (e.target.classList.contains("re-joint-ratio-input")) {
            updateJointTotalRatio();
          }
        });
      }
    }

    function showSoldRealEstates() {
      currentRealEstateSubtab = 'sold';
      document.querySelectorAll('.real-estate-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === 'sold'));
      renderRealEstateWithOwner(app.currentOwner);
    }

    function selectRealEstateSubtab(reSubtabBtn) {
      const subtab = reSubtabBtn.dataset.subtab;
      currentRealEstateSubtab = subtab;
      document.querySelectorAll('.real-estate-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === subtab));
      renderRealEstateWithOwner(app.currentOwner);
    }

    function editSoldRealEstate(soldEditBtn) {
      const sid = soldEditBtn.dataset.soldReEdit;
      const soldItem = rawSoldRealEstates.find(s => s.id === sid);
      if (soldItem) openRealEstateSellDialog(null, soldItem);
    }

    async function deleteSoldRealEstate(soldDelBtn) {
      const sid = soldDelBtn.dataset.soldReDel;
      const soldItem = rawSoldRealEstates.find(s => s.id === sid);
      const sName = soldItem ? (soldItem.clean_name || soldItem.name || '부동산') : '이 부동산 매도';
      if (confirm(`'${sName}'의 매도 실현손익 기록을 삭제하시겠습니까?`)) {
        try {
          await app.api(`/api/realized-pnl/${sid}`, { method: 'DELETE' });
          app.toast('부동산 매도 실현손익 기록이 삭제되었습니다.');
          await app.loadDashboard();
          await app.loadRealizedPnl(app.currentOwner);
        } catch (err) {
          app.toast(err.message || '삭제 실패', true);
        }
      }
    }

    async function refreshRealEstateKbPrice(reKbRefreshBtn) {
      const rid = reKbRefreshBtn.dataset.reRefreshKbId;
      reKbRefreshBtn.disabled = true;
      reKbRefreshBtn.textContent = '⏳';
      try {
        const res = await app.api(`/api/real-estates/${rid}/refresh-kb-price`, { method: 'POST' });
        app.toast(res.message || 'KB시세가 갱신되었습니다.');
        await app.loadDashboard();
      } catch (err) {
        app.toast(err.message || 'KB시세 갱신 실패', true);
      } finally {
        reKbRefreshBtn.disabled = false;
        reKbRefreshBtn.textContent = '🔄';
      }
    }

    function openRealEstateSale(reSellBtn) {
      const rid = reSellBtn.dataset.reSellId;
      const reItem = rawRealEstates.find(r => r.id === rid);
      if (reItem) openRealEstateSellDialog(reItem);
    }

    function editRealEstate(reEditBtn) {
      const rid = reEditBtn.dataset.reEditId;
      const reItem = rawRealEstates.find(r => r.id === rid);
      if (reItem) openRealEstateDialog(reItem);
    }

    async function deleteRealEstate(reDelBtn) {
      const rid = reDelBtn.dataset.reDelId;
      const reItem = rawRealEstates.find(r => r.id === rid);
      const reName = reItem ? reItem.name : '이 부동산 자산';
      if (confirm(`'${reName}'을(를) 삭제하시겠습니까?\n(연결된 대출과의 링크도 함께 해제됩니다.)`)) {
        try {
          await app.api(`/api/real-estates/${rid}`, { method: 'DELETE' });
          app.toast('부동산 자산이 삭제되었습니다.');
          await app.loadDashboard();
        } catch (err) {
          app.toast(err.message || '삭제 실패', true);
        }
      }
    }

    return {
      publicActions: {
        renderRealEstate,
        renderRealEstateWithOwner,
        calcRealEstatePreview,
        updateRealEstateTypeFields,
        renderJointOwnershipRows,
        updateJointTotalRatio,
        openRealEstateDialog,
        fetchKbMarketPrice,
        openRealEstateSellDialog,
        openDirectAddSoldReDialog,
        calcRealEstateSellProfit,
        submitRealEstateSell,
      },
      actions: {
        bindForm,
        showSoldRealEstates,
        selectRealEstateSubtab,
        editSoldRealEstate,
        deleteSoldRealEstate,
        refreshRealEstateKbPrice,
        openRealEstateSale,
        editRealEstate,
        deleteRealEstate,
      },
      get rawRealEstates() { return rawRealEstates; },
    };
  }

  window.WealthRealEstateFeatureController = { create };
})();
