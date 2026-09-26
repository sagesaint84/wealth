(() => {
  'use strict';

  const ATTRIBUTE = 'data-korean-currency';
  const CONTEXTUAL_KRW_IDS = new Set([
    'divFormAmount',
    'pnlFormAmount',
    'fiWhatIfExtraDividend',
    'fiWhatIfExtraInterest',
    'fiWhatIfDistribution',
    'fiWhatIfRealizedGain',
    'fiWhatIfEtfTaxGain',
    'fiWhatIfCorporateBase',
    'fiWhatIfCorporateExpense',
    'fiWhatIfOwnerDistribution',
  ]);
  const EXCLUDED_ID_OR_NAME = /(?:fx[_-]?rate|interest[_-]?rate|rate|percent|pct|ownership|quantity|year|month|duration|day|ratio)$/i;
  const KRW_LABEL = /(?:\bKRW\b|원화|₩|\(원\)|원\))/i;

  function parseAmount(value) {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(String(value).replace(/,/g, '').trim());
    return Number.isFinite(parsed) ? parsed : null;
  }

  function formatKrwDigits(value) {
    const parsed = parseAmount(value);
    if (parsed === null) return '';
    const rounded = Math.round(parsed);
    return `${rounded.toLocaleString('ko-KR')}원`;
  }

  function formatChunk(value) {
    const n = Math.trunc(value);
    if (!n) return '';
    const parts = [];
    const thousands = Math.floor(n / 1000);
    const hundreds = Math.floor((n % 1000) / 100);
    const remainder = n % 100;
    if (thousands) parts.push(`${thousands}천`);
    if (hundreds) parts.push(`${hundreds}백`);
    if (remainder) parts.push(String(remainder));
    return parts.join(' ');
  }

  function formatKoreanAmount(value) {
    const parsed = parseAmount(value);
    if (parsed === null || parsed === 0) return '';
    const negative = parsed < 0;
    let amount = Math.abs(Math.round(parsed));
    if (!amount) return '';

    const units = ['', '만', '억', '조', '경'];
    const chunks = [];
    let unitIndex = 0;
    while (amount > 0 && unitIndex < units.length) {
      const chunk = amount % 10000;
      if (chunk) chunks.unshift(`${formatChunk(chunk)}${units[unitIndex]}`);
      amount = Math.floor(amount / 10000);
      unitIndex += 1;
    }
    const rendered = `${chunks.join(' ')} 원`.replace(/\s+원$/, ' 원');
    return negative ? `-${rendered} (마이너스)` : rendered;
  }

  function labelText(input) {
    return input?.closest?.('label')?.textContent || '';
  }

  function contextualCurrency(input) {
    if (!input?.form) return null;
    if (input.id === 'divFormAmount') {
      return input.form.querySelector('#divFormCurrency')?.value || 'KRW';
    }
    if (input.id === 'pnlFormAmount') {
      return input.form.querySelector('#pnlFormCurrency')?.value || 'KRW';
    }
    const selector = input.form.querySelector('select[name="currency"]');
    return selector?.value || null;
  }

  function isExcluded(input) {
    const key = `${input?.id || ''} ${input?.name || ''}`.trim();
    return Boolean(key && EXCLUDED_ID_OR_NAME.test(key));
  }

  function isKrwMoneyInput(input) {
    if (!input || input.tagName !== 'INPUT') return false;
    if (input.type !== 'number' || input.readOnly || input.disabled) return false;
    if (input.hasAttribute('data-money-preview-off')) return false;
    if (isExcluded(input)) return false;

    const contextCurrency = contextualCurrency(input);
    if (CONTEXTUAL_KRW_IDS.has(input.id)) {
      return contextCurrency ? String(contextCurrency).toUpperCase() === 'KRW' : true;
    }
    if (input.hasAttribute(ATTRIBUTE)) return true;
    if (/(?:^|_)krw(?:$|_)/i.test(input.name || '') || /Krw$/.test(input.id || '')) return true;
    if (!KRW_LABEL.test(labelText(input))) return false;
    if (contextCurrency && String(contextCurrency).toUpperCase() !== 'KRW') return false;
    return true;
  }

  function findHint(input) {
    const parent = input.parentElement;
    if (!parent) return null;
    const existing = [...parent.children].find(child => child.classList?.contains('korean-currency-hint'));
    return existing || null;
  }

  function ensureHint(input) {
    let hint = findHint(input);
    if (!hint) {
      hint = document.createElement('div');
      hint.className = 'korean-currency-hint';
      input.parentElement?.appendChild(hint);
    }
    hint.dataset.moneyPreview = 'true';
    hint.style.cssText = 'font-size:11.5px;font-weight:700;color:#38bdf8;margin-top:4px;display:flex;align-items:center;gap:6px;line-height:1.35;flex-wrap:wrap;transition:all 0.15s ease;';
    return hint;
  }

  function hideHint(input) {
    const hint = findHint(input);
    if (hint?.dataset?.moneyPreview === 'true') hint.style.display = 'none';
  }

  function renderHint(input) {
    if (!isKrwMoneyInput(input)) {
      hideHint(input);
      return;
    }
    const parsed = parseAmount(input.value);
    const hint = ensureHint(input);
    if (parsed === null || parsed === 0) {
      hint.style.display = 'none';
      hint.replaceChildren();
      return;
    }

    const negative = parsed < 0;
    const numeric = document.createElement('span');
    numeric.className = 'krw-money-preview-numeric';
    numeric.textContent = formatKrwDigits(parsed);
    const separator = document.createElement('span');
    separator.className = 'krw-money-preview-separator';
    separator.textContent = '·';
    const friendly = document.createElement('span');
    friendly.className = 'krw-money-preview-friendly';
    friendly.textContent = formatKoreanAmount(parsed);

    hint.style.display = 'flex';
    hint.style.color = negative ? '#fb7185' : '#38bdf8';
    hint.replaceChildren(numeric, separator, friendly);
    hint.setAttribute('aria-live', 'polite');
  }

  function scan(root = document) {
    if (root?.tagName === 'INPUT') renderHint(root);
    root?.querySelectorAll?.('input[type="number"]').forEach(renderHint);
  }

  function refreshForm(form) {
    form?.querySelectorAll?.('input[type="number"]').forEach(renderHint);
  }

  const api = {
    parseAmount,
    formatKrwDigits,
    formatKoreanAmount,
    isKrwMoneyInput,
    renderHint,
    scan,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.WealthMoneyInput = api;
  if (typeof document === 'undefined') return;

  document.addEventListener('input', event => {
    const target = event.target;
    if (target?.tagName === 'INPUT') renderHint(target);
  });
  document.addEventListener('change', event => {
    const target = event.target;
    if (target?.tagName === 'SELECT' && (target.name === 'currency' || target.id === 'divFormCurrency' || target.id === 'pnlFormCurrency')) {
      refreshForm(target.form);
    }
  });
  document.addEventListener('focusin', event => {
    if (event.target?.tagName === 'INPUT') renderHint(event.target);
  });

  const start = () => {
    scan(document);
    const observer = new MutationObserver(records => {
      records.forEach(record => record.addedNodes.forEach(node => {
        if (node?.nodeType === 1) scan(node);
      }));
    });
    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
