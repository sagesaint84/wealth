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
  let loaded=false, loading=null, active=null;
  async function load() {
    if(loading)return loading;
    loading=(async()=>{
      const response=await fetch('/api/color-preferences');
      if(!response.ok)throw new Error('색상 설정을 불러오지 못했습니다. 다시 시도하세요.');
      replace(await response.json());loaded=true;changed();
    })();
    try {await loading;} finally {loading=null;}
  }
  async function persist(group,key,color) {
    if(!groups.includes(group)||!validKey(key)||(color!==null&&!picker().isValidHexColor(color)))throw new Error('색상이 유효하지 않습니다.');
    const response=await fetch('/api/color-preferences',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({group,key,color:color===null?null:picker().normalizeHexColor(color)})});
    const data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'색상을 저장하지 못했습니다.');
    replace(data);drafts[group].delete(key);changed();
  }
  function openInlineEditor(anchor, adapter=null) {
    if(active?.saving)return;
    const {colorGroup:group,colorKey:key,colorLabel:label}=anchor.dataset;
    const currentColor=()=>adapter?adapter.getValue():resolve(group,key);
    const preview=color=>{if(adapter)adapter.onPreview(color);else{drafts[group].set(key,color);changed();}};
    const cancelPreview=()=>{if(adapter)adapter.onCancel();else{drafts[group].delete(key);changed();}};
    const rect=anchor.getBoundingClientRect();
    const scopeId=anchor.closest('[id]')?.id;
    const chart=anchor.closest('[data-bucket-chart]')?.dataset.bucketChart;
    const findAnchor=()=>anchor.isConnected?anchor:[...(document.getElementById(scopeId)||document).querySelectorAll('[data-inline-color],[data-bucket-color]')].find(n=>n.dataset.colorGroup===group&&n.dataset.colorKey===key&&(!chart||n.closest('[data-bucket-chart]')?.dataset.bucketChart===chart));
    active?.field.closeColorPicker();
    const editor={group,key,anchor,saving:false,field:null};active=editor;
    const field=picker().create({value:currentColor(),label:label+' 색상 변경',closeOnChange:false,canClose:()=>!editor.saving,
      anchorRect:()=>findAnchor()?.getBoundingClientRect()||rect,bottomInset:innerWidth<768?88:0,
      onChange:preview,
      onClose:focus=>{if(active===editor)active=null;field.remove();cancelPreview();
        queueMicrotask(()=>{if(!focus||active)return;bindControls();const target=findAnchor();
          target?.focus({preventScroll:true});});}
    });
    editor.field=field;field.classList.add('wealth-visualization-editor');
    field.ignoreOutsidePointer=target=>!!target.closest('[data-inline-color],[data-bucket-color],.classification-row,.sector-legend-item');
    field.dataset.colorGroup=group;field.dataset.colorKey=key;
    const panel=field.querySelector('.wealth-color-palette');
    const heading=document.createElement('strong');heading.className='wealth-inline-color-heading';heading.textContent=label+' 색상';panel.prepend(heading);
    const footer=document.createElement('span');footer.className='wealth-inline-color-footer';
    const status=document.createElement('span');status.className='wealth-inline-color-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    const save=document.createElement('button');save.type='button';save.className='button secondary compact';save.dataset.colorSave='';save.textContent='저장';
    const reset=document.createElement('button');reset.type='button';reset.className='button secondary compact';reset.dataset.colorReset='';reset.textContent='기본색 복원';
    reset.hidden=!!adapter&&!adapter.onReset;
    const cancel=document.createElement('button');cancel.type='button';cancel.className='button secondary compact';cancel.textContent='닫기';cancel.dataset.colorCancel='';
    footer.append(save,reset,cancel);panel.append(footer,status);
    const submit=async color=>{
      if(editor.saving)return;
      editor.saving=true;panel.inert=true;
      try {if(adapter)await (color===null?adapter.onReset():adapter.onSave(color));else await persist(group,key,color);editor.saving=false;field.closeColorPicker();}
      catch(error){cancelPreview();field.setColor(currentColor());status.textContent=error.message+' 저장된 색상으로 돌아갔습니다.';}
      finally {editor.saving=false;panel.inert=false;}
    };
    save.onclick=()=>submit(field.dataset.color);reset.onclick=()=>submit(null);cancel.onclick=()=>field.closeColorPicker();
    document.body.append(field);
    const trigger=field.querySelector('.wealth-color-trigger');trigger.click();trigger.tabIndex=-1;trigger.setAttribute('aria-hidden','true');
    if(!adapter&&!loaded){save.disabled=true;reset.disabled=true;load().then(()=>{if(active!==editor)return;field.closeColorPicker();bindControls();const replacement=findAnchor();if(replacement)openInlineEditor(replacement);})
      .catch(error=>{if(active!==editor)return;status.textContent=error.message;});}
  }
  function decorate(node,group,key,label) {
    node.dataset.inlineColor='';node.dataset.colorGroup=group;node.dataset.colorKey=key;node.dataset.colorLabel=label;
    node.classList.add('wealth-inline-color-control');node.setAttribute('aria-label',label+' 색상 변경');node.title=label+' 색상 변경';
    node.setAttribute('aria-haspopup','dialog');node.style.setProperty('--chosen-color',resolve(group,key));
    const expanded=active?.group===group&&active?.key===key;
    node.setAttribute('aria-expanded',String(expanded));
    const panel=expanded&&active.field?.querySelector('.wealth-color-palette');
    if(panel)node.setAttribute('aria-controls',panel.id);else node.removeAttribute('aria-controls');
  }
  function marker(parent,group,key,label,before=null) {
    let button=parent.querySelector(':scope > button[data-inline-color]');
    if(!button){button=document.createElement('button');button.type='button';parent.insertBefore(button,before);}
    decorate(button,group,key,label);return button;
  }
  function bindControls() {
    document.querySelectorAll('[data-bucket-color]').forEach(node=>{
      const expanded=active?.group===node.dataset.colorGroup&&active?.key===node.dataset.colorKey;
      node.setAttribute('aria-expanded',String(expanded));
      const panel=expanded&&active.field?.querySelector('.wealth-color-palette');
      if(panel)node.setAttribute('aria-controls',panel.id);else node.removeAttribute('aria-controls');
    });
    document.querySelectorAll('#calendarPanel .calendar-legend-item[data-color-key]').forEach(node=>{
      const key=node.dataset.colorKey,label=key==='dividend'?'배당·이자':calendar.find(row=>row[0]===key)?.[1];
      if(!label)return;decorate(node,groups[0],key,label);node.setAttribute('role','button');node.tabIndex=0;node.classList.add('wealth-inline-color-legend');
    });
    document.querySelectorAll('#homeAssetAllocationLegend > [data-color-key]').forEach(row=>{
      const item=catalog[groups[1]].get(row.dataset.colorKey);if(!item)return;
      marker(row,groups[1],item.key,item.label,row.firstChild);row.classList.add('wealth-inline-color-asset-legend');
    });
    document.querySelectorAll('#wealthMixLegend > [data-color-key]').forEach(row=>{
      const item=catalog[groups[1]].get(row.dataset.colorKey),name=row.firstElementChild?.firstElementChild;if(!item||!name)return;
      marker(name,groups[1],item.key,item.label,name.firstChild);name.classList.add('wealth-inline-color-label');
    });
    document.querySelectorAll('.classification-row[data-color-key],.sector-legend-item[data-color-key]').forEach(row=>{
      const item=catalog[groups[2]].get(row.dataset.colorKey);if(!item)return;
      const name=row.querySelector('.classification-title strong')||row.querySelector('strong');if(!name)return;
      row.querySelector('.sector-legend-color')?.remove();marker(name,groups[2],item.key,item.label,name.firstChild);
      row.tabIndex=0;row.setAttribute('role','button');
    });
  }
  api.load=load;api.persist=persist;api.openInlineEditor=openInlineEditor;
  Object.defineProperty(api,'loaded',{get:()=>loaded});
  function mount() {
    for(const [key,name,color] of calendar)register(groups[0],{key,name},color);
    let queued=false;
    const schedule=()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;bindControls();});};
    new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
    host.addEventListener('wealth:colors',schedule);
    document.addEventListener('click',event=>{
      const control=event.target.closest('[data-inline-color]');
      if(!control){
        const row=event.target.closest('.classification-row,.sector-legend-item'),editor=active;
        if(editor&&row&&!editor.field.contains(event.target))queueMicrotask(()=>{
          if(active!==editor||editor.saving)return;
          const focused=document.activeElement,key=row.dataset.colorKey,selector=row.matches('.classification-row')?'.classification-row':'.sector-legend-item';
          editor.field.closeColorPicker(false);
          queueMicrotask(()=>{if(active)return;bindControls();const target=focused.isConnected?focused:[...document.querySelectorAll(selector)].find(n=>n.dataset.colorKey===key);target?.focus({preventScroll:true});});
        });
        return;
      }
      event.preventDefault();event.stopImmediatePropagation();openInlineEditor(control);
    },true);
    document.addEventListener('keydown',event=>{
      const control=event.target.closest('[data-inline-color]');
      if(control&&['Enter',' '].includes(event.key)){event.preventDefault();event.stopImmediatePropagation();openInlineEditor(control);}
      else if(event.target.matches('.classification-row[data-sector-filter]')&&['Enter',' '].includes(event.key)){
        event.preventDefault();event.target.click();
      }
    },true);
    const retry=()=>{if(!loaded)load().catch(()=>{});};
    host.addEventListener('wealth:portfolio',retry);host.addEventListener('wealth:view',retry);
    host.addEventListener('hashchange',()=>{if(active&&!active.saving)active.field.closeColorPicker(false);});
    bindControls();retry();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
})(typeof window==='undefined'?null:window);
