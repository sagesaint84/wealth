/* One native dialog per id; consumers own content, pending reads and actions. */
(() => {
  'use strict';
  function create({id, className = 'dialog', labelledBy} = {}) {
    const dialog = document.createElement('dialog');
    if (id !== undefined) dialog.id = id;
    dialog.className = className;
    if (labelledBy) dialog.setAttribute('aria-labelledby', labelledBy);
    return dialog;
  }
  window.WealthDialogShell = Object.freeze({create, ensure({id, labelledBy, onClose}) {
    let dialog = document.getElementById(id);
    if (!dialog) {
      dialog = create({id, labelledBy});
      document.body.append(dialog);
    }
    if (!dialog.dataset.wealthShell) {
      dialog.dataset.wealthShell = 'ready';
      dialog.addEventListener('close', () => onClose?.());
    }
    return dialog;
  }});
})();
