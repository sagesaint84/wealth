(() => {
  'use strict';

  const expandedIpoIds = new Set();
  const ipoMetadataById = new Map();
  const SCORE_CORE_LABELS = {
    institutional_competition_ratio: '기관경쟁률',
    lockup_commitment_ratio: '의무보유확약률',
    tradable_share_ratio: '유통가능주식비율',
    pricing_discipline: '공모가 결정정보',
  };
  let decorateQueued = false;
  let metadataLoaded = false;
  let metadataDirty = true;
  let metadataPromise = null;

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
      #ipoListWrapper .ipo-market-badge.ipo-market-unknown {
        color: #94a3b8 !important;
        border-color: rgba(148, 163, 184, 0.35) !important;
        background: rgba(148, 163, 184, 0.09) !important;
      }
      #ipoListWrapper .ipo-score-diagnostic {
        display: block;
        margin-top: 4px;
        max-width: 280px;
        color: #94a3b8;
        font-size: 10.5px;
        line-height: 1.35;
        font-weight: 500;
      }
      #ipoListWrapper .ipo-metalogos-reference {
        display: block;
        margin-top: 6px;
        max-width: 430px;
        color: #a5b4fc;
        font-size: 10.5px;
        line-height: 1.4;
        font-weight: 500;
      }
      #ipoListWrapper .ipo-metalogos-reference a {
        color: #c4b5fd;
        text-decoration: underline;
        text-underline-offset: 2px;
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

  function scoreDiagnosticText(score) {
    if (!score || typeof score !== 'object') return '점수 데이터가 아직 생성되지 않았습니다.';
    if (score.status === 'NOT_APPLICABLE') return '';
    const isCalculating = score.is_calculating === true || score.score === null || score.score === undefined;
    if (!isCalculating) return '';

    const parts = [];
    const coverage = Number(score.coverage);
    if (Number.isFinite(coverage)) parts.push(`데이터 ${coverage}%`);
    const missing = Array.isArray(score.core_missing) ? score.core_missing : [];
    if (missing.length > 0) {
      const labels = missing.map(key => SCORE_CORE_LABELS[key] || String(key));
      parts.push(`부족: ${labels.join(', ')}`);
    } else if (Number.isFinite(coverage) && coverage < 75) {
      parts.push('정식 점수 기준 75% 미만');
    }
    return parts.join(' · ') || '점수 입력 데이터를 확인 중입니다.';
  }

  function decorateMarketBadge(card, meta) {
    const titleGroup = card.querySelector('.ipo-card-title-group');
    if (!titleGroup || !metadataLoaded) return;
    const originalBadge = titleGroup.querySelector('.ipo-market-badge:not([data-wealth-market-decorated="true"])');
    if (originalBadge) return;

    let badge = titleGroup.querySelector('.ipo-market-badge[data-wealth-market-decorated="true"]');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'ipo-market-badge';
      badge.dataset.wealthMarketDecorated = 'true';
      const codeBadge = titleGroup.querySelector('.ipo-code-badge');
      if (codeBadge) titleGroup.insertBefore(badge, codeBadge);
      else titleGroup.appendChild(badge);
    }

    const market = String(meta?.market || '').trim();
    const text = market || '시장 미확인';
    if (badge.textContent !== text) badge.textContent = text;
    badge.classList.toggle('ipo-market-unknown', !market);
    badge.title = market ? `공식 시장구분: ${market}` : '현재 canonical IPO 데이터에 시장구분이 없습니다.';
  }

  function decorateScoreDiagnostic(card, meta) {
    const scoreBox = card.querySelector('.ipo-score-box');
    if (!scoreBox || !metadataLoaded) return;
    const diagnostic = scoreDiagnosticText(meta?.score);
    let note = scoreBox.querySelector('.ipo-score-diagnostic');
    if (!diagnostic) {
      note?.remove();
      return;
    }
    if (!note) {
      note = document.createElement('span');
      note.className = 'ipo-score-diagnostic';
      scoreBox.appendChild(note);
    }
    if (note.textContent !== diagnostic) note.textContent = diagnostic;
    scoreBox.title = diagnostic;
  }

  function trustedMetalogosUrl(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    try {
      const url = new URL(raw);
      const host = url.hostname.toLowerCase();
      if (url.protocol !== 'https:') return '';
      if (host !== 'metalogos.ai' && host !== 'www.metalogos.ai') return '';
      if (!url.pathname.startsWith('/160ipo/stock/')) return '';
      return url.href;
    } catch (_err) {
      return '';
    }
  }

  function compactReferenceNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '';
    return Number.isInteger(number) ? number.toLocaleString('ko-KR') : String(number);
  }

  function decorateMetalogosReference(card, meta) {
    const scoreBox = card.querySelector('.ipo-score-box');
    if (!scoreBox || !metadataLoaded) return;
    const reference = meta?.sources?.metalogos160;
    let note = scoreBox.querySelector('.ipo-metalogos-reference');
    if (!reference || typeof reference !== 'object') {
      note?.remove();
      return;
    }

    if (!note) {
      note = document.createElement('span');
      note.className = 'ipo-metalogos-reference';
      scoreBox.appendChild(note);
    }
    note.replaceChildren();
    note.title = 'Metalogos 160 공개자료의 참고값입니다. Wealth IPO Score 산정에는 사용하지 않습니다.';

    const parts = ['160 보조자료', 'Wealth Score 미반영'];
    const attractiveness = compactReferenceNumber(reference.attractiveness_score);
    const demandCount = compactReferenceNumber(reference.demand_participant_count_reference);
    const lockupCount = compactReferenceNumber(reference.lockup_participant_count_reference);
    const tradable = compactReferenceNumber(reference.tradable_share_ratio_reference);
    if (attractiveness) parts.push(`매력지수 ${attractiveness}`);
    if (demandCount) parts.push(`수요예측기관 ${demandCount}`);
    if (lockupCount) parts.push(`확약기관 ${lockupCount}`);
    if (tradable) parts.push(`유통가능 ${tradable}%`);

    const text = document.createElement('span');
    text.textContent = parts.join(' · ');
    note.appendChild(text);

    const sourceUrl = trustedMetalogosUrl(reference.url);
    if (sourceUrl) {
      const separator = document.createTextNode(' · ');
      const link = document.createElement('a');
      link.href = sourceUrl;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = '160 원문';
      note.append(separator, link);
    }
  }

  function decorateCard(card) {
    if (!(card instanceof HTMLElement)) return;
    card.classList.add('ipo-compact-card');
    const ipoId = String(card.dataset.ipoId || '');
    if (ipoId && expandedIpoIds.has(ipoId)) card.classList.add('ipo-card-expanded');
    else card.classList.remove('ipo-card-expanded');

    const meta = ipoId ? ipoMetadataById.get(ipoId) : null;
    decorateMarketBadge(card, meta);
    decorateScoreDiagnostic(card, meta);
    decorateMetalogosReference(card, meta);

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
    if (metadataDirty && !metadataPromise) void loadIpoMetadata();
  }

  function queueDecorate() {
    if (decorateQueued) return;
    decorateQueued = true;
    window.requestAnimationFrame(decorate);
  }

  async function loadIpoMetadata(force = false) {
    if (!force && metadataLoaded && !metadataDirty) return;
    if (metadataPromise) return metadataPromise;
    metadataPromise = (async () => {
      try {
        const response = await fetch('/api/ipo/market', {
          credentials: 'same-origin',
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        ipoMetadataById.clear();
        (Array.isArray(payload?.ipos) ? payload.ipos : []).forEach(item => {
          const ipoId = String(item?.ipo_id || '');
          if (ipoId) ipoMetadataById.set(ipoId, item);
        });
        metadataLoaded = true;
        metadataDirty = false;
      } catch (err) {
        console.warn('IPO 표시 진단 데이터를 불러오지 못했습니다:', err);
        metadataLoaded = false;
        metadataDirty = false;
      } finally {
        metadataPromise = null;
        queueDecorate();
      }
    })();
    return metadataPromise;
  }

  function invalidateIpoMetadata() {
    metadataDirty = true;
    metadataLoaded = false;
    ipoMetadataById.clear();
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
    document.getElementById('ipoRefreshBtn')?.addEventListener('click', invalidateIpoMetadata, true);
    const observer = new MutationObserver(queueDecorate);
    observer.observe(wrapper, { childList: true, subtree: true });
    void loadIpoMetadata();
    queueDecorate();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
