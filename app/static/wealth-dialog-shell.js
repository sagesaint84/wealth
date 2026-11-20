/* One native dialog per id; consumers own content, pending reads and actions. */
(() => {
  'use strict';
  window.WealthDialogShell = Object.freeze({ensure({id, labelledBy, onClose}) {
    let dialog = document.getElementById(id);
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.id = id;
      dialog.className = 'dialog';
      if (labelledBy) dialog.setAttribute('aria-labelledby', labelledBy);
      document.body.append(dialog);
    }
    if (!dialog.dataset.wealthShell) {
      dialog.dataset.wealthShell = 'ready';
      dialog.addEventListener('close', () => onClose?.());
    }
    return dialog;
  }});
})();
