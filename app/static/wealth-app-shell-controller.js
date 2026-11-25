(() => {
  "use strict";

  function create({ window, document, updateKoreanCurrencyHint, loadLedger }) {
    let deferredInstallPrompt = null;
    let currentModule = "wealth"; // "wealth" | "ledger"

    function bindDialogCancel() {
      // 다이얼로그 닫기 버튼 공통 처리
      document.addEventListener("click", (event) => {
        const button = event.target.closest(".dialog .close, .dialog .dialog-actions button[value='cancel']");
        if (!button) return;
        event.preventDefault();
        button.closest("dialog")?.close();
      });
    }

    function bindMoneyHints() {
      document.addEventListener('input', (e) => {
        if (e.target && e.target.hasAttribute('data-korean-currency')) {
          updateKoreanCurrencyHint(e.target);
        }
      });
    }

    function closeDialog(idOrEl) {
      try {
        const el = typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
        if (!el) return;
        if (typeof el.close === 'function') {
          el.close();
        } else {
          el.removeAttribute('open');
          el.style.display = 'none';
        }
      } catch (err) {
        console.error('[DIALOG] closeDialog error:', err);
      }
    }

    function bindDialogControls() {
      // 다이얼로그 닫기 버튼 위임 (※ 팝업 외 배경 클릭 시에는 닫히지 않도록 보호)
      document.addEventListener('click', (e) => {
        // 닫기 버튼 클릭 처리 (.close, [data-close-dialog], .dialog-close-btn, [aria-label="닫기"] 등)
        const closeBtn = e.target.closest('[data-close-dialog], .close, .dialog-close-btn, [aria-label="닫기"]');
        if (closeBtn) {
          const targetId = closeBtn.getAttribute('data-close-dialog');
          if (targetId) {
            closeDialog(targetId);
            return;
          }
          const dialog = closeBtn.closest('dialog');
          if (dialog && dialog.id !== 'forcePasswordModal') {
            closeDialog(dialog);
            return;
          }
        }
      });

      // 다이얼로그 내부 입력창에서 Enter 키 누를 때 화면이 닫히지 않고 [저장] 버튼 자동 실행
      document.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        if (e.isComposing) return; // 한글 조합 중 엔터는 무시

        // textarea 내에서의 줄바꿈은 허용
        if (e.target && e.target.tagName === 'TEXTAREA') return;

        const dialog = e.target?.closest?.('dialog');
        if (!dialog || !dialog.open) return;

        // input, select 등 다이얼로그 폼 입력 요소에서 Enter를 친 경우
        if (e.target && ['INPUT', 'SELECT'].includes(e.target.tagName)) {
          e.preventDefault(); // 기본 submit 또는 dialog 자동 닫기 방지

          // 해당 다이얼로그 안의 [저장] 버튼 우선 탐색 후 클릭
          const saveBtn = dialog.querySelector('#accountAddSaveBtn, button[type="submit"]:not([value="cancel"]), button.primary:not([value="cancel"])');
          if (saveBtn) {
            saveBtn.click();
          } else {
            const form = dialog.querySelector('form');
            if (form) {
              if (typeof form.requestSubmit === 'function') form.requestSubmit();
              else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
            }
          }
        }
      });
    }

    function bindPwa() {
      window.addEventListener("beforeinstallprompt", (e) => {
        e.preventDefault();
        deferredInstallPrompt = e;
        console.log("[PWA] beforeinstallprompt event fired! PWA is installable.");
        const btn = document.getElementById("pwaInstallButton");
        if (btn) btn.style.display = "inline-flex";
      });

      window.addEventListener("appinstalled", () => {
        deferredInstallPrompt = null;
        console.log("[PWA] PWA was installed successfully.");
        const btn = document.getElementById("pwaInstallButton");
        if (btn) btn.style.display = "none";
      });

      if ("serviceWorker" in window.navigator) {
        window.addEventListener("load", () => {
          window.navigator.serviceWorker.register("/sw.js", { scope: "/" })
            .then((reg) => {
              reg.update();
              console.log("[PWA] Service Worker registered with scope:", reg.scope);
            })
            .catch((err) => console.error("[PWA] Service Worker registration failed:", err));
        });
      }
    }

    function triggerPwaInstall() {
      if (deferredInstallPrompt) {
        deferredInstallPrompt.prompt();
        deferredInstallPrompt.userChoice.then((choiceResult) => {
          if (choiceResult.outcome === "accepted") {
            console.log("[PWA] User accepted install prompt");
          }
          deferredInstallPrompt = null;
        });
      } else {
        alert("현재 브라우저 환경에서는 [메뉴 ⋮] -> [앱 설치] 또는 [홈 화면에 추가]를 이용해 주세요.");
      }
    }

    function setAppTheme(theme) {
      const validThemes = ['purple', 'oled', 'white'];
      if (!validThemes.includes(theme)) theme = 'purple';

      if (theme === 'purple') {
        document.documentElement.removeAttribute('data-theme');
      } else {
        document.documentElement.setAttribute('data-theme', theme);
      }

      document.querySelectorAll('#themeSwitcherTabs .theme-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.theme === theme);
      });

      try {
        window.localStorage.setItem('app_theme', theme);
      } catch (e) {}
    }

    function initAppTheme() {
      let savedTheme = 'purple';
      try {
        savedTheme = window.localStorage.getItem('app_theme') || 'purple';
      } catch (e) {}
      setAppTheme(savedTheme);
    }

    function handleThemeClick(event) {
      const themeTab = event.target.closest('#themeSwitcherTabs .theme-tab');
      if (!themeTab) return false;
      event.preventDefault();
      if (typeof window.setAppTheme === 'function') window.setAppTheme(themeTab.dataset.theme);
      return true;
    }

    function switchMainModule(mod) {
      currentModule = mod;
      const wealthNavBtn = document.getElementById("navTabWealth");
      const ledgerNavBtn = document.getElementById("navTabLedger");
      const wealthWrapper = document.getElementById("userAssetDashboardWrapper");
      const ledgerWrapper = document.getElementById("userLedgerWrapper");

      if (mod === "wealth") {
        if (wealthNavBtn) { wealthNavBtn.className = "button primary"; wealthNavBtn.style.color = "#fff"; }
        if (ledgerNavBtn) { ledgerNavBtn.className = "button secondary"; ledgerNavBtn.style.color = "#94a3b8"; }
        if (wealthWrapper) wealthWrapper.style.display = "block";
        if (ledgerWrapper) ledgerWrapper.style.display = "none";
      } else {
        if (wealthNavBtn) { wealthNavBtn.className = "button secondary"; wealthNavBtn.style.color = "#94a3b8"; }
        if (ledgerNavBtn) { ledgerNavBtn.className = "button primary"; ledgerNavBtn.style.color = "#fff"; }
        if (wealthWrapper) wealthWrapper.style.display = "none";
        if (ledgerWrapper) ledgerWrapper.style.display = "block";
        loadLedger();
      }
    }

    function initAppVersion() {
      const metaVer = document.querySelector('meta[name="application-version"]')?.content;
      const verEl = document.getElementById('appVersionDisplay');
      if (verEl && metaVer) {
        verEl.textContent = `앱 버전 v${metaVer}`;
      }
    }

    async function bootstrap({ brokerImports, initializeFeatures, initializeSession }) {
      brokerImports.initializeScreens();
      initAppTheme();
      initAppVersion();
      initializeFeatures();
      brokerImports.bindEvents();
      await initializeSession();
    }

    function bindLifecycle({ bootstrap, getDashboard, getUserProfile, getIncomeTab, cancelPendingIncome, renderInvestmentView }) {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap);
      } else {
        bootstrap();
      }

      window.addEventListener('wealth:view', ({ detail }) => {
        // Hidden subview notifications must not cancel a direct dividend entry.
        const activeView = document.querySelector('.wealth-workspace')?.dataset.activeView;
        if (activeView ? activeView !== 'income' : detail !== 'income' && detail !== 'ledger') cancelPendingIncome();
        window.WealthStartup?.dashboardRendered(getDashboard());
        void window.WealthStartup?.loadVisible();
        if (detail === 'invest') renderInvestmentView();
        const currentUserProfile = getUserProfile();
        if (detail === 'ledger' && currentUserProfile && !currentUserProfile.must_change_password && currentUserProfile.username !== 'admin') loadLedger();
      });
      window.addEventListener('wealth:role', ({ detail }) => {
        if (!detail.isAdminUser && getIncomeTab() === 'ledger') loadLedger();
      });
    }

    return {
      closeDialog, initAppTheme, initAppVersion, setAppTheme, switchMainModule, triggerPwaInstall,
      getCurrentModule: () => currentModule,
      bindDialogCancel, bindMoneyHints, bindDialogControls, bindPwa, handleThemeClick, bootstrap, bindLifecycle,
    };
  }

  window.WealthAppShellController = { create };
})();
