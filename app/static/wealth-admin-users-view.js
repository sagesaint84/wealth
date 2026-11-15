(() => {
  "use strict";

  function create({ document, html }) {
    function getTables() {
      return ['adminMainUserListTbody', 'adminUserListTbody'].map(id => document.getElementById(id));
    }

    function writeTables(tables, markup) {
      for (const table of tables) {
        if (table) table.innerHTML = markup;
      }
    }

    function renderCounts({ total, pending, active }) {
      for (const [id, count] of [
        ['adminStatTotalUsers', total], ['adminStatActiveUsers', active], ['adminStatPendingUsers', pending],
      ]) {
        const element = document.getElementById(id);
        if (element) element.textContent = `${count}명`;
      }
    }

    function renderStatus(tables, message, isError = false) {
      const style = isError ? ' style="color:#ff718c;"' : '';
      writeTables(tables, `<tr><td colspan="6" class="admin-empty-cell"${style}>${html(message)}</td></tr>`);
    }

    function userRow({ id, username, role, roleClass, isSelf, pending, createdAt, notice, stored, disabled, canDelete }) {
      const arg = html(JSON.stringify(String(username ?? '')));
      const statusBadge = pending
        ? '<span class="admin-status-badge pending">⚠️ 비번 변경 필요</span>'
        : '<span class="admin-status-badge active">정상 활성</span>';
      return `
        <tr class="admin-row">
          <td class="admin-cell-user">
            👤 ${html(username)}
            ${isSelf ? '<span class="admin-self-badge">(나)</span>' : ''}
          </td>
          <td class="admin-cell-role">
            <span class="admin-role-badge ${roleClass}">
              ${html(role)}
            </span>
          </td>
          <td class="admin-cell-status">${statusBadge}</td>
          <td class="admin-cell-update">
            ${notice ?? `<label><input type="checkbox" data-update-user="${html(id)}" data-update-name="${html(username)}" data-update-stored="${stored}" aria-label="${html(username)} 시스템 업데이트 권한" ${stored ? 'checked' : ''} ${disabled ? 'disabled' : ''}> 업데이트·이미지 정리</label>`}
          </td>
          <td class="admin-cell-date">${html(createdAt)}</td>
          <td class="admin-cell-actions">
            <div style="display:inline-flex;gap:8px;">
              <button type="button" class="button secondary compact admin-btn-reset" onclick="handleAdminResetUserPw(${arg})" title="초기 4자리 비밀번호로 재설정">
                🔑 비번 초기화(4자리)
              </button>
              ${canDelete ? `<button type="button" class="button secondary compact admin-btn-delete" onclick="handleAdminDeleteUser(${arg})" title="계정 및 데이터 삭제">
                🗑️ 삭제
              </button>` : ''}
            </div>
          </td>
        </tr>
      `;
    }

    function renderUsers(tables, rows) {
      if (!rows.length) {
        renderStatus(tables, '등록된 사용자가 없습니다.');
        return;
      }
      writeTables(tables, rows.map(userRow).join(''));
    }

    return Object.freeze({ getTables, renderCounts, renderStatus, renderUsers });
  }

  window.WealthAdminUsersView = Object.freeze({ create });
})();
