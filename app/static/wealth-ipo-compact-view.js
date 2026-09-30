(() => {
  'use strict';

  const expandedIpoIds = new Set();
  let decorateQueued = false;

  function installStyles() {
    if (document.getElementById('wealthIpoCompactViewStyles')) return;
    const style = document.createElement('style');
    style.id = 'wealthIpoCompactViewStyles';
    style.textContent = `
      #ipoListWrapper .ipo-cards-container {
        grid-template-columns: minmax(0, 1fr) !important;
        gap: 10px !important;
      }
      #ipoListWrapper .ipo-card.ipo-compact-card {
        min-height: 0 !important;
        overflow: hidden;
      }
      #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-card-body,
      #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-card-footer,
      #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-score-box {
        display: none !important;
      }
      #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-card-header {
        display: grid !important;
        grid-template-columns: minmax(0, 1fr) auto auto !important;
        align-items: center !important;
        gap: 14px !important;
        padding-top: 14px !important;
        padding-bottom: 14px !important;
      }
      #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-card-title-group {
        min-width: 0;
      }
      #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-company-name {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      #ipoListWrapper .ipo-card-detail-toggle {
        white-space: nowrap;
        min-width: 68px;
      }
      #ipoListWrapper .ipo-card.ipo-card-expanded .ipo-card-detail-toggle {
        align-self: start;
      }
      @media (max-width: 760px) {
        #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-card-header {
          grid-template-columns: minmax(0, 1fr) auto !important;
          gap: 9px !important;
        }
        #ipoListWrapper .ipo-card.ipo-compact-card:not(.ipo-card-expanded) .ipo-status-badges {
          grid-column: 1 / -1;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function updateToggle(card, button) {
    const expanded = card.classList.contains('ipo-card-expanded');
    button.textContent = expanded ? '접기' : '자세히';
    button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    const name = card.querySelector('.ipo-company-name')?.textContent?.trim() || '공모주';
    button.setAttribute('aria-label', `${name} ${expanded ? '상세 접기' : '상세 보기'}`);
  }

  function decorateCard(card) {
    if (!(card instanceof HTMLElement)) return;
    card.classList.add('ipo-compact-card');
    const ipoId = String(card.dataset.ipoId || '');
    if (ipoId && expandedIpoIds.has(ipoId)) card.classList.add('ipo-card-expanded');
    else card.classList.remove('ipo-card-expanded');

    const header = card.querySelector('.ipo-card-header');
    if (!header) return;
    let toggle = header.querySelector('.ipo-card-detail-toggle');
    if (!toggle) {
      toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'button secondary compact ipo-card-detail-toggle';
      header.appendChild(toggle);
    }
    updateToggle(card, toggle);
  }

  function enableFutureNavigation(wrapper) {
    const state = window.WealthIpoState;
    if (!state || state.getFilterGroup?.() !== 'ALL') return;
    const nextButton = wrapper.querySelector('#ipoNextMonthBtn');
    if (nextButton) {
      nextButton.disabled = false;
      nextButton.removeAttribute('aria-disabled');
      nextButton.title = '다음 달';
    }
  }

  function decorate() {
    decorateQueued = false;
    installStyles();
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;
    wrapper.querySelectorAll('.ipo-card').forEach(decorateCard);
    enableFutureNavigation(wrapper);
  }

  function queueDecorate() {
    if (decorateQueued) return;
    decorateQueued = true;
    window.requestAnimationFrame(decorate);
  }

  function moveAllViewToNextMonth(event, wrapper) {
    const nextButton = event.target?.closest?.('#ipoNextMonthBtn');
    if (!nextButton || !wrapper.contains(nextButton)) return false;
    const state = window.WealthIpoState;
    const date = window.WealthIpoDate;
    if (!state || !date || state.getFilterGroup?.() !== 'ALL') return false;

    event.preventDefault();
    event.stopImmediatePropagation();
    const year = Number(state.getHistoryYear?.());
    const month = Number(state.getHistoryMonth?.());
    if (!Number.isInteger(year) || !Number.isInteger(month)) return true;
    const shifted = date.shiftIpoMonth(year, month, 1);
    state.setHistoryYear?.(shifted.year);
    state.setHistoryMonth?.(shifted.month);
    state.setMonthExplicitlySelected?.(true);
    state.renderIpoList?.();
    return true;
  }

  function handleClick(event) {
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;
    if (moveAllViewToNextMonth(event, wrapper)) return;

    const toggle = event.target?.closest?.('.ipo-card-detail-toggle');
    if (!toggle || !wrapper.contains(toggle)) return;
    const card = toggle.closest('.ipo-card');
    if (!card) return;
    const ipoId = String(card.dataset.ipoId || '');
    const expanded = !card.classList.contains('ipo-card-expanded');
    card.classList.toggle('ipo-card-expanded', expanded);
    if (ipoId) {
      if (expanded) expandedIpoIds.add(ipoId);
      else expandedIpoIds.delete(ipoId);
    }
    updateToggle(card, toggle);
  }

  function mount() {
    installStyles();
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;
    wrapper.addEventListener('click', handleClick, true);
    const observer = new MutationObserver(queueDecorate);
    observer.observe(wrapper, { childList: true, subtree: true });
    queueDecorate();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
