/* Browser-local market card display preferences. No market data or authentication policy. */
(() => {
  'use strict';

  function create({ getCurrentUserProfile, renderMarkets, document, window }) {
const marketCardKey = item => String(item.symbol || item.label);
function marketPreferenceKey() {
  const profile=getCurrentUserProfile();
  const id=profile?.id || profile?.username;
  return id ? `wealth.market-cards.v1:${encodeURIComponent(String(id))}` : null;
}
function hiddenMarketCards() {
  try {const value=JSON.parse(localStorage.getItem(marketPreferenceKey()) || '[]');
    return new Set(Array.isArray(value) ? value.filter(v=>typeof v==='string'&&v.length<=100).slice(0,64) : []);
  } catch (_) {return new Set();}
}
function marketCardSettings(items) {
  let button=document.getElementById('marketCardSettings');
  if(!button){
    button=document.createElement('button');button.id='marketCardSettings';button.type='button';button.className='button secondary';button.textContent='표시 설정';button.setAttribute('aria-haspopup','dialog');
    document.querySelector('#marketPanel .panel-head')?.append(button);
    const dialog=document.createElement('dialog');dialog.id='marketCardDialog';dialog.className='dialog';dialog.setAttribute('aria-labelledby','marketCardDialogTitle');
    document.body.append(dialog);
    button.addEventListener('click',()=>{
      const hidden=hiddenMarketCards(),identity=marketPreferenceKey();
      dialog.innerHTML='<form><div class="dialog-head"><h2 id="marketCardDialogTitle">표시할 지수 선택</h2></div><div class="market-card-choices"></div><p role="status"></p><div class="dialog-actions"><button type="button" class="button secondary">취소</button><button type="submit" class="button primary">저장</button></div></form>';
      for(const item of button.marketItems){
        const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.value=item.key;check.checked=!hidden.has(item.key);const title=document.createElement('span');title.textContent=item.label;label.append(check,title);dialog.querySelector('.market-card-choices').append(label);
      }
      dialog.querySelector('[type=button]').onclick=()=>dialog.close();
      dialog.querySelector('form').onsubmit=e=>{
        e.preventDefault();if(!identity||identity!==marketPreferenceKey()){dialog.close();return;}
        const next=new Set(hiddenMarketCards());
        dialog.querySelectorAll('input').forEach(n=>n.checked?next.delete(n.value):next.add(n.value));
        try{localStorage.setItem(identity,JSON.stringify([...next]));dialog.close();renderMarkets();}
        catch(_){dialog.querySelector('[role=status]').textContent='이 브라우저에 설정을 저장하지 못했습니다.';}
      };
      dialog.showModal();
    });
    window.addEventListener('wealth:role',()=>{dialog.close();renderMarkets();});
  }
  button.marketItems=items;button.disabled=!marketPreferenceKey();
}

    return Object.freeze({ marketCardKey, marketPreferenceKey, hiddenMarketCards, marketCardSettings });
  }

  window.WealthMarketCardPreferences = Object.freeze({ create });
})();
