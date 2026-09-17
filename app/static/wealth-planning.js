/* User-confirmed history and investment purpose classification. No trading calls. */
(() => {
  'use strict';
  const home = document.querySelector('[data-wealth-page="home"]');
  const invest = document.querySelector('[data-wealth-page="invest"]');
  if (!home || !invest) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const won = value => `${Math.round(value).toLocaleString('ko-KR')}원`;
  const BUCKET_PRESETS = [
    ['코어','장기 핵심 자산'], ['성장','성장 중심 자산'], ['배당','배당과 현금흐름 자산'],
    ['섹터','산업군 중심 자산'], ['테마','테마 중심 자산'], ['전술','전술적 운용 자산'],
    ['방어','변동성 방어 자산'], ['현금','투자 대기 자금'],
  ];
  const BUCKET_PRESET_COLORS = {
    '코어': '#5FC5D9',
    '성장': '#A8C95B',
    '배당': '#7F78E8',
    '섹터': '#A886DB',
    '테마': '#CF788B',
    '전술': '#D19A66',
    '방어': '#82966A',
    '현금': '#5A9FE8',
    'core': '#5FC5D9',
    'growth': '#A8C95B',
    'dividend': '#7F78E8',
    'sector': '#A886DB',
    'theme': '#CF788B',
    'tactical': '#D19A66',
    'defensive': '#82966A',
    'cash': '#5A9FE8',
  };
  const BUCKET_COLORS = ['#5FC5D9','#A8C95B','#7F78E8','#A886DB','#CF788B','#D19A66','#82966A','#5A9FE8'];
  let state = null, summary = null, portfolioView = null, editorView = null, editorRevision = null, range = '1Y', dirty = false, syncBlocked = false;
  window.addEventListener('beforeunload', e => { if(dirty || editingRecord) { e.preventDefault(); e.returnValue = ''; } });
  const historyPanel = document.createElement('article');
  historyPanel.className = 'wealth-history wealth-composition';
  historyPanel.innerHTML = `<div class="wealth-section-heading wealth-history-heading"><div><p class="wealth-eyebrow">NET WORTH HISTORY</p><h3>순자산 추이</h3><p class="wealth-history-description">확인해 저장한 날짜별 순자산 기록입니다.</p></div></div>
    <p class="wealth-help wealth-history-help">자금 입출금·자산 등록도 반영되므로 투자수익률과는 다릅니다.</p>
    <div class="wealth-periods compact-record-tabs" aria-label="순자산 조회 기간"><button type="button" class="heatmap-tab" data-period="1D">일간</button><button type="button" class="heatmap-tab" data-period="1W">주간</button><button type="button" class="heatmap-tab" data-period="1M">월간</button><button type="button" class="heatmap-tab active" data-period="1Y">연간</button><button type="button" class="heatmap-tab" data-period="ALL">전체</button></div>
    <p id="wealthHistoryStatus" class="wealth-help" role="status">기록을 불러오는 중입니다.</p><div id="wealthHistorySummary" class="wealth-history-summary" aria-label="순자산 요약"></div><div class="wealth-history-main"><div id="wealthHistoryPlot"></div><details id="wealthHistoryDetails" class="wealth-history-details" open></details></div>`;
  (home.querySelector('#wealthMarketSlot') || home).before(historyPanel);
  const historyManager = document.createElement('div');
  historyManager.className='wealth-history-selection';
  historyManager.innerHTML='<p id="wealthHistoryEditStatus" class="wealth-help" role="status"></p>';
  historyManager.hidden = true;
  historyPanel.querySelector('.wealth-periods').after(historyManager);
  const historyDialog=document.createElement('dialog');
  historyDialog.className='dialog wealth-history-dialog';
  historyDialog.setAttribute('aria-labelledby','wealthHistoryDialogTitle');
  historyDialog.innerHTML='<form id="wealthHistoryEditForm"><div class="dialog-head"><h2 id="wealthHistoryDialogTitle">과거 기록 추가</h2><button type="button" class="close" id="wealthCloseHistory" aria-label="기록 입력 닫기">×</button></div><p class="dialog-description" id="wealthHistoryScope"></p><div class="form-grid"><label>날짜<input name="date" type="date" required></label><label>총자산 (원)<input name="assets" type="number" min="0" step="0.01" required></label><label>총부채 (원)<input name="debt" type="number" min="0" step="0.01" required></label><label>순자산 (원)<input name="net_worth" type="number" step="0.01" readonly aria-readonly="true"></label><label class="wealth-history-memo">메모 (선택)<textarea name="memo" maxlength="1000" rows="3"></textarea></label></div><p id="wealthHistoryFormStatus" class="wealth-help" role="status"></p><button type="button" class="button secondary" id="wealthOpenExistingHistory" hidden>기존 기록 수정</button><div class="dialog-actions"><button type="button" id="wealthCancelHistory" class="button secondary">취소</button><button type="submit" class="button primary">저장</button></div></form>';
  document.body.append(historyDialog);
  let editingRecord=null, historyBusy=false;
  const editForm=document.getElementById('wealthHistoryEditForm');
  const editStatus=document.getElementById('wealthHistoryEditStatus');
  const formStatus=document.getElementById('wealthHistoryFormStatus');
  const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  function openHistory(record=null) {
    if(!state || !summary || historyBusy)return;
    editingRecord=record?{...record,revision:state.revision}:{adding:true,source:'manual',owner:summary.owner,revision:state.revision};
    editForm.reset();
    document.getElementById('wealthHistoryDialogTitle').textContent=record?'기록 수정':'기록 추가';
    document.getElementById('wealthHistoryScope').textContent=editingRecord.owner+' · 총자산과 총부채를 입력하면 순자산이 자동 계산됩니다. 실제 계좌 잔고는 바뀌지 않습니다.';
    editForm.elements.date.max=today();editForm.elements.date.value=record?.date || today();
    editForm.elements.assets.value=record?.assets ?? '';
    editForm.elements.debt.value=record?.debt ?? '';
    editForm.elements.net_worth.value=(record?.assets != null && record?.debt != null) ? Number(record.assets)-Number(record.debt) : '';
    editForm.elements.memo.value=record?.memo || '';
    const updateNetWorth=()=>{const a=editForm.elements.assets.value, d=editForm.elements.debt.value; editForm.elements.net_worth.value=(a!=='' && d!=='') ? Number(a)-Number(d) : '';};
    editForm.elements.assets.oninput=updateNetWorth; editForm.elements.debt.oninput=updateNetWorth;
    formStatus.textContent='';document.getElementById('wealthOpenExistingHistory').hidden=true;
    if(!historyDialog.open)historyDialog.showModal();
  }
  function closeHistory(){if(historyBusy)return;historyDialog.close();editingRecord=null;}
  historyDialog.addEventListener('cancel',e=>{if(historyBusy)e.preventDefault();});
  historyDialog.addEventListener('close',()=>{editingRecord=null;});
  document.getElementById('wealthCancelHistory').addEventListener('click',closeHistory);
  document.getElementById('wealthCloseHistory').addEventListener('click',closeHistory);
  document.getElementById('wealthOpenExistingHistory').addEventListener('click',()=>{
    const record=state.history.find(r=>r.owner===editingRecord?.owner && r.date===editForm.elements.date.value);
    if(record){showHistoryDate(record.date);openHistory(record);}
  });
  editForm.addEventListener('submit',async e=>{
    e.preventDefault();if(!editingRecord || historyBusy)return;
    const record=editingRecord,date=editForm.elements.date.value;
    const duplicate=state.history.find(r=>r.owner===record.owner && r.date===date && (record.adding || r.date!==record.date));
    if(duplicate){formStatus.textContent='해당 날짜의 기록이 이미 있습니다. 기존 기록을 수정하시겠습니까?';document.getElementById('wealthOpenExistingHistory').hidden=false;return;}
    const assets=Number(editForm.elements.assets.value),debt=Number(editForm.elements.debt.value);
    if(!Number.isFinite(assets)||assets<0||!Number.isFinite(debt)||debt<0){formStatus.textContent='총자산과 총부채를 입력하세요.';return;}
    const payload={revision:record.revision,owner:record.owner,date:record.adding?date:record.date,new_date:date,memo:editForm.elements.memo.value,confirm:true,net_worth:assets-debt,assets,debt,total_assets_krw:assets,total_debt_krw:debt,net_worth_krw:assets-debt};
    historyBusy=true;editForm.inert=true;
    try{state=await request(record.adding?'/snapshot-manual':'/snapshot-edit',payload);historyBusy=false;closeHistory();showHistoryDate(date);editStatus.textContent=record.adding?'과거 기록을 추가했습니다.':'기록을 수정했습니다.';}
    catch(error){formStatus.textContent=error.message;}
    finally{historyBusy=false;editForm.inert=false;}
  });
  historyPanel.addEventListener('click', async e => {
    const actionButton = e.target.closest('[data-history-action]');
    if (actionButton) {
      if (actionButton.dataset.historyAction === 'wealthSaveSnapshot') saveSnapshot(actionButton);
      if (actionButton.dataset.historyAction === 'wealthAddHistory') openHistory();
      return;
    }
    const edit = e.target.closest('[data-history-edit]');
    const del = e.target.closest('[data-history-delete]');
    if (edit) { const record = state?.history.find(r => r.date === edit.dataset.historyEdit && r.owner === summary?.owner); if (record) openHistory(record); }
    if (del) { const record = state?.history.find(r => r.date === del.dataset.historyDelete && r.owner === summary?.owner); if (!record || !confirm(`${record.date} 순자산 기록을 삭제할까요?`)) return; historyBusy=true; try { state=await request('/snapshot-delete',{revision:state.revision,date:record.date,owner:record.owner,confirm:true}); renderHistory(); } finally { historyBusy=false; } }
  });
  const syncStatus = document.createElement('p');
  syncStatus.className = 'wealth-help wealth-sync-status'; syncStatus.setAttribute('role', 'status');
  document.querySelector('.wealth-owner-bar').after(syncStatus);
  const draftNotice=document.createElement('p');draftNotice.className='wealth-help';draftNotice.setAttribute('role','status');syncStatus.after(draftNotice);
  function markDirty() { dirty=true;draftNotice.textContent=`전략 버킷에 미저장 변경이 있습니다 · 편집 범위: ${editorView?.owner || '모두'}. 투자 → 전략 버킷에서 저장하거나 다시 불러오세요.`; }
  window.addEventListener('wealth:sync', ({detail}) => {
    syncBlocked = detail.state !== 'success';
    const labels = {running:'증권사 잔고·보유종목 동기화 중…',partial:'일부 증권사 동기화 실패 — 결과를 확인한 뒤 다시 동기화하세요.',error:'계좌 동기화 실패 — 다시 시도하세요.',empty:'동기화된 증권사가 없습니다. 설정의 OpenAPI를 확인하세요.',success:`전체 설정 증권사 동기화 성공 · ${new Date().toLocaleString('ko-KR')}`};
    syncStatus.textContent = detail.message || labels[detail.state] || '';
    renderHistory();
  });
  const bucketPanel = document.createElement('article');
  bucketPanel.className = 'wealth-bucket-panel wealth-composition';
  bucketPanel.innerHTML = `<h3>전략 버킷</h3><p class="wealth-help">증권 보유종목과 예수금을 목적별로 관리합니다. 계좌 기본 분류보다 보유내역별 예외가 우선하며, 같은 종목도 계좌별로 구분됩니다. 미분류도 전체 비중에 포함됩니다. 목표는 사용자 공통 설정이며 현재 비중은 선택한 가족 범위 기준입니다.</p><div id="wealthBucketSummary"></div>
    <details id="wealthBucketEditor"><summary>버킷과 분류 관리</summary><form id="wealthBucketForm"><div class="wealth-bucket-presets"><strong>추천 버킷</strong><p class="wealth-help">필요한 항목만 선택하세요. 저장 전에는 실제 분류가 변경되지 않습니다.</p><div id="wealthBucketPresetButtons" class="wealth-bucket-preset-buttons"></div></div><div id="wealthBucketRows"></div><button id="wealthAddBucket" type="button" class="button secondary">+ 사용자 정의 버킷</button><p id="wealthBucketTargetStatus" class="wealth-bucket-target-status" role="status"></p><h4>계좌별 기본 버킷</h4><div id="wealthAccountAssignments"></div><h4>보유내역별 예외</h4><p class="wealth-help">동기화로 보유내역 ID가 바뀌면 기존 예외를 자동 추정하지 않습니다. 분류를 다시 확인하세요.</p><div id="wealthHoldingAssignments"></div><div class="wealth-editor-actions"><button type="submit" class="button primary">분류 저장</button><button type="button" id="wealthReloadPlanning" class="button secondary">다시 불러오기</button></div></form></details><p id="wealthBucketStatus" class="wealth-help" role="status"></p>`;
  invest.append(bucketPanel);
  const nav = document.createElement('div'); nav.className = 'wealth-invest-tabs';
  nav.setAttribute('aria-label','투자 화면 선택');
  nav.innerHTML = '<button type="button" data-invest="overview" aria-pressed="true">📊 포트폴리오</button><button type="button" data-invest="heatmap">🗺️ 히트맵</button><button type="button" data-invest="records">🗓️ 주식기록</button><button type="button" data-invest="buckets">🎯 전략 버킷</button><button type="button" data-invest="tax_accounts">🧾 절세계좌</button><button type="button" data-invest="holdings">📋 보유종목</button>';
  invest.prepend(nav);
  function selectTab(tab) {
    ['summaryPanel','assetHeatmapPanel','holdingsPanel'].forEach(id => document.getElementById(id).classList.toggle('wealth-invest-hidden', !((tab === 'overview' && id === 'summaryPanel') || (tab === 'heatmap' && id === 'assetHeatmapPanel') || (tab === 'holdings' && id === 'holdingsPanel'))));
    document.getElementById('recordsPanel').classList.toggle('wealth-invest-hidden',tab !== 'records');
    bucketPanel.classList.toggle('wealth-invest-hidden',tab !== 'buckets');
    if (tab === 'records' || tab === 'tax_accounts') {
      const view = document.querySelector(`#recordViewTabs [data-view="${tab === 'tax_accounts' ? 'tax_accounts' : 'combo'}"]`);
      if (view && !view.classList.contains('active')) view.click();
      document.getElementById('recordsPanel').classList.remove('wealth-invest-hidden');
    }
    nav.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.invest === tab)));
    window.dispatchEvent(new CustomEvent('wealth:view',{detail:'invest'}));
  }
  nav.addEventListener('click', e => { if(e.target.dataset.invest) selectTab(e.target.dataset.invest); });
  selectTab('overview');
  async function request(path, payload) {
    const response = await fetch('/api/planning' + path, payload ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)} : {});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '저장하지 못했습니다.');
    return data;
  }
  async function load(discardDraft = false) {
    try { state = await request(''); if(discardDraft) dirty=false; renderHistory(); renderBucketSummary(); if(!dirty) renderEditor(); }
    catch(error) { document.getElementById('wealthHistoryStatus').textContent = error.message; document.getElementById('wealthBucketStatus').textContent = error.message; }
  }
  window.addEventListener('wealth:role', ({detail}) => { if(!detail.isAdminUser) load(); });
  window.addEventListener('wealth:summary', ({detail}) => { summary = detail; renderHistory(); });
  window.addEventListener('wealth:portfolio', ({detail}) => {
    portfolioView = detail; renderBucketSummary();
    if(!dirty) renderEditor();
    else document.getElementById('wealthBucketStatus').textContent = `미저장 변경 있음 · 편집 범위: ${editorView.owner}. 현재 조회 범위와 다를 수 있습니다. 저장하거나 ‘다시 불러오기’를 선택하세요.`;
  });
  historyPanel.querySelector('.wealth-periods').addEventListener('click', e => {
    if(!e.target.dataset.period) return;
    range = e.target.dataset.period;
    historyPanel.querySelectorAll('[data-period]').forEach(b => b.classList.toggle('active',b.dataset.period === range));
    renderHistory();
  });
  function renderHistory() {
    if(!state || !summary) return;
    const allRecords=state.history.filter(r=>r.owner===summary.owner).sort((a,b)=>String(a.date||'').localeCompare(String(b.date||'')));
    const records=filterHistoryPeriod(allRecords,range);
    const plot = document.getElementById('wealthHistoryPlot');
    const details = document.getElementById('wealthHistoryDetails');
    document.getElementById('wealthHistoryStatus').textContent = records.length ? `${summary.owner === '모두' ? '전체 가족' : summary.owner} · ${records.length}개 기록${records.length > 1 ? ' · 기간 증감 '+won(records.at(-1).net_worth-records[0].net_worth) : ' · 두 번째 기록부터 추세를 표시합니다.'}` : '아직 기록이 없습니다. 자산 정보를 확인한 뒤 ‘기록’을 누르세요. 과거 값을 추정하지 않습니다.';
    const summaryBox=document.getElementById('wealthHistorySummary');
    if(!records.length) { summaryBox.replaceChildren(); plot.replaceChildren(); renderHistoryDetails(details, records); return; }
    const values=records.map(r=>Number(r.net_worth)||0), firstValue=values[0], latestValue=values.at(-1), minValue=Math.min(...values), maxValue=Math.max(...values);
    summaryBox.innerHTML=`<div><span>기간 시작</span><strong>${won(firstValue)}</strong></div><div><span>최근 기록</span><strong>${won(latestValue)}</strong></div><div><span>최저 / 최고</span><strong>${won(minValue)} · ${won(maxValue)}</strong></div><div><span>기간 증감</span><strong class="${latestValue-firstValue >= 0 ? 'is-positive' : 'is-negative'}">${latestValue-firstValue >= 0 ? '+' : ''}${won(latestValue-firstValue)}</strong></div>`;
    const lo=Math.min(...values), hi=Math.max(...values), span=hi-lo || Math.max(Math.abs(hi)*0.05,1);
    const first=Date.parse(records[0].date), duration=Date.parse(records.at(-1).date)-first || 1;
    const containerWidth = plot.clientWidth || 800;
    const width = containerWidth;
    const pad = Math.max(48, Math.min(64, Math.round(width * 0.06)));
    const left = pad, right = width - pad, lineTop = 48, lineBottom = 137, barBaseline = 202;
    const points=records.map(r=>[records.length === 1 ? width/2 : left+(Date.parse(r.date)-first)/duration*(right-left), lineBottom-(r.net_worth-lo)/span*(lineBottom-lineTop)]);
    const deltas=records.map((r,i)=>i ? (Number(r.net_worth)||0)-(Number(records[i-1].net_worth)||0) : 0), maxDelta=Math.max(...deltas.map(v=>Math.abs(v)),1);
    const barWidth=Math.max(3,Math.min(24,(right-left)/Math.max(records.length*2,1)));
    const bars=records.map((r,i)=>{if(!i || !deltas[i])return '';const height=Math.abs(deltas[i])/maxDelta*42, y=deltas[i]>0?barBaseline-height:barBaseline;return `<rect class="wealth-history-bar ${deltas[i]>0?'is-positive':'is-negative'}" x="${points[i][0]-barWidth/2}" y="${y}" width="${barWidth}" height="${height}" rx="2"><title>${esc(r.date)} · 전 기록 대비 변화 ${deltas[i]>0?'+':''}${won(deltas[i])}</title></rect>`;}).join('');
    const showLabels = new Array(records.length).fill(false);
    if (records.length === 1) {
      showLabels[0] = true;
    } else if (records.length > 1) {
      showLabels[0] = true;
      showLabels[records.length - 1] = true;
      const minSpacing = 64;
      let lastX = points[0][0];
      const lastIdx = records.length - 1;
      const endX = points[lastIdx][0];
      for (let i = 1; i < lastIdx; i++) {
        if (points[i][0] - lastX >= minSpacing && endX - points[i][0] >= minSpacing) {
          showLabels[i] = true;
          lastX = points[i][0];
        }
      }
    }
    const pointLabels=points.map((p,i)=>`<g class="wealth-history-point"><circle cx="${p[0]}" cy="${p[1]}" r="4" fill="#9b8afb" stroke="#0e162b" stroke-width="2"><title>${esc(records[i].date)} · 순자산 ${won(records[i].net_worth)}${i?' · 전 기록 대비 '+(deltas[i]>0?'+':'')+won(deltas[i]):' · 비교할 이전 기록 없음'}</title></circle>${showLabels[i] ? `<text x="${p[0]}" y="${Math.max(16,p[1]-10)}" fill="#f3f5ff" font-size="10" font-weight="700" text-anchor="middle">${won(records[i].net_worth)}</text><text x="${p[0]}" y="232" fill="currentColor" font-size="10" text-anchor="middle">${esc(records[i].date)}</text>` : ''}</g>`).join('');
    plot.innerHTML = `<div class="wealth-history-chart-card"><div class="wealth-history-legend" aria-label="그래프 범례"><span><i class="legend-line"></i>순자산</span><span><i class="legend-positive"></i>순자산 증가</span><span><i class="legend-negative"></i>순자산 감소</span></div><svg class="wealth-history-chart" viewBox="0 0 ${width} 250" style="width:100%;height:250px;display:block" role="img" aria-label="날짜별 순자산과 전 기록 대비 변화 추이"><path d="M${left} ${barBaseline}H${right}" stroke="currentColor" opacity=".2"/><path d="M${left} ${lineBottom}H${right}" stroke="currentColor" opacity=".12" stroke-dasharray="2 4"/>${bars}<polyline points="${points.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#9b8afb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${pointLabels}</svg></div>`;
    renderHistoryDetails(details, records);
  }
  function renderHistoryDetails(details, records) {
    const disabled = !state || !summary || syncBlocked ? ' disabled' : '';
    const recordCards=[...records].reverse().map(r=>`<article class="wealth-history-record"><div class="wealth-history-record-head"><time datetime="${esc(r.date)}">${esc(r.date)}</time><strong>${won(r.net_worth)}</strong></div><p class="wealth-history-record-amounts"><span class="record-asset">총자산 ${r.assets == null ? '미입력' : won(r.assets)}</span><span class="record-debt">총부채 ${r.debt == null ? '미입력' : won(r.debt)}</span></p><div class="wealth-history-record-note"><span class="record-source">구분 · ${r.source==='manual'?'직접 입력':'현재 자산 기록'}</span><span class="record-memo">메모 · ${esc(r.memo || '없음')}</span></div><div class="wealth-history-record-actions"><button type="button" class="button secondary tiny" data-history-edit="${esc(r.date)}">수정</button><button type="button" class="button text danger tiny" data-history-delete="${esc(r.date)}">삭제</button></div></article>`).join('');
    details.innerHTML = `<summary><span>기록 상세 보기</span><span>${records.length}개 <button type="button" class="button primary tiny" data-history-action="wealthSaveSnapshot"${disabled}>기록</button><button type="button" class="button secondary tiny" data-history-action="wealthAddHistory"${disabled}>추가</button></span></summary>${records.length ? `<div class="wealth-history-record-list">${recordCards}</div>` : ''}`;
  }
  function filterHistoryPeriod(records, period) {
    if (!records.length || period === 'ALL') return records;
    if (period === '1D') return records.slice(-2);
    if (period === '1W') {
      const valid = records.filter(r => /^\d{4}-\d{2}-\d{2}$/.test(String(r.date || '')));
      if (!valid.length) return [];
      const anchor = String(valid.at(-1).date);
      const anchorMs = Date.UTC(Number(anchor.slice(0, 4)), Number(anchor.slice(5, 7)) - 1, Number(anchor.slice(8, 10)));
      return records.filter(r => {
        const value = String(r.date || '');
        if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
        const ms = Date.UTC(Number(value.slice(0, 4)), Number(value.slice(5, 7)) - 1, Number(value.slice(8, 10)));
        const diffDays = (anchorMs - ms) / 86400000;
        return diffDays >= 0 && diffDays <= 7;
      });
    }
    const days = period === '1M' ? 30 : 365;
    const cutoff = Date.now() - days * 86400000;
    const filtered = records.filter(r => Date.parse(`${r.date}T23:59:59+09:00`) >= cutoff);
    return filtered.length >= 2 ? filtered : records.slice(-days);
  }
  function showHistoryDate(date) {
    // A newly added old date must be visible even outside the active period.
    range='ALL';historyPanel.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('active',b.dataset.period==='ALL'));
    renderHistory();
  }
  window.addEventListener('wealth:view',({detail})=>{if(detail==='home')requestAnimationFrame(renderHistory);});
  window.addEventListener('resize',()=>{if(!home.hidden)requestAnimationFrame(renderHistory);});
  async function saveSnapshot(snapshotButton) {
    if(!state || !summary || syncBlocked) return;
    const date = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const exists=state.history.some(r=>r.date === date && r.owner === summary.owner);
    if(!confirm(`${summary.owner === '모두' ? '전체 가족' : summary.owner}의 현재 순자산 ${won(summary.netWorth)}을 기록할까요?\n${exists ? '기존 기록을 교체합니다.' : '확인한 현재 값만 저장합니다.'}\n등록 자산과 최근 동기화 결과를 확인하세요.`)) return;
    snapshotButton.disabled=true;
    try { state=await request('/snapshot',{revision:state.revision,owner:summary.owner,assets:summary.netWorth+summary.debt,debt:summary.debt,net_worth:summary.netWorth,fx_rates:summary.fxRates,valuation_at:summary.updatedAt,replace:exists}); renderHistory(); }
    catch(error) { document.getElementById('wealthHistoryStatus').textContent=error.message; }
    finally { snapshotButton.disabled=syncBlocked; }
  }
  function bucketColor(id) {
    if(id === '__unclassified__') return '#697386';
    if(id === '__unallocated__') return '#35415b';
    if(id && typeof id === 'object') {
      if(id.id === '__unclassified__') return '#697386';
      if(id.id === '__unallocated__') return '#35415b';
      if(id.name && BUCKET_PRESET_COLORS[String(id.name).trim()]) return BUCKET_PRESET_COLORS[String(id.name).trim()];
      id = id.id || id.name || '';
    }
    const key = String(id || '').trim();
    if(BUCKET_PRESET_COLORS[key]) return BUCKET_PRESET_COLORS[key];
    const item = state?.buckets?.find(b => String(b.id) === key);
    if(item && BUCKET_PRESET_COLORS[String(item.name || '').trim()]) {
      return BUCKET_PRESET_COLORS[String(item.name || '').trim()];
    }
    const draftRow = typeof document !== 'undefined' && document.querySelector ? document.querySelector(`.wealth-bucket-edit-row[data-id="${key}"] [name="bucketName"]`) : null;
    if(draftRow && BUCKET_PRESET_COLORS[String(draftRow.value || '').trim()]) {
      return BUCKET_PRESET_COLORS[String(draftRow.value || '').trim()];
    }
    let hash=0;
    for(const char of String(id)) hash=((hash*31)+char.codePointAt(0))>>>0;
    return BUCKET_COLORS[hash%BUCKET_COLORS.length];
  }
  function donutGradient(items, valueField) {
    let cursor=0;
    const segments=items.filter(item=>Number(item[valueField])>0).map(item=>{
      const start=cursor;
      cursor+=Number(item[valueField]);
      return `${bucketColor(item.id)} ${start}% ${Math.min(cursor,100)}%`;
    });
    return segments.length ? `conic-gradient(${segments.join(',')})` : 'var(--surface-2)';
  }
  function allocationLegend(items, valueField, showAmount=false) {
    return items.map(item=>`<div class="wealth-bucket-legend-row" style="--bucket-color:${bucketColor(item.id)}"><span>${esc(item.name)}</span><strong>${Number(item[valueField]||0).toFixed(1)}%</strong>${showAmount?`<small>${won(item.value)}</small>`:''}</div>`).join('');
  }
  function renderBucketSummary() {
    if(!state || !portfolioView) return;
    let result;
    try { result=window.WealthPlanningModel.bucketAllocationComparison(state,portfolioView); }
    catch(error) { document.getElementById('wealthBucketSummary').textContent=error.message; return; }
    const {buckets,current,target,total,targetTotal,targetConfigured}=result;
    const targetPanel=targetConfigured
      ? `<div class="wealth-bucket-chart-row"><div class="wealth-bucket-donut" role="img" aria-label="목표 비중: ${target.map(item=>`${esc(item.name)} ${Number(item.value).toFixed(1)}%`).join(', ')}" style="background:${donutGradient(target,'value')}"><span>목표 합계</span><strong>100%</strong></div><div class="wealth-bucket-legend">${allocationLegend(target,'value')}</div></div>`
      : '<div class="wealth-bucket-empty"><strong>목표 비중이 아직 설정되지 않았습니다.</strong><span>추천 버킷을 선택하거나 사용자 정의 버킷의 목표를 입력하세요.</span></div>';
    const currentPanel=total>0
      ? `<div class="wealth-bucket-chart-row"><div class="wealth-bucket-donut" role="img" aria-label="현재 비중: ${current.map(item=>`${esc(item.name)} ${Number(item.percent).toFixed(1)}%`).join(', ')}" style="background:${donutGradient(current,'percent')}"><span>현재 합계</span><strong>100%</strong></div><div class="wealth-bucket-legend">${allocationLegend(current,'percent',true)}</div></div>`
      : '<div class="wealth-bucket-empty"><strong>표시할 현재 증권 자산이 없습니다.</strong><span>선택한 가족 범위의 보유종목과 예수금을 확인하세요.</span></div>';
    const cards=[...buckets,{id:'__unclassified__',name:'미분류',purpose:'버킷이 지정되지 않은 보유내역과 예수금',target:null,value:current.find(item=>item.id==='__unclassified__')?.value||0}];
    document.getElementById('wealthBucketSummary').innerHTML = `<p class="wealth-help">${esc(portfolioView.owner)} · 증권 평가액과 예수금 ${won(total)} · 매매 주문은 실행하지 않습니다.</p><div class="wealth-bucket-comparison"><section><h4>목표 비중</h4><p>사용자 공통 전략 · 설정 합계 ${targetTotal.toFixed(1)}%</p>${targetPanel}</section><section><h4>현재 비중</h4><p>${esc(portfolioView.owner)} 범위 · 미분류 포함</p>${currentPanel}</section></div><div class="wealth-bucket-cards">${cards.map(b=>{const currentItem=current.find(item=>item.id===b.id),pct=currentItem?.percent||0,value=currentItem?.value||0;return `<article style="--bucket-color:${bucketColor(b.id)}"><h4>${esc(b.name)}</h4><p>${esc(b.purpose)}</p><strong>${won(value)}</strong><p>현재 ${pct.toFixed(1)}%${b.target === null ? '' : ` / 목표 ${b.target}% · 차이 ${(pct-b.target).toFixed(1)}%p`}</p></article>`;}).join('')}</div>`;
  }
  function bucketRow(bucket) {
    const row=document.createElement('div'); row.className='wealth-bucket-edit-row'; row.dataset.id=bucket.id;
    row.innerHTML=`<label>이름<input name="bucketName" maxlength="50" required value="${esc(bucket.name)}"></label><label>목적<input name="purpose" maxlength="200" value="${esc(bucket.purpose)}"></label><label>목표 %<input name="target" type="number" min="0" max="100" step="0.1" value="${bucket.target}" required></label><button type="button" class="button secondary" data-remove-bucket>제거</button>`;
    return row;
  }
  function renderPresetButtons() {
    const names=new Set(draftBuckets().map(bucket=>bucket.name.trim()).filter(Boolean));
    document.getElementById('wealthBucketPresetButtons').innerHTML=BUCKET_PRESETS.map(([name])=>`<button type="button" class="wealth-bucket-preset${names.has(name)?' active':''}" data-bucket-preset="${esc(name)}" aria-pressed="${names.has(name)}" style="--bucket-color:${bucketColor(name)}"><i class="wealth-bucket-preset-dot"></i>${esc(name)}</button>`).join('');
  }
  function draftTargetValidation() {
    const inputs=[...document.querySelectorAll('.wealth-bucket-edit-row [name="target"]')];
    const values=inputs.map(input=>input.value.trim()===''?NaN:Number(input.value));
    if(values.some(value=>!Number.isFinite(value)||value<0||value>100)) return {valid:false,total:NaN,message:'각 목표 비중은 0% 이상 100% 이하로 입력하세요.'};
    const total=values.reduce((sum,value)=>sum+value,0);
    if(total>100.000001) return {valid:false,total,message:`목표 비중 합계가 ${total.toFixed(1)}%입니다. 100% 이하로 조정해주세요.`};
    return {valid:true,total,message:total===100?'목표 비중 합계 100.0%입니다.':`목표 비중 합계 ${total.toFixed(1)}% · 미배정 ${(100-total).toFixed(1)}%`};
  }
  function renderDraftTargetStatus() {
    const validation=draftTargetValidation(),status=document.getElementById('wealthBucketTargetStatus');
    status.textContent=validation.message;
    status.classList.toggle('invalid',!validation.valid);
    return validation;
  }
  function addDraftBucket(name='',purpose='') {
    const buckets=draftBuckets();
    if(buckets.length>=30) return;
    if(name && buckets.some(bucket=>bucket.name.trim()===name)) {
      document.getElementById('wealthBucketStatus').textContent=`‘${name}’ 버킷이 이미 있습니다.`;
      return;
    }
    markDirty();
    document.getElementById('wealthBucketRows').append(bucketRow({id:crypto.randomUUID(),name,purpose,target:0}));
    renderPresetButtons();renderDraftTargetStatus();renderAssignments();
  }
  function renderEditor() {
    if(!state || !portfolioView) return;
    editorView = portfolioView; editorRevision = state.revision;
    draftNotice.textContent='';
    document.getElementById('wealthBucketStatus').textContent='';
    document.getElementById('wealthAccountAssignments').replaceChildren();
    document.getElementById('wealthHoldingAssignments').replaceChildren();
    const rows=document.getElementById('wealthBucketRows'); rows.replaceChildren(...state.buckets.map(bucketRow));
    renderPresetButtons();renderDraftTargetStatus();renderAssignments();
  }
  function draftBuckets() { return [...document.querySelectorAll('.wealth-bucket-edit-row')].map(row=>({id:row.dataset.id,name:row.querySelector('[name="bucketName"]').value,purpose:row.querySelector('[name="purpose"]').value,target:Number(row.querySelector('[name="target"]').value)})); }
  function renderAssignments() {
    const buckets=draftBuckets();
    const options=(value,holding)=>`<option value="${holding?'__inherit__':''}">${holding?'계좌 기본값 사용':'미분류'}</option>${holding?'<option value="">명시적 미분류</option>':''}`+buckets.map(b=>`<option value="${esc(b.id)}"${b.id === value?' selected':''}>${esc(b.name || '이름 미입력')}</option>`).join('');
    for(const [field,target] of [['accounts','wealthAccountAssignments'],['holdings','wealthHoldingAssignments']]) {
      const holder=document.getElementById(target);
      const previous=new Map([...holder.querySelectorAll('select')].map(s=>[s.dataset.id,s.value]));
      const items=field === 'accounts' ? editorView.accounts : editorView.holdings.filter(h=>editorView.accounts.some(a=>a.id === h.account_id));
      holder.innerHTML=items.map(item=>{const value=previous.has(String(item.id))?previous.get(String(item.id)):Object.hasOwn(state[field],item.id)?state[field][item.id]:field==='holdings'?'__inherit__':'';return `<label class="wealth-assignment">${esc(field==='holdings' ? `${item.account_name || item.account_id} · ${item.name}` : `${item.broker || ''} · ${item.name}`)}<select data-field="${field}" data-id="${esc(item.id)}">${options(value,field==='holdings')}</select></label>`;}).join('') || '<p class="wealth-help">선택한 가족 범위에 분류할 증권 내역이 없습니다.</p>';
      holder.querySelectorAll('select').forEach(s=>{const value=previous.has(s.dataset.id)?previous.get(s.dataset.id):state[field][s.dataset.id]; if(value!==undefined && [...s.options].some(o=>o.value===value)) s.value=value;});
    }
  }
  document.getElementById('wealthBucketForm').addEventListener('input',e=>{markDirty();renderDraftTargetStatus();if(e.target.name==='bucketName'){renderPresetButtons();renderAssignments();}});
  document.getElementById('wealthBucketForm').addEventListener('change',e=>{markDirty();renderDraftTargetStatus();if(e.target.name==='bucketName'){renderPresetButtons();renderAssignments();}});
  document.getElementById('wealthBucketPresetButtons').addEventListener('click',e=>{const button=e.target.closest('[data-bucket-preset]');if(!button)return;const preset=BUCKET_PRESETS.find(([name])=>name===button.dataset.bucketPreset);if(preset)addDraftBucket(...preset);});
  document.getElementById('wealthAddBucket').addEventListener('click',()=>addDraftBucket());
  document.getElementById('wealthBucketRows').addEventListener('click',e=>{if(e.target.hasAttribute('data-remove-bucket')){e.target.closest('.wealth-bucket-edit-row').remove();markDirty();renderPresetButtons();renderDraftTargetStatus();renderAssignments();}});
  document.getElementById('wealthReloadPlanning').addEventListener('click',()=>{if(!dirty || confirm('저장하지 않은 분류 변경을 버리고 다시 불러올까요?'))load(true);});
  document.getElementById('wealthBucketForm').addEventListener('submit',async e=>{
    e.preventDefault(); if(!state)return;
    const button=e.submitter; button.disabled=true;
    const targetValidation=renderDraftTargetStatus();
    if(!targetValidation.valid){document.getElementById('wealthBucketStatus').textContent=targetValidation.message;button.disabled=false;return;}
    const buckets=draftBuckets(), ids=new Set(buckets.map(b=>b.id));
    const payload={revision:editorRevision,buckets,accounts:{...state.accounts},holdings:{...state.holdings}};
    for(const field of ['accounts','holdings']) for(const key of Object.keys(payload[field])) if(payload[field][key] && !ids.has(payload[field][key])) delete payload[field][key];
    document.querySelectorAll('.wealth-assignment select').forEach(s=>{if(s.value==='__inherit__')delete payload[s.dataset.field][s.dataset.id];else payload[s.dataset.field][s.dataset.id]=s.value;});
    try { state=await request('/buckets',payload);dirty=false;renderBucketSummary();renderEditor();document.getElementById('wealthBucketStatus').textContent='분류를 저장했습니다. 실제 잔고와 거래는 변경하지 않았습니다.'; }
    catch(error){document.getElementById('wealthBucketStatus').textContent=error.message;}
    finally{button.disabled=false;}
  });
})();
