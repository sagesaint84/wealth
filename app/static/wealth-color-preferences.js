/* Shared presentation colors. Financial producers retain their original values. */
(function (host) {
  'use strict';
  const picker = () => host ? host.WealthColorPicker : require('./wealth-color-picker.js');
  const groups = ['calendar_event_colors','asset_category_colors','stock_category_colors'];
  const calendar = [
    ['ipo_subscription','청약','#A5B4FC'],['ipo_listing','상장','#D8B4FE'],['profit','수익','#F87171'],
    ['loss','손실','#448AFF'],['dividend','배당','#FFE082'],['income','수입','#FFAB40'],['expense','지출','#4DF0FF']
  ];
  const categories = [
    ['real_estate','부동산'],['domestic_stock','국내주식'],['tenant_deposit','임차보증금'],
    ['domestic_foreign_etf','국내상장해외ETF'],['domestic_etf','국내ETF'],['foreign_etf','해외ETF'],
    ['cash','현금·예수금'],['insurance','보험'],['savings','예·적금'],['foreign_stock','해외주식'],
    ['us_index','미국 대표지수'],['semiconductor','반도체'],['financial_holding','금융지주'],['infrastructure','전력·인프라']
  ];
  const aliases = new Map(categories.map(([key,label]) => [label.replace(/\s/g,''),key]));
  const catalog = Object.fromEntries(groups.map(group => [group,new Map()]));
  let stored = Object.fromEntries(groups.map(group => [group,{}]));
  const drafts = Object.fromEntries(groups.map(group => [group,new Map()]));
  const validKey = key => typeof key==='string' && key.length<=512 && /^(?:[a-z][a-z0-9_]*|(?:id|name):[A-Za-z0-9_.!~*'()%:-]+)$/.test(key) && !['constructor','prototype'].includes(key);
  const keyFor = (group,item) => {
    if(!groups.includes(group)) throw new Error('Unknown color group');
    if(group===groups[0]) return typeof item==='string'?item:item.key;
    const id=item?.category_id ?? item?.classification_id ?? item?.sector_id ?? item?.key;
    if(id != null && String(id).trim()) return 'id:'+encodeURIComponent(String(id).normalize('NFC').trim());
    const label=String(typeof item==='string'?item:item?.name || 'unknown').normalize('NFC').trim();
    return aliases.get(label.replace(/\s/g,'')) || 'name:'+encodeURIComponent(label);
  };
  const fallback = key => {
    let hash=0; for(const char of key) hash=((hash*31)+char.codePointAt(0))>>>0;
    const colors=picker().getRecommendedPalette(); return colors[hash%colors.length];
  };
  const resolve = (group,key,defaultColor) => picker().getFallbackColor(
    drafts[group]?.get(key) ?? (Object.hasOwn(stored[group] || {},key)?stored[group][key]:null),
    picker().normalizeHexColor(defaultColor) || catalog[group]?.get(key)?.defaultColor || fallback(key));
  const register = (group,item,defaultColor) => {
    const key=keyFor(group,item); if(!validKey(key)) return picker().getFallbackColor(defaultColor);
    const label=typeof item==='string'?item:item.name || key;
    const previous=catalog[group].get(key);
    const resolvedDefault=previous?.defaultColor || picker().normalizeHexColor(defaultColor) || fallback(key);
    catalog[group].set(key,{key,label,defaultColor:resolvedDefault});
    if(host && (!previous || previous.label!==label)) host.dispatchEvent(new CustomEvent('wealth:color-catalog'));
    return resolve(group,key,resolvedDefault);
  };
  const replace = data => {
    stored=Object.fromEntries(groups.map(group => [group,Object.fromEntries(
      Object.entries(data?.[group] || {}).filter(([key,value])=>validKey(key) && picker().isValidHexColor(value)).map(([key,value])=>[key,picker().normalizeHexColor(value)])
    )]));
  };
  const api={groups,calendar,keyFor,validKey,resolve,register,replace,fallback,
    snapshot:()=>structuredClone(stored),entries:group=>[...catalog[group].values()]};
  if(typeof module==='object' && module.exports) module.exports=api;
  if(!host)return;
  host.WealthColorPreferences=api;
  const changed=()=>host.dispatchEvent(new CustomEvent('wealth:colors'));
  function mount() {
    const page=document.querySelector('[data-wealth-page="settings"]'); if(!page)return;
    const section=document.createElement('details');section.id='wealthColorSettings';section.className='wealth-color-settings';
    section.innerHTML='<summary>그래프·캘린더 색상</summary><p class="wealth-help">색상 선택 후 저장하세요. 금액과 분류는 변경되지 않습니다.</p><p class="wealth-help" role="status" id="wealthColorStatus"></p><button type="button" class="button secondary compact" id="wealthColorRetry">색상 설정 다시 불러오기</button>';
    page.append(section);
    const status=section.querySelector('[role=status]');let loaded=false,loading=null,saving=false;
    const fieldsets=new Map();
    for(const [group,label] of [[groups[0],'캘린더 이벤트'],[groups[1],'자산군'],[groups[2],'주식 포트폴리오 분류']]) {
      const details=document.createElement('details');details.dataset.colorGroup=group;
      const summary=document.createElement('summary');summary.textContent=label;
      const rows=document.createElement('div');rows.className='wealth-color-setting-rows';details.append(summary,rows);section.append(details);fieldsets.set(group,rows);
    }
    const strategy=document.createElement('p');strategy.className='wealth-help';strategy.innerHTML='전략 버킷 색상은 <a href="#invest">투자 화면의 전략 버킷</a>에서 설정합니다.';section.append(strategy);
    for(const [key,label,color] of calendar) register(groups[0],{key,name:label},color);
    function render() {
      for(const group of groups) for(const item of api.entries(group)) {
        const rows=fieldsets.get(group);let row=[...rows.children].find(r=>r.dataset.colorKey===item.key);
        if(!row) {
          row=document.createElement('div');row.className='wealth-color-setting-row';row.dataset.colorKey=item.key;
          const label=document.createElement('span');label.className='wealth-color-setting-label';
          const field=picker().create({value:resolve(group,item.key,item.defaultColor),label:item.label+' 색상 선택',onChange:color=>{drafts[group].set(item.key,color);status.textContent='선택한 색상을 저장하세요.';changed();}});
          const save=document.createElement('button');save.type='button';save.className='button secondary compact';save.textContent='저장';save.dataset.colorSave='';save.setAttribute('aria-label',item.label+' 색상 저장');
          const reset=document.createElement('button');reset.type='button';reset.className='button secondary compact';reset.textContent='기본색';reset.dataset.colorReset='';reset.setAttribute('aria-label',item.label+' 기본색 복원');
          const persist=async color=>{
            if(saving)return;
            saving=true;section.querySelectorAll('.wealth-color-setting-row').forEach(r=>r.inert=true);
            try {
              const res=await fetch('/api/color-preferences',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({group,key:item.key,color})});
              const data=await res.json();if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'색상을 저장하지 못했습니다.');
              replace(data);drafts[group].delete(item.key);row.remove();render();status.textContent='색상을 저장했습니다.';changed();
            }catch(error){status.textContent=error.message;}finally{saving=false;section.querySelectorAll('.wealth-color-setting-row').forEach(r=>r.inert=false);}
          };
          save.onclick=()=>persist(field.dataset.color);reset.onclick=()=>persist(null);
          row.append(label,field,save,reset);rows.append(row);
        }
        row.querySelector('.wealth-color-setting-label').textContent=item.label;
        row.inert=saving;
        row.querySelectorAll('button[data-color-save],button[data-color-reset]').forEach(b=>b.disabled=!loaded);
      }
    }
    async function load() {
      if(loading)return loading;
      loading=(async()=>{
        try {const res=await fetch('/api/color-preferences');if(!res.ok)throw new Error('색상 설정을 불러오지 못했습니다. 다시 시도하세요.');replace(await res.json());loaded=true;status.textContent='';
          fieldsets.forEach(rows=>rows.replaceChildren());render();changed();
        }catch(error){status.textContent=error.message;loaded=false;render();}finally{loading=null;}
      })();return loading;
    }
    section.querySelector('#wealthColorRetry').onclick=load;
    host.addEventListener('wealth:color-catalog',()=>queueMicrotask(render));
    host.addEventListener('wealth:portfolio',()=>{if(!loaded)load();});
    host.addEventListener('wealth:view',event=>{if(event.detail==='settings' && !loaded)load();});
    render();load();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})(typeof window==='undefined'?null:window);
