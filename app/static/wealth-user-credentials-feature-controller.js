(() => {
  "use strict";

  function create({ window, document, api, toast }) {
    // ── USER OPENAPI CONFIGURATION ──────────────────────────────────────────────
    const openApiFields = {
      toss: ['Toss', 'Client Secret 입력'], kb: ['Kb', 'KB App Secret 입력'],
      nh: ['Nh', '나무 App Secret 입력'], kis: ['Kis', '한투 App Secret 입력'],
      kiwoom: ['Kiwoom', '키움 App Secret 입력'],
    };
    let userOpenApiSnapshot = {};

    async function loadUserOpenApiSettings(brokers = null) {
      const config = await api('/api/user/openapi-config');
      const selected = brokers || Object.keys(openApiFields);
      for (const broker of selected) {
        const [prefix, secretPlaceholder] = openApiFields[broker];
        const value = config[broker] || {};
        userOpenApiSnapshot[broker] = value; // This endpoint returns masked values only.
        const field = suffix => document.getElementById('openapi' + prefix + suffix);
        const badge = field('Badge');
        if (badge) {
          badge.textContent = value.configured ? '연결됨' : '미연결';
          badge.className = 'openapi-badge ' + (value.configured ? 'connected' : 'disconnected');
        }
        if (field('DeleteBtn')) field('DeleteBtn').style.display = value.has_app_key || value.configured ? 'inline-flex' : 'none';
        if (field('Key')) field('Key').value = value.app_key || '';
        if (field('Secret')) {
          field('Secret').value = '';
          field('Secret').placeholder = value.configured ? '******** (등록됨 - 변경 시만 입력)' : secretPlaceholder;
        }
        if (field('AccountNo')) {
          field('AccountNo').value = '';
          field('AccountNo').placeholder = value.account_no ? value.account_no + ' (등록됨 - 변경 시만 입력)' : '변경할 계좌번호 입력';
        }
      }
      if (!brokers) renderDartOpenApiStatus(config.dart);
    }

    function renderDartOpenApiStatus(dartConfig, updateBadge) {
      const badge = document.getElementById('openapiDartBadge');
      const deleteButton = document.getElementById('openapiDartDeleteBtn');
      const input = document.getElementById('openapiDartKey');
      const configured = !!dartConfig?.configured;
      if (updateBadge) updateBadge(badge, configured);
      else if (badge) {
        badge.textContent = configured ? '연결됨' : '미연결';
        badge.className = `openapi-badge ${configured ? 'connected' : 'disconnected'}`;
      }
      if (deleteButton) deleteButton.style.display = dartConfig?.has_api_key ? 'inline-flex' : 'none';
      if (input) {
        input.value = '';
        input.placeholder = configured ? '******** (등록됨 - 변경 시에만 입력)' : '40자리 OpenDART 인증키 입력';
      }
    }

    async function refreshDartOpenApiStatus() {
      const config = await api('/api/user/openapi-config');
      renderDartOpenApiStatus(config.dart);
    }

    async function handleSaveDartApi() {
      const input = document.getElementById('openapiDartKey');
      const key = (input?.value || '').trim();
      if (!key) { toast('OpenDART API Key를 입력하세요.'); return; }
      try {
        await api('/api/user/openapi-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dart: { api_key: key } }),
        });
        if (input) input.value = '';
        toast('OpenDART API Key가 안전하게 저장되었습니다.');
        await refreshDartOpenApiStatus();
      } catch (err) {
        alert(err.message || '저장 실패');
      }
    }

    async function handleDeleteDartApi() {
      if (!confirm('정말로 OpenDART API 키를 삭제하시겠습니까?')) return;
      try {
        const res = await api('/api/user/openapi-config/dart', { method: 'DELETE' });
        toast(res.message || 'OpenDART 설정이 삭제되었습니다.');
        const input = document.getElementById('openapiDartKey');
        if (input) input.value = '';
        await refreshDartOpenApiStatus();
      } catch (err) {
        alert(err.message || '삭제 실패');
      }
    }

    async function handleTestDartApi() {
      try {
        const result = await api('/api/user/openapi-config/dart/test', { method: 'POST' });
        if (result.valid) {
          toast(result.message || 'OpenDART 연결을 확인했습니다.');
        } else {
          toast(`OpenDART 연결 확인 실패: ${result.message || result.error_code || 'UNKNOWN_ERROR'}`);
        }
      } catch (err) {
        alert(err.message || '연결 확인 실패');
      }
    }

    async function handleDeleteBrokerApi(broker) {
      const names = { toss: '토스증권', kb: 'KB증권', nh: '나무증권', kis: '한국투자증권', kiwoom: '키움증권', dart: 'OpenDART' };
      const bname = names[broker] || broker;
      if (!confirm(`정말로 ${bname} OpenAPI 키와 시크릿을 삭제(연결 해제)하시겠습니까?`)) return;

      try {
        const res = await api(`/api/user/openapi-config/${encodeURIComponent(broker)}`, {
          method: 'DELETE'
        });
        toast(res.message || `${bname} OpenAPI 키가 삭제되었습니다.`);
        await loadUserOpenApiSettings([broker]);
      } catch (err) {
        alert(err.message || '삭제 실패');
      }
    }

    async function handleSaveUserOpenApi(e) {
      if (e) e.preventDefault();
      const btn = document.getElementById('saveUserOpenApiBtn');
      const statusMsg = document.getElementById('openapiStatusMsg');

      // Omit untouched broker sections. The backend's blank app_key means delete,
      // so retain its masked key when changing only a secret/account number.
      const payload = {};
      for (const [broker, [prefix]] of Object.entries(openApiFields)) {
        const field = suffix => (document.getElementById('openapi' + prefix + suffix)?.value || '').trim();
        const stored = userOpenApiSnapshot[broker] || {};
        const key = field('Key'), secret = field('Secret'), account = field('AccountNo');
        const changedKey = key && key !== (stored.app_key || '');
        const changedAccount = account && !account.includes('*');
        if (!changedKey && !secret && !changedAccount) continue;
        payload[broker] = {app_key: key || stored.app_key || '', app_secret: secret};
        if (changedAccount) payload[broker].account_no = account;
      }
      if (!Object.keys(payload).length) { toast('변경할 인증정보를 입력해 주세요.'); return; }
      if (statusMsg) statusMsg.style.display = 'none';

      if (btn) {
        btn.disabled = true;
        btn.textContent = '저장 중...';
      }

      try {
        const res = await api('/api/user/openapi-config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        toast(res.message || '증권사 OpenAPI 설정이 안전하게 저장되었습니다.');
        await loadUserOpenApiSettings(Object.keys(payload));
      } catch (err) {
        if (statusMsg) {
          statusMsg.style.display = 'block';
          statusMsg.style.background = 'rgba(255,113,140,0.15)';
          statusMsg.style.color = '#ff718c';
          statusMsg.textContent = '저장 실패: ' + (err.message || String(err));
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = '💾 설정 저장';
        }
      }
    }

    // WEALTH_KRX_MARKETPLACE_CONFIG_V1
    async function loadKrxMarketplaceConfig() {
      const badge = document.getElementById('openapiKrxBadge');
      const login = document.getElementById('openapiKrxLoginId');
      const password = document.getElementById('openapiKrxPassword');
      const del = document.getElementById('openapiKrxDeleteBtn');
      const msg = document.getElementById('openapiKrxMessage');
      if (!badge || !login || !password) return;
      try {
        const res = await fetch('/api/user/krx-marketplace-config', { cache: 'no-store' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'KRX 설정 조회 실패');
        badge.textContent = data.configured ? '\uC5F0\uACB0\uB428' : '\uBBF8\uC124\uC815';
        badge.className = `openapi-badge ${data.configured ? 'connected' : 'disconnected'}`;
        login.value = '';
        login.placeholder = data.login_id || 'KRX 아이디';
        password.value = '';
        password.placeholder = data.password_configured ? '******** (변경 시에만 입력)' : 'KRX 비밀번호';
        if (del) del.style.display = data.configured || data.login_id_configured ? '' : 'none';
        if (msg) msg.textContent = '자격증명은 이 사용자 전용 data/users/<username>/secrets에 저장됩니다.';
      } catch (err) {
        if (msg) msg.textContent = 'KRX 설정을 불러오지 못했습니다.';
        throw new Error('KRX_CONFIG_LOAD_FAILED');
      }
    }

    async function saveKrxMarketplaceConfig() {
      const login = document.getElementById('openapiKrxLoginId');
      const password = document.getElementById('openapiKrxPassword');
      const msg = document.getElementById('openapiKrxMessage');
      const payload = {};
      if (login?.value.trim()) payload.login_id = login.value.trim();
      if (password?.value) payload.password = password.value;
      if (!Object.keys(payload).length) { if (msg) msg.textContent = '변경할 아이디 또는 비밀번호를 입력해 주세요.'; return; }
      try {
        const res = await fetch('/api/user/krx-marketplace-config', {
          method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'KRX 설정 저장 실패');
        if (msg) msg.textContent = data.message || '저장되었습니다.';
        await loadKrxMarketplaceConfig();
      } catch (err) { if (msg) msg.textContent = err?.message || 'KRX 설정 저장에 실패했습니다.'; }
    }

    async function testKrxMarketplaceConfig() {
      const msg = document.getElementById('openapiKrxMessage');
      const badge = document.getElementById('openapiKrxBadge');

      if (msg) msg.textContent = 'KRX login check...';

      try {
        const res = await fetch('/api/user/krx-marketplace-config/test', {
          method: 'POST',
        });
        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || 'KRX connection check failed');
        }

        if (badge) {
          badge.textContent = data.valid
            ? '\uC5F0\uACB0\uB428'
            : '\uC5F0\uACB0 \uC2E4\uD328';
          badge.className = `openapi-badge ${
            data.valid ? 'connected' : 'disconnected'
          }`;
        }

        if (msg) {
          msg.textContent =
            data.message ||
            (data.valid
              ? '\uC5F0\uACB0 \uC815\uC0C1'
              : '\uC5F0\uACB0 \uC2E4\uD328');
        }
      } catch (err) {
        if (badge) {
          badge.textContent = '\uC5F0\uACB0 \uC2E4\uD328';
          badge.className = 'openapi-badge disconnected';
        }

        if (msg) {
          msg.textContent =
            err?.message || 'KRX connection check failed';
        }
      }
    }

    async function deleteKrxMarketplaceConfig() {
      if (!window.confirm('저장된 KRX Data Marketplace 아이디와 비밀번호를 삭제할까요?')) return;
      const msg = document.getElementById('openapiKrxMessage');
      try {
        const res = await fetch('/api/user/krx-marketplace-config', { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'KRX 설정 삭제 실패');
        if (msg) msg.textContent = data.message || '삭제되었습니다.';
        await loadKrxMarketplaceConfig();
      } catch (err) { if (msg) msg.textContent = err?.message || 'KRX 설정 삭제에 실패했습니다.'; }
    }

    return {
      actions: {
        loadUserOpenApiSettings,
        renderDartOpenApiStatus,
        refreshDartOpenApiStatus,
        handleSaveDartApi,
        handleDeleteDartApi,
        handleTestDartApi,
        handleDeleteBrokerApi,
        handleSaveUserOpenApi,
        loadKrxMarketplaceConfig,
        saveKrxMarketplaceConfig,
        testKrxMarketplaceConfig,
        deleteKrxMarketplaceConfig,
      },
    };
  }

  window.WealthUserCredentialsFeatureController = { create };
})();
