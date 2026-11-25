(() => {
  "use strict";

  function bind({
    document, appShell, accountActions, familyActions, incomeActions, insuranceActions,
    investmentActions, realEstateActions, confirm, selectOwner, switchAccountCategory,
    openFamilyManager, openIntegratedBankDialog, openBankAccountDialog, openSavingAccountDialog,
    openLoanAccountDialog, openInsuranceAccountDialog, openRealEstateDialog,
  }) {
    document.addEventListener('click', async (e) => {
      if (appShell.handleThemeClick(e)) return;

      // 가족 탭 선택 (모든 섹션 전역 연동)
      const familyTab = e.target.closest('.family-tabs .family-tab');
      if (familyTab) {
        selectOwner(familyTab.dataset.owner);
        return;
      }

      // 🔍 자산분류 항목(섹터/자산군) 클릭 시 보유종목 자동 검색 & 스크롤 연동
      const sectorItem = e.target.closest('[data-sector-filter]');
      if (sectorItem) {
        investmentActions.selectSector(e, sectorItem);
        return;
      }

      // 👨‍👩‍👧‍👦 가족 구성원 관리 모달 열기 (상단바 & 계좌 섹션)
      if (e.target.closest('#topbarFamilyBtn, #manageFamilyBtn')) {
        await openFamilyManager();
        return;
      }

      // 🗂️ 계좌 3대 카테고리 (증권 / 은행 / 보험) 탭 전환
      const catTab = e.target.closest('.account-cat-tab');
      if (catTab) {
        e.preventDefault();
        switchAccountCategory(catTab.dataset.cat);
        return;
      }

      // ➕ 계좌 추가 모달 열기 (증권 계좌)
      if (e.target.closest('#addAccountBtn')) {
        accountActions.openAccountAddDialog();
        return;
      }

      // 🏦 통합 은행 계좌 추가 모달 열기 (자유통장 / 예·적금 / 대출)
      if (e.target.closest('#addBankIntegratedBtn')) {
        openIntegratedBankDialog();
        return;
      }

      // 🏦 일반 은행 계좌 추가 모달 열기 (하위 호환)
      if (e.target.closest('#addBankAccountBtn')) {
        openBankAccountDialog();
        return;
      }

      // ➕ 예·적금 추가 모달 열기
      if (e.target.closest('#addSavingBtn')) {
        openSavingAccountDialog();
        return;
      }

      // 💳 대출·마이너스통장 추가 모달 열기
      if (e.target.closest('#addLoanBtn')) {
        openLoanAccountDialog();
        return;
      }

      // ➕ 보험/연금/공제 추가 모달 열기
      if (e.target.closest('#addInsuranceBtn')) {
        openInsuranceAccountDialog();
        return;
      }

      // 🏠 부동산 자산 추가 모달 열기
      if (e.target.closest('#addRealEstateBtn')) {
        openRealEstateDialog();
        return;
      }

      // ✎ 증권/연금/IRP 계좌 정보 수정 모달 열기 (증권 탭, 보험/연금 탭, 절세계좌 탭 어디서든 100% 동작)
      const acctEditBtn = e.target.closest('[data-account-edit-id]');
      if (acctEditBtn) {
        accountActions.editAccountFromRow(e, acctEditBtn);
        return;
      }

      const historyButton = e.target.closest('[data-national-history-id]');
      const analysisButton=e.target.closest('[data-national-analysis-id]');
      const importButton=e.target.closest('[data-national-import-id]');
      if(analysisButton||importButton){
        insuranceActions.openNationalPensionTool(analysisButton, importButton);
        return;
      }
      if (historyButton) {
        insuranceActions.openNationalPensionHistoryFromRow(historyButton);
        return;
      }
      // 보험/연금 수정
      const insEditBtn = e.target.closest('[data-insurance-edit-id]');
      if (insEditBtn) {
        insuranceActions.editInsuranceAccount(insEditBtn);
        return;
      }

      // 보험/연금 삭제
      const insDelBtn = e.target.closest('[data-insurance-del-id]');
      if (insDelBtn) {
        await insuranceActions.deleteInsuranceAccount(insDelBtn);
        return;
      }

      // 대출·마이너스통장 수정
      const loanEditBtn = e.target.closest('[data-loan-edit-id]');
      if (loanEditBtn) {
        accountActions.editLoanAccount(loanEditBtn);
        return;
      }

      // 대출·마이너스통장 삭제
      const loanDelBtn = e.target.closest('[data-loan-del-id]');
      if (loanDelBtn) {
        await accountActions.deleteLoanAccount(loanDelBtn);
        return;
      }

      // 🗂️ 은행 서브 탭 전환 (전체 / 자유 / 예적금 / 대출)
      const subtabBtn = e.target.closest('.savings-subtab');
      if (subtabBtn) {
        accountActions.selectSavingsSubtab(subtabBtn);
        return;
      }

      // 🏷️ 상단 부동산 실현손익 카드 클릭 시 [매도] 서브탭으로 즉시 전환
      if (e.target.closest('#cardRealEstateRealized')) {
        realEstateActions.showSoldRealEstates();
        return;
      }

      // 🗂️ 부동산 서브 탭 전환 (전체 / 자가보유 / 임대 / 임차 / 매도)
      const reSubtabBtn = e.target.closest('.real-estate-subtab');
      if (reSubtabBtn) {
        realEstateActions.selectRealEstateSubtab(reSubtabBtn);
        return;
      }

      // 매도 부동산 기록 수정
      const soldEditBtn = e.target.closest('[data-sold-re-edit]');
      if (soldEditBtn) {
        realEstateActions.editSoldRealEstate(soldEditBtn);
        return;
      }

      // 매도 부동산 기록 삭제
      const soldDelBtn = e.target.closest('[data-sold-re-del]');
      if (soldDelBtn) {
        await realEstateActions.deleteSoldRealEstate(soldDelBtn);
        return;
      }

      // 부동산 KB시세 즉시 갱신
      const reKbRefreshBtn = e.target.closest('[data-re-refresh-kb-id]');
      if (reKbRefreshBtn) {
        await realEstateActions.refreshRealEstateKbPrice(reKbRefreshBtn);
        return;
      }

      // 부동산 매각 및 실현손익 기록
      const reSellBtn = e.target.closest('[data-re-sell-id]');
      if (reSellBtn) {
        realEstateActions.openRealEstateSale(reSellBtn);
        return;
      }

      // 부동산 수정
      const reEditBtn = e.target.closest('[data-re-edit-id]');
      if (reEditBtn) {
        realEstateActions.editRealEstate(reEditBtn);
        return;
      }

      // 부동산 삭제
      const reDelBtn = e.target.closest('[data-re-del-id]');
      if (reDelBtn) {
        await realEstateActions.deleteRealEstate(reDelBtn);
        return;
      }


      // 예·적금 수정
      const savingEditBtn = e.target.closest('[data-saving-edit-id]');
      if (savingEditBtn) {
        accountActions.editSavingAccount(savingEditBtn);
        return;
      }

      // 예·적금 삭제
      const savingDelBtn = e.target.closest('[data-saving-del-id]');
      if (savingDelBtn) {
        await accountActions.deleteSavingAccount(savingDelBtn);
        return;
      }

      // 은행 계좌 수정
      const bankEditBtn = e.target.closest('[data-bank-edit-id]');
      if (bankEditBtn) {
        accountActions.editBankAccount(bankEditBtn);
        return;
      }

      // 은행 계좌 삭제
      const bankDelBtn = e.target.closest('[data-bank-del-id]');
      if (bankDelBtn) {
        await accountActions.deleteBankAccount(bankDelBtn);
        return;
      }

      // 가족 구성원 추가
      if (e.target.closest('#addMemberBtn')) {
        await familyActions.addFamilyMember();
        return;
      }

      // 가족 구성원 이름 수정
      const renameBtn = e.target.closest('.family-rename-btn');
      if (renameBtn) {
        await familyActions.renameFamilyMember(renameBtn);
        return;
      }

      // 가족 구성원 삭제
      const deleteMemberBtn = e.target.closest('.family-delete-btn');
      if (deleteMemberBtn) {
        await familyActions.deleteFamilyMember(deleteMemberBtn);
        return;
      }

      // 절세계좌 보유종목 정렬 헤더 클릭
      const taxTh = e.target.closest('#assetChart [data-tax-sort]');
      if (taxTh) {
        investmentActions.sortTaxHoldings(taxTh);
        return;
      }

      // 절세계좌 보유종목 수정/삭제 버튼
      const taxEditBtn = e.target.closest('#assetChart .edit-button');
      const taxDelBtn = e.target.closest('#assetChart .delete-button');
      if (taxEditBtn) {
        investmentActions.editTaxHolding(taxEditBtn);
        return;
      }
      if (taxDelBtn && confirm("이 보유종목을 삭제할까요?")) {
        await investmentActions.deleteTaxHolding(taxDelBtn);
        return;
      }

      // 실현손익 테이블 정렬 헤더 클릭
      const pnlTh = e.target.closest('#pnlMonthlyDetail [data-pnl-sort]');
      if (pnlTh) {
        incomeActions.sortPnlDetail(pnlTh);
        return;
      }

      // 배당금 테이블 정렬 헤더 클릭
      const divTh = e.target.closest('#dividendMonthlyDetail [data-div-sort]');
      if (divTh) {
        incomeActions.sortDividendDetail(divTh);
        return;
      }

      // 보유종목 정렬 헤더 클릭
      const th = e.target.closest('.sortable-th');
      if (th && th.dataset.sort) {
        investmentActions.sortHoldings(th);
        return;
      }

      // 종목 차트 버튼 또는 종목명 클릭
      const chartBtn = e.target.closest('.stock-chart-btn, .holding-name-link');
      if (chartBtn) {
        investmentActions.openHoldingChart(chartBtn);
        return;
      }

      // 종목 차트 모달 기간 탭 클릭
      const chartTab = e.target.closest('#stockChartPeriodTabs .heatmap-tab');
      if (chartTab) {
        await investmentActions.selectChartPeriod(chartTab);
        return;
      }

      // 배당 재조회 버튼
      const divRefreshBtn = e.target.closest('#refreshDividendBtn');
      if (divRefreshBtn) {
        incomeActions.refreshDividends(divRefreshBtn);
        return;
      }

      // 배당 모드 탭 (🔮 예상 vs 💵 실제)
      const divModeTab = e.target.closest('#dividendModeTabs .heatmap-tab');
      if (divModeTab) {
        incomeActions.switchDividendMode(divModeTab);
        return;
      }

      // 💾 실제 배당 저장하기 버튼
      if (e.target.closest('#dividendSaveBtn')) {
        incomeActions.submitDividend(e);
        return;
      }

      // 💾 매도 실현손익 저장하기 버튼
      if (e.target.closest('#pnlSaveBtn')) {
        incomeActions.submitPnl(e);
        return;
      }

      // ➕ 실제 배당 추가 버튼
      if (e.target.closest('#addDividendBtn')) {
        incomeActions.addDividend();
        return;
      }

      // 📂 실제 배당 가져오기 버튼
      if (e.target.closest('#importDividendBtn')) {
        incomeActions.openDividendImport();
        return;
      }

      // 🗑️ 실제 배당 전체 일괄 삭제 버튼
      if (e.target.closest('#clearAllDividendBtn')) {
        incomeActions.clearDividends();
        return;
      }

      // 실제 배당 수정 버튼
      const editActualDivBtn = e.target.closest('.edit-actual-div-btn');
      if (editActualDivBtn) {
        incomeActions.editDividend(editActualDivBtn);
        return;
      }

      // 실제 배당 삭제 버튼
      const delActualDivBtn = e.target.closest('.delete-actual-div-btn');
      if (delActualDivBtn) {
        await incomeActions.deleteDividend(delActualDivBtn);
        return;
      }

      // 배당 막대 차트 월/연도 선택
      const divBar = e.target.closest('.dividend-bar-group');
      if (divBar && incomeActions.selectDividendBar(divBar)) return;

      // 배당 전체 보기 버튼
      if (e.target.closest('#clearDivMonthBtn')) {
        incomeActions.clearDividendMonth();
        return;
      }

      // 실현손익 거래유형 탭 (🏢 전체 vs 📦 공모주)
      const pnlTab = e.target.closest('#pnlTradeTypeTabs .heatmap-tab');
      if (pnlTab) {
        incomeActions.selectPnlType(pnlTab);
        return;
      }

      // ➕ 실현손익 추가 버튼
      if (e.target.closest('#addPnlBtn')) {
        incomeActions.addPnl();
        return;
      }

      // 📂 실현손익 가져오기 버튼
      if (e.target.closest('#importPnlBtn')) {
        incomeActions.openPnlImport();
        return;
      }

      // 🗑️ 매도 실현손익 전체 일괄 삭제 버튼
      if (e.target.closest('#clearAllPnlBtn')) {
        incomeActions.clearPnl();
        return;
      }

      // 실현손익 수정 버튼
      const editPnlBtn = e.target.closest('.edit-pnl-btn');
      if (editPnlBtn) {
        incomeActions.editPnl(editPnlBtn);
        return;
      }

      // 실현손익 삭제 버튼
      const delPnlBtn = e.target.closest('.delete-pnl-btn');
      if (delPnlBtn) {
        await incomeActions.deletePnl(delPnlBtn);
        return;
      }

      // 실현손익 막대 차트 월/연도 선택
      const pnlBar = e.target.closest('.pnl-bar-group');
      if (pnlBar && incomeActions.selectPnlBar(pnlBar)) return;

      // 실현손익 전체 보기 버튼
      if (e.target.closest('#clearPnlMonthBtn')) {
        incomeActions.clearPnlMonth();
        return;
      }
    });
  }

  window.WealthGlobalActionController = { bind };
})();
