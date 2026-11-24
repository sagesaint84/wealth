(() => {
  "use strict";

  function create({ window, document, api, html, toast, loadFamilyMembers, loadDashboard, finishStartupIncomeReads }) {
    // ── 21. 멀티유저 인증 세션 및 사용자 관리 (Admin) ───────────────────────────
    let currentUserProfile = null;
    const adminUsersView = window.WealthAdminUsersView.create({ document, html });

    async function initAuthSession() {
      try {
        const me = await api('/api/auth/me');
        currentUserProfile = me;

        // 1) 초기 비밀번호 상태이면 강제 변경 모달만 띄우고 모든 패널 가림
        if (me.must_change_password) {
          console.warn('[AUTH] 초기 비밀번호 강제 변경 상태 감지');
          const wrapper = document.getElementById('userAssetDashboardWrapper');
          if (wrapper) wrapper.style.display = 'none';
          const adminPanel = document.getElementById('adminMainPanel');
          if (adminPanel) adminPanel.style.display = 'none';

          const forceModal = document.getElementById('forcePasswordModal');
          if (forceModal) {
            if (!forceModal.open) {
              try { forceModal.showModal(); } catch (e) { forceModal.setAttribute('open', ''); }
            }
            forceModal.addEventListener('cancel', (e) => e.preventDefault()); // ESC 닫기 방지
          }
          return false; // 비밀번호 변경 전에는 자산/관리 데이터 로드 중단
        }

        // 2) 정상 계정이면 역할에 따라 화면 분기
        await applyUserRoleView(me);
        return true;
      } catch {
        console.error('[AUTH] 세션 정보 확인 실패');
        return false;
      }
    }

    async function applyUserRoleView(me) {
      if (!me || me.must_change_password) return;
      const isAdminUser = (me.username === 'admin');
      window.dispatchEvent(new CustomEvent('wealth:role', { detail: { isAdminUser } }));

      // 상단 사용자명 표시
      const unameEl = document.getElementById('topbarUsername');
      if (unameEl) {
        unameEl.textContent = isAdminUser ? 'admin (시스템 관리자)' : me.username;
      }

      // 상단 타이틀 커스텀
      const brandTitle = document.querySelector('.topbar .title h1');
      const brandEyebrow = document.querySelector('.topbar .title p');
      if (brandTitle) {
        brandTitle.textContent = isAdminUser ? '👑 시스템 관리자 - 사용자 계정 관리' : '자산';
      }
      if (brandEyebrow) {
        brandEyebrow.textContent = isAdminUser ? 'SYSTEM ADMIN CONSOLE' : 'Wealth';
      }

      // 관리자 팝업 버튼: admin 계정(username === 'admin')으로 접속 시에만 노출 (sagesaint 등 계정은 완전 숨김)
      const adminBtn = document.getElementById('adminUserBtn');
      if (adminBtn) {
        const showAdminBtn = Boolean(me && me.username === 'admin');
        adminBtn.style.setProperty('display', showAdminBtn ? 'inline-flex' : 'none', 'important');
      }

      // PWA 설치 버튼은 admin일 때 숨김
      const pwaBtn = document.getElementById('pwaInstallButton');
      if (pwaBtn && isAdminUser) {
        pwaBtn.style.display = 'none';
      }

      const assetWrapper = document.getElementById('userAssetDashboardWrapper');
      const adminMainPanel = document.getElementById('adminMainPanel');

      if (isAdminUser) {
        // 👑 admin 계정: 자산 관리 화면은 완전히 제외하고, 사용자 관리 화면만 노출!
        if (assetWrapper) assetWrapper.style.display = 'none';
        if (adminMainPanel) adminMainPanel.style.display = 'block';

        // 관리자 사용자 목록 및 통계 로드
        await refreshAdminUserList();
      } else {
        // 👤 일반 사용자/마스터 사용자(sagesaint 등): 자산 관리 화면 정상 노출
        if (adminMainPanel) adminMainPanel.style.display = 'none';
        if (assetWrapper) assetWrapper.style.display = '';

        // 일반 자산 데이터 로드
        await loadAssetDataForUser();
      }
    }

    async function loadAssetDataForUser() {
      if (currentUserProfile?.must_change_password || currentUserProfile?.username === 'admin') return;
      if (loadAssetDataForUser.pending) return loadAssetDataForUser.pending;
      const pending = (async () => {
        let priceRefreshSucceeded = false;
        const familyMembersReady = loadFamilyMembers().catch(() => {});

        // 접속 시 먼저 최신 시세/환율을 반영한다. 성공한 경우에만 당일 자동 스냅샷을 기록한다.
        try {
          await api("/api/refresh-prices", { method: "POST" });
          priceRefreshSucceeded = true;
        } catch (e) {
          toast(e.message || "접속 시 시세 갱신에 실패해 자동 기록을 건너뜁니다.", true);
        }
        try {
          await loadDashboard(priceRefreshSucceeded);
        } catch (e) {
          toast(e.message || "대시보드를 불러오지 못했습니다.", true);
        }

        if (priceRefreshSucceeded) {
          try {
            await api("/api/planning/snapshot-all", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ source: "auto" }),
            });
            window.dispatchEvent(new CustomEvent('wealth:planning-refresh'));
          } catch (e) {
            toast(e.message || "접속 시 순자산 자동 기록에 실패했습니다.", true);
          }
        }

        globalThis.WealthStartup?.ready();
        window.dispatchEvent(new CustomEvent('wealth:assets-ready'));
        globalThis.WealthStartup?.count('supplementary');
        // No reads assuming refreshed prices start before both recording steps settle.
        loadAssetDataForUser.supplementary = Promise.allSettled([
          familyMembersReady,
          globalThis.WealthStartup?.loadVisible(),
        ]).finally(finishStartupIncomeReads);
      })();
      loadAssetDataForUser.pending = pending;
      try { await pending; }
      finally { if (loadAssetDataForUser.pending === pending) loadAssetDataForUser.pending = null; }
    }

    async function handleForcePasswordSubmit(e) {
      if (e) e.preventDefault();
      const p1 = document.getElementById('forceNewPassword')?.value || '';
      const p2 = document.getElementById('forceNewPasswordConfirm')?.value || '';
      if (p1.length < 4) {
        alert('비밀번호는 최소 4자 이상이어야 합니다.');
        return;
      }
      if (p1 !== p2) {
        alert('비밀번호 확인이 일치하지 않습니다.');
        return;
      }
      try {
        await api('/api/auth/force-change-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_password: p1 })
        });
        toast('새 비밀번호가 설정되었습니다! 화면으로 접속합니다.');
        const modal = document.getElementById('forcePasswordModal');
        if (modal) {
          try { modal.close(); } catch (e) { modal.removeAttribute('open'); }
        }
        // Re-read server capability after the pending-password state is cleared.
        await initAuthSession();
      } catch (err) {
        alert(err.message || '비밀번호 변경에 실패했습니다.');
      }
    }

    function openChangePasswordModal() {
      const modal = document.getElementById('changePasswordModal');
      if (modal) {
        document.getElementById('changeOldPassword').value = '';
        document.getElementById('changeNewPassword').value = '';
        document.getElementById('changeNewPasswordConfirm').value = '';
        modal.showModal();
      }
    }

    async function handleChangePasswordSubmit(e) {
      if (e) e.preventDefault();
      const oldP = document.getElementById('changeOldPassword')?.value || '';
      const p1 = document.getElementById('changeNewPassword')?.value || '';
      const p2 = document.getElementById('changeNewPasswordConfirm')?.value || '';
      if (p1.length < 4) {
        alert('새 비밀번호는 최소 4자 이상이어야 합니다.');
        return;
      }
      if (p1 !== p2) {
        alert('새 비밀번호가 일치하지 않습니다.');
        return;
      }
      try {
        await api('/api/auth/change-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ old_password: oldP, new_password: p1 })
        });
        toast('비밀번호가 성공적으로 변경되었습니다.');
        const modal = document.getElementById('changePasswordModal');
        if (modal) modal.close();
      } catch (err) {
        alert(err.message || '비밀번호 변경 실패');
      }
    }

    async function openAdminUsersModal() {
      const modal = document.getElementById('adminUsersModal');
      if (!modal) return;
      modal.showModal();
      await refreshAdminUserList();
    }

    async function refreshAdminUserList() {
      if (currentUserProfile?.must_change_password) return;
      const tables = adminUsersView.getTables();
      adminUsersView.renderStatus(tables, '불러오는 중...');
      try {
        const res = await api('/api/admin/users');
        const users = res.users || [];
        const total = users.length;
        const pending = users.filter(u => u.must_change_password).length;
        adminUsersView.renderCounts({ total, pending, active: total - pending });

        adminUsersView.renderUsers(tables, users.map(u => {
          const isAdminRoot = u.username === 'admin';
          const stored = u.permissions?.system_update === true;
          return {
            id: u.id, username: u.username, role: u.role,
            roleClass: u.role === 'admin' ? 'admin' : 'user',
            isSelf: currentUserProfile && currentUserProfile.username === u.username,
            pending: u.must_change_password,
            createdAt: u.created_at ? u.created_at.substring(0, 10) : '-',
            notice: isAdminRoot ? '관리자 기본 권한' : !u.id ? '식별자 확인 필요' : null,
            stored, disabled: (u.must_change_password || u.active === false) && !stored,
            canDelete: !isAdminRoot,
          };
        }));
      } catch (err) {
        console.error('[ADMIN] 사용자 목록 로드 실패');
        adminUsersView.renderStatus(tables, `목록 로드 실패: ${err.message || String(err)}`, true);
      }
    }

    async function handleAdminCreateUser(e) {
      if (e) e.preventDefault();
      // 메인 화면 폼 또는 다이얼로그 폼에서 입력값 읽기
      const uname = (document.getElementById('adminMainNewUsername')?.value || document.getElementById('adminNewUsername')?.value || '').trim();
      const pw = (document.getElementById('adminMainNewPassword')?.value || document.getElementById('adminNewPassword')?.value || '').trim();

      if (!uname) {
        alert('사용자 아이디를 입력하세요.');
        return;
      }
      if (pw.length !== 4) {
        alert('초기 비밀번호는 정확히 4자리여야 합니다.');
        return;
      }
      try {
        const res = await api('/api/admin/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: uname, initial_password: pw })
        });
        toast(res.message || '사용자가 등록되었습니다.');

        // 폼 초기화
        if (document.getElementById('adminMainNewUsername')) document.getElementById('adminMainNewUsername').value = '';
        if (document.getElementById('adminMainNewPassword')) document.getElementById('adminMainNewPassword').value = '';
        if (document.getElementById('adminNewUsername')) document.getElementById('adminNewUsername').value = '';
        if (document.getElementById('adminNewPassword')) document.getElementById('adminNewPassword').value = '';

        await refreshAdminUserList();
      } catch (err) {
        alert(err.message || '사용자 생성 실패');
      }
    }

    async function handleAdminResetUserPw(username) {
      const newPw = prompt(`[${username}] 계정의 초기 비밀번호(4자리)를 입력하세요:`, '0000');
      if (newPw === null) return;
      const cleanPw = newPw.trim();
      if (cleanPw.length !== 4) {
        alert('초기화 비밀번호는 정확히 4자리여야 합니다.');
        return;
      }
      try {
        const res = await api(`/api/admin/users/${encodeURIComponent(username)}/reset-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_password: cleanPw })
        });
        toast(res.message || '비밀번호가 초기화되었습니다.');
        await refreshAdminUserList();
      } catch (err) {
        alert(err.message || '초기화 실패');
      }
    }

    async function handleAdminDeleteUser(username) {
      if (!confirm(`정말로 사용자 '${username}' 계정과 해당 자산 데이터를 모두 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;
      try {
        const res = await api(`/api/admin/users/${encodeURIComponent(username)}`, {
          method: 'DELETE'
        });
        toast(res.message || '사용자 계정이 삭제되었습니다.');
        await refreshAdminUserList();
      } catch (err) {
        alert(err.message || '삭제 실패');
      }
    }

    return {
      getCurrentUserProfile: () => currentUserProfile,
      actions: {
        initAuthSession,
        applyUserRoleView,
        loadAssetDataForUser,
        handleForcePasswordSubmit,
        openChangePasswordModal,
        handleChangePasswordSubmit,
        openAdminUsersModal,
        refreshAdminUserList,
        handleAdminCreateUser,
        handleAdminResetUserPw,
        handleAdminDeleteUser,
      },
    };
  }

  window.WealthUserAccessFeatureController = { create };
})();
