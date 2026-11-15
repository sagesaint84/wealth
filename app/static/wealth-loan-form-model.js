(() => {
  'use strict';

  function editValues(loan) {
    return {
      fields: {
        loan_type: loan.loan_type || "minus",
        owner: loan.owner || "모두",
        bank_name: loan.bank_name || "",
        product_name: loan.product_name || "",
        limit_amount: loan.limit_amount || "",
        current_balance: loan.current_balance || "",
        interest_rate: loan.interest_rate || "",
        repayment_type: loan.repayment_type || "bullet",
      },
      linkedAccountId: loan.linked_account_id || "",
      overdraftBankAccountId: loan.overdraft_bank_account_id || "",
      maturityDate: loan.maturity_date || "",
      memo: loan.memo || "",
    };
  }

  window.WealthLoanFormModel = Object.freeze({ editValues });
})();
