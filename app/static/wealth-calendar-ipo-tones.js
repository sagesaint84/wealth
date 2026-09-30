(() => {
  'use strict';

  const STYLE_ID = 'wealthCalendarIpoToneOverrides';
  if (document.getElementById(STYLE_ID)) return;

  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    .calendar-legend,
    .cal-badge {
      --calendar-subscription-bg: rgba(79, 70, 229, 0.20);
      --calendar-subscription-fg: #A5B4FC;
      --calendar-listing-bg: rgba(168, 85, 247, 0.20);
      --calendar-listing-fg: #D8B4FE;
    }
  `;
  document.head.appendChild(style);
})();
