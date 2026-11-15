(() => {
  'use strict';

  function editValues(item) {
    return {
      fields: {
        insurance_type: item.insurance_type || "protection",
        owner: item.owner || "모두",
        company_name: item.company_name || "",
        product_name: item.product_name || "",
        payment_status: item.payment_status || "paying",
        income_bracket: item.income_bracket || "40m_to_100m",
        ...(item.marginal_tax_rate ? { marginal_tax_rate: String(item.marginal_tax_rate) } : {}),
        monthly_premium: item.monthly_premium || "",
        total_paid_amount: item.total_paid_amount || "",
        expected_amount: item.expected_amount || "",
      },
      monthlyPayout: item.monthly_payout || "",
      payoutDuration: String(item.payout_duration_years || 20),
      datesAndMemo: {
        start_date: item.start_date || "",
        maturity_date: item.maturity_date || "",
        memo: item.memo || "",
      },
    };
  }

  window.WealthInsuranceFormModel = Object.freeze({ editValues });
})();
