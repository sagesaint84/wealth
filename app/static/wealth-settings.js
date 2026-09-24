(() => {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  let clearBotToken = false;
  let clearWebhookSecret = false;
  let notificationsSnapshot = null;
  let systemSnapshot = null;
  let webhookSnapshot = null;
  let tossSessionSnapshot = null;
  let _lastKnownTossStatus = null;  // tracks last polled session status for re-auth guard

  function sourceLabel(configured, source) {
    if (!configured || source === 'none') return '미설정';
    if (source === 'stored') return 'Wealth에 저장됨';
    if (source === 'environment') return '환경변수 fallback';
    return '설정됨';
  }

  function setError(id, message = '') {
    const element = byId(id);
    element.textContent = message;
    element.hidden = !message;
  }

  function setStatus(id, configured, source) {
    const element = byId(id);
    element.textContent = sourceLabel(configured, source);
    element.className = `settings-source ${source || 'none'}`;
  }

  function safeMessage(error, fallback) {
    const message = typeof error?.message === 'string' ? error.message : '';
    return message && message !== '[object Object]' ? message : fallback;
  }

  function parseOptionalId(value, label) {
    const normalized = value.trim();
    if (!normalized) return null;
    if (!/^-?\d+$/.test(normalized)) throw new Error(`${label}는 정수 형식이어야 합니다.`);
    const number = Number(normalized);
    if (!Number.isSafeInteger(number)) throw new Error(`${label} 값이 너무 큽니다.`);
    return number;
  }

  function validateTime(value) {
    return timePattern.test(String(value || '').trim());
  }

  function reminderValues(containerId) {
    return [...document.querySelectorAll(`#${containerId} input`)].map((input) => input.value.trim());
  }

  function addReminderRow(value = '', containerId = 'settingsReminderTimes', label = '공모주 청약 알림 시간') {
    const row = document.createElement('div');
    row.className = 'settings-reminder-row';
    const input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'numeric';
    input.placeholder = 'HH:MM';
    input.value = value;
    input.setAttribute('aria-label', label);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'button secondary compact';
    remove.textContent = '삭제';
    remove.addEventListener('click', () => {
      const list = byId(containerId);
      if (list.children.length <= 1) {
        setError('settingsAutomationError', '최소 1개의 알림 시간이 필요합니다.');
        return;
      }
      row.remove();
    });
    row.append(input, remove);
    byId(containerId).append(row);
    return input;
  }

  function renderNotifications(data) {
    const telegram = data.telegram;
    notificationsSnapshot = telegram;
    byId('settingsTelegramEnabled').checked = telegram.enabled === true;
    byId('settingsChatId').value = telegram.chat_id ?? '';
    byId('settingsAllowedUserId').value = telegram.allowed_user_id ?? '';
    byId('settingsAllowedChatId').value = telegram.allowed_chat_id ?? '';
    setStatus('settingsBotStatus', telegram.bot_token_configured, telegram.bot_token_source);
    setStatus('settingsWebhookStatus', telegram.webhook_secret_configured, telegram.webhook_secret_source);
    byId('settingsClearBot').hidden = telegram.bot_token_source !== 'stored';
    byId('settingsClearWebhook').hidden = telegram.webhook_secret_source !== 'stored';
    byId('settingsClearBot').disabled = false;
    byId('settingsClearWebhook').disabled = false;
    byId('settingsClearBot').textContent = '저장된 값 삭제';
    byId('settingsClearWebhook').textContent = '저장된 값 삭제';
    byId('settingsBotToken').value = '';
    byId('settingsWebhookSecret').value = '';
    clearBotToken = false;
    clearWebhookSecret = false;
    updateManagementButtons();
  }

  function renderSystem(data) {
    systemSnapshot = data;
    byId('settingsPublicBaseUrl').value = data.public_base_url ?? '';
    byId('settingsPublicUrlSource').textContent = sourceLabel(Boolean(data.public_base_url), data.public_base_url_source);
    byId('settingsSaveSystem').hidden = !data.can_manage;
    byId('settingsPublicBaseUrl').disabled = !data.can_manage;
    renderAutomationOwner(data);
    // Own Toss state is loaded separately.  System settings intentionally do
    // not disclose local executable/config/session metadata.
    updateManagementButtons();
  }

  function renderTossSession(toss) {
    const section = byId('settingsTossSessionSection');
    if (!section) return;
    section.hidden = false;
    if (!toss) return;
    tossSessionSnapshot = toss;
    byId('settingsTossConfigured').textContent = `${toss.enabled ? '활성' : '비활성'} · ${toss.expected_version}`;
    byId('settingsTossSessionPresent').textContent = '확인하지 않음';
    byId('settingsTossSessionEnabled').checked = toss.session_check_enabled === true;
    for (const id of ['settingsTossSessionEnabled','settingsCheckTossSession','settingsSaveTossSession','settingsTossLoginStart']) byId(id).disabled = !toss.enabled || !toss.allowed;
  }

  async function saveTossSessionSettings() {
    const button = byId('settingsSaveTossSession'); setError('settingsAutomationError');
    try {
      busy(button, true);
      const result = await api('/api/settings/toss-wts', {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_check_enabled:byId('settingsTossSessionEnabled').checked})});
      tossSessionSnapshot = {...(tossSessionSnapshot || {}), ...result.toss_wts}; toast('내 Toss 세션 자동 점검 설정을 저장했습니다.');
    } catch (error) { const message=safeMessage(error,'Toss 세션 설정을 저장하지 못했습니다.'); setError('settingsAutomationError',message); toast(message,true); }
    finally { busy(button,false); }
  }

  async function checkTossSessionStatus() {
    const button = byId('settingsCheckTossSession'); setError('settingsAutomationError');
    try {
      busy(button,true); const status=await api('/api/settings/toss-wts/status',{method:'POST'});
      _lastKnownTossStatus = status;
      byId('settingsTossSessionPresent').textContent=status.session_present ? '있음' : '없음';
      byId('settingsTossLiveStatus').textContent=status.active && status.valid ? 'active / valid' : (status.error_code || 'invalid');
      byId('settingsTossExpiry').textContent=status.server_expires_at ? `${status.server_expires_at} · ${status.hours_remaining}시간` : '없음';
      byId('settingsTossCheckedAt').textContent=status.checked_at || '없음';
    } catch (error) { const message=safeMessage(error,'Toss 세션 상태를 확인하지 못했습니다.'); setError('settingsAutomationError',message); toast(message,true); }
    finally { busy(button,false); }
  }

  // -----------------------------------------------------------------------
  // Toss WTS QR login lifecycle
  // Verified tossctl v0.50.3: auth login --headless --link --qr-output <path>
  // -----------------------------------------------------------------------
  let _tossLoginAttemptId = null;
  let _tossLoginPollTimer = null;

  function _tossLoginReset() {
    clearInterval(_tossLoginPollTimer);
    _tossLoginPollTimer = null;
    _tossLoginAttemptId = null;
    const qrArea = byId('settingsTossLoginQrArea');
    const startBtn = byId('settingsTossLoginStart');
    const cancelBtn = byId('settingsTossLoginCancel');
    const statusEl = byId('settingsTossLoginStatus');
    const qrImg = byId('settingsTossLoginQr');
    if (qrArea) qrArea.hidden = true;
    if (qrImg) qrImg.src = '';
    if (statusEl) statusEl.textContent = '';
    if (startBtn) { startBtn.disabled = false; startBtn.hidden = false; }
    if (cancelBtn) cancelBtn.hidden = true;
  }

  async function startTossLogin() {
    setError('settingsAutomationError');
    const startBtn = byId('settingsTossLoginStart');
    const cancelBtn = byId('settingsTossLoginCancel');
    const qrArea = byId('settingsTossLoginQrArea');
    const statusEl = byId('settingsTossLoginStatus');

    // Re-auth guard: if we already know the session is active+valid, require
    // explicit confirmation before sending reauthenticate=true.
    let reauthenticate = false;
    const knownValid = _lastKnownTossStatus && _lastKnownTossStatus.active && _lastKnownTossStatus.valid;
    if (knownValid) {
      const confirmed = window.confirm(
        '현재 Toss WTS 세션이 유효한 상태입니다.\n' +
        '재인증을 시작하면 세션이 초기화될 수 있습니다.\n\n' +
        '계속하시겠습니까? (재인증 시작)'
      );
      if (!confirmed) return;
      reauthenticate = true;
    } else {
      if (!window.confirm('Toss WTS QR 인증을 시작합니다.\n진행 중인 세션 연장과 충돌할 수 있습니다. 계속하시겠습니까?')) return;
    }

    try {
      busy(startBtn, true);
      const result = await api('/api/settings/toss-wts/login/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reauthenticate }),
      });
      _tossLoginAttemptId = result.attempt_id;
      if (startBtn) startBtn.hidden = true;
      if (cancelBtn) cancelBtn.hidden = false;
      if (qrArea) qrArea.hidden = false;
      if (statusEl) statusEl.textContent = 'QR 코드를 기다리는 중… Toss 앱에서 스캔해주세요.';
      _tossLoginPollTimer = setInterval(pollTossLogin, 3000);
      await pollTossLogin();
    } catch (error) {
      // Handle 409 TOSS_SESSION_ALREADY_VALID gracefully
      const code = error && error.code;
      let message;
      if (code === 'TOSS_SESSION_ALREADY_VALID') {
        message = '현재 세션이 유효합니다. 재인증이 필요하면 세션 상태 확인 후 다시 시도하세요.';
      } else if (code === 'TOSS_AUTH_OPERATION_BUSY') {
        message = '다른 인증 작업이 진행 중입니다. 잠시 후 다시 시도하세요.';
      } else {
        message = safeMessage(error, 'Toss WTS 인증을 시작하지 못했습니다.');
      }
      setError('settingsAutomationError', message);
      toast(message, true);
      _tossLoginReset();
    } finally {
      busy(startBtn, false);
    }
  }

  async function pollTossLogin() {
    if (!_tossLoginAttemptId) return;
    const statusEl = byId('settingsTossLoginStatus');
    const qrImg = byId('settingsTossLoginQr');
    try {
      const result = await api(`/api/settings/toss-wts/login/${_tossLoginAttemptId}`);
      const status = result.status;
      if (status === 'pending') {
        if (qrImg) qrImg.src = `/api/settings/toss-wts/login/${_tossLoginAttemptId}/qr?t=${Date.now()}`;
        if (statusEl) statusEl.textContent = 'QR 코드를 Toss 앱으로 스캔해주세요.';
      } else if (status === 'success') {
        if (statusEl) statusEl.textContent = '\u2705 인증이 완료됐습니다. 세션 상태를 확인하세요.';
        _tossLoginReset();
        toast('Toss WTS 초기 인증이 완료됐습니다. 세션 상태를 확인해 주세요.');
        await checkTossSessionStatus();
      } else if (status === 'cancelled') {
        if (statusEl) statusEl.textContent = '인증이 취소됐습니다.';
        _tossLoginReset();
      } else if (status === 'timeout') {
        if (statusEl) statusEl.textContent = '\u23f1 인증 시간이 초과됐습니다. 다시 시도해 주세요.';
        _tossLoginReset();
        toast('Toss WTS 인증 시간 초과. 다시 시도해 주세요.', true);
      } else {
        if (statusEl) statusEl.textContent = `인증 실패 (${result.error_code || 'AUTH_LOGIN_FAILED'})`;
        _tossLoginReset();
        toast('Toss WTS 인증에 실패했습니다. 수동 확인이 필요합니다.', true);
      }
    } catch (_) {
      // Poll errors are non-fatal; keep polling
    }
  }

  async function cancelTossLogin() {
    if (!_tossLoginAttemptId) return;
    const cancelBtn = byId('settingsTossLoginCancel');
    try {
      busy(cancelBtn, true);
      await api(`/api/settings/toss-wts/login/${_tossLoginAttemptId}/cancel`, { method: 'POST' });
    } catch (_) {
      // Ignore cancel errors — reset UI anyway
    } finally {
      _tossLoginReset();
    }
  }

  function renderAutomationOwner(data) {
    const section = byId('settingsAutomationOwnerSection');
    if (!section) return;
    section.hidden = !data.can_manage;
    const nameEl = byId('settingsAutomationOwnerName');
    const sourceEl = byId('settingsAutomationOwnerSource');
    if (nameEl) nameEl.textContent = data.automation_owner || '미설정';
    if (sourceEl) sourceEl.textContent = sourceLabel(Boolean(data.automation_owner), data.automation_owner_source);
    const setBtn = byId('settingsSetAutomationOwner');
    const clearBtn = byId('settingsClearAutomationOwner');
    if (setBtn) setBtn.disabled = !data.can_manage || data.automation_owner === data.current_username;
    if (clearBtn) clearBtn.disabled = !data.can_manage || (!data.automation_owner && data.automation_owner_source !== 'environment');
  }

  function updateManagementButtons() {
    const telegram = notificationsSnapshot || {};
    const system = systemSnapshot || {};
    const owner = system.telegram_webhook_owner === system.current_username;
    byId('settingsSendTest').disabled = !(telegram.enabled && telegram.bot_token_configured && telegram.chat_id !== null);
    byId('settingsCheckTelegram').disabled = !(telegram.enabled && telegram.bot_token_configured);
    byId('settingsConnectWebhook').disabled = !(system.can_manage && owner && system.public_base_url && telegram.enabled && telegram.bot_token_configured && telegram.webhook_secret_configured && telegram.allowed_user_id !== null && telegram.allowed_chat_id !== null);
    byId('settingsDisconnectWebhook').disabled = !(system.can_manage && owner && webhookSnapshot?.configured);
  }

  function renderAutomation(data) {
    const automation = data.automation;
    byId('settingsTimezone').textContent = automation.timezone;
    byId('settingsMorningEnabled').checked = automation.ipo_refresh_morning.enabled;
    byId('settingsMorningTime').value = automation.ipo_refresh_morning.time;
    byId('settingsRemindersEnabled').checked = automation.ipo_reminders.enabled;
    byId('settingsListingRemindersEnabled').checked = automation.ipo_listing_reminders.enabled;
    byId('settingsEveningEnabled').checked = automation.ipo_refresh_evening.enabled;
    byId('settingsEveningTime').value = automation.ipo_refresh_evening.time;
    byId('settingsDailyCloseEnabled').checked = automation.daily_close.enabled;
    byId('settingsDailyCloseTime').value = automation.daily_close.time;
    byId('settingsReminderTimes').replaceChildren();
    byId('settingsListingReminderTimes').replaceChildren();
    automation.ipo_reminders.times.forEach((value) => addReminderRow(value));
    automation.ipo_listing_reminders.times.forEach((value) => addReminderRow(value, 'settingsListingReminderTimes', '공모주 상장일 알림 시간'));
  }

  async function reloadSettings() {
    const promises = [
      api('/api/settings/notifications'),
      api('/api/settings/automation'),
      api('/api/settings/system'),
      api('/api/settings/toss-wts'),
    ];

    const [notifications, automation, system, toss] = await Promise.all(promises);
    renderNotifications(notifications);
    renderAutomation(automation);
    renderSystem(system);
    renderTossSession(toss.toss_wts);
  }

  async function saveSystemSettings() {
    const button=byId('settingsSaveSystem');setError('settingsTelegramError');
    try {
      busy(button,true);
      const result=await api('/api/settings/system',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({public_base_url:byId('settingsPublicBaseUrl').value.trim() || null,telegram_webhook_owner:systemSnapshot.current_username})});
      renderSystem(result);toast('Public URL과 webhook 사용자를 저장했습니다.');
    } catch(error) { const message=safeMessage(error,'Public URL을 저장하지 못했습니다.');setError('settingsTelegramError',message);toast(message,true); }
    finally {busy(button,false);}
  }

  async function checkTelegramStatus() {
    const button=byId('settingsCheckTelegram');setError('settingsTelegramError');
    try {
      busy(button,true);const result=await api('/api/settings/telegram/status');webhookSnapshot=result.webhook;
      byId('settingsBotApiStatus').textContent=result.bot.username ? `@${result.bot.username} · Bot API 응답 정상` : 'Bot API 응답 정상';
      byId('settingsWebhookApiStatus').textContent=!result.webhook.configured?'연결되지 않음':(result.webhook.matches_expected?'Wealth URL에 연결됨':'다른 URL에 연결됨');
      byId('settingsWebhookDetails').hidden=false;byId('settingsWebhookUrl').textContent=result.webhook.actual_url || '없음';byId('settingsPendingUpdates').textContent=String(result.webhook.pending_update_count);byId('settingsWebhookLastError').textContent=result.webhook.last_error_message || '없음';updateManagementButtons();
    } catch(error) { webhookSnapshot=null;byId('settingsBotApiStatus').textContent='Bot API 확인 실패';byId('settingsWebhookApiStatus').textContent='확인 실패';const message=safeMessage(error,'Telegram 상태를 확인하지 못했습니다.');setError('settingsTelegramError',message);toast(message,true);updateManagementButtons(); }
    finally {busy(button,false);}
  }

  async function runManagementOperation(buttonId,url,loadingMessage,successMessage) {
    const button=byId(buttonId);setError('settingsTelegramError');
    try {button.dataset.label??=button.textContent;button.disabled=true;button.textContent=loadingMessage;await api(url,{method:'POST'});toast(successMessage);await checkTelegramStatus();}
    catch(error){const message=safeMessage(error,'Telegram 작업을 완료하지 못했습니다.');setError('settingsTelegramError',message);toast(message,true);}
    finally{button.textContent=button.dataset.label;updateManagementButtons();}
  }

  async function openSettings() {
    const dialog = byId('notificationSettingsDialog');
    byId('settingsLoading').hidden = false;
    byId('settingsContent').hidden = true;
    setError('settingsTelegramError');
    setError('settingsAutomationError');
    dialog.showModal();
    try {
      await reloadSettings();
      byId('settingsContent').hidden = false;
    } catch (_error) {
      toast('설정을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.', true);
      dialog.close();
    } finally {
      byId('settingsLoading').hidden = true;
    }
  }

  async function saveTelegram() {
    const button = byId('settingsSaveTelegram');
    setError('settingsTelegramError');
    let nonSecretSaved = false;
    try {
      const telegram = {
        enabled: byId('settingsTelegramEnabled').checked,
        chat_id: parseOptionalId(byId('settingsChatId').value, 'Chat ID'),
        allowed_user_id: parseOptionalId(byId('settingsAllowedUserId').value, 'Allowed User ID'),
        allowed_chat_id: parseOptionalId(byId('settingsAllowedChatId').value, 'Allowed Chat ID'),
      };
      busy(button, true);
      await api('/api/settings/notifications', {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({telegram})});
      nonSecretSaved = true;
      const botToken = byId('settingsBotToken').value;
      const webhookSecret = byId('settingsWebhookSecret').value;
      const secretPatch = {};
      if (botToken) secretPatch.bot_token = botToken;
      if (webhookSecret) secretPatch.webhook_secret = webhookSecret;
      if (clearBotToken) secretPatch.clear_bot_token = true;
      if (clearWebhookSecret) secretPatch.clear_webhook_secret = true;
      if (Object.keys(secretPatch).length) {
        await api('/api/settings/telegram/secrets', {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(secretPatch)});
      }
      byId('settingsBotToken').value = '';
      byId('settingsWebhookSecret').value = '';
      await reloadSettings();
      toast('Telegram 설정을 저장했습니다.');
    } catch (error) {
      byId('settingsBotToken').value = '';
      byId('settingsWebhookSecret').value = '';
      const message = nonSecretSaved ? '일부 설정은 저장되었지만 비밀정보 저장에 실패했습니다. 현재 상태를 다시 불러옵니다.' : safeMessage(error, '설정을 저장하지 못했습니다. 잠시 후 다시 시도해주세요.');
      setError('settingsTelegramError', message);
      toast(message, true);
      if (nonSecretSaved) await reloadSettings().catch(() => {});
    } finally {
      busy(button, false);
    }
  }

  async function saveAutomation() {
    const button = byId('settingsSaveAutomation');
    setError('settingsAutomationError');
    try {
      const times = reminderValues('settingsReminderTimes');
      const listingTimes = reminderValues('settingsListingReminderTimes');
      const named = [
        ['IPO 오전 갱신', byId('settingsMorningTime').value],
        ['IPO 장후 갱신', byId('settingsEveningTime').value],
        ['일일 마감', byId('settingsDailyCloseTime').value],
      ];
      if (named.some(([, value]) => !validateTime(value)) || times.some((value) => !validateTime(value)) || listingTimes.some((value) => !validateTime(value))) throw new Error('시간은 HH:MM 형식이어야 합니다.');
      if (!times.length || !listingTimes.length) throw new Error('최소 1개의 알림 시간이 필요합니다.');
      if (new Set(times).size !== times.length || new Set(listingTimes).size !== listingTimes.length) throw new Error('알림 시간을 중복해서 입력할 수 없습니다.');
      const automation = {
        timezone: 'Asia/Seoul',
        ipo_refresh_morning: {enabled: byId('settingsMorningEnabled').checked, time: named[0][1].trim()},
        ipo_reminders: {enabled: byId('settingsRemindersEnabled').checked, times: [...times].sort()},
        ipo_listing_reminders: {enabled: byId('settingsListingRemindersEnabled').checked, times: [...listingTimes].sort()},
        ipo_refresh_evening: {enabled: byId('settingsEveningEnabled').checked, time: named[1][1].trim()},
        daily_close: {enabled: byId('settingsDailyCloseEnabled').checked, time: named[2][1].trim()},
      };
      busy(button, true);
      const result = await api('/api/settings/automation', {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({automation})});
      renderAutomation(result);
      toast('자동화 설정을 저장했습니다.');
    } catch (error) {
      const message = safeMessage(error, '설정을 저장하지 못했습니다. 잠시 후 다시 시도해주세요.');
      setError('settingsAutomationError', message);
      toast(message, true);
    } finally {
      busy(button, false);
    }
  }

  async function setAutomationOwner() {
    const button = byId('settingsSetAutomationOwner');
    setError('settingsAutomationError');
    try {
      busy(button, true);
      const result = await api('/api/settings/system', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({automation_owner: systemSnapshot.current_username})
      });
      renderSystem(result);
      toast('전역 자동화 실행 사용자를 설정했습니다.');
    } catch (error) {
      const message = safeMessage(error, '전역 자동화 실행 사용자를 저장하지 못했습니다.');
      setError('settingsAutomationError', message);
      toast(message, true);
    } finally {
      busy(button, false);
    }
  }

  async function clearAutomationOwner() {
    const button = byId('settingsClearAutomationOwner');
    setError('settingsAutomationError');
    if (!window.confirm('전역 자동화 실행 사용자를 해제하시겠습니까?\n환경변수 fallback이 있으면 해당 사용자가 기준이 됩니다.')) return;
    try {
      busy(button, true);
      const result = await api('/api/settings/system', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({automation_owner: null})
      });
      renderSystem(result);
      toast('전역 자동화 실행 사용자를 해제했습니다.');
    } catch (error) {
      const message = safeMessage(error, '전역 자동화 실행 사용자를 해제하지 못했습니다.');
      setError('settingsAutomationError', message);
      toast(message, true);
    } finally {
      busy(button, false);
    }
  }

  function requestClear(kind) {
    const label = kind === 'bot' ? 'Bot Token' : 'Webhook Secret';
    if (!window.confirm(`저장된 ${label}을 삭제하시겠습니까?\n환경변수 fallback이 있으면 해당 값이 다시 사용될 수 있습니다.`)) return;
    if (kind === 'bot') clearBotToken = true;
    else clearWebhookSecret = true;
    const button = byId(kind === 'bot' ? 'settingsClearBot' : 'settingsClearWebhook');
    button.textContent = '삭제 예정';
    button.disabled = true;
  }

  document.addEventListener('DOMContentLoaded', () => {
    byId('settingsSaveTelegram')?.addEventListener('click', saveTelegram);
    byId('settingsSaveAutomation')?.addEventListener('click', saveAutomation);
    byId('settingsSetAutomationOwner')?.addEventListener('click', setAutomationOwner);
    byId('settingsClearAutomationOwner')?.addEventListener('click', clearAutomationOwner);
    byId('settingsSaveTossSession')?.addEventListener('click', saveTossSessionSettings);
    byId('settingsCheckTossSession')?.addEventListener('click', checkTossSessionStatus);
    byId('settingsTossLoginStart')?.addEventListener('click', startTossLogin);
    byId('settingsTossLoginCancel')?.addEventListener('click', cancelTossLogin);
    byId('settingsAddReminder')?.addEventListener('click', () => addReminderRow('').focus());
    byId('settingsAddListingReminder')?.addEventListener('click', () => addReminderRow('', 'settingsListingReminderTimes', '공모주 상장일 알림 시간').focus());
    byId('settingsClearBot')?.addEventListener('click', () => requestClear('bot'));
    byId('settingsClearWebhook')?.addEventListener('click', () => requestClear('webhook'));
    byId('settingsSaveSystem')?.addEventListener('click', saveSystemSettings);
    byId('settingsCheckTelegram')?.addEventListener('click', checkTelegramStatus);
    byId('settingsSendTest')?.addEventListener('click', () => runManagementOperation('settingsSendTest','/api/settings/telegram/test','전송 중…','Telegram 테스트 메시지를 전송했습니다.'));
    byId('settingsConnectWebhook')?.addEventListener('click', () => {
      if (webhookSnapshot?.configured && !webhookSnapshot.matches_expected && !window.confirm('현재 Telegram webhook이 다른 URL을 사용 중입니다. Wealth URL로 변경하시겠습니까?')) return;
      runManagementOperation('settingsConnectWebhook','/api/settings/telegram/webhook/connect','연결 중…','Telegram webhook을 연결했습니다.');
    });
    byId('settingsDisconnectWebhook')?.addEventListener('click', () => {
      if (!window.confirm('Webhook 연결을 해제하시겠습니까?\nTelegram에서 Wealth로 들어오는 청약 완료 응답이 중단됩니다.')) return;
      runManagementOperation('settingsDisconnectWebhook','/api/settings/telegram/webhook/disconnect','해제 중…','Telegram webhook 연결을 해제했습니다.');
    });
    byId('settingsBotToken')?.addEventListener('input', () => {
      if (!byId('settingsBotToken').value) return;
      clearBotToken = false;
      byId('settingsClearBot').disabled = false;
      byId('settingsClearBot').textContent = '저장된 값 삭제';
    });
    byId('settingsWebhookSecret')?.addEventListener('input', () => {
      if (!byId('settingsWebhookSecret').value) return;
      clearWebhookSecret = false;
      byId('settingsClearWebhook').disabled = false;
      byId('settingsClearWebhook').textContent = '저장된 값 삭제';
    });
    document.querySelectorAll('[data-settings-close]').forEach((button) => button.addEventListener('click', () => byId('notificationSettingsDialog').close()));
  });

  window.openNotificationSettings = openSettings;
  window.WealthSettings = {validateTime, sourceLabel, parseOptionalId};
})();
