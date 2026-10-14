/* One reviewed import surface inside the existing pension dialog. No automatic financial writes. */
(() => {
  'use strict';
  let item=null,draft=null,busy=false,generation=0,serial=0;
  const node=(tag,text)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;return e;};
  const panel=()=>document.getElementById('npImportPanel');
  const status=text=>{document.getElementById('npImportStatus').textContent=text;};
  const button=(text,fn)=>{const e=node('button',text);e.type='button';e.className='button secondary compact';e.onclick=fn;return e;};
  function input(parent,key,labelText,value,type='number') {
    const names={start:'시작 월 (YYYY-MM)',end:'종료 월 (YYYY-MM)',membership:'가입종별',paid:'기간 실제 납부액',unpaid:'기간 미납액',income_base:'기준소득월액',paid_months:'납부 월수',unpaid_months:'미납 월수',year:'연도',month:'월',kind:'금액 성격',amount:'금액',deposit:'연도 실제 납부액',value:'검토 값'};
    const choices={membership:{unknown:'미확인',workplace:'사업장',regional:'지역'},kind:{paid:'납부금액',billed:'고지금액'}};
    const label=node('label',names[key]||labelText),field=document.createElement(choices[key]?'select':'input');
    if(choices[key])for(const [key,text] of Object.entries(choices[key])){const option=node('option',text);option.value=key;field.append(option);}
    else field.type=['paid','unpaid','income_base','paid_months','unpaid_months','deposit','amount'].includes(key)?'number':type;
    field.id=`npImportField${++serial}`;label.htmlFor=field.id;field.dataset.key=key;field.value=value??'';
    if(field.type==='number'){field.min='0';field.step='1';if(['value','amount','deposit','paid','unpaid','income_base'].includes(key))field.dataset.koreanCurrency='';}
    label.append(field);parent.append(label);return field;
  }
  function reviewRow(kind,label,value,description) {
    const row=node('div');row.className='np-import-row';row.dataset.kind=kind;
    const chooseLabel=node('label','적용');
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.approve='';
    checkbox.id=`npImportApprove${++serial}`;chooseLabel.htmlFor=checkbox.id;chooseLabel.prepend(checkbox);row.append(chooseLabel);
    row.append(node('strong',label),node('p',description));
    for(const [key,entry] of Object.entries(value))input(row,key,key,entry,typeof entry==='number'?'number':'text');
    document.getElementById('npImportReview').append(row);return row;
  }
  function render(response) {
    document.getElementById('npImportReview').replaceChildren();draft=response;
    response.fields.forEach(field=>{
      const row=reviewRow('field',field.label,{value:field.value},`${field.status} · ${field.comparison||'기존 값 미확인'} · 현재 ${field.current??'미확인'} · ${field.key==='total_paid_amount'||field.key==='monthly_payout'?'선택 시 원본 금액 변경':'참고 메타데이터만 저장'}`);
      row.dataset.field=field.key;
      if(field.key.endsWith('months'))delete row.querySelector('[data-key=value]').dataset.koreanCurrency;
      if(field.conflict)row.append(node('p','자료 내 불일치: 수정·확인 후 선택하세요.'));
    });
    response.periods.forEach(period=>reviewRow('period','기간별 납부내역 · 연도 배분 확인 필요',{
      start:period.start,end:period.end,membership:period.membership,paid:period.paid,unpaid:period.unpaid,
      income_base:period.income_base,paid_months:period.paid_months,unpaid_months:period.unpaid_months},
      `${period.status} · 본인 부담액·사업장 내 지위 미확인. 여러 해 합계를 자동 배분하지 않습니다.`));
    response.monthly.forEach(month=>reviewRow('monthly',`${month.year}년 ${month.month}월 ${month.kind==='billed'?'사업장 고지액':'지역 납부액'}`,{
      year:month.year,month:month.month,kind:month.kind,amount:month.amount},`${month.status} · 실제 본인 부담액·공제 인정액으로 자동 반영하지 않습니다.`));
    response.annual.forEach(year=>reviewRow('annual',`${year.year}년 실제 납부액`,{year:year.year,deposit:year.deposit},
      `${year.status} · 기존 ${response.expected.yearly_contributions?.find(row=>String(row.year)===String(year.year))?.deposit??'미확인'} · 선택한 연도만 교체 (합산 없음)`));
    status(response.warnings.join(' · ')||'각 값을 확인·수정하고 적용할 항목만 선택하세요. 기본은 모두 미선택입니다.');
    document.getElementById('npImportApply').disabled=false;
    window.refreshDialogKoreanHints?.(document.getElementById('nationalPensionHistoryDialog'));
  }
  function safeDraft() {
    if(window.WealthNationalPension?.hasDraft()||JSON.stringify(readNationalPensionHistoryRows())!==JSON.stringify(nationalPensionHistoryOriginal)){
      throw new Error('저장하지 않은 납부 이력·분석이 있습니다. 먼저 저장하거나 취소·다시 불러와 주세요.');
    }
  }
  async function analyze() {
    if(busy||!item?.id)return;
    const file=document.getElementById('npImportFile').files[0];if(!file){status('파일을 선택하세요.');return;}
    if(file.size>10*1024*1024){status('10MB 이하 파일을 선택하세요.');return;}
    const token=generation;busy=true;document.getElementById('npImportFields').disabled=true;
    try {
      safeDraft();status('서버 내부에서 자료를 분석하고 있습니다.');
      const result=await api(`/api/insurance-accounts/${encodeURIComponent(item.id)}/national-pension-import/preview?document_type=${document.getElementById('npImportType').value}`,{
        method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});
      if(token===generation)render(result);
    }catch(error){if(token===generation)status(error.message);}
    finally{if(token===generation){busy=false;document.getElementById('npImportFields').disabled=false;}}
  }
  async function apply() {
    if(busy||!draft||!item?.id)return;
    const token=generation;
    try {
      safeDraft();
      const metadata={document_type:draft.document_type,fields:{},periods:[],monthly:[]},annual=[];
      let selected=0;
      document.querySelectorAll('#npImportReview .np-import-row').forEach(row=>{
        if(!row.querySelector('[data-approve]').checked)return;
        selected++;const value={};row.querySelectorAll('[data-key]').forEach(field=>{
          if(!field.checkValidity())throw new Error('입력값을 확인하세요.');
          const key=field.dataset.key, numeric=field.type==='number'||(['paid','unpaid','income_base','paid_months','unpaid_months','deposit'].includes(key));
          value[key]=numeric?(field.value===''?null:Number(field.value)):field.value;
        });
        if(row.dataset.kind==='field'){
          const key=row.dataset.field,raw=value.value;
          metadata.fields[key]=['query_date','issued_date','pension_start','pension_basis'].includes(key)?raw:raw===''?null:Number(raw);
        }else if(row.dataset.kind==='annual')annual.push(value);
        else metadata[row.dataset.kind==='period'?'periods':'monthly'].push(value);
      });
      if(!selected)throw new Error('적용할 항목을 선택하세요.');
      if(!confirm('선택한 값만 저장할까요? 선택한 누적납부액·월 연금액·기존 연도 금액은 교체됩니다.'))return;
      busy=true;document.getElementById('npImportFields').disabled=true;
      const result=await api(`/api/insurance-accounts/${encodeURIComponent(item.id)}/national-pension-import/apply`,{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fingerprint:draft.fingerprint,expected:draft.expected,metadata,annual})});
      if(token!==generation)return;
      // Compare a fresh canonical read with the acknowledged persisted snapshot.
      const fresh=await api(`/api/insurance-accounts/${encodeURIComponent(item.id)}/national-pension-analysis`);
      if(JSON.stringify(fresh.history)!==JSON.stringify(result.item.yearly_contributions||[])||fresh.total_paid_amount!==result.item.total_paid_amount||fresh.monthly_payout!==result.item.monthly_payout){
        throw new Error('저장 응답과 재조회가 다릅니다. 다시 불러와 확인해 주세요.');
      }
      draft=null;status('선택 항목을 저장하고 재조회로 확인했습니다.');toast('국민연금 자료를 반영했습니다.');
      closeDialog('nationalPensionHistoryDialog');await loadDashboard();
    }catch(error){if(token===generation){status(`${error.message} 검토 초안은 유지됩니다. 충돌 시 자료를 다시 분석하세요.`);toast(error.message,true);}}
    finally{if(token===generation){busy=false;document.getElementById('npImportFields').disabled=false;}}
  }
  function open(currentItem) {
    if(!currentItem?.id)return;
    if(busy){status('진행 중인 요청이 끝난 뒤 다시 시도하세요.');return;}
    item=currentItem;panel().hidden=false;panel().open=true;panel().scrollIntoView({block:'start'});
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const dialog=document.getElementById('nationalPensionHistoryDialog');
    const section=node('details');section.id='npImportPanel';section.hidden=true;section.append(node('summary','📄 국민연금 자료 가져오기 · PDF·사진'));
    const fields=node('fieldset');fields.id='npImportFields';section.append(fields);
    fields.append(node('p','외부 OCR 전송 없이 분석합니다. 실제 납부액·고지액·본인 부담액은 다릅니다. 선택한 항목만 저장합니다.'));
    const file=input(fields,'file','국민연금 PDF 또는 사진',null,'file');file.id='npImportFile';file.parentElement.htmlFor=file.id;file.accept='.pdf,.png,.jpg,.jpeg';
    const label=node('label','자료 종류'),select=node('select');select.id='npImportType';label.htmlFor=select.id;
    for(const [value,text] of Object.entries({auto:'내용으로 식별',history:'가입내역조회',certificate:'소득공제용 납부확인서'})){const option=node('option',text);option.value=value;select.append(option);}label.append(select);fields.append(label);
    fields.append(button('분석·미리보기',analyze));
    const review=node('div');review.id='npImportReview';fields.append(review);
    const applyButton=button('선택 항목 저장',apply);applyButton.id='npImportApply';applyButton.disabled=true;fields.append(applyButton);
    fields.append(button('검토 취소',()=>{draft=null;review.replaceChildren();applyButton.disabled=true;status('검토를 취소했습니다. 기존 데이터는 유지됩니다.');}));
    fields.append(button('확인한 연도 실제 납부액 추가',()=>{if(draft){reviewRow('annual','사용자 확인 실제 연도 납부액',{year:'',deposit:null},'기간 합계를 자동 배분하지 않습니다. 확인한 실제 연도 금액만 선택하세요.');}}));
    const notice=node('p');notice.id='npImportStatus';notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');section.append(notice);
    document.getElementById('npAnalysisPanel').before(section);
    const entry=button('📄 국민연금 자료 가져오기',()=>open(nationalPensionHistoryItem));section.before(entry);
    dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
    dialog.addEventListener('click',event=>{if(busy&&event.target.closest('.close,button[value=cancel],[data-np-action],[data-np-add]')){event.preventDefault();event.stopImmediatePropagation();status('요청이 진행 중입니다. 완료 후 다른 작업을 해 주세요.');}},true);
    document.getElementById('nationalPensionHistoryForm').addEventListener('submit',event=>{if(busy){event.preventDefault();event.stopImmediatePropagation();}},true);
    dialog.addEventListener('close',()=>{generation++;busy=false;item=null;draft=null;file.value='';review.replaceChildren();section.hidden=true;fields.disabled=false;applyButton.disabled=true;});
    const invalidate=()=>{draft=null;review.replaceChildren();applyButton.disabled=true;status('파일·종류가 변경되었습니다. 다시 분석해 주세요.');};
    file.addEventListener('change',invalidate);select.addEventListener('change',invalidate);
  });
  window.WealthPensionImport={open};
})();
