(() => {
  "use strict";

  function create({ document, html }) {
    function showBrokerMessage(id, message, type) {
      const el = document.getElementById(id);
      if (!el) return;
      el.className = `toss-wts-message ${type}`;
      el.textContent = message;
      el.style.display = 'block';
    }

    function brokerTableEmptyRow(colspan, message) {
      return `<tr><td colspan="${colspan}" class="toss-wts-empty">${html(message)}</td></tr>`;
    }

    function brokerTableLoadingRow(colspan, message) {
      return `<tr><td colspan="${colspan}" class="toss-wts-loading">⏳ ${html(message)}</td></tr>`;
    }

    function brokerImportPreviewRow({
      feedIndex, itemIndex, itemName, itemNameSizeClass, itemDate, isIpo,
      currentFee, providerPnl, finalPnl, memo, feeText,
    }) {
      return `<div class="broker-import-modal-row" data-feed-index="${feedIndex}" data-item-index="${itemIndex}" style="margin-top:8px;padding:8px;border:1px solid var(--border);border-radius:8px;">` +
        `<div class="broker-import-item-header">` +
          `<div class="broker-import-item-title">` +
            `<strong class="broker-import-item-name ${itemNameSizeClass}">${html(itemName)}</strong>` +
            `${itemDate ? `<span class="muted" style="font-size:12px;margin-left:6px;">(${html(itemDate)})</span>` : ''}` +
          `</div>` +
          `<div class="broker-import-item-controls">` +
            `<label style="font-size:12px;">유형: ` +
              `<select class="modal-broker-stock-type toss-wts-select" data-feed-index="${feedIndex}" data-item-index="${itemIndex}" style="padding:2px 6px;font-size:12px;">` +
                `<option value="general" ${isIpo ? '' : 'selected'}>일반주식</option>` +
                `<option value="ipo" ${isIpo ? 'selected' : ''}>공모주</option>` +
              `</select>` +
            `</label>` +
            `<label class="modal-broker-fee-wrap" data-item-index="${itemIndex}" style="font-size:12px;${isIpo ? 'display:inline-flex;align-items:center;gap:4px;' : 'display:none;'}">공모청약비: ` +
              `<input class="modal-broker-ipo-fee toss-wts-input" data-feed-index="${feedIndex}" data-item-index="${itemIndex}" type="number" min="0" step="1" value="${html(String(currentFee))}" style="width:75px;padding:2px 6px;font-size:12px;" required> 원` +
            `</label>` +
          `</div>` +
        `</div>` +
        `<div class="modal-broker-effect" style="margin-top:6px;font-size:12px;color:var(--text-muted);">` +
          (isIpo ? (
            `유형: <strong>공모주</strong> · 공모청약비 ${html(feeText)}원 · ` +
            `제공사 손익 <strong class="broker-import-pnl ${providerPnl.toneClass}">${html(providerPnl.text)}</strong> · 최종 Wealth 손익 <strong class="broker-import-pnl ${finalPnl.toneClass}">${html(finalPnl.text)}</strong>` +
            `${memo ? `<br><span class="muted">메모: ${html(memo)}</span>` : ''}`
          ) : (
            `유형: <strong>일반주식</strong> · 최종 Wealth 손익 <strong class="broker-import-pnl ${finalPnl.toneClass}">${html(finalPnl.text)}</strong>` +
            `${memo ? `<br><span class="muted">메모: ${html(memo)}</span>` : ''}`
          )) +
        `</div>` +
      `</div>`;
    }

    return Object.freeze({ brokerImportPreviewRow, showBrokerMessage, brokerTableEmptyRow, brokerTableLoadingRow });
  }
  window.WealthBrokerUI = Object.freeze({ create });
})();
