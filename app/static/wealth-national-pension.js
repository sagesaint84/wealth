/* Optional pension metadata editor. All financial totals remain owned by Wealth. */
(() => {
  'use strict';
  const sourceOptions = {unknown:'미확인',agency:'공단 자료 확인',tax_return:'세금 신고 자료 확인',user:'사용자 직접 입력',estimate:'계산 추정'};
  const membershipOptions = {unknown:'미확인',workplace:'사업장가입자',regional:'지역가입자',voluntary:'임의가입자',continued:'임의계속가입자'};
  const roleOptions = {unknown:'미확인',employee:'근로자',sole_proprietor:'개인사업장 사용자',corporate_representative:'법인 대표'};
  const incomeOptions = {unknown:'미확인',employment:'근로소득',business:'사업소득',mixed:'혼합',other:'기타'};
  let state = null, item = null, generation = 0, serial = 0, busy = false, dirty = false;
  const root = () => document.getElementById('npAnalysisPanel');
  const fieldset = () => document.getElementById('npAnalysisFields');
  const notice = message => { document.getElementById('npAnalysisNotice').textContent = message; };
  const moneyText = value => value == null ? '미확인' : `₩${Number(value).toLocaleString('ko-KR', {maximumFractionDigits:2})}`;
  const element = (tag, text, className) => { const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node; };
  function field(parent, key, labelText, type, value, options = null) {
    const label=element('label',labelText), input=document.createElement(options?'select':'input');
    input.id=`npAnalysisField${++serial}`;input.dataset.key=key;label.htmlFor=input.id;
    if(options) Object.entries(options).forEach(([key,text])=>{const option=element('option',text);option.value=key;input.append(option);});
    else { input.type=type;if(type==='number'){input.step='any';if(!['premium_growth','inflation'].includes(key))input.min='0';input.placeholder='미확인';} }
    if(type==='money'){input.type='number';input.step='any';input.min='0';input.dataset.koreanCurrency='';input.placeholder='미확인';}
    if(key==='business_income')input.removeAttribute('min');
    if(key==='year'){input.min='1988';input.max=String(new Date().getFullYear());input.step='1';}
    if(['start_month','end_month'].includes(key)){input.min='1';input.max='12';input.step='1';}
    if(key==='paid_months'){input.max='12';input.step='1';}
    if(key==='end_age'){input.min='65';input.max='110';input.step='1';}
    if(['inflation','premium_growth'].includes(key)){input.min='-50';input.max='50';}
    if(type==='checkbox')input.checked=value===true;
    else input.value=value??(options?'unknown':'');
    label.append(input);parent.append(label);return input;
  }
  function row(kind, value = {}) {
    const container=document.getElementById(`npAnalysis-${kind}`), box=element('div',null,'np-analysis-row');box.dataset.row=kind;
    if(kind==='membership_periods') {
      field(box,'year','연도','number',value.year);
      field(box,'start_month','시작 월','number',value.start_month);
      field(box,'end_month','종료 월','number',value.end_month);
      field(box,'membership_type','가입유형','select',value.membership_type,membershipOptions);
      field(box,'workplace_role','사업장 내 지위','select',value.workplace_role,roleOptions);
    } else if(kind==='annual_details') {
      field(box,'year','연도','number',value.year);
      const amounts={agency_paid:'공단 실제 납부 보험료',personal_paid:'본인 실제 부담액',employer_paid:'사용자·사업장 부담액',unpaid:'미납 보험료',future_expected:'향후 예상 보험료(참고)',deductible_amount:'소득공제 인정액(참고)'};
      Object.entries(amounts).forEach(([key,text])=>field(box,key,text,'money',value[key]));
      field(box,'paid_months','실제 납부 월수','number',value.paid_months);
      field(box,'payment_date','본인 실제 부담 납부일(연간 총액 대표일)','date',value.payment_date);
      field(box,'source','자료 출처','select',value.source,sourceOptions);
      field(box,'verified','입력액 확인 완료','checkbox',value.verified);
    } else if(kind==='tax_years') {
      field(box,'year','과세연도','number',value.year);
      field(box,'income_type','소득 유형','select',value.income_type,incomeOptions);
      const amounts={gross_salary:'세전 총급여(참고)',business_revenue:'사업 매출액(참고)',business_income:'사업소득금액(참고)',expenses:'필요경비(참고)',taxable_before:'연금 공제 직전 과세표준',allowed_deduction:'실제 소득공제 인정액',actual_tax_saving:'신고에서 확인한 실제 절세액'};
      Object.entries(amounts).forEach(([key,text])=>field(box,key,text,'money',value[key]));
      field(box,'saving_date','신고 절세 혜택 확인일','date',value.saving_date);
      field(box,'source','자료 출처','select',value.source,sourceOptions);
      field(box,'verified','과세표준·공제 인정액 확인 완료','checkbox',value.verified);
    } else {
      field(box,'date','납부일','date',value.date);field(box,'amount','예상 본인 부담액','money',value.amount);
    }
    const remove=element('button','행 삭제','button secondary compact');remove.type='button';remove.setAttribute('aria-label',`${kind==='membership_periods'?'가입유형':kind==='tax_years'?'세금 정보':'부담액/일정'} 행 삭제`);
    remove.onclick=()=>{if(confirm('이 행을 삭제할까요? 저장 전까지 원본은 유지됩니다.')){box.remove();dirty=true;}};box.append(remove);container.append(box);
    if(window.refreshDialogKoreanHints)window.refreshDialogKoreanHints(document.getElementById('nationalPensionHistoryDialog'));
  }
  function readRows(kind) {
    return [...document.querySelectorAll(`#npAnalysis-${kind} [data-row]`)].map(box=>{
      const value={};box.querySelectorAll('[data-key]').forEach(input=>{
        const key=input.dataset.key;
        value[key]=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?null:Number(input.value)):(input.value||null);
      });return value;
    });
  }
  function read() {
    if([...fieldset().querySelectorAll('input')].some(input=>!input.checkValidity()))throw new Error('입력 금액·날짜·숫자의 형식을 확인해 주세요.');
    const scenario={};document.querySelectorAll('#npAnalysis-scenario [data-key]').forEach(input=>{
      const key=input.dataset.key;
      let value=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?null:Number(input.value)):(input.value||null);
      if(['inflation','premium_growth'].includes(key)&&value!=null)value/=100;
      scenario[key]=value;
    });
    const scheduleEnabled=scenario.schedule_enabled;delete scenario.schedule_enabled;
    scenario.future_schedule=scheduleEnabled?readRows('future_schedule'):null;
    return {membership_periods:readRows('membership_periods'),annual_details:readRows('annual_details'),tax_years:readRows('tax_years'),scenario};
  }
  function render(data) {
    for(const kind of ['membership_periods','annual_details','tax_years','future_schedule']){
      document.getElementById(`npAnalysis-${kind}`).replaceChildren();
      (kind==='future_schedule'?data.scenario?.future_schedule:data[kind])?.forEach(value=>row(kind,value));
    }
    const scenario=data.scenario||{}, box=document.getElementById('npAnalysis-scenario');box.replaceChildren();
    for(const [key,label] of Object.entries({birth_date:'생년월일(나이 시나리오 기준)',as_of_date:'분석·현재가치 기준일',pension_start:'예상 연금 개시일',premium_start:'향후 납부 시작일',premium_end:'향후 보험료 납부 종료일'}))field(box,key,label,'date',scenario[key]);
    field(box,'monthly_pension','공단 예상 월 연금액(시나리오 입력)','money',scenario.monthly_pension);
    field(box,'pension_value_basis','예상 연금액 기준','select',scenario.pension_value_basis,{unknown:'미확인',current_value:'분석 기준일 현재가치',future_nominal:'연금 개시 시점 명목금액'});
    field(box,'future_monthly_premium','향후 월 본인 부담 보험료(시작일 명목금액)','money',scenario.future_monthly_premium);
    field(box,'premium_growth','향후 보험료 연간 증가율 (%)','number',scenario.premium_growth==null?null:scenario.premium_growth*100);
    field(box,'inflation','연간 물가상승률 가정 (%)','number',scenario.inflation==null?null:scenario.inflation*100);
    field(box,'pension_indexed','수령액 물가연동 가정','checkbox',scenario.pension_indexed);
    field(box,'output_basis','전체 현금흐름 표시·IRR 금액 기준','select',scenario.output_basis||'nominal',{nominal:'명목금액 · 명목 IRR',real:'분석 기준일 실질금액 · 실질 IRR'});
    field(box,'end_age','추가 수령 종료 나이(65~110세)','number',scenario.end_age??90);
    field(box,'annual_date_method','연간 총액의 납부일 근사','select',scenario.annual_date_method||'exact_only',{exact_only:'입력한 납부 대표일만 사용',mid_year:'해당 연도 6월 30일로 근사',year_end:'해당 연도 12월 31일로 근사'});
    field(box,'past_history_complete','과거 본인 납부 기록의 완전성 확인','checkbox',scenario.past_history_complete);
    field(box,'assume_agency_as_personal','공단 총액을 본인 부담액으로 간주하는 가정 선택(개인 실제 IRR 아님)','checkbox',scenario.assume_agency_as_personal);
    field(box,'include_tax_savings','신고에서 확인한 실제 절세액 반영 IRR 별도 표시','checkbox',scenario.include_tax_savings);
    field(box,'schedule_enabled','사용자 지정 납부 일정 사용(빈 일정은 미래 납부 0원 가정)','checkbox',scenario.future_schedule!=null);
    document.getElementById('npAnalysisResults').replaceChildren();
    dirty=false;
  }
  async function open(currentItem) {
    item=currentItem;state=null;busy=true;const token=++generation;
    root().hidden=false;fieldset().disabled=true;notice('국민연금 분석 정보를 불러오는 중입니다.');
    try{
      const response=await api(`/api/insurance-accounts/${encodeURIComponent(currentItem.id)}/national-pension-analysis`);
      if(token!==generation)return;
      state=response;render(response.analysis||{});
      document.getElementById('npAnalysisReference').textContent=`원래 누적납입액 ${moneyText(response.total_paid_amount)} · 원래 월 연금액 ${moneyText(response.monthly_payout)} · 연금 개시 참고일 ${response.maturity_date||'미확인'}. 아래 입력은 원본을 수정하지 않습니다.`;
      notice('빈 금액은 미확인입니다. 가입유형으로 부담액·공제액을 자동 추정하지 않습니다.');
    }catch(error){if(token===generation)notice(error.message);}
    finally{if(token===generation){busy=false;fieldset().disabled=!state;}}
  }
  function showResults(result) {
    const box=document.getElementById('npAnalysisResults');box.replaceChildren();
    box.append(element('h4','세금 혜택 계산 결과','dialog-subheading'));
    result.tax_years.forEach(row=>{
      const basis={filing_confirmed:'세금 신고 자료 확인값',verified_input:'확인 입력값 · 신고 확정 여부 미확인',estimate:'추정 입력값 · 미확정',unknown:'미확인 입력값'}[row.input_basis]||'입력 확인 여부 미확인';
      const text=row.status==='estimated'?`${row.year}년 · 실제 인정액 ${moneyText(row.allowed_deduction)} · 적용액 ${moneyText(row.applied_deduction)} · 공제 전 ${moneyText(row.tax_before)} → 후 ${moneyText(row.tax_after)} · 예상 감소분 ${moneyText(row.estimated_reduction)}${row.capped?' (과세표준 한도 적용)':''}`:`${row.year}년 · 미산정: ${row.reason}`;
      box.append(element('p',`${basis} · ${text} · ${row.actual_tax_saving_confirmed?'신고 확인 절세액':'입력 절세액 · 신고 확인 미완료'} ${moneyText(row.actual_tax_saving)}`));
      const link=element('a','국세청 적용 연도별 세율표');link.href=row.source_url;link.target='_blank';link.rel='noopener noreferrer';box.append(link);box.append(element('p',row.notice));
    });
    const returns=result.returns;box.append(element('h4','수령 기간별 분석','dialog-subheading'));
    if(returns.status!=='scenario'){box.append(element('p',returns.reason));return;}
    box.append(element('p',`${returns.basis==='real'?'실질':'명목'} 금액 기준 · ${returns.personal_cost_assumed?'공단 총액을 개인 지출로 간주한 가정 시뮬레이션':'실제 본인 부담액 기준'} · ${returns.annual_dates_approximated?'연간 납부일 근사 적용':'입력 납부일 사용'}`));
    box.append(element('p',returns.notice));
    const irrText=irr=>irr?.status==='ok'?`${(irr.rate*100).toFixed(2)}%`:`미산정 (${irr?.reason||'선택하지 않음'})`;
    returns.scenarios.forEach(row=>{
      const card=element('article',null,'np-analysis-result');card.append(element('h4',`${row.age}세까지`));
      if(row.status!=='scenario')card.append(element('p',row.reason));
      else{
        card.append(element('p',`미래 보험료 ${moneyText(row.future_premiums)} · 수령 합계 ${moneyText(row.pension_receipts)}`));
        card.append(element('p',`미래 순현금흐름 ${moneyText(row.future_net_cash_flow)} · 과거 포함 순현금흐름 ${moneyText(row.net_cash_flow)}`));
        card.append(element('p',`납부원금 첫 회수 시점 ${row.payback_date||'미산정/회수 없음'} · 세전 IRR ${irrText(row.pre_tax_irr)}`));
        if(row.tax_benefit_irr)card.append(element('p',`신고 확인 절세액 반영 IRR ${irrText(row.tax_benefit_irr)}`));
        card.append(element('p',`수령 세후 IRR ${irrText(row.after_tax_irr)}`));
      }
      box.append(card);
    });
  }
  async function action(kind) {
    if(busy||!state)return;
    if(kind==='reset'&&!confirm('국민연금 분석 정보만 삭제할까요? 실제 납부 이력·상품 금액은 유지됩니다.'))return;
    const token=generation, target=item, previous=state;busy=true;
    try{
      const analysis=read();
      fieldset().disabled=true;
      const response=await api(`/api/insurance-accounts/${encodeURIComponent(target.id)}/national-pension-analysis${kind==='calculate'?'/calculate':''}`,{
        method:kind==='calculate'?'POST':kind==='reset'?'DELETE':'PUT',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({analysis,revision:previous.revision,expected_history:previous.history})});
      if(token!==generation)return;
      if(kind==='calculate'){showResults(response);notice('계산 결과는 미저장 분석입니다. 원본 금액이나 순자산에 반영하지 않습니다.');}
      else{state={...previous,...response};target.national_pension_analysis={...response.analysis,revision:response.revision};render(response.analysis);notice(kind==='reset'?'분석 정보만 삭제했습니다.':'분석 정보를 저장했습니다.');toast(document.getElementById('npAnalysisNotice').textContent);}
    }catch(error){if(token===generation){notice(`${error.message} 입력 초안은 유지됩니다. 충돌 시 다시 불러와 주세요.`);toast(error.message,true);}}
    finally{if(token===generation){busy=false;fieldset().disabled=false;}}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    document.querySelectorAll('[data-np-add]').forEach(button=>button.addEventListener('click',()=>{row(button.dataset.npAdd);dirty=true;}));
    fieldset()?.addEventListener('input',()=>{dirty=true;});
    fieldset()?.addEventListener('change',()=>{dirty=true;});
    document.querySelectorAll('[data-np-action]').forEach(button=>button.addEventListener('click',()=>{
      if(busy)return;
      const kind=button.dataset.npAction;
      if(kind==='reload'){if(confirm('분석 초안을 버리고 저장값을 다시 불러올까요?'))open(item);}
      else if(kind==='cancel'){if(state&&!busy){render(state.analysis||{});notice('분석 초안을 취소했습니다.');}}
      else action(kind);
    }));
    fieldset()?.addEventListener('keydown',event=>{
      if(event.key==='Enter'&&event.target.matches('input:not([type=checkbox])')){event.preventDefault();action('calculate');}
    });
    const dialog=document.getElementById('nationalPensionHistoryDialog');
    dialog?.addEventListener('cancel',event=>{
      if(busy&&state){event.preventDefault();notice('분석 요청이 진행 중입니다. 완료 후 닫아 주세요.');}
    });
    dialog?.addEventListener('click',event=>{
      if(busy&&state&&event.target.closest('.close, button[value=cancel]')){
        event.preventDefault();event.stopImmediatePropagation();notice('분석 요청이 진행 중입니다. 완료 후 닫아 주세요.');
      }
    },true);
    document.getElementById('nationalPensionHistoryForm')?.addEventListener('submit',event=>{
      if(busy&&state){event.preventDefault();event.stopImmediatePropagation();notice('분석 요청 완료 후 납부 이력을 저장하세요.');}
    },true);
    dialog?.addEventListener('close',()=>{generation++;busy=false;state=null;});
  });
  window.WealthNationalPension={open,hasDraft:()=>busy||dirty};
})();
