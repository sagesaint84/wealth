/* Shared opaque color model and picker. No surface-specific storage or financial writes. */
(function (host) {
  'use strict';
  const palette = ['#FF5A5F','#FF9F1C','#FFD60A','#2ECF73','#22C7B8','#4D96FF','#7C6CFF','#FF5FA2'];
  const normalizeHexColor = value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value.trim()) ? value.trim().toUpperCase() : null;
  const isValidHexColor = value => normalizeHexColor(value) !== null;
  const getFallbackColor = (value, fallback = palette[0]) => normalizeHexColor(value) || normalizeHexColor(fallback) || palette[0];
  const getRecommendedPalette = () => [...palette];
  const getPickerMode = width => Number.isFinite(width) && width >= 768 ? 'advanced' : 'palette';
  const clamp = (n, max = 1) => Math.max(0, Math.min(max, n));
  function hsvToHex(h, s, v) {
    if (![h,s,v].every(Number.isFinite)) return getFallbackColor(null);
    h = ((h % 360) + 360) % 360; s = clamp(s); v = clamp(v);
    const c = v * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c;
    const rgb = [[c,x,0],[x,c,0],[0,c,x],[0,x,c],[x,0,c],[c,0,x]][Math.floor(h / 60)];
    return '#' + rgb.map(n => Math.round((n + m) * 255).toString(16).padStart(2,'0')).join('').toUpperCase();
  }
  function hexToHsv(value) {
    const hex = getFallbackColor(value), rgb = [1,3,5].map(i => parseInt(hex.slice(i,i + 2),16) / 255);
    const max = Math.max(...rgb), min = Math.min(...rgb), d = max - min;
    let h = 0;
    if (d) { const i = rgb.indexOf(max); h = 60 * (i === 0 ? ((rgb[1]-rgb[2])/d + 6) % 6 : i === 1 ? (rgb[2]-rgb[0])/d + 2 : (rgb[0]-rgb[1])/d + 4); }
    return {h, s: max ? d / max : 0, v: max};
  }
  function renderColorPreview({value, label = '색상', className = ''} = {}) {
    const preview = document.createElement('span'); preview.className = `wealth-color-preview ${className}`.trim();
    preview.style.setProperty('--chosen-color', getFallbackColor(value));
    preview.setAttribute('role', 'img'); preview.setAttribute('aria-label', `${label}: ${getFallbackColor(value)}`);
    return preview;
  }
  function create({value, label = '색상 선택', onChange}) {
    let color = getFallbackColor(value), hsv = hexToHsv(color), draft = color;
    const root = document.createElement('span'); root.className = 'wealth-color-picker';
    const button = document.createElement('button'); button.type = 'button'; button.className = 'wealth-color-trigger';
    button.setAttribute('aria-label', label); button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-expanded', 'false');
    const panel = document.createElement('span'); panel.className = 'wealth-color-palette'; panel.hidden = true;
    panel.id = 'wealth-color-' + crypto.randomUUID(); panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', label);
    button.setAttribute('aria-controls', panel.id);
    const advanced = document.createElement('span'); advanced.className = 'wealth-color-advanced';
    advanced.innerHTML = `<span class="wealth-color-sv" tabindex="0" role="slider" aria-label="채도와 밝기" aria-valuemin="0" aria-valuemax="100"><i></i></span>
      <label class="wealth-color-hue-label">색상(Hue)<input class="wealth-color-hue" type="range" min="0" max="359" step="1" aria-label="색상(Hue)"></label>
      <label class="wealth-color-hex-label">HEX<input class="wealth-color-hex" type="text" maxlength="32" spellcheck="false" autocomplete="off" aria-label="HEX 색상" placeholder="#RRGGBB"></label>
      <span class="wealth-color-error" role="status" aria-live="polite"></span><button type="button" class="wealth-color-apply">색상 적용</button>`;
    const choices = document.createElement('span'); choices.className = 'wealth-color-choices'; choices.setAttribute('aria-label','추천 색상');
    const current = document.createElement('span'); current.className = 'wealth-color-current';
    panel.append(choices, current, advanced);
    const hexInput = advanced.querySelector('.wealth-color-hex'), hue = advanced.querySelector('.wealth-color-hue');
    const sv = advanced.querySelector('.wealth-color-sv'), marker = sv.querySelector('i'), apply = advanced.querySelector('.wealth-color-apply');
    const error = advanced.querySelector('.wealth-color-error');
    hexInput.setAttribute('aria-describedby', panel.id + '-error'); error.id = panel.id + '-error';
    const close = (focus = false) => { panel.hidden = true; button.setAttribute('aria-expanded','false'); if (focus) button.focus(); };
    const sync = () => {
      root.dataset.color = color; button.style.setProperty('--chosen-color',color); button.title = `${label}: ${color}`;
      choices.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed',String(b.dataset.color === color)));
    };
    const position = () => {
      if (panel.hidden) return;
      const r = button.getBoundingClientRect(), p = panel.getBoundingClientRect();
      panel.style.left = Math.max(8, Math.min(r.left, innerWidth - p.width - 8)) + 'px';
      panel.style.top = Math.max(8, Math.min(r.bottom + 4, innerHeight - p.height - 8)) + 'px';
    };
    root.repositionColorPicker = position;
    const updateDraft = (value, keepInput = false, hueHint = null) => {
      draft = normalizeHexColor(value); apply.disabled = !draft;
      hexInput.setAttribute('aria-invalid', String(!draft)); error.textContent = draft ? '' : '#RRGGBB 형식으로 입력해 주세요.';
      if (!draft) return;
      hsv = hexToHsv(draft); if (Number.isFinite(hueHint)) hsv.h = hueHint;
      hue.value = String(Math.round(hsv.h));
      if (!keepInput) hexInput.value = draft;
      current.replaceChildren(renderColorPreview({value:draft,label:'선택 색상'}),document.createTextNode(draft));
      sv.style.setProperty('--hue-color',hsvToHex(hsv.h,1,1)); marker.style.left = hsv.s * 100 + '%'; marker.style.top = (1-hsv.v) * 100 + '%';
      sv.setAttribute('aria-valuenow',String(Math.round(hsv.s * 100))); sv.setAttribute('aria-valuetext',`채도 ${Math.round(hsv.s * 100)}%, 밝기 ${Math.round(hsv.v * 100)}%`);
    };
    const commit = value => { const valid = normalizeHexColor(value); if (!valid) return; updateDraft(valid); color = valid; sync(); close(true); onChange?.(color); };
    palette.forEach(choice => {
      const swatch = document.createElement('button'); swatch.type = 'button'; swatch.dataset.color = choice;
      swatch.style.setProperty('--chosen-color',choice); swatch.setAttribute('aria-label',choice);
      swatch.addEventListener('click',() => commit(choice)); choices.append(swatch);
    });
    hexInput.addEventListener('input',() => updateDraft(hexInput.value,true));
    hexInput.addEventListener('keydown',e => { if(e.key === 'Enter') { e.preventDefault(); if(draft) commit(draft); } });
    apply.addEventListener('click',() => commit(draft));
    hue.addEventListener('input',() => { const h = Number(hue.value); updateDraft(hsvToHex(h,hsv.s,hsv.v),false,h); });
    const move = e => { const r = sv.getBoundingClientRect(), h = hsv.h; updateDraft(hsvToHex(h,clamp((e.clientX-r.left)/r.width),1-clamp((e.clientY-r.top)/r.height)),false,h); };
    sv.addEventListener('pointerdown',e => { if(e.button !== 0) return; e.preventDefault(); sv.focus(); sv.setPointerCapture(e.pointerId); move(e); });
    sv.addEventListener('pointermove',e => { if(sv.hasPointerCapture(e.pointerId)) move(e); });
    sv.addEventListener('pointerup',e => { if(sv.hasPointerCapture(e.pointerId)) sv.releasePointerCapture(e.pointerId); });
    sv.addEventListener('keydown',e => {
      if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) return;
      e.preventDefault(); const step = e.shiftKey ? .1 : .01, h = hsv.h;
      updateDraft(hsvToHex(h,hsv.s + (e.key==='ArrowRight'?step:e.key==='ArrowLeft'?-step:0),hsv.v + (e.key==='ArrowUp'?step:e.key==='ArrowDown'?-step:0)),false,h);
    });
    button.addEventListener('click',() => {
      if(!panel.hidden) return close();
      document.querySelectorAll('.wealth-color-palette:not([hidden])').forEach(p => p.closest('.wealth-color-picker').querySelector('.wealth-color-trigger').click());
      panel.dataset.mode = getPickerMode(innerWidth); advanced.hidden = panel.dataset.mode !== 'advanced';
      updateDraft(color); panel.hidden = false; button.setAttribute('aria-expanded','true'); position();
      (choices.querySelector('[aria-pressed="true"]') || choices.querySelector('button')).focus();
    });
    root.addEventListener('keydown',e => {
      if(e.key==='Escape' && !panel.hidden) { e.preventDefault(); e.stopPropagation(); close(true); }
      if(e.target.parentNode===choices && ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {
        e.preventDefault(); const buttons = [...choices.children], i = buttons.indexOf(e.target), delta = {ArrowLeft:-1,ArrowRight:1,ArrowUp:-4,ArrowDown:4}[e.key];
        buttons[(i+delta+buttons.length)%buttons.length].focus();
      }
      if(e.key==='Tab' && !panel.hidden) {
        const focusable = [...panel.querySelectorAll('button,input,[tabindex="0"]')].filter(n => !n.disabled && n.getClientRects().length);
        const first=focusable[0], last=focusable[focusable.length-1];
        if(e.shiftKey && e.target===first) { e.preventDefault(); last.focus(); } else if(!e.shiftKey && e.target===last) { e.preventDefault(); first.focus(); }
      }
    });
    root.append(button,panel); sync(); return root;
  }
  const api = {create,normalizeHexColor,isValidHexColor,getFallbackColor,getRecommendedPalette,renderColorPreview,getPickerMode,hsvToHex,hexToHsv,palette:getRecommendedPalette(),valid:isValidHexColor};
  if(typeof module==='object' && module.exports) module.exports = api;
  if(host) host.WealthColorPicker = api;
  if(typeof document !== 'undefined') {
    const closeAll = () => document.querySelectorAll('.wealth-color-trigger[aria-expanded="true"]').forEach(b => b.click());
    document.addEventListener('pointerdown',e => document.querySelectorAll('.wealth-color-picker').forEach(root => {
      if(!root.contains(e.target) && root.querySelector('.wealth-color-trigger').getAttribute('aria-expanded')==='true') root.querySelector('.wealth-color-trigger').click();
    }));
    window.addEventListener('resize',closeAll);
    window.addEventListener('scroll',e => {
      if(!e.target.closest?.('.wealth-color-palette')) document.querySelectorAll('.wealth-color-trigger[aria-expanded="true"]').forEach(b => b.closest('.wealth-color-picker').repositionColorPicker());
    },true);
  }
})(typeof window === 'undefined' ? null : window);
