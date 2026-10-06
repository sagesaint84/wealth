/* Display metadata only. Financial calculations and records stay in wealth.js. */
(() => {
  'use strict';
  let confirmed = {version: 1}, unlocked = false, category = 'securities';
  let ready = false, saving = false, drag = null, frame = 0;
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
    let button = children(host, '.account-order-handle')[0];
    if (!button) {
      button = document.createElement('button');
      button.type = 'button'; button.className = 'account-order-handle'; button.textContent = '⋮⋮';
      button.dataset.orderLevel = level; host.prepend(button);
    }
    button.title = `${label} 순서 이동 (드래그 또는 위/아래 방향키)`; button.setAttribute('aria-label', `${label} 순서 이동`);
  }
  function controls() {
    const supported = ['securities', 'banking'].includes(category);
    const button = lock();
    if (button) {
      button.hidden = !supported; button.disabled = !ready || saving;
      button.textContent = unlocked ? '🔓 순서 편집' : '🔒 순서 잠금';
      button.title = unlocked ? '순서 편집을 잠급니다' : '핸들로 계좌/기관 순서를 편집합니다';
      button.setAttribute('aria-label', button.title);
      button.setAttribute('aria-pressed', String(unlocked));
    }
    panel()?.classList.toggle('account-order-editing', supported && unlocked);
    panel()?.classList.toggle('account-order-saving', saving);
    panel()?.querySelectorAll('.account-order-handle').forEach(button => {
      const scope = button.closest('[data-order-scope]')?.dataset.orderScope;
      button.hidden = !supported || !unlocked || scope !== category;
      button.disabled = saving; button.tabIndex = button.hidden ? -1 : 0;
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
      const count = head.querySelector('span');
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
        // Derived overdrafts have no loan preference or child drag handle. They
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
    if (drag) cancel();
    if (!scope || scope === 'securities') securities();
    if (!scope || scope === 'banking') banking();
    controls();
  }
  function cancel() {
    if (!drag) return;
    const state = drag; drag = null;
    clearTimeout(state.timer); cancelAnimationFrame(frame); frame = 0;
    state.before.forEach(node => state.parent.append(node));
    state.item.classList.remove('account-order-dragged'); state.handle.classList.remove('account-order-pressed');
    state.target?.classList.remove('account-order-target');
    if (state.handle.hasPointerCapture?.(state.pointer)) state.handle.releasePointerCapture(state.pointer);
    panel()?.classList.remove('account-order-drag-active');
  }
  function activate(state) {
    if (drag !== state || !unlocked || saving || !state.item.isConnected) return cancel();
    state.active = true; state.item.classList.add('account-order-dragged');
    state.handle.classList.add('account-order-pressed'); panel()?.classList.add('account-order-drag-active');
    state.handle.setPointerCapture?.(state.pointer);
    const tick = () => {
      if (drag !== state) return;
      const box = state.scroller === document.scrollingElement
        ? {top: 0, bottom: window.innerHeight} : state.scroller.getBoundingClientRect();
      if (state.y < box.top + 36) state.scroller.scrollTop -= 10;
      else if (state.y > box.bottom - 36) state.scroller.scrollTop += 10;
      moveTarget(state); frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
  }
  function moveTarget(state) {
    // Never move outside the original parent/institution/source kind.
    const box = state.parent.getBoundingClientRect();
    if (state.x < box.left || state.x > box.right || state.y < box.top - 30 || state.y > box.bottom + 30) return;
    const others = children(state.parent, state.selector).filter(node => node !== state.item && node.dataset.orderDerived !== 'true');
    const target = others.find(node => state.y < node.getBoundingClientRect().top + node.getBoundingClientRect().height / 2);
    state.target?.classList.remove('account-order-target'); state.target = target || others.at(-1);
    state.target?.classList.add('account-order-target');
    if (target) state.parent.insertBefore(state.item, target);
    else if (others.length) state.parent.insertBefore(state.item, others.at(-1).nextSibling);
  }
  function down(event) {
    const button = event.target.closest('.account-order-handle');
    if (!button || button.hidden || !unlocked || !ready || saving || drag || event.button > 0 || event.isPrimary === false) return;
    const level = button.dataset.orderLevel;
    const item = button.closest(level === 'institutions' ? '.broker-group,.bank-institution-group' : '[data-order-id]');
    if (!item || item.dataset.orderScope !== category || item.dataset.orderDerived === 'true') return;
    const parent = item.parentElement;
    let scroller = parent;
    while (scroller !== panel() && scroller.parentElement &&
      !(scroller.scrollHeight > scroller.clientHeight && /auto|scroll/.test(getComputedStyle(scroller).overflowY))) scroller = scroller.parentElement;
    if (scroller.scrollHeight <= scroller.clientHeight || !/auto|scroll/.test(getComputedStyle(scroller).overflowY)) scroller = document.scrollingElement;
    const state = {item, parent, handle: button, before: [...parent.children], level,
      selector: level === 'institutions' ? '.broker-group,.bank-institution-group' : '[data-order-id]',
      pointer: event.pointerId, touch: event.pointerType !== 'mouse', active: false,
      startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, scroller};
    drag = state;
    if (state.touch) state.timer = setTimeout(() => activate(state), 450);
  }
  function move(event) {
    const state = drag;
    if (!state || event.pointerId !== state.pointer) return;
    state.x = event.clientX; state.y = event.clientY;
    const distance = Math.hypot(state.x - state.startX, state.y - state.startY);
    if (!state.active) {
      if (state.touch && distance > 8) return cancel();
      if (!state.touch && distance >= 5) activate(state);
    }
    if (state.active) {event.preventDefault(); moveTarget(state);}
  }
  async function save(operation) {
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
    }
  }
  function operationFor(state) {
    const operation = {scope: state.item.dataset.orderScope, level: state.level};
    if (state.level === 'institutions') {
      operation.order = children(state.parent, state.selector).map(node => node.dataset.orderKey);
    } else {
      operation.kind = state.item.dataset.orderKind; operation.institution = state.item.dataset.orderKey;
      operation.order = children(state.parent, state.selector).filter(node => node.dataset.orderDerived !== 'true' && node.dataset.orderId).map(node => node.dataset.orderId);
    }
    return operation;
  }
  function up(event) {
    const state = drag;
    if (!state || event.pointerId !== state.pointer) return;
    const after = [...state.parent.children];
    const changed = state.active && after.some((node, i) => node !== state.before[i]);
    const operation = operationFor(state);
    cancel(); // restore confirmed layout while the only permitted save is in flight
    if (changed) void save(operation);
  }
  function setCategory(value) {cancel(); category = value; controls();}
  document.addEventListener('pointerdown', down);
  document.addEventListener('pointermove', move, {passive: false});
  document.addEventListener('pointerup', up);
  document.addEventListener('pointercancel', cancel);
  document.addEventListener('lostpointercapture', event => {if (drag?.pointer === event.pointerId) cancel();});
  window.addEventListener('blur', cancel);
  document.addEventListener('touchmove', event => {if (drag?.active) event.preventDefault();}, {passive: false});
  document.addEventListener('contextmenu', event => {if (drag?.active) event.preventDefault();});
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') return cancel();
    const button = event.target.closest('.account-order-handle');
    if (!button || button.hidden || !unlocked || !ready || saving || drag || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const level = button.dataset.orderLevel;
    const selector = level === 'institutions' ? '.broker-group,.bank-institution-group' : '[data-order-id]';
    const item = button.closest(selector), parent = item.parentElement;
    const before = [...parent.children];
    const siblings = children(parent, selector).filter(node => node.dataset.orderDerived !== 'true' && (level === 'institutions' || node.dataset.orderId));
    const neighbor = siblings[siblings.indexOf(item) + (event.key === 'ArrowUp' ? -1 : 1)];
    if (!neighbor) return;
    parent.insertBefore(item, event.key === 'ArrowUp' ? neighbor : neighbor.nextSibling);
    const operation = operationFor({item, parent, selector, level});
    before.forEach(node => parent.append(node));
    void save(operation);
  });
  document.addEventListener('click', event => {
    if (event.target.closest('#accountOrderLock') && ready && !saving) {cancel(); unlocked = !unlocked; controls();}
    else if (event.target.closest('.account-order-handle')) event.preventDefault();
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
