(() => {
  'use strict';

  function editValues(saving, isHousing) {
    return {
      fields: {
        saving_type: saving.saving_type || (isHousing ? "housing" : "deposit"),
        owner: saving.owner || "모두",
        bank_name: saving.bank_name || "",
        product_name: saving.product_name || "",
        start_date: saving.start_date || "",
        end_date: saving.end_date || "",
        duration_months: isHousing ? 0 : (saving.duration_months || 12),
        interest_rate: saving.interest_rate || "",
        monthly_amount: saving.monthly_amount || "",
        target_amount: saving.target_amount || "",
        current_paid_amount: saving.current_paid_amount || "",
        tax_type: saving.tax_type || "normal",
        auto_transfer_day: saving.auto_transfer_day || "",
      },
      withdrawAccountId: saving.withdraw_account_id || "",
      depositAccountId: saving.deposit_account_id || "",
      memo: saving.memo || "",
    };
  }

  window.WealthSavingsFormModel = Object.freeze({ editValues });
})();
