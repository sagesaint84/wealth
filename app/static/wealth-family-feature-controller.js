(() => {
  "use strict";

  function create(app) {
    const familyView = window.WealthFamilyView.create({ document });
    function renderFamilyMemberList(members) { familyView.renderFamilyMemberList(members); }

    async function openFamilyManager() {
      const dlg = document.getElementById('familyManagerDialog');
      if (!dlg) return;
      try {
        const res = await app.api('/api/family-members');
        renderFamilyMemberList(res.members || []);
      } catch(e) {
        renderFamilyMemberList([]);
      }
      dlg.showModal();
    }

    async function loadFamilyMembers() {
      try {
        const res = await app.api('/api/family-members');
        const members = res.members || [];
        renderFamilyTabs(members);
        updateOwnerSelectOptions(members);
      } catch (e) {}
    }

    function updateOwnerSelectOptions(members) { familyView.updateOwnerSelectOptions(members); }
    function renderFamilyTabs(members) { familyView.renderFamilyTabs(members, app.currentOwner); }

    function refreshMemberViews(res) {
      renderFamilyTabs(res.members || []);
      updateOwnerSelectOptions(res.members || []);
      renderFamilyMemberList(res.members || []);
    }

    async function addFamilyMember() {
      const input = document.getElementById('newMemberName');
      const name = (input?.value || '').trim();
      if (!name) { app.toast('이름을 입력해 주세요.', true); return; }
      try {
        const res = await app.api('/api/family-members', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        app.toast(res.message || '추가했습니다.');
        if (input) input.value = '';
        refreshMemberViews(res);
      } catch(err) { app.toast(err.message, true); }
    }

    async function renameFamilyMember(renameBtn) {
      const row = renameBtn.closest('.family-member-row');
      const input = row?.querySelector('.family-member-name-input');
      const oldName = renameBtn.dataset.name;
      const newName = (input?.value || '').trim();
      if (!newName || newName === oldName) return;
      try {
        const res = await app.api(`/api/family-members/${encodeURIComponent(oldName)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName }),
        });
        app.toast(res.message || '수정했습니다.');
        refreshMemberViews(res);
        await app.loadDashboard();
      } catch(err) { app.toast(err.message, true); }
    }

    async function deleteFamilyMember(deleteMemberBtn) {
      const name = deleteMemberBtn.dataset.name;
      if (!confirm(`'${name}' 구성원을 삭제할까요?\n연결된 계좌는 '모두'로 변경됩니다.`)) return;
      try {
        const res = await app.api(`/api/family-members/${encodeURIComponent(name)}`, { method: 'DELETE' });
        app.toast(res.message || '삭제했습니다.');
        refreshMemberViews(res);
        await app.loadDashboard();
      } catch(err) { app.toast(err.message, true); }
    }

    return {
      publicActions: {
        renderFamilyMemberList,
        openFamilyManager,
        loadFamilyMembers,
        updateOwnerSelectOptions,
        renderFamilyTabs,
      },
      actions: {
        addFamilyMember,
        renameFamilyMember,
        deleteFamilyMember,
      },
    };
  }

  window.WealthFamilyFeatureController = { create };
})();
