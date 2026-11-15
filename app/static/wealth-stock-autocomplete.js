/* Shared stock autocomplete. Form callbacks retain their feature-specific calculations. */
(() => {
  'use strict';
  function create({ api, html, document, getDashboard, getActualDividendData, getPnlData }) {
const POPULAR_STOCKS = [
  // 이자 / 현금성 배당 전용 항목 (종목코드 선택 가능)
  { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
  { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
  { code: "INTEREST_RP", name: "RP이자", currency: "KRW" },
  { code: "INTEREST_CASH", name: "예탁금이자", currency: "KRW" },

  { code: "005930", name: "삼성전자", currency: "KRW" },
  { code: "005935", name: "삼성전자우", currency: "KRW" },
  { code: "000660", name: "SK하이닉스", currency: "KRW" },
  { code: "373220", name: "LG에너지솔루션", currency: "KRW" },
  { code: "207940", name: "삼성바이오로직스", currency: "KRW" },
  { code: "005380", name: "현대차", currency: "KRW" },
  { code: "000270", name: "기아", currency: "KRW" },
  { code: "068270", name: "셀트리온", currency: "KRW" },
  { code: "035420", name: "NAVER", currency: "KRW" },
  { code: "035720", name: "카카오", currency: "KRW" },
  { code: "005490", name: "POSCO홀딩스", currency: "KRW" },
  { code: "105560", name: "KB금융", currency: "KRW" },
  { code: "055550", name: "신한지주", currency: "KRW" },
  { code: "086790", name: "하나금융지주", currency: "KRW" },
  { code: "316140", name: "우리금융지주", currency: "KRW" },
  { code: "069500", name: "KODEX 200", currency: "KRW" },
  { code: "360750", name: "TIGER 미국S&P500", currency: "KRW" },
  { code: "133690", name: "TIGER 미국나스닥100", currency: "KRW" },
  { code: "379800", name: "KODEX 미국S&P500TR", currency: "KRW" },
  { code: "379810", name: "KODEX 미국나스닥100TR", currency: "KRW" },
  { code: "360200", name: "ACE 미국S&P500", currency: "KRW" },
  { code: "449450", name: "PLUS 고배당주", currency: "KRW" },
  { code: "AAPL", name: "애플 (Apple)", currency: "USD" },
  { code: "MSFT", name: "마이크로소프트 (Microsoft)", currency: "USD" },
  { code: "NVDA", name: "엔비디아 (NVIDIA)", currency: "USD" },
  { code: "GOOGL", name: "알파벳 A (Google)", currency: "USD" },
  { code: "AMZN", name: "아마존 (Amazon)", currency: "USD" },
  { code: "META", name: "메타 (Meta)", currency: "USD" },
  { code: "TSLA", name: "테슬라 (Tesla)", currency: "USD" },
  { code: "QQQ", name: "인베스코 QQQ (Invesco QQQ)", currency: "USD" },
  { code: "QQQM", name: "인베스코 나스닥100 (QQQM)", currency: "USD" },
  { code: "SPY", name: "SPDR S&P 500 (SPY)", currency: "USD" },
  { code: "IVV", name: "iShares Core S&P 500", currency: "USD" },
  { code: "VOO", name: "Vanguard S&P 500", currency: "USD" },
  { code: "SPYG", name: "SPDR Portfolio S&P 500 Growth", currency: "USD" },
  { code: "SCHD", name: "Schwab US Dividend Equity", currency: "USD" },
  { code: "TLT", name: "iShares 20+ Year Treasury Bond", currency: "USD" },
  { code: "TQQQ", name: "ProShares UltraPro QQQ", currency: "USD" },
  { code: "QLD", name: "ProShares Ultra QQQ", currency: "USD" },
];

const POPULAR_IPO_STOCKS = [
  { code: "394420", name: "리센스메디컬", currency: "KRW" },
  { code: "493280", name: "아이엠바이오로직스", currency: "KRW" },
  { code: "408470", name: "한패스", currency: "KRW" },
  { code: "462870", name: "시프트업", currency: "KRW" },
  { code: "475560", name: "더본코리아", currency: "KRW" },
  { code: "278470", name: "에이피알", currency: "KRW" },
  { code: "443060", name: "HD현대마린솔루션", currency: "KRW" },
  { code: "454910", name: "두산로보틱스", currency: "KRW" },
  { code: "450080", name: "에코프로머티", currency: "KRW" },
  { code: "440110", name: "파두", currency: "KRW" },
];
const RECENT_SEARCHED_STOCKS = new Map();

function getAllKnownStockList() {
  const map = new Map();
  POPULAR_STOCKS.forEach(s => map.set(s.code.toUpperCase(), { ...s }));
  POPULAR_IPO_STOCKS.forEach(s => map.set(s.code.toUpperCase(), { ...s }));
  RECENT_SEARCHED_STOCKS.forEach((s, code) => {
    if (!map.has(code.toUpperCase())) map.set(code.toUpperCase(), { ...s });
  });
  (getDashboard()?.holdings || []).forEach(h => {
    if (h.code) {
      map.set(h.code.toUpperCase(), {
        code: h.code.toUpperCase(),
        name: h.name || h.code,
        currency: h.currency || (h.code.length === 6 && /^\d+$/.test(h.code) ? "KRW" : "USD"),
      });
    }
  });
  (getActualDividendData()?.records || []).forEach(r => {
    if (r.code) {
      map.set(r.code.toUpperCase(), {
        code: r.code.toUpperCase(),
        name: r.name || r.code,
        currency: r.currency || "KRW",
      });
    }
  });
  (getPnlData()?.records || []).forEach(r => {
    if (r.code) {
      map.set(r.code.toUpperCase(), {
        code: r.code.toUpperCase(),
        name: r.name || r.code,
        currency: r.currency || "KRW",
      });
    }
  });
  return [...map.values()];
}

function populateStockDatalists() {
  const list = getAllKnownStockList();
  const codeListEl = document.getElementById("holdingCodeList");
  const nameListEl = document.getElementById("holdingNameList");

  if (codeListEl) {
    codeListEl.replaceChildren(...list.map(s => {
      const option = document.createElement('option');
      option.value = s.code;
      option.textContent = `${s.name} (${s.currency})`;
      return option;
    }));
  }
  if (nameListEl) {
    nameListEl.replaceChildren(...list.map(s => {
      const option = document.createElement('option');
      option.value = s.name;
      option.textContent = `${s.code} · ${s.currency}`;
      return option;
    }));
  }
}

function attachStockAutoFill(formId, updateFieldsFn) {
  const form = document.getElementById(formId);
  if (!form) return;
  const codeInput = form.querySelector("[name='code']");
  const nameInput = form.querySelector("[name='name']");
  const currSelect = form.querySelector("[name='currency']");

  form._stockUpdateFieldsFn = updateFieldsFn;

  // 종목 자동완성 추천 드롭다운 컨테이너 생성/확보
  if (nameInput) {
    if (!nameInput.parentElement.style.position) {
      nameInput.parentElement.style.position = "relative";
    }
    let dropdownEl = nameInput.parentElement.querySelector(".stock-suggestions-dropdown");
    if (!dropdownEl) {
      dropdownEl = document.createElement("div");
      dropdownEl.className = "stock-suggestions-dropdown";
      dropdownEl.style.display = "none";
      nameInput.parentElement.appendChild(dropdownEl);
    }
  }

  if (form._stockInvalidateSearch) {
    form._stockInvalidateSearch();
    return;
  }

  let searchGeneration = 0;
  let searchTimer = null;
  function invalidateSearch() {
    searchGeneration++;
    clearTimeout(searchTimer);
    searchTimer = null;
  }
  function searchSnapshot() {
    return { generation: searchGeneration, code: codeInput?.value,
      name: nameInput?.value, currency: currSelect?.value };
  }
  function isCurrentSearch(request) {
    return request.generation === searchGeneration && form.isConnected &&
      request.code === codeInput?.value && request.name === nameInput?.value &&
      request.currency === currSelect?.value;
  }
  form._stockInvalidateSearch = invalidateSearch;
  form.addEventListener('reset', invalidateSearch);
  currSelect?.addEventListener('change', invalidateSearch);

  function highlightAutofill(inputEl) {
    if (!inputEl) return;
    inputEl.classList.remove("input-autofill-flash");
    void inputEl.offsetWidth; // reflow 강제
    inputEl.classList.add("input-autofill-flash");
    setTimeout(() => {
      inputEl.classList.remove("input-autofill-flash");
    }, 1300);
  }

  function onCodeChanged() {
    invalidateSearch();
    const raw = (codeInput?.value || "").trim().toUpperCase();
    if (!raw) return;

    // 이자 코드 즉시 매칭
    const INTEREST_CODES = {
      "INTEREST_KRW": { name: "원화이자", currency: "KRW" },
      "INTEREST_USD": { name: "달러이자", currency: "USD" },
      "INTEREST_RP": { name: "RP이자", currency: "KRW" },
      "INTEREST_CASH": { name: "예탁금이자", currency: "KRW" },
    };
    if (INTEREST_CODES[raw]) {
      const match = INTEREST_CODES[raw];
      if (nameInput && (!nameInput.value || nameInput.value.includes("이자"))) nameInput.value = match.name;
      if (currSelect) currSelect.value = match.currency;
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
      return;
    }

    const all = getAllKnownStockList();
    const found = all.find(s => s.code.toUpperCase() === raw || s.code.toUpperCase().replace(/\s+/g, '') === raw.replace(/\s+/g, ''));
    if (found) {
      if (nameInput) {
        nameInput.value = found.name;
        highlightAutofill(nameInput);
      }
      if (currSelect && found.currency) currSelect.value = found.currency;
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
    } else if (raw.length >= 2) {
      // 온라인 검색으로 코드 -> 종목명 탐색
      const request = searchSnapshot();
      api(`/api/stock-search?q=${encodeURIComponent(raw)}`).then(res => {
        if (!isCurrentSearch(request)) return;
        if (res && res.found && res.name) {
          if (nameInput) {
            nameInput.value = res.name;
            highlightAutofill(nameInput);
          }
          if (currSelect && res.currency) currSelect.value = res.currency;
          RECENT_SEARCHED_STOCKS.set(raw, { code: res.code || raw, name: res.name, currency: res.currency || 'KRW' });
          populateStockDatalists();
          if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
        }
      }).catch(() => {});
    }
  }

  let activeIndex = -1;
  let currentSuggestions = [];

  function getDropdown() {
    return nameInput?.parentElement?.querySelector(".stock-suggestions-dropdown");
  }

  function hideSuggestions() {
    const dropdown = getDropdown();
    if (dropdown) {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
    }
    currentSuggestions = [];
    activeIndex = -1;
  }

  function renderSuggestions(list, isIpo) {
    const dropdown = getDropdown();
    if (!dropdown) return;
    currentSuggestions = list || [];
    activeIndex = -1;
    if (!currentSuggestions.length) {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
      return;
    }

    dropdown.innerHTML = `
      <div class="stock-suggestions-header">
        <span>${isIpo ? '📦 공모주 종목 검색 결과' : '🔍 종목 검색 결과'} (${currentSuggestions.length})</span>
        <span class="stock-suggestions-hint">선택 시 종목코드/통화 자동 완성</span>
      </div>
      <div class="stock-suggestions-list">
        ${currentSuggestions.map((s, idx) => `
          <div class="stock-suggestion-item" data-index="${idx}">
            <div class="stock-suggestion-left">
              <span class="stock-suggestion-icon">${isIpo ? '📦' : '📈'}</span>
              <strong class="stock-suggestion-name">${html(s.name)}</strong>
            </div>
            <div class="stock-suggestion-right">
              <span class="stock-suggestion-code">${html(s.code)}</span>
              <span class="stock-suggestion-curr">${html(s.currency || 'KRW')}</span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
    dropdown.style.display = "block";

    dropdown.querySelectorAll(".stock-suggestion-item").forEach(itemEl => {
      itemEl.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const idx = Number(itemEl.dataset.index);
        selectSuggestion(currentSuggestions[idx]);
      });
      itemEl.addEventListener("mouseenter", () => {
        activeIndex = Number(itemEl.dataset.index);
        updateHighlight();
      });
    });
  }

  function updateHighlight() {
    const dropdown = getDropdown();
    if (!dropdown) return;
    const items = dropdown.querySelectorAll(".stock-suggestion-item");
    items.forEach((it, idx) => {
      if (idx === activeIndex) {
        it.classList.add("selected");
        it.scrollIntoView({ block: "nearest" });
      } else {
        it.classList.remove("selected");
      }
    });
  }

  function selectSuggestion(item) {
    if (!item) return;
    invalidateSearch();
    if (nameInput) nameInput.value = item.name;
    if (codeInput) {
      codeInput.value = item.code;
      highlightAutofill(codeInput);
    }
    if (currSelect && item.currency) {
      currSelect.value = item.currency;
    }
    hideSuggestions();

    RECENT_SEARCHED_STOCKS.set(item.code.toUpperCase(), { ...item });
    populateStockDatalists();

    if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
  }

  function onNameChanged(e) {
    invalidateSearch();
    const raw = (nameInput?.value || "").trim();
    if (!raw) {
      hideSuggestions();
      return;
    }

    const cleanRaw = raw.toLowerCase().replace(/\s+/g, '');
    const isIpo = (form.querySelector("[name='asset_type']")?.value === "ipo") || (form.querySelector("[name='is_ipo']")?.value === "true");

    // [중요] 이자 관련 키워드 우선 매칭 (화이자 주식 오매칭 완벽 방어)
    const INTEREST_KEYWORDS = {
      "원화이자": { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
      "원화예탁금이용료": { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
      "달러이자": { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
      "외화이자": { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
      "usd이자": { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
      "rp이자": { code: "INTEREST_RP", name: "RP이자", currency: "KRW" },
      "예탁금이자": { code: "INTEREST_CASH", name: "예탁금이자", currency: "KRW" },
      "예탁금이용료": { code: "INTEREST_CASH", name: "예탁금이자", currency: "KRW" },
      "이자": { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
    };

    if (INTEREST_KEYWORDS[cleanRaw]) {
      const match = INTEREST_KEYWORDS[cleanRaw];
      if (codeInput) codeInput.value = match.code;
      if (currSelect) currSelect.value = match.currency;
      hideSuggestions();
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
      return;
    }

    // 1. 로컬 저장된 목록에서 즉각 검색
    const all = getAllKnownStockList();
    const localMatches = all.filter(s => {
      const cleanStockName = s.name.toLowerCase().replace(/\s+/g, '');
      const cleanCode = s.code.toLowerCase().replace(/\s+/g, '');
      if (cleanStockName === '화이자' || cleanStockName.startsWith('화이자(')) {
        if (cleanRaw.includes('이자') && cleanRaw !== '화이자') return false;
      }
      return cleanStockName.includes(cleanRaw) || cleanCode.includes(cleanRaw);
    }).slice(0, 6);

    let exactMatch = all.find(s => {
      const cleanStockName = s.name.toLowerCase().replace(/\s+/g, '');
      if (cleanStockName === '화이자' || cleanStockName.startsWith('화이자(')) {
        if (cleanRaw.includes('이자') && cleanRaw !== '화이자') return false;
      }
      return cleanStockName === cleanRaw || s.name === raw;
    });

    if (exactMatch) {
      if (codeInput) {
        codeInput.value = exactMatch.code;
        highlightAutofill(codeInput);
      }
      if (currSelect && exactMatch.currency) currSelect.value = exactMatch.currency;
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
    }

    if (localMatches.length > 0 && nameInput === document.activeElement) {
      renderSuggestions(localMatches, isIpo);
    }

    // 2. 온라인 백엔드 검색 디바운스 (180ms) - 리센스메디컬 등 미색인 공모주 즉각 반영
    const delay = (e && (e.type === 'change' || e.type === 'blur')) ? 0 : 180;
    const request = searchSnapshot();
    searchTimer = setTimeout(async () => {
      if (!isCurrentSearch(request)) return;
      try {
        const res = await api(`/api/stock-search?q=${encodeURIComponent(raw)}`);
        if (!isCurrentSearch(request) || !res) return;

        const candidates = [];
        const seenCodes = new Set();

        if (res.suggestions && res.suggestions.length > 0) {
          res.suggestions.forEach(s => {
            if (!seenCodes.has(s.code.toUpperCase())) {
              seenCodes.add(s.code.toUpperCase());
              candidates.push(s);
            }
          });
        }
        localMatches.forEach(s => {
          if (!seenCodes.has(s.code.toUpperCase())) {
            seenCodes.add(s.code.toUpperCase());
            candidates.push(s);
          }
        });

        if (nameInput === document.activeElement && candidates.length > 0) {
          renderSuggestions(candidates.slice(0, 8), isIpo);
        }

        // 검색 성공 시 코드 입력칸 업데이트 (기존 코드와 무관하게 종목명에 맞추어 갱신)
        if (res.found && res.code) {
          if (codeInput) {
            codeInput.value = res.code;
            highlightAutofill(codeInput);
          }
          if (currSelect && res.currency) {
            currSelect.value = res.currency;
          }
          RECENT_SEARCHED_STOCKS.set(res.code.toUpperCase(), {
            code: res.code,
            name: res.name || raw,
            currency: res.currency || 'KRW',
          });
          populateStockDatalists();
          if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
        }
      } catch (err) {}
    }, delay);
  }

  function onNameKeydown(e) {
    const dropdown = getDropdown();
    if (!dropdown || dropdown.style.display !== "block" || !currentSuggestions.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % currentSuggestions.length;
      updateHighlight();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + currentSuggestions.length) % currentSuggestions.length;
      updateHighlight();
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (activeIndex >= 0 && activeIndex < currentSuggestions.length) {
        e.preventDefault();
        selectSuggestion(currentSuggestions[activeIndex]);
      } else if (currentSuggestions.length === 1 && e.key === "Enter") {
        e.preventDefault();
        selectSuggestion(currentSuggestions[0]);
      }
    } else if (e.key === "Escape") {
      hideSuggestions();
    }
  }

  if (!codeInput._boundAuto) {
    codeInput._boundAuto = true;
    codeInput.addEventListener("input", onCodeChanged);
    codeInput.addEventListener("change", onCodeChanged);
  }
  if (!nameInput._boundAuto) {
    nameInput._boundAuto = true;
    nameInput.addEventListener("input", onNameChanged);
    nameInput.addEventListener("change", onNameChanged);
    nameInput.addEventListener("keydown", onNameKeydown);
    nameInput.addEventListener("blur", () => {
      setTimeout(hideSuggestions, 250);
    });
  }
}

    return Object.freeze({ populateStockDatalists, attachStockAutoFill });
  }
  window.WealthStockAutocomplete = Object.freeze({ create });
})();
