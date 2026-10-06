/* Display metadata only. Financial calculations and records stay in wealth.js. */
(() => {
  'use strict';
  let confirmed = {version: 1}, unlocked = false, category = 'securities';
  let ready = false, saving = false;
  const panel = () => document.getElementById('accountsPanel');
  const lock = () => document.getElementById('accountOrderLock');
  const roots = [['banksListWrap', 'bank_accounts'], ['savingsGrid', 'savings_accounts'], ['loansGrid', 'loan_accounts']];
  const children = (parent, selector) => [...parent.children].filter(node => node.matches(selector));
  const normalized = label => String(label || '기타').normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase();
  function key(label, scope) {
    const compare = normalized(label);
    // Use only aliases returned by the server; match casing/spacing safely even
    // when a newly edited record uses a different spelling of a known alias.
    const match = Object.entries(confirmed[scope]?.aliases || {}).find(([alias]) => normalized(alias) === compare);
    return match ? match[1] : compare;
  }
  function sort(nodes, order, identity) {
    const ranks = new Map((Array.isArray(order) ? order : []).map((id, i) => [id, i]));
    return nodes.map((node, i) => ({node, i})).sort((a, b) =>
      (ranks.get(identity(a.node)) ?? Infinity) - (ranks.get(identity(b.node)) ?? Infinity) || a.i - b.i
    ).map(entry => entry.node);
  }
  function handle(host, label, level) {
    let group = children(host, '.account-order-controls')[0];
    if (!group) {
      group = document.createElement('span'); group.className = 'account-order-controls';
      group.dataset.orderLevel = level;
      for (const [direction, text] of [[-1, '↑'], [1, '↓']]) {
        const button = document.createElement('button'); button.type = 'button';
        button.dataset.orderDirection = direction; button.textContent = text; group.append(button);
      }
      host.prepend(group);
    }
    [...group.children].forEach(button => {
      const text = `${label} ${Number(button.dataset.orderDirection) < 0 ? '위로' : '아래로'} 이동`;
      button.title = text; button.setAttribute('aria-label', text);
    });
  }
  function context(group) {
    const level = group.dataset.orderLevel;
    const selector = level === 'institutions' ? '.broker-group,.bank-institution-group' : '[data-order-id]';
    const item = group.closest(selector), parent = item.parentElement;
    const siblings = children(parent, selector).filter(node => node.dataset.orderDerived !== 'true' && (level === 'institutions' || node.dataset.orderId));
    return {item, parent, siblings, level};
  }
  function controls() {
    const supported = ['securities', 'banking'].includes(category);
    const button = lock();
    if (button) {
      button.hidden = !supported; button.disabled = !ready || saving;
      button.textContent = unlocked ? '↕ 순서 편집' : '🔒 순서 잠금';
      button.title = unlocked ? '순서 편집을 잠급니다' : '위/아래 버튼으로 계좌/기관 순서를 편집합니다';
      button.setAttribute('aria-label', button.title);
      button.setAttribute('aria-pressed', String(unlocked));
    }
    panel()?.classList.toggle('account-order-editing', supported && unlocked);
    panel()?.classList.toggle('account-order-saving', saving);
    panel()?.querySelectorAll('.account-order-controls').forEach(group => {
      const {item, siblings} = context(group);
      group.hidden = !supported || !unlocked || item.dataset.orderScope !== category;
      const index = siblings.indexOf(item);
      [...group.children].forEach(button => {
        const neighbor = siblings[index + Number(button.dataset.orderDirection)];
        button.disabled = saving || !neighbor;
        button.tabIndex = group.hidden ? -1 : 0;
      });
    });
  }

  function securities() {
    const root = document.getElementById('accountList');
    if (!root) return;
    const groups = new Map();
    children(root, '.broker-group').forEach(group => {
      const label = group.dataset.orderInstitution;
      const identity = key(label, 'securities');
      group.dataset.orderKey = identity; group.dataset.orderScope = 'securities';
      if (groups.has(identity)) {
        const target = groups.get(identity).querySelector('.broker-accounts');
        group.querySelectorAll('.account-row').forEach(row => target.append(row));
        group.remove();
      } else groups.set(identity, group);
    });
    sort([...groups.values()], confirmed.securities?.institutions, node => node.dataset.orderKey).forEach(group => {
      root.append(group);
      const identity = group.dataset.orderKey;
      const head = group.querySelector('.broker-head'), list = group.querySelector('.broker-accounts');
      handle(head, confirmed.securities?.labels?.[identity] || group.dataset.orderInstitution, 'institutions');
      const rows = children(list, '.account-row');
      sort(rows, confirmed.securities?.accounts?.[identity], row => row.dataset.orderId).forEach(row => {
        list.append(row); row.dataset.orderScope = 'securities'; row.dataset.orderKey = identity;
        row.dataset.orderKind = 'accounts';
        if (row.dataset.orderId) handle(row.querySelector('.account-row-title-line'), row.dataset.orderLabel, 'accounts');
      });
      const count = children(head, 'span').find(node => !node.classList.contains('account-order-controls'));
      if (count) count.textContent = `${rows.length}개 계좌`;
    });
  }
  function banking() {
    roots.forEach(([id, kind]) => {
      const root = document.getElementById(id);
      if (!root) return;
      const records = [...root.querySelectorAll('[data-order-id]')];
      if (!records.length) return;
      const template = root.querySelector('thead')?.cloneNode(true);
      const groups = new Map();
      records.forEach(row => {
        const identity = key(row.dataset.orderInstitution, 'banking');
        if (!groups.has(identity)) groups.set(identity, []);
        groups.get(identity).push(row);
      });
      root.replaceChildren(); root.classList.add('account-order-group-root');
      sort([...groups.keys()].map(identity => ({identity})), confirmed.banking?.institutions, node => node.identity).forEach(({identity}) => {
        const group = document.createElement('section'); group.className = 'bank-institution-group';
        Object.assign(group.dataset, {orderScope: 'banking', orderKey: identity, orderKind: kind});
        const head = document.createElement('div'); head.className = 'bank-institution-head';
        const title = document.createElement('strong');
        title.textContent = confirmed.banking?.labels?.[identity] || groups.get(identity)[0].dataset.orderInstitution;
        head.append(title); handle(head, title.textContent, 'institutions'); group.append(head);
        let list;
        if (kind === 'bank_accounts') {
          const table = document.createElement('table'); table.className = 'banks-table';
          if (template) table.append(template.cloneNode(true));
          list = document.createElement('tbody'); table.append(list); group.append(table);
        } else {
          list = document.createElement('div'); list.className = 'bank-group-items savings-card-grid'; group.append(list);
        }
        const rows = groups.get(identity);
        // Derived overdrafts have no loan preference or child order controls. They
        // follow bank_accounts order, after actual loans in the bank's section.
        const actual = rows.filter(row => row.dataset.orderDerived !== 'true');
        const derived = rows.filter(row => row.dataset.orderDerived === 'true');
        const ordered = sort(actual, confirmed.banking?.[kind]?.[identity], row => row.dataset.orderId)
          .concat(sort(derived, confirmed.banking?.bank_accounts?.[identity], row => row.dataset.orderId));
        ordered.forEach(row => {
          Object.assign(row.dataset, {orderScope: 'banking', orderKey: identity, orderKind: kind});
          if (row.dataset.orderDerived !== 'true' && row.dataset.orderId) {
            const host = kind === 'bank_accounts' ? row.children[1] : row.querySelector('.saving-badge-row');
            handle(host, row.dataset.orderLabel, 'accounts');
          }
          list.append(row);
        });
        root.append(group);
      });
    });
  }
  function rendered(scope) {
    if (!scope || scope === 'securities') securities();
    if (!scope || scope === 'banking') banking();
    controls();
  }
  async function save(operation, focus) {
    saving = true; controls();
    try {
      const response = await fetch('/api/account-display-order', {method: 'PATCH',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(operation)});
      if (!response.ok) throw new Error('order save failed');
      confirmed = await response.json();
    } catch (_) {
      if (typeof toast === 'function') toast('순서 저장에 실패했습니다. 저장된 순서로 복원합니다.', true);
    } finally {
      saving = false; rendered();
      if (focus && unlocked) {
        const groups = [...panel().querySelectorAll('.account-order-controls')];
        const target = groups.find(group => {
          const {item, level} = context(group);
          return item.dataset.orderScope === focus.scope && level === focus.level &&
            item.dataset.orderKey === focus.key && item.dataset.orderKind === focus.kind &&
            item.dataset.orderId === focus.id;
        });
        const button = target?.querySelector(`[data-order-direction="${focus.direction}"]`);
        if (button && !button.disabled && !target.hidden) button.focus({preventScroll: true});
      }
    }
  }
  function setCategory(value) {category = value; controls();}
  document.addEventListener('click', event => {
    if (event.target.closest('#accountOrderLock') && ready && !saving) {
      unlocked = !unlocked; controls(); return;
    }
    const button = event.target.closest('.account-order-controls button');
    if (!button || button.disabled || !unlocked || !ready || saving) return;
    const group = button.parentElement;
    if (group.hidden) return;
    const {item, siblings, level} = context(group);
    if (item.dataset.orderScope !== category || item.dataset.orderDerived === 'true') return;
    const direction = Number(button.dataset.orderDirection), index = siblings.indexOf(item);
    const neighbor = siblings[index + direction];
    if (!neighbor) return;
    // Build only the visible subset; the server preserves hidden owner positions.
    [siblings[index], siblings[index + direction]] = [neighbor, item];
    const operation = {scope: item.dataset.orderScope, level};
    if (level === 'institutions') operation.order = siblings.map(node => node.dataset.orderKey);
    else {
      operation.kind = item.dataset.orderKind; operation.institution = item.dataset.orderKey;
      operation.order = siblings.map(node => node.dataset.orderId);
    }
    void save(operation, {scope: item.dataset.orderScope, level, key: item.dataset.orderKey,
      kind: item.dataset.orderKind, id: item.dataset.orderId, direction});
  });
  window.WealthAccountReorder = {rendered, setCategory};
  controls();
  fetch('/api/account-display-order').then(response => {
    if (!response.ok) throw new Error('order load failed');
    return response.json();
  }).then(order => {confirmed = order; ready = true; rendered();}).catch(() => {
    if (typeof toast === 'function') toast('계좌 순서를 불러오지 못했습니다. 새로고침 후 다시 시도하세요.', true);
  });
})();
