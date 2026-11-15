/* Holding market signals: owns request state, cache, generation guards and presentation. */
(() => {
  'use strict';

  function create({ $, api, html, number, document, window, globalThis,
                    getDashboard, getRawDashboard, getCurrentOwner, getCurrentUserProfile,
                    currentWealthView }) {
const holdingSignalState = {context: '', rows: [], generation: 0, pending: false, active: false, phase: 'idle', checkedAt: 0, cache: new Map(), requests: new Map()};
const holdingSignalLabels = {SMA20_BREAKDOWN:'20일선 이탈',SMA50_BREAKDOWN:'50일선 이탈',GOLDEN_CROSS:'골든크로스',DEAD_CROSS:'데드크로스'};
function holdingSignalsContext() {
  const source = getRawDashboard() || getDashboard();
  return JSON.stringify([getCurrentUserProfile()?.username, getCurrentOwner(), (source?.accounts || []).map(a => [a.id,a.owner,a.broker,a.name,a.account_type]),
    (source?.holdings || []).map(h => [h.id,h.account_id,h.owner,h.code,h.name,h.currency,h.market,h.quantity])]);
}
function holdingSignalsActive() {
  return globalThis.WealthStartup?.canRead() && window.WealthWorkspaceRoute?.resolve().key === 'home' && window.WealthWorkspaceRoute.resolve().homeTab === 'markets'
    && currentWealthView() === 'home' && document.getElementById('homeTab-markets')?.getAttribute('aria-selected') === 'true';
}
function syncHoldingSignalsContext() {
  const context = holdingSignalsContext(), active = holdingSignalsActive();
  if (context !== holdingSignalState.context || active !== holdingSignalState.active) {
    holdingSignalState.generation++;
    Object.assign(holdingSignalState, {context, active, rows: [], pending: false, phase: 'idle'});
    renderHoldingSignals();
  }
  if (active) void loadHoldingSignals();
}
function renderHoldingSignals() {
  const host = $('#holdingSignalsRows'), status = $('#holdingSignalsStatus');
  if (!host) return;
  const {rows, phase} = holdingSignalState;
  const value = n => n == null ? '미정' : number(n, 4);
  const reliable = row => ['ok','insufficient_data'].includes(row.status);
  if (status) status.textContent = phase === 'loading' ? '신호 조회 중…' : phase === 'error' ? '자료 조회 불가' : '';
  host.innerHTML = Object.entries(holdingSignalLabels).map(([signal, label]) => {
    const matches = rows.filter(row => reliable(row) && (row.events || []).includes(signal));
    const unavailable = rows.filter(row => !reliable(row) ||
      (row.status === 'insufficient_data' && !row.available?.[signal] && !(row.events || []).includes(signal))).length;
    const empty = phase === 'loading' ? '조회 중…' : phase === 'ready' ? '해당 종목 없음' : '자료 미확인';
    return `<section class="holding-signal-section" data-signal="${signal}" aria-labelledby="signalTitle${signal}">
      <h4 id="signalTitle${signal}">${html(label)}</h4>
      ${matches.map(row => `<article class="holding-signal-row"><strong>${html(row.name)} · ${html(row.code)}</strong>
        <span>${html(row.as_of || '기준일 미확인')} · 종가 ${value(row.close)}</span>
        <small>SMA20 ${value(row.sma20)} · SMA50 ${value(row.sma50)}</small>
        <small>${html(row.source || '자료 미확인')} · ${html((row.accounts || []).map(a => [a.owner,a.broker,a.account_name].filter(Boolean).join(' · ')).filter((a,i,all) => all.indexOf(a) === i).join(' / '))}</small>
      </article>`).join('') || `<p class="holding-signal-empty">${empty}</p>`}
      ${unavailable ? `<p class="holding-signal-empty">자료 미확인 ${unavailable}종목</p>` : ''}
    </section>`;
  }).join('');
}
async function loadHoldingSignals() {
  if (!holdingSignalsActive() || holdingSignalState.pending || !(getRawDashboard() || getDashboard())) return;
  const owner = getCurrentOwner(), context = holdingSignalState.context;
  const cached = holdingSignalState.cache.get(context);
  if (holdingSignalState.phase === 'ready' && cached && Date.now() - cached.at < 900000) return;
  if (holdingSignalState.phase === 'error' && Date.now() - holdingSignalState.checkedAt < 30000) return;
  const generation = ++holdingSignalState.generation;
  Object.assign(holdingSignalState, {rows: [], pending: true, phase: 'loading'});
  renderHoldingSignals();
  try {
    let response;
    if (cached && Date.now() - cached.at < 900000) {
      response = cached.value;
    } else {
      let pending = holdingSignalState.requests.get(context);
      if (!pending) {
        pending = api(`/api/holdings/signals?owner=${encodeURIComponent(owner)}`).then(value => {
          holdingSignalState.cache.set(context, {value, at: Date.now()});
          while (holdingSignalState.cache.size > 8) holdingSignalState.cache.delete(holdingSignalState.cache.keys().next().value);
          return value;
        }).finally(() => {
          if (holdingSignalState.requests.get(context) === pending) holdingSignalState.requests.delete(context);
        });
        holdingSignalState.requests.set(context, pending);
      }
      response = await pending;
    }
    if (generation !== holdingSignalState.generation || context !== holdingSignalsContext() || !holdingSignalsActive()) return;
    Object.assign(holdingSignalState, {rows: response.items || [], phase: 'ready'});
  } catch (_) {
    if (generation === holdingSignalState.generation && context === holdingSignalsContext() && holdingSignalsActive()) {
      holdingSignalState.phase = 'error';
      holdingSignalState.checkedAt = Date.now();
    }
  } finally {
    if (generation === holdingSignalState.generation) {
      holdingSignalState.pending = false;
      renderHoldingSignals();
    }
  }
}

    // State is the original object, not a second cache or snapshot.
    return Object.freeze({ syncHoldingSignalsContext, loadHoldingSignals, state: holdingSignalState });
  }

  window.WealthHoldingSignals = Object.freeze({ create });
})();
