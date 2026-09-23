import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/wealth-settings.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/wealth-overrides.css").read_text(encoding="utf-8")
LAYOUT_JS = (ROOT / "app/static/wealth-layout.js").read_text(encoding="utf-8")


def test_settings_entry_dialog_and_module_are_wired():
    assert 'id="notificationSettingsBtn"' in HTML
    assert 'onclick="openNotificationSettings()"' in HTML
    assert '⏰ 알림' in HTML
    assert '⚙️ 알림·자동화' not in HTML
    assert "'notificationSettingsBtn'" in LAYOUT_JS
    assert "['topbarFamilyBtn', 'userOpenApiBtn', 'notificationSettingsBtn']" in LAYOUT_JS
    assert 'id="notificationSettingsDialog"' in HTML
    assert '/static/wealth-settings.js?v=1.3.0' in HTML
    assert 'aria-labelledby="notificationSettingsTitle"' in HTML


def test_settings_uses_existing_api_contract_only():
    for endpoint in (
        "/api/settings/notifications",
        "/api/settings/automation",
        "/api/settings/telegram/secrets",
        "/api/settings/system",
        "/api/settings/toss-wts",
        "/api/settings/toss-wts/status",
        "/api/settings/telegram/status",
        "/api/settings/telegram/test",
        "/api/settings/telegram/webhook/connect",
        "/api/settings/telegram/webhook/disconnect",
    ):
        assert endpoint in JS
    assert "setWebhook" not in JS and "getWebhookInfo" not in JS


def test_secret_values_are_never_rendered_or_persisted():
    assert ".value = telegram.bot_token" not in JS
    assert ".value = telegram.webhook_secret" not in JS
    assert "localStorage" not in JS and "sessionStorage" not in JS
    assert "console." not in JS
    assert 'autocomplete="new-password"' in HTML
    assert "settingsBotToken').value = ''" in JS
    assert "settingsWebhookSecret').value = ''" in JS
    assert "if (botToken) secretPatch.bot_token" in JS
    assert "if (webhookSecret) secretPatch.webhook_secret" in JS


def test_secret_source_and_clear_semantics_are_explicit():
    assert "Wealth에 저장됨" in JS
    assert "환경변수 fallback" in JS
    assert "미설정" in JS
    assert "clear_bot_token" in JS and "clear_webhook_secret" in JS
    assert "telegram.bot_token_source !== 'stored'" in JS
    assert "환경변수 fallback이 있으면" in JS


def test_time_and_id_validation_contracts():
    assert "/^(?:[01]\\d|2[0-3]):[0-5]\\d$/" in JS
    assert "/^-?\\d+$/" in JS
    assert "Number.isSafeInteger" in JS
    assert "new Set(times).size !== times.length" in JS
    assert "[...times].sort()" in JS
    assert "최소 1개의 알림 시간이 필요합니다." in JS


def test_listing_reminder_settings_are_independent_from_subscription_reminders():
    assert '공모주 상장일 알림' in HTML
    assert 'id="settingsListingRemindersEnabled"' in HTML
    assert 'id="settingsListingReminderTimes"' in HTML
    assert 'id="settingsAddListingReminder"' in HTML
    assert "automation.ipo_listing_reminders" in JS
    assert "ipo_listing_reminders: {enabled:" in JS
    assert "공모주 상장일 알림 시간" in JS


def test_opendart_system_credential_ui_is_admin_only_and_never_rehydrates_key():
    wealth_js = (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")
    assert 'id="openapiDartSection"' in HTML
    assert "시장 데이터 API · OpenDART" in HTML
    assert 'id="openapiDartKey"' in HTML
    assert "dartSection.hidden = !isSystemAdmin" in wealth_js
    assert "currentUserProfile?.role === 'admin'" in wealth_js
    assert ".openapi-broker-card:not(#openapiDartSection)" not in wealth_js
    assert "if (isSystemAdmin) {\n    await loadDartCredentialStatus();\n    return;" not in wealth_js
    assert "'/api/settings/dart'" in wealth_js
    assert "handleSaveDartApi" in wealth_js
    assert "handleTestDartApi" in wealth_js
    assert "handleDeleteDartApi" in wealth_js
    assert "if (input) input.value = '';" in wealth_js
    assert "config.dart.api_key" not in wealth_js


def test_partial_failure_and_blank_secret_contracts():
    assert "if (Object.keys(secretPatch).length)" in JS
    assert "일부 설정은 저장되었지만 비밀정보 저장에 실패했습니다." in JS
    assert "await reloadSettings()" in JS
    assert "Promise.all" in JS


def test_responsive_settings_styles_exist():
    assert ".settings-dialog" in CSS
    assert ".settings-reminder-row" in CSS
    assert "@media(max-width:620px)" in CSS


def test_management_ui_does_not_auto_call_external_status():
    assert 'id="settingsCheckTelegram"' in HTML
    assert 'id="settingsSendTest"' in HTML
    assert 'id="settingsConnectWebhook"' in HTML
    assert 'id="settingsDisconnectWebhook"' in HTML
    assert "api('/api/settings/telegram/status')" in JS
    assert "Telegram 상태 확인" in HTML


def test_automation_owner_ui_and_contract():
    assert 'id="settingsAutomationOwnerSection"' in HTML
    assert 'id="automationOwnerTitle"' in HTML
    assert '전역 자동화 실행 사용자' in HTML
    assert 'id="settingsSetAutomationOwner"' in HTML
    assert 'id="settingsClearAutomationOwner"' in HTML
    assert 'renderAutomationOwner' in JS
    assert 'automation_owner' in JS
    assert 'setAutomationOwner' in JS
    assert 'clearAutomationOwner' in JS


def test_toss_session_management_ui_is_explicit_and_secret_safe():
    assert 'id="settingsTossSessionSection"' in HTML
    assert 'id="settingsCheckTossSession"' in HTML
    assert 'id="settingsSaveTossSession"' in HTML
    assert '세션 자동 점검' in HTML
    assert 'Toss 모바일 앱 승인이 필요할 수 있습니다.' in HTML
    assert 'checkTossSessionStatus' in JS
    assert "api('/api/settings/toss-wts/status'" in JS
    assert 'auth extend' not in JS
    assert 'session.json' not in JS


def test_toss_login_ui_elements_present():
    assert 'id="settingsTossLoginSection"' in HTML
    assert 'id="settingsTossLoginStart"' in HTML
    assert 'id="settingsTossLoginCancel"' in HTML
    assert 'id="settingsTossLoginQrArea"' in HTML
    assert 'id="settingsTossLoginQr"' in HTML
    assert 'id="settingsTossLoginStatus"' in HTML
    assert 'aria-live="polite"' in HTML
    assert '초기 인증 / 재인증' in HTML


def test_toss_login_api_endpoints_in_js():
    assert "'/api/settings/toss-wts/login/start'" in JS
    assert "`/api/settings/toss-wts/login/${_tossLoginAttemptId}`" in JS
    assert "`/api/settings/toss-wts/login/${_tossLoginAttemptId}/cancel`" in JS
    assert "startTossLogin" in JS
    assert "pollTossLogin" in JS
    assert "cancelTossLogin" in JS
    assert "_tossLoginReset" in JS


def test_toss_login_security_invariants():
    # QR image must be fetched via API, not from static assets
    assert "/api/settings/toss-wts/login/" in JS
    assert "/static/" not in JS.split("/api/settings/toss-wts/login/")[1][:40]
    # QR polling must not use localStorage, sessionStorage, or console
    assert "localStorage" not in JS
    assert "sessionStorage" not in JS
    assert "console." not in JS
    # No session.json or subprocess output must appear
    assert "session.json" not in JS
    assert "stdout" not in JS
    assert "stderr" not in JS
    # cancel poll is non-fatal (errors suppressed)
    assert "// Poll errors are non-fatal" in JS


def test_toss_login_settings_uses_extended_api_contract():
    """All new login endpoints must be referenced in JS."""
    for endpoint in (
        "/api/settings/toss-wts/login/start",
        "/api/settings/toss-wts/login/",
        "/api/settings/toss-wts/login/${_tossLoginAttemptId}/cancel",
    ):
        assert endpoint in JS


class SettingsFrontendTests(unittest.TestCase):
    def test_entry_and_contract(self):
        test_settings_entry_dialog_and_module_are_wired()
        test_settings_uses_existing_api_contract_only()

    def test_secret_security_and_sources(self):
        test_secret_values_are_never_rendered_or_persisted()
        test_secret_source_and_clear_semantics_are_explicit()

    def test_validation_and_save_flow(self):
        test_time_and_id_validation_contracts()
        test_partial_failure_and_blank_secret_contracts()
        test_opendart_system_credential_ui_is_admin_only_and_never_rehydrates_key()

    def test_responsive_styles(self):
        test_responsive_settings_styles_exist()
        test_management_ui_does_not_auto_call_external_status()

    def test_automation_owner_ui(self):
        test_automation_owner_ui_and_contract()
        test_toss_session_management_ui_is_explicit_and_secret_safe()

    def test_toss_login_ui_and_security(self):
        test_toss_login_ui_elements_present()
        test_toss_login_api_endpoints_in_js()
        test_toss_login_security_invariants()
        test_toss_login_settings_uses_extended_api_contract()
