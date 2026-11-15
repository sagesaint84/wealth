(() => {
  "use strict";

  function create({ html, number }) {
    function deleteButton(idx, className, style) {
      return `<button type="button" class="${className}" data-index="${idx}" style="${style}" title="삭제">✕</button>`;
    }

    function render(form, container, rows, { cumulativeSaved, cumulativeDeposit }) {
      if (!rows.length) {
        container.innerHTML = `
      <div style="font-size:11.5px;color:#94a3b8;padding:12px 8px;text-align:center;background:rgba(0,0,0,0.2);border-radius:6px;">
        등록된 연도별 납입 이력이 없습니다.<br>
        상단에서 <strong>연도와 납입금액</strong>을 입력 후 <strong>[➕ 연도 추가 / 반영]</strong>을 눌러주세요.
      </div>
    `;
      } else {
        container.innerHTML = rows.map(({ idx, yr, dep, isDed, rate, saved }) => `
        <div class="account-yearly-card" data-index="${idx}" data-year="${html(yr)}" style="display:flex;align-items:center;justify-content:space-between;padding:7px 10px;border-radius:6px;gap:8px;">
          <div style="display:flex;align-items:center;gap:8px;flex:1;flex-wrap:wrap;">
            <span style="font-weight:700;font-size:13px;color:#38bdf8;min-width:55px;">${html(yr)}년</span>
            <span class="account-yearly-dep" style="font-size:12.5px;font-weight:600;min-width:90px;">₩${number(dep, 0)}</span>
            <span style="font-size:11px;padding:2px 7px;border-radius:4px;background:${isDed ? 'rgba(56,189,248,0.15)' : 'rgba(52,211,153,0.15)'};color:${isDed ? '#38bdf8' : '#34d399'};font-weight:600;">
              ${isDed ? `🎯 공제 (${rate}%)` : '🌿 비공제'}
            </span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:12px;font-weight:700;color:${isDed ? '#4ade80' : '#94a3b8'};min-width:80px;text-align:right;">
              ${isDed ? `+₩${number(saved, 0)}` : '절세제외(₩0)'}
            </span>
            <button type="button" class="account-yearly-edit-btn" data-index="${idx}" style="border-radius:4px;padding:2px 7px;font-size:11px;cursor:pointer;" title="상단 입력창으로 불러와 수정">수정</button>
            ${deleteButton(idx, 'account-yearly-del-btn', 'border-radius:4px;padding:2px 7px;font-size:11px;cursor:pointer;')}
          </div>
        </div>
      `).join("");
      }

      const cumSavedEl = form?.querySelector("#accountCumulativeSavedText");
      if (cumSavedEl) cumSavedEl.textContent = `₩${number(cumulativeSaved, 0)}`;

      const cumDepEl = form?.querySelector("#accountCumulativeDepositText");
      if (cumDepEl) cumDepEl.textContent = `₩${number(cumulativeDeposit, 0)}`;
    }

    function renderYellowUmbrella(form, container, rows, cumulativeSaved) {
      if (!rows.length) {
        container.innerHTML = `<div style="font-size:11px;color:#94a3b8;padding:8px 4px;text-align:center;">등록된 연도별 납입 이력이 없습니다. [+ 연도 추가]를 눌러 과거 연도별 입금액을 기록해보세요.</div>`;
      } else {
        container.innerHTML = rows.map(({ idx, yr, dep, ded, saved }) => {
        return `
          <div class="yu-yearly-row" data-index="${idx}" style="display:flex;align-items:center;gap:6px;background:rgba(0,0,0,0.25);border:1px solid rgba(234,179,8,0.25);padding:5px 8px;border-radius:6px;">
            <input type="number" class="yu-yearly-year" value="${html(yr)}" placeholder="연도" style="width:68px;font-size:12px;padding:3px 6px;border-radius:4px;border:1px solid #334155;background:#0f172a;color:#f8fafc;" />
            <span style="font-size:11px;color:#94a3b8;">년</span>
            <input type="number" class="yu-yearly-deposit" value="${dep || ''}" placeholder="납입액" style="flex:1;min-width:70px;font-size:12px;padding:3px 6px;border-radius:4px;border:1px solid #334155;background:#0f172a;color:#f8fafc;" min="0" step="any" />
            <span style="font-size:11px;color:#94a3b8;">원</span>
            <select class="yu-yearly-deductible" style="width:78px;font-size:11.5px;padding:3px 4px;border-radius:4px;border:1px solid #334155;background:#0f172a;color:${ded ? '#facc15' : '#34d399'};font-weight:600;">
              <option value="true" ${ded ? "selected" : ""}>공제</option>
              <option value="false" ${!ded ? "selected" : ""}>비공제</option>
            </select>
            <span class="yu-yearly-saved-badge" style="min-width:85px;text-align:right;font-size:11.5px;font-weight:700;color:${ded ? '#4ade80' : '#34d399'};">
              ${ded ? `+₩${number(saved, 0)}` : '비공제(₩0)'}
            </span>
            ${deleteButton(idx, 'yu-yearly-del-btn', 'background:transparent;border:none;color:#f87171;cursor:pointer;font-size:14px;padding:0 4px;')}
          </div>
        `;
        }).join("");
      }
      const cumEl = form?.querySelector("#yuCumulativeSavedText");
      if (cumEl) cumEl.textContent = `₩${number(cumulativeSaved, 0)}`;
    }

    return Object.freeze({ render, renderYellowUmbrella });
  }
  window.WealthAccountYearlyView = Object.freeze({ create });
})();
