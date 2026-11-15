(() => {
  'use strict';

  async function loadBrokers(ipoId) {
    const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/broker-options`);
    if (!response.ok) throw new Error('broker options unavailable');
    return (await response.json()).brokers || [];
  }

  async function loadAccountCandidates(ipoId, owner, broker, remap) {
    const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/account-candidates?owner=${encodeURIComponent(owner)}&broker=${encodeURIComponent(broker)}${remap ? '&remap=true' : ''}`);
    if (!response.ok) throw new Error('account candidates unavailable');
    return response.json();
  }

  async function loadAllocation(ipoId, owner) {
    const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/allocation`);
    if (!response.ok) return undefined;
    return response.json();
  }

  async function loadSaleCandidates(ipoId, owner) {
    const response = await fetch(`/api/ipo/applications/${encodeURIComponent(ipoId)}/applicants/${encodeURIComponent(owner)}/allocation/sale-candidates`);
    return response.ok ? (await response.json()).candidates || [] : [];
  }

  window.WealthIpoApplicantApi = Object.freeze({ loadBrokers, loadAccountCandidates, loadAllocation, loadSaleCandidates });
})();
