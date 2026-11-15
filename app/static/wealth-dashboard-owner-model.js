(() => {
  'use strict';

  function selectOwnedAccounts(accounts, owner) {
    return owner === '모두' ? accounts : accounts.filter(account => (account.owner || '모두') === owner);
  }

  function selectAccountsAndHoldings(source, owner) {
    if (owner === '모두') {
      return { accounts: source.accounts || [], holdings: source.holdings || [] };
    }

    const accounts = selectOwnedAccounts(source.accounts || [], owner);
    const ownedIds = new Set(accounts.map(account => account.id));
    const holdings = (source.holdings || []).filter(holding =>
      ownedIds.has(holding.account_id) || (holding.owner && holding.owner === owner)
    );
    return { accounts, holdings };
  }

  window.WealthDashboardOwnerModel = Object.freeze({ selectOwnedAccounts, selectAccountsAndHoldings });
})();
