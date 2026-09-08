/* User-confirmed history and investment purpose classification. No trading calls. */
(() => {
  'use strict';
  const home = document.querySelector('[data-wealth-page="home"]');
  const invest = document.querySelector('[data-wealth-page="invest"]');
  if (!home || !invest) return;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const won = value => `${Math.round(value).toLocaleString('ko-KR')}원`;
  let state = null, summary = null, portfolioView = null, range = 365, dirty = false, syncBlocked = false;
  const historyPanel = document.createElement('article');
  historyPanel.className = 'wealth-history wealth-composition';
  historyPanel.innerHTML = `<div class="wealth-section-heading"><div><p class="wealth-eyebrow">NET WORTH HISTORY</p><h3>순자산 추이</h3></div><button type="button" class="button secondary" id="wealthSaveSnapshot" disabled>오늘 기록</button></div>
    <p class="wealth-help">사용자가 확인해 저장한 날짜별 기록입니다. 자금 입출금·자산 등록도 반영되므로 투자수익률이 아닙니다.</p>
    <div class="wealth-periods" aria-label="순자산 조회 기간"><button data-days="30">1개월</button><button data-days="90">3개월</button><button data-days="365" aria-pressed="true">1년</button><button data-days="0">전체</button></div>
    <p id="wealthHistoryStatus" class="wealth-help" role="status">기록을 불러오는 중입니다.</p><div id="wealthHistoryPlot"></div>`;
  home.querySelector('.wealth-home-secondary').before(historyPanel);
  const syncStatus = document.createElement('p');
  syncStatus.className = 'wealth-help wealth-sync-status'; syncStatus.setAttribute('role', 'status');
  document.querySelector('.wealth-owner-bar').after(syncStatus);
  window.addEventListener('wealth:sync', ({detail}) => {
    syncBlocked = detail.state !== 'success';
    const labels = {running:'증권사 잔고·보유종목 동기화 중…',partial:'일부 증권사 동기화 실패 — 결과를 확인한 뒤 다시 동기화하세요.',error:'계좌 동기화 실패 — 다시 시도하세요.',empty:'동기화된 증권사가 없습니다. 설정의 OpenAPI를 확인하세요.',success:`전체 설정 증권사 동기화 성공 · ${new Date().toLocaleString('ko-KR')}`};
    syncStatus.textContent = labels[detail.state] || '';
    snapshotButton.disabled = syncBlocked || !state || !summary;
  });
  const bucketPanel = document.createElement('article');
  bucketPanel.className = 'wealth-bucket-panel wealth-composition';
  bucketPanel.innerHTML = `<h3>전략 버킷</h3><p class="wealth-help">증권 보유종목과 예수금을 목적별로 관리합니다. 계좌 기본 분류보다 보유내역별 예외가 우선하며, 같은 종목도 계좌별로 구분됩니다. 미분류도 전체 비중에 포함됩니다. 목표는 사용자 공통 설정이며 현재 비중은 선택한 가족 범위 기준입니다.</p><div id="wealthBucketSummary"></div>
    <details id="wealthBucketEditor"><summary>버킷과 분류 관리</summary><form id="wealthBucketForm"><div id="wealthBucketRows"></div><button id="wealthAddBucket" type="button" class="button secondary">버킷 추가</button><h4>계좌별 기본 버킷</h4><div id="wealthAccountAssignments"></div><h4>보유내역별 예외</h4><p class="wealth-help">동기화로 보유내역 ID가 바뀌면 기존 예외를 자동 추정하지 않습니다. 분류를 다시 확인하세요.</p><div id="wealthHoldingAssignments"></div><div class="wealth-editor-actions"><button type="submit" class="button primary">분류 저장</button><button type="button" id="wealthReloadPlanning" class="button secondary">다시 불러오기</button></div></form></details><p id="wealthBucketStatus" class="wealth-help" role="status"></p>`;
  invest.append(bucketPanel);
  const nav = document.createElement('div'); nav.className = 'wealth-invest-tabs';
  nav.setAttribute('aria-label','투자 화면 선택');
  nav.innerHTML = '<button type="button" data-invest="overview" aria-pressed="true">포트폴리오</button><button type="button" data-invest="buckets">전략 버킷</button><button type="button" data-invest="records">주식기록</button>';
  invest.prepend(nav);
  function selectTab(tab) {
    ['summaryPanel','assetHeatmapPanel','holdingsPanel'].forEach(id => document.getElementById(id).classList.toggle('wealth-invest-hidden',tab !== 'overview'));
    document.getElementById('recordsPanel').classList.toggle('wealth-invest-hidden',tab !== 'records');
    bucketPanel.classList.toggle('wealth-invest-hidden',tab !== 'buckets');
    nav.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.invest === tab)));
    window.dispatchEvent(new CustomEvent('wealth:view',{detail:'invest'}));
  }
  nav.addEventListener('click', e => { if(e.target.dataset.invest) selectTab(e.target.dataset.invest); });
  selectTab('overview');
  const snapshotButton = document.getElementById('wealthSaveSnapshot');
  async function request(path, payload) {
    const response = await fetch('/api/planning' + path, payload ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)} : {});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '저장하지 못했습니다.');
    return data;
  }
  async function load() {
    try { state = await request(''); renderHistory(); renderBucketSummary(); if(!dirty) renderEditor(); }
    catch(error) { document.getElementById('wealthHistoryStatus').textContent = error.message; document.getElementById('wealthBucketStatus').textContent = error.message; }
    snapshotButton.disabled = !state || !summary || syncBlocked;
  }
  window.addEventListener('wealth:role', ({detail}) => { if(!detail.isAdminUser) load(); });
  window.addEventListener('wealth:summary', ({detail}) => { summary = detail; renderHistory(); snapshotButton.disabled = !state || syncBlocked; });
  window.addEventListener('wealth:portfolio', ({detail}) => { portfolioView = detail; renderBucketSummary(); if(!dirty) renderEditor(); });
  historyPanel.querySelector('.wealth-periods').addEventListener('click', e => {
    if(!e.target.dataset.days) return;
    range = Number(e.target.dataset.days);
    historyPanel.querySelectorAll('[data-days]').forEach(b => b.setAttribute('aria-pressed',String(Number(b.dataset.days) === range)));
    renderHistory();
  });
  function renderHistory() {
    if(!state || !summary) return;
    const cutoff = Date.now() - range * 86400000;
    const records = state.history.filter(r => r.owner === summary.owner && (!range || Date.parse(r.date+'T23:59:59+09:00') >= cutoff)).sort((a,b)=>a.date.localeCompare(b.date));
    const plot = document.getElementById('wealthHistoryPlot');
    document.getElementById('wealthHistoryStatus').textContent = records.length ? `${summary.owner === '모두' ? '전체 가족' : summary.owner} · ${records.length}개 기록${records.length > 1 ? ' · 기간 증감 '+won(records.at(-1).net_worth-records[0].net_worth) : ' · 두 번째 기록부터 추세를 표시합니다.'}` : '아직 기록이 없습니다. 자산 정보를 확인한 뒤 ‘오늘 기록’을 누르세요. 과거 값을 추정하지 않습니다.';
    if(!records.length) { plot.replaceChildren(); return; }
    const values = records.map(r=>r.net_worth), lo=Math.min(...values), hi=Math.max(...values), span=hi-lo || Math.max(Math.abs(hi)*0.05,1);
    const first=Date.parse(records[0].date), duration=Date.parse(records.at(-1).date)-first || 1;
    const width=Math.max(plot.clientWidth || 800,250), left=16, right=width-16;
    const points=records.map(r=>[records.length === 1 ? width/2 : left+(Date.parse(r.date)-first)/duration*(right-left), 170-(r.net_worth-lo)/span*130]);
    plot.innerHTML = `<svg class="wealth-history-chart" viewBox="0 0 ${width} 210" role="img" aria-label="날짜별 순자산 추이. 아래 기록 표에서 정확한 값을 확인할 수 있습니다."><path d="M${left} 180H${right}" stroke="currentColor" opacity=".2"/><polyline points="${points.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#9b8afb" stroke-width="3"/>${points.map((p,i)=>`<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="#9b8afb"><title>${esc(records[i].date)}: ${won(records[i].net_worth)}</title></circle>`).join('')}<text x="${left}" y="205" fill="currentColor" font-size="12">${esc(records[0].date)}</text><text x="${right}" y="205" text-anchor="end" fill="currentColor" font-size="12">${esc(records.at(-1).date)}</text></svg><details><summary>기록 상세 보기</summary><div class="table-wrap"><table><thead><tr><th>날짜</th><th>총자산</th><th>총부채</th><th>순자산</th></tr></thead><tbody>${records.map(r=>`<tr><td>${esc(r.date)}</td><td>${won(r.assets)}</td><td>${won(r.debt)}</td><td>${won(r.net_worth)}</td></tr>`).join('')}</tbody></table></div></details>`;
  }
  window.addEventListener('wealth:view',({detail})=>{if(detail==='home')requestAnimationFrame(renderHistory);});
  window.addEventListener('resize',()=>{if(!home.hidden)requestAnimationFrame(renderHistory);});
  snapshotButton.addEventListener('click', async () => {
    if(!state || !summary || syncBlocked) return;
    const date = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const exists=state.history.some(r=>r.date === date && r.owner === summary.owner);
    if(!confirm(`${summary.owner === '모두' ? '전체 가족' : summary.owner}의 현재 순자산 ${won(summary.netWorth)}을 기록할까요?\n${exists ? '오늘 기록을 교체합니다.' : '확인한 현재 값만 저장합니다.'}\n등록 자산과 최근 동기화 결과를 확인하세요.`)) return;
    snapshotButton.disabled=true;
    try { state=await request('/snapshot',{revision:state.revision,owner:summary.owner,assets:summary.netWorth+summary.debt,debt:summary.debt,net_worth:summary.netWorth,fx_rates:summary.fxRates,valuation_at:summary.updatedAt,replace:exists}); renderHistory(); }
    catch(error) { document.getElementById('wealthHistoryStatus').textContent=error.message; }
    finally { snapshotButton.disabled=syncBlocked; }
  });
  function renderBucketSummary() {
    if(!state || !portfolioView) return;
    let result;
    try { result=window.WealthPlanningModel.bucketTotals(state,portfolioView); }
    catch(error) { document.getElementById('wealthBucketSummary').textContent=error.message; return; }
    const {totals,total}=result;
    document.getElementById('wealthBucketSummary').innerHTML = `<p class="wealth-help">${esc(portfolioView.owner)} · 증권 평가액과 예수금 ${won(total)} · 매매 주문은 실행하지 않습니다.</p><div class="wealth-bucket-cards">${[...state.buckets,{id:'',name:'미분류',purpose:'버킷이 지정되지 않은 보유내역과 예수금',target:null}].map(b=>{const value=totals.get(b.id)||0,pct=total ? value/total*100 : 0;return `<article><h4>${esc(b.name)}</h4><p>${esc(b.purpose)}</p><strong>${won(value)}</strong><p>현재 ${pct.toFixed(1)}%${b.target === null ? '' : ` / 목표 ${b.target}% · 차이 ${(pct-b.target).toFixed(1)}%p`}</p></article>`;}).join('')}</div>`;
  }
  function bucketRow(bucket) {
    const row=document.createElement('div'); row.className='wealth-bucket-edit-row'; row.dataset.id=bucket.id;
    row.innerHTML=`<label>이름<input name="bucketName" maxlength="50" required value="${esc(bucket.name)}"></label><label>목적<input name="purpose" maxlength="200" value="${esc(bucket.purpose)}"></label><label>목표 %<input name="target" type="number" min="0" max="100" step="0.1" value="${bucket.target}" required></label><button type="button" class="button secondary" data-remove-bucket>제거</button>`;
    return row;
  }
  function renderEditor() {
    if(!state || !portfolioView) return;
    const rows=document.getElementById('wealthBucketRows'); rows.replaceChildren(...state.buckets.map(bucketRow));
    renderAssignments();
  }
  function draftBuckets() { return [...document.querySelectorAll('.wealth-bucket-edit-row')].map(row=>({id:row.dataset.id,name:row.querySelector('[name="bucketName"]').value,purpose:row.querySelector('[name="purpose"]').value,target:Number(row.querySelector('[name="target"]').value)})); }
  function renderAssignments() {
    const buckets=draftBuckets();
    const options=(value,holding)=>`<option value="${holding?'__inherit__':''}">${holding?'계좌 기본값 사용':'미분류'}</option>${holding?'<option value="">명시적 미분류</option>':''}`+buckets.map(b=>`<option value="${esc(b.id)}"${b.id === value?' selected':''}>${esc(b.name || '이름 미입력')}</option>`).join('');
    for(const [field,target] of [['accounts','wealthAccountAssignments'],['holdings','wealthHoldingAssignments']]) {
      const holder=document.getElementById(target);
      const previous=new Map([...holder.querySelectorAll('select')].map(s=>[s.dataset.id,s.value]));
      const items=field === 'accounts' ? portfolioView.accounts : portfolioView.holdings.filter(h=>portfolioView.accounts.some(a=>a.id === h.account_id));
      holder.innerHTML=items.map(item=>{const value=previous.has(String(item.id))?previous.get(String(item.id)):Object.hasOwn(state[field],item.id)?state[field][item.id]:field==='holdings'?'__inherit__':'';return `<label class="wealth-assignment">${esc(field==='holdings' ? `${item.account_name || item.account_id} · ${item.name}` : `${item.broker || ''} · ${item.name}`)}<select data-field="${field}" data-id="${esc(item.id)}">${options(value,field==='holdings')}</select></label>`;}).join('') || '<p class="wealth-help">선택한 가족 범위에 분류할 증권 내역이 없습니다.</p>';
      holder.querySelectorAll('select').forEach(s=>{const value=previous.has(s.dataset.id)?previous.get(s.dataset.id):state[field][s.dataset.id]; if(value!==undefined && [...s.options].some(o=>o.value===value)) s.value=value;});
    }
  }
  document.getElementById('wealthBucketForm').addEventListener('input',e=>{dirty=true;if(e.target.name==='bucketName')renderAssignments();});
  document.getElementById('wealthBucketForm').addEventListener('change',e=>{dirty=true;if(e.target.name==='bucketName')renderAssignments();});
  document.getElementById('wealthAddBucket').addEventListener('click',()=>{if(draftBuckets().length>=30)return;dirty=true;document.getElementById('wealthBucketRows').append(bucketRow({id:crypto.randomUUID(),name:'',purpose:'',target:0}));renderAssignments();});
  document.getElementById('wealthBucketRows').addEventListener('click',e=>{if(e.target.hasAttribute('data-remove-bucket')){e.target.closest('.wealth-bucket-edit-row').remove();dirty=true;renderAssignments();}});
  document.getElementById('wealthReloadPlanning').addEventListener('click',()=>{if(!dirty || confirm('저장하지 않은 분류 변경을 버리고 다시 불러올까요?')){dirty=false;load();}});
  document.getElementById('wealthBucketForm').addEventListener('submit',async e=>{
    e.preventDefault(); if(!state)return;
    const button=e.submitter; button.disabled=true;
    const buckets=draftBuckets(), ids=new Set(buckets.map(b=>b.id));
    const payload={revision:state.revision,buckets,accounts:{...state.accounts},holdings:{...state.holdings}};
    for(const field of ['accounts','holdings']) for(const key of Object.keys(payload[field])) if(payload[field][key] && !ids.has(payload[field][key])) delete payload[field][key];
    document.querySelectorAll('.wealth-assignment select').forEach(s=>{if(s.value==='__inherit__')delete payload[s.dataset.field][s.dataset.id];else payload[s.dataset.field][s.dataset.id]=s.value;});
    try { state=await request('/buckets',payload);dirty=false;renderBucketSummary();renderEditor();document.getElementById('wealthBucketStatus').textContent='분류를 저장했습니다. 실제 잔고와 거래는 변경하지 않았습니다.'; }
    catch(error){document.getElementById('wealthBucketStatus').textContent=error.message;}
    finally{button.disabled=false;}
  });
})();
