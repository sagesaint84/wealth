(() => {
  'use strict';
  const panel = document.getElementById('ledgerOcrPanel');
  if (!panel) return;
  const byId = id => document.getElementById(id);
  const fileInput = byId('ledgerOcrFile'), analyze = byId('ledgerOcrAnalyze');
  const status = byId('ledgerOcrStatus'), review = byId('ledgerOcrReview'), type = byId('ledgerOcrType');
  const add = byId('ledgerOcrAdd'), check = byId('ledgerOcrCheck'), save = byId('ledgerOcrSave');
  const confirmation = byId('ledgerOcrConfirmation'), confirmed = byId('ledgerOcrConfirmed');
  const summary = byId('ledgerOcrSummary');
  let drafts = [], options = null, analysisRevision = 0, draftRevision = 0, controller = null;
  let checked = null, pending = null, busy = false, analyzing = false, lifecycle = 0;
  const kinds = {unknown:'미확인',normal:'일반 거래',bank_transfer:'이체',card_approval_candidate:'카드 승인',card_cancellation:'취소',refund:'환불',card_bill:'카드대금'};
  function node(tag, value) { const element = document.createElement(tag); element.textContent = value; return element; }
  function money(value) {
    return typeof value === 'string' && /^\d+$/.test(value) ? BigInt(value).toLocaleString('ko-KR') : '미확인';
  }
  function totalMoney(value) {
    if(typeof value!=='string' || !/^\d+(?:\.\d+)?$/.test(value))return '미확인';
    const [whole,fraction]=value.split('.');
    return BigInt(whole).toLocaleString('ko-KR')+(fraction?'.'+fraction:'');
  }
  function selected() { return drafts.filter(row => row.selected); }
  function payload(row) {
    return {date:row.date,amount:row.amount.replaceAll(',','').trim(),type:row.type,owner:row.owner,
      category:row.category,merchant:row.merchant,transaction_time:row.transaction_time,memo:row.memo,
      direction:row.direction,source_kind:row.source_kind,special_confirmed:row.special_confirmed,
      duplicate_confirmed:row.duplicate_confirmed};
  }
  function problems(row) {
    const errors = [];
    const day = /^\d{4}-\d{2}-\d{2}$/.test(row.date) ? new Date(row.date+'T00:00:00Z') : null;
    if (!day || !Number.isFinite(day.getTime()) || day.toISOString().slice(0,10)!==row.date) errors.push('전체 날짜');
    const amount = row.amount.replaceAll(',','').trim();
    if (!/^\d+(?:\.\d+)?$/.test(amount) || !Number.isFinite(Number(amount)) || Number(amount)<=0) errors.push('양수 금액');
    if (!['income','expense','transfer'].includes(row.type)) errors.push('거래 종류');
    if (!options?.owners?.includes(row.owner)) errors.push('소유자');
    if (!options?.categories?.[row.type]?.includes(row.category)) errors.push('분류');
    if (!['inflow','outflow'].includes(row.direction) || row.type==='income' && row.direction!=='inflow' || row.type==='expense' && row.direction!=='outflow') errors.push('입출금');
    if (row.source_kind==='bank_transfer' && row.type!=='transfer') errors.push('이체 종류');
    if (['card_cancellation','refund'].includes(row.source_kind) && !row.special_confirmed) errors.push('취소·환불 반영 확인');
    if (row.transaction_time && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(row.transaction_time)) errors.push('시간 HH:MM');
    return errors;
  }
  function controls() {
    const locked = busy;
    for (const control of review.querySelectorAll('input,select,button')) control.disabled = locked;
    analyze.disabled = locked || analyzing; fileInput.disabled = locked || analyzing; type.disabled = locked || analyzing;
    add.disabled = locked; byId('ledgerOcrOptions').disabled = locked;
    check.disabled = locked || !selected().length;
    confirmed.disabled = locked;
    save.disabled = busy || !!pending || !checked || !confirmed.checked || checked.duplicates.some((flag,index)=>flag && !selected()[index]?.duplicate_confirmed);
    save.textContent = '확인한 거래 추가';
    check.textContent = pending ? '저장 내역 다시 조회' : '선택 행 중복 검토';
  }
  function update() {
    const rows = selected();
    summary.textContent = `전체 ${drafts.length}행 · 선택 ${rows.length}행 · 미확인 필수값 ${rows.filter(row=>problems(row).length).length}행`;
    for (const row of drafts) {
      const message = review.querySelector(`[data-errors="${row.id}"]`);
      if (message) message.textContent = problems(row).length ? '확인 필요: '+problems(row).join(', ') : '필수값 입력 완료 · 최종 검토 필요';
      const unknown = review.querySelector(`[data-amount-unknown="${row.id}"]`);
      if(unknown)unknown.hidden=!row.amountUnknown;
    }
    controls();
  }
  function changed() { draftRevision++; checked=null; confirmed.checked=false; confirmation.hidden=true; update(); }
  function selectControl(row, key, label, values) {
    const wrapper = node('label',label), control = document.createElement('select');
    control.dataset.field=key;control.setAttribute('aria-label',label);
    control.append(new Option('직접 선택 · 미확인',''));
    for (const [value,name] of values) control.append(new Option(name,value));
    control.value=row[key];
    control.addEventListener('change',()=>{
      row[key]=control.value;
      if (key==='type') {
        row.category='';
        if (row.type==='income') row.direction='inflow';
        if (row.type==='expense') row.direction='outflow';
        render();
      }
      changed();
    });
    wrapper.append(control);return wrapper;
  }
  function field(row,key,label,inputType='text') {
    const wrapper=node('label',label), control=document.createElement('input');
    control.type=inputType;control.value=row[key];control.dataset.field=key;
    control.placeholder='미확인 · 직접 입력';control.setAttribute('aria-label',label);
    control.maxLength=key==='memo'?1000:key==='merchant'?200:100;
    if(key==='amount')control.inputMode='decimal';
    control.addEventListener('input',()=>{row[key]=control.value;if(key==='amount')row.amountUnknown=false;changed();});
    wrapper.append(control);return wrapper;
  }
  function tick(row,key,label) {
    const wrapper=node('label',label), control=document.createElement('input');
    control.type='checkbox';control.checked=row[key];control.dataset.field=key;
    control.addEventListener('change',()=>{row[key]=control.checked;changed();});
    wrapper.prepend(control);return wrapper;
  }
  function render() {
    review.replaceChildren();
    for(const row of drafts) {
      const card=document.createElement('article');card.className='ledger-ocr-row';card.dataset.row=row.id;
      card.append(tick(row,'selected','이 행 추가 대상으로 선택'));
      card.append(node('p',row.reference || '수동 입력 · 모든 필수값을 직접 확인해 주세요.'));
      const amountNote=node('p','0원(미확인) · 인식하지 못한 금액입니다. 실제 금액을 직접 입력해 주세요.');
      amountNote.dataset.amountUnknown=row.id;card.append(amountNote);
      const grid=document.createElement('div');grid.className='ledger-ocr-fields';
      grid.append(field(row,'date','거래일 (연도 포함)','date'),field(row,'amount','금액 (양수)'),
        selectControl(row,'type','가계부 종류',[['income','수입'],['expense','지출'],['transfer','이체']]),
        selectControl(row,'direction','입출금',[['inflow','입금'],['outflow','출금']]),
        selectControl(row,'owner','소유자',(options?.owners || []).map(value=>[value,value])),
        selectControl(row,'category','분류',(options?.categories?.[row.type] || []).map(value=>[value,value])),
        field(row,'merchant','거래처 (선택)'),field(row,'transaction_time','시간 HH:MM (선택)'),field(row,'memo','메모 (선택)'),
        selectControl(row,'source_kind','거래 성격',Object.entries(kinds)));
      card.append(grid,tick(row,'special_confirmed','취소·환불의 반영 방법을 직접 확인했습니다. 원거래는 변경하지 않습니다.'));
      if(row.duplicate)card.append(node('p','중복 후보: 기존 내역 또는 선택한 다른 행과 유사합니다.'),tick(row,'duplicate_confirmed','중복 후보이지만 별도 거래임을 확인했습니다.'));
      const errors=node('p','');errors.dataset.errors=row.id;card.append(errors);
      const remove=node('button','행 제외·삭제');remove.type='button';remove.className='button secondary compact';
      remove.addEventListener('click',()=>{drafts=drafts.filter(item=>item!==row);changed();render();});
      card.append(remove);review.append(card);
    }
    update();
  }
  function newRow(source={}) {
    const parts=source.transaction_date_parts;
    const amountKnown=source.amount!=null && /^\d+(?:\.\d+)?$/.test(String(source.amount)) && Number.isFinite(Number(source.amount));
    return {id:crypto.randomUUID(),selected:false,date:source.transaction_date || '',amount:amountKnown?String(source.amount):'0',amountUnknown:!amountKnown,
      type:'',owner:'',category:'',direction:source.direction==='inflow'||source.direction==='outflow'?source.direction:'',
      merchant:source.counterparty || source.merchant || '',transaction_time:source.transaction_time || '',memo:'',
      source_kind:source.transaction_type_candidate in kinds?source.transaction_type_candidate:'unknown',
      special_confirmed:false,duplicate_confirmed:false,duplicate:false,
      reference:Object.keys(source).length ? `${source.transaction_date || (parts?.month && parts?.day ? `${parts.month}월 ${parts.day}일 · 연도 미확인` : '거래일을 확인해 주세요.')} · ${source.direction==='inflow'?'+':source.direction==='outflow'?'-':''}₩${money(source.amount)} · 거래 후 잔액 ₩${money(source.balance_after)} (참고 전용) · ${kinds[source.transaction_type_candidate] ? kinds[source.transaction_type_candidate]+' 후보' : '종류 미확인'} · ${source.review_reasons?.includes('year_missing')?'현재 연도로 채우지 않습니다.':''}` : ''};
  }
  async function request(path,body) {
    const response=await fetch('/api/ledger/document-import/'+path,{method:body?'POST':'GET',credentials:'same-origin',
      headers:body?{'Content-Type':'application/json'}:{},...(body?{body:JSON.stringify(body)}:{})});
    const data=await response.json();
    if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:'요청을 완료하지 못했습니다.');error.status=response.status;throw error;}
    return data;
  }
  async function loadOptions() {
    if(!byId('ledgerExcelDialog').open)return;
    const active=lifecycle;
    try {const result=await request('options');if(active!==lifecycle || !byId('ledgerExcelDialog').open)return;
      if(!Array.isArray(result.owners) || !result.owners.every(value=>typeof value==='string') || !['income','expense','transfer'].every(key=>Array.isArray(result.categories?.[key]) && result.categories[key].every(value=>typeof value==='string')))throw new Error('소유자·분류 목록을 확인하지 못했습니다.');
      options=result;render();}
    catch(error){if(active===lifecycle && byId('ledgerExcelDialog').open)status.textContent=error.message+' 입력한 초안은 유지됩니다.';}
  }
  byId('ledgerOcrOptions').addEventListener('click',loadOptions);
  panel.addEventListener('toggle',()=>{if(panel.open && byId('ledgerExcelDialog').open && !options)loadOptions();});
  add.addEventListener('click',()=>{drafts.push(newRow());changed();render();});
  check.addEventListener('click',async()=>{
    if(busy)return;
    if(selected().some(row=>problems(row).length)){status.textContent='선택 행의 필수값을 먼저 입력해 주세요.';update();return;}
    const version=draftRevision, rows=selected(), wasUncertain=!!pending;
    if(wasUncertain)rows.forEach(row=>{row.duplicate_confirmed=false;});
    busy=true;controls();
    try {
      const result=await request('review',{rows:rows.map(payload)});
      if(version!==draftRevision)return;
      pending=null;checked=result;
      rows.forEach((row,index)=>{row.duplicate=!!result.duplicates[index];});
      confirmation.hidden=false;confirmed.checked=false;
      byId('ledgerOcrTotal').textContent=`선택 ${result.count}건 · 금액 합계 ₩${totalMoney(result.total)} (순현금흐름 아님). 계좌·카드·배당 잔액은 변경하지 않습니다.`;
      status.textContent=wasUncertain
        ? '기존 가계부를 다시 조회했습니다. 이전 저장 여부를 내역에서 확인하고, 이미 추가된 행은 제외하세요. 자동으로 다시 저장하지 않습니다.'
        : result.duplicates.some(Boolean)?'중복 후보를 확인해 주세요. 별도 거래로 확인하면 다시 검토해 주세요.':'검토 완료. 마지막 확인 후 추가할 수 있습니다.';
      if(wasUncertain && typeof window.loadLedger==='function')window.loadLedger().catch(()=>{status.textContent+=' 내역 화면을 새로고침해 확인해 주세요.';});
      render();
    } catch(error){checked=null;confirmation.hidden=true;status.textContent=error.message+' 초안은 유지됩니다.';}
    finally {busy=false;controls();}
  });
  confirmed.addEventListener('change',controls);
  save.addEventListener('click',async()=>{
    if(busy || pending || !checked || !confirmed.checked || selected().some(row=>problems(row).length))return;
    const body={rows:selected().map(payload),revision:checked.revision,review_token:checked.review_token,confirmed:true};
    const savedIds=selected().map(row=>row.id);
    busy=true;controls();
    try {
      const result=await request('commit',body);
      const ids=new Set(savedIds);drafts=drafts.filter(row=>!ids.has(row.id));pending=null;
      changed();render();status.textContent=`${result.count}건 추가 완료`;
      if(typeof window.loadLedger==='function')window.loadLedger().catch(()=>{status.textContent='가계부 저장은 완료됐습니다. 화면은 새로고침해 주세요.';});
    } catch(error) {
      pending=!(error.status>=400 && error.status<500);
      checked=null;confirmation.hidden=true;confirmed.checked=false;
      status.textContent=error.message+' 초안은 유지됩니다.'+(pending?' 저장 여부가 미확인입니다. 저장 내역 다시 조회 후 기존 내역을 확인하세요. 자동 재저장은 하지 않습니다.':' 중복 검토를 다시 해 주세요.');
    } finally {busy=false;controls();}
  });
  analyze.addEventListener('click',async()=>{
    const file=fileInput.files[0];
    if(!file){status.textContent='파일을 선택하거나 수동 행을 추가해 주세요.';return;}
    if(file.size>10*1024*1024){status.textContent='10MiB 이하 파일을 선택해 주세요. 수동 입력도 가능합니다.';return;}
    const active=++analysisRevision;controller?.abort();controller=new AbortController();analyzing=true;controls();
    status.textContent='오프라인 분석 중… 기존 편집 초안은 유지됩니다.';
    try {
      const response=await fetch(`/api/ledger/document-import/preview?document_type=${encodeURIComponent(type.value)}`,{
        method:'POST',credentials:'same-origin',headers:{'Content-Type':file.type || 'application/octet-stream'},body:file,signal:controller.signal});
      const data=await response.json();if(active!==analysisRevision)return;
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'분석하지 못했습니다.');
      if(!Array.isArray(data.rows))throw new Error('분석 형식을 확인하지 못했습니다.');
      drafts.push(...data.rows.map(newRow));changed();render();
      status.textContent=data.rows.length?'인식값은 미확인 초안입니다. 수정·선택한 행만 검토 후 추가하세요.':'읽은 거래가 없습니다. 수동 행을 추가해 주세요.';
    } catch(error){if(active===analysisRevision && error.name!=='AbortError')status.textContent=error.message+' 기존 초안은 유지됩니다. 수동 행을 추가할 수 있습니다.';}
    finally {if(active===analysisRevision){analyzing=false;controller=null;controls();}}
  });
  byId('ledgerExcelDialog')?.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  byId('ledgerExcelDialog')?.addEventListener('close',()=>{
    lifecycle++;analysisRevision++;controller?.abort();controller=null;analyzing=false;fileInput.value='';
    if(!busy && !pending){drafts=[];checked=null;draftRevision++;review.replaceChildren();confirmation.hidden=true;confirmed.checked=false;status.textContent='';}
    controls();
  });
  controls();
})();
