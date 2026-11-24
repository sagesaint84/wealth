/* Shared toast, busy button, and action feedback. */
(() => {
  'use strict';

  function create({ $ }) {
    let toastTimer;
    function toast(message, isError = false) {
      const element = $("#toast");
      if (!element) return;
      element.textContent = message;
      element.className = `toast show${isError ? " error" : ""}`;
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => { element.className = "toast"; }, 3600);
    }

    function busy(button, enabled) {
      if (!button) return;
      button.dataset.label ??= button.textContent;
      button.disabled = enabled;
      if (enabled) button.setAttribute("aria-busy", "true");
      else button.removeAttribute("aria-busy");
      button.textContent = enabled ? "처리 중…" : button.dataset.label;
    }

    async function action(button, request, after) {
      busy(button, true);
      try {
        const result = await request();
        toast(result.message || "반영했습니다.");
        if (after) await after();
      } catch (error) {
        toast(error.message, true);
      } finally {
        busy(button, false);
      }
    }

    return Object.freeze({ toast, busy, action });
  }

  function renderEmpty(container, message, { fullWidth = false } = {}) {
    const empty = container.ownerDocument.createElement("div");
    empty.className = "empty";
    empty.dataset.ui = "empty-state";
    if (fullWidth) empty.setAttribute("style", "grid-column:1/-1;");
    empty.textContent = message;
    container.replaceChildren(empty);
  }

  window.WealthOperationFeedback = Object.freeze({ create, renderEmpty });
})();
