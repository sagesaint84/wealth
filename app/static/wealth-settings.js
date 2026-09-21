(() => {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
  let clearBotToken = false;
  let clearWebhookSecret = false;

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

  function reminderValues() {
    return [...document.querySelectorAll('#settingsReminderTimes input')].map((input) => input.value.trim());
  }

  function addReminderRow(value = '') {
    const row = document.createElement('div');
    row.className = 'settings-reminder-row';
    const input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'numeric';
    input.placeholder = 'HH:MM';
    input.value = value;
    input.setAttribute('aria-label', '공모주 청약 알림 시간');
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'button secondary compact';
    remove.textContent = '삭제';
    remove.addEventListener('click', () => {
      const list = byId('settingsReminderTimes');
      if (list.children.length <= 1) {
        setError('settingsAutomationError', '최소 1개의 알림 시간이 필요합니다.');
        return;
      }
      row.remove();
    });
    row.append(input, remove);
    byId('settingsReminderTimes').append(row);
    return input;
  }

  function renderNotifications(data) {
    const telegram = data.telegram;
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
  }

  function renderAutomation(data) {
    const automation = data.automation;
    byId('settingsTimezone').textContent = automation.timezone;
    byId('settingsMorningEnabled').checked = automation.ipo_refresh_morning.enabled;
    byId('settingsMorningTime').value = automation.ipo_refresh_morning.time;
    byId('settingsRemindersEnabled').checked = automation.ipo_reminders.enabled;
    byId('settingsEveningEnabled').checked = automation.ipo_refresh_evening.enabled;
    byId('settingsEveningTime').value = automation.ipo_refresh_evening.time;
    byId('settingsDailyCloseEnabled').checked = automation.daily_close.enabled;
    byId('settingsDailyCloseTime').value = automation.daily_close.time;
    byId('settingsReminderTimes').replaceChildren();
    automation.ipo_reminders.times.forEach(addReminderRow);
  }

  async function reloadSettings() {
    const [notifications, automation] = await Promise.all([
      api('/api/settings/notifications'),
      api('/api/settings/automation'),
    ]);
    renderNotifications(notifications);
    renderAutomation(automation);
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
      const times = reminderValues();
      const named = [
        ['IPO 오전 갱신', byId('settingsMorningTime').value],
        ['IPO 장후 갱신', byId('settingsEveningTime').value],
        ['일일 마감', byId('settingsDailyCloseTime').value],
      ];
      if (named.some(([, value]) => !validateTime(value)) || times.some((value) => !validateTime(value))) throw new Error('시간은 HH:MM 형식이어야 합니다.');
      if (!times.length) throw new Error('최소 1개의 알림 시간이 필요합니다.');
      if (new Set(times).size !== times.length) throw new Error('알림 시간을 중복해서 입력할 수 없습니다.');
      const automation = {
        timezone: 'Asia/Seoul',
        ipo_refresh_morning: {enabled: byId('settingsMorningEnabled').checked, time: named[0][1].trim()},
        ipo_reminders: {enabled: byId('settingsRemindersEnabled').checked, times: [...times].sort()},
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
    byId('settingsAddReminder')?.addEventListener('click', () => addReminderRow('').focus());
    byId('settingsClearBot')?.addEventListener('click', () => requestClear('bot'));
    byId('settingsClearWebhook')?.addEventListener('click', () => requestClear('webhook'));
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
