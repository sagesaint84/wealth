/* Shared palette control. Labels always use theme text, never the chosen color. */
(() => {
  'use strict';
  const palette = ['#A78BFA','#FB7185','#7DD3FC','#E11D48','#BE123C','#8B5CF6','#60A5FA','#1D4ED8',
    '#5FC5D9','#A8C95B','#7F78E8','#A886DB','#CF788B','#D19A66','#82966A','#5A9FE8'];
  const valid = color => typeof color === 'string' && /^#[0-9A-Fa-f]{6}$/.test(color);
  function create({value, label = '색상 선택', onChange}) {
    let color = valid(value) ? value.toUpperCase() : palette[0];
    const root = document.createElement('span'); root.className = 'wealth-color-picker';
    const button = document.createElement('button'); button.type = 'button';
    button.className = 'wealth-color-trigger'; button.setAttribute('aria-label', label);
    button.setAttribute('aria-haspopup', 'dialog'); button.setAttribute('aria-expanded', 'false');
    const panel = document.createElement('span'); panel.className = 'wealth-color-palette'; panel.hidden = true;
    panel.id = 'wealth-color-' + crypto.randomUUID(); panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', label); button.setAttribute('aria-controls', panel.id);
    const close = (focus = false) => { panel.hidden = true; button.setAttribute('aria-expanded', 'false'); if (focus) button.focus(); };
    const sync = () => {
      root.dataset.color = color; button.style.setProperty('--chosen-color', color);
      button.title = `${label}: ${color}`;
      panel.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.color === color)));
    };
    const choices = [...new Set([color, ...palette])];
    choices.forEach(choice => {
      const swatch = document.createElement('button'); swatch.type = 'button'; swatch.dataset.color = choice;
      swatch.style.setProperty('--chosen-color', choice); swatch.setAttribute('aria-label', choice);
      swatch.addEventListener('click', () => { color = choice; sync(); close(true); onChange?.(color); });
      panel.append(swatch);
    });
    button.addEventListener('click', () => {
      if (!panel.hidden) return close();
      document.querySelectorAll('.wealth-color-palette:not([hidden])').forEach(p => p.closest('.wealth-color-picker').querySelector('.wealth-color-trigger').click());
      panel.hidden = false; button.setAttribute('aria-expanded', 'true');
      const r = button.getBoundingClientRect();
      panel.style.left = Math.max(8, Math.min(r.left, innerWidth - 216)) + 'px';
      panel.style.top = Math.max(8, Math.min(r.bottom + 4, innerHeight - 200)) + 'px';
      panel.querySelector('[aria-pressed="true"]')?.focus();
    });
    root.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !panel.hidden) { e.preventDefault(); e.stopPropagation(); close(true); }
      if (e.target.parentNode === panel && ['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) {
        e.preventDefault(); const buttons = [...panel.children], index = buttons.indexOf(e.target);
        const delta = {ArrowLeft:-1, ArrowRight:1, ArrowUp:-4, ArrowDown:4}[e.key];
        buttons[(index + delta + buttons.length) % buttons.length].focus();
      }
    });
    root.append(button, panel); sync();
    return root;
  }
  document.addEventListener('pointerdown', e => document.querySelectorAll('.wealth-color-picker').forEach(root => {
    if (!root.contains(e.target) && root.querySelector('.wealth-color-trigger').getAttribute('aria-expanded') === 'true') root.querySelector('.wealth-color-trigger').click();
  }));
  window.WealthColorPicker = {create, palette: [...palette], valid};
})();
