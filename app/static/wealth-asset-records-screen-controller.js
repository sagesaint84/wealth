(() => {
  'use strict';

  function create({ document, $, stockRecordsView, renderTaxAccountHoldings }) {
    function render(records, currentRecordPeriod, currentRecordView, currentOwner) {
      const recordsEyebrow = document.getElementById('recordsEyebrow');
      const recordsHeading = document.getElementById('recordsHeadingText');
      const taxView = currentRecordView === 'tax_accounts';
      if (recordsEyebrow) recordsEyebrow.textContent = taxView ? 'TAX-ADVANTAGED ACCOUNTS' : 'STOCK RECORDS';
      if (recordsHeading) recordsHeading.textContent = taxView ? '절세계좌' : '주식기록';

      if (taxView) {
        $("#recordsPanel")?.classList.add("is-tax-view");
        const sideSummaryEl = document.querySelector(".record-side-summary");
        if (sideSummaryEl) sideSummaryEl.style.display = "none";
        if ($("#recordPeriodTabs")) $("#recordPeriodTabs").style.display = "none";
        if ($("#snapshotButton")) $("#snapshotButton").style.display = "none";
        if ($("#addRecordButton")) $("#addRecordButton").style.display = "none";
        if ($("#recordCount")) $("#recordCount").style.display = "none";
        renderTaxAccountHoldings(currentOwner);
        return;
      }

      // 전체주식 콤보 차트 뷰 툴바 및 레이아웃 복원
      $("#recordsPanel")?.classList.remove("is-tax-view");
      const sideSummaryEl = document.querySelector(".record-side-summary");
      if (sideSummaryEl) sideSummaryEl.style.display = "";
      if ($("#snapshotButton")) $("#snapshotButton").style.display = "";
      if ($("#addRecordButton")) $("#addRecordButton").style.display = "";
      if ($("#recordPeriodTabs")) $("#recordPeriodTabs").style.display = "";
      if ($("#recordPeriodTabs")) $("#recordPeriodTabs").style.opacity = "1";
      if ($("#recordCount")) $("#recordCount").style.display = "";
      const sideSummarySmall = document.querySelector(".record-side-summary small");
      if (sideSummarySmall) sideSummarySmall.textContent = "저장된 날짜별 자산 추이";

      stockRecordsView.render(records, currentRecordPeriod, currentRecordView);
    }

    function openRecordDialog(record, { getNetWorth, getOwner }) {
      const form = $("#assetRecordForm");
      if (!form) return;
      form.reset();
      form.dataset.recordId = record?.id || "";
      $("#assetRecordDialogTitle") && ($("#assetRecordDialogTitle").textContent = record ? "주식기록 수정" : "주식기록 추가");
      form.date.value = record?.date || new Date().toISOString().slice(0, 10);
      form.total_value_krw.value = record?.total_value_krw ?? record?.total_assets_krw ?? "";
      if (form.total_assets_krw) form.total_assets_krw.value = record?.total_assets_krw ?? record?.total_value_krw ?? "";
      if (form.total_debt_krw) form.total_debt_krw.value = record?.total_debt_krw ?? "";
      if (form.net_worth_krw) form.net_worth_krw.value = getNetWorth();
      form.total_cost_krw.value = record?.total_cost_krw ?? "";
      form.profit_krw.value = record?.profit_krw ?? "";
      form.return_rate.value = record?.return_rate ?? "";
      form.day_profit_krw.value = record?.day_profit_krw ?? "";
      form.krw_value_krw.value = record?.krw_value_krw ?? "";
      form.usd_value_krw.value = record?.usd_value_krw ?? "";
      form.holding_count.value = record?.holding_count ?? "";
      form.memo.value = record?.memo ?? "";
      if (form.owner) form.owner.value = getOwner();
      $("#assetRecordDialog")?.showModal();
    }

    return Object.freeze({ render, openRecordDialog });
  }

  window.WealthAssetRecordsScreenController = Object.freeze({ create });
})();
