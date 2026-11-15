(() => {
  "use strict";

  function render(select, accounts, { placeholder, separator = " ", preserveMissingLabels = false, emptyMissingId = false }) {
    const document = select.ownerDocument;
    const placeholderOption = document.createElement("option");
    placeholderOption.value = "";
    placeholderOption.textContent = placeholder;
    const options = document.createDocumentFragment();
    options.append(placeholderOption);
    for (const account of accounts) {
      const option = document.createElement("option");
      const bankName = preserveMissingLabels ? account.bank_name : (account.bank_name ?? "");
      const accountName = preserveMissingLabels ? account.account_name : (account.account_name ?? "");
      option.value = emptyMissingId ? (account.id ?? "") : account.id;
      option.textContent = `${bankName}${separator}${accountName} (${account.owner || "모두"})`;
      options.append(option);
    }
    select.replaceChildren(options);
  }

  window.WealthBankAccountOptions = { render };
})();
