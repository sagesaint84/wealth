/* Shared family presentation. Selection state and actions belong to the caller. */
(() => {
  'use strict';

  const FAMILY_TAB_CONTAINER_IDS = [
    'topbarFamilyTabs',
    'recordsFamilyTabs',
    'heatmapFamilyTabs',
    'dividendFamilyTabs',
    'pnlFamilyTabs',
    'holdingsFamilyTabs',
    'familyTabs',
    'ledgerFamilyTabs',
  ];

  function create({ document }) {
    function button(className, label) {
      const node = document.createElement('button');
      node.type = 'button';
      node.className = className;
      node.textContent = label;
      return node;
    }

    function renderFamilyTabs(members, currentOwner) {
      const owners = ['모두', ...members];
      for (const id of FAMILY_TAB_CONTAINER_IDS) {
        const container = document.getElementById(id);
        if (!container) continue;
        container.replaceChildren(...owners.map(owner => {
          const tab = button('family-tab', owner);
          tab.dataset.owner = owner;
          tab.classList.toggle('active', owner === currentOwner);
          return tab;
        }));
      }
    }

    function renderFamilyMemberList(members) {
      const list = document.getElementById('familyMemberList');
      if (!list) return;
      if (!members.length) {
        const empty = document.createElement('p');
        empty.style.cssText = 'color:var(--muted);font-size:13px;';
        empty.textContent = '구성원이 없습니다.';
        list.replaceChildren(empty);
        return;
      }

      list.replaceChildren(...members.map(name => {
        const row = document.createElement('div');
        row.className = 'family-member-row';
        row.style.cssText = 'display:flex;align-items:center;gap:8px;';
        const input = document.createElement('input');
        input.className = 'family-member-name-input';
        input.type = 'text';
        input.defaultValue = name;
        input.dataset.original = name;
        input.style.cssText = 'flex:1;font-size:13px;';
        input.maxLength = 20;
        const rename = button('button secondary compact family-rename-btn', '수정');
        const remove = button('button text danger compact family-delete-btn', '삭제');
        rename.dataset.name = name;
        remove.dataset.name = name;
        row.append(input, rename, remove);
        return row;
      }));
    }

    function updateOwnerSelectOptions(members) {
      const owners = ['모두', ...members];
      document.querySelectorAll('select[name="owner"]').forEach(select => {
        const previous = select.value;
        select.replaceChildren(...owners.map(owner => {
          const option = document.createElement('option');
          option.value = owner;
          option.textContent = owner;
          return option;
        }));
        if ([...select.options].some(option => option.value === previous)) {
          select.value = previous;
        }
      });
    }

    return Object.freeze({ renderFamilyTabs, renderFamilyMemberList, updateOwnerSelectOptions });
  }

  window.WealthFamilyView = Object.freeze({ create });
})();
