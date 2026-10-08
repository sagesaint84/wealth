import unittest
from pathlib import Path


class KftcOpenBankingUITests(unittest.TestCase):
    def setUp(self):
        self.static_dir = Path(__file__).resolve().parents[1] / "app" / "static"
        self.index_html = (self.static_dir / "index.html").read_text(encoding="utf-8")
        self.wealth_js = (self.static_dir / "wealth.js").read_text(encoding="utf-8")
        self.wealth_settings_js = (self.static_dir / "wealth-settings.js").read_text(encoding="utf-8")

    def test_retired_kftc_card_absent_from_index_html(self):
        self.assertNotIn('id="kftcOpenBankingCard"', self.index_html)
        self.assertNotIn('id="kftcConnectBtn"', self.index_html)
        self.assertNotIn('id="kftcCheckStatusBtn"', self.index_html)
        self.assertNotIn('id="kftcFetchAccountsBtn"', self.index_html)
        self.assertNotIn('id="kftcDisconnectBtn"', self.index_html)
        self.assertNotIn('id="kftcEnvBadge"', self.index_html)

    def test_retired_kftc_card_absent_from_user_openapi_modal(self):
        # Retirement is enforced at the producer, without a hide/remove shim.
        self.assertNotIn('id="openapiKftcSection"', self.index_html)
        self.assertNotIn('id="openapiKftcEnabled"', self.index_html)
        self.assertNotIn('id="openapiKftcEnvironment"', self.index_html)
        self.assertNotIn('id="openapiKftcClientId"', self.index_html)
        self.assertNotIn('id="openapiKftcClientSecret"', self.index_html)
        self.assertNotIn('id="openapiKftcClientUseCode"', self.index_html)
        self.assertNotIn('id="openapiKftcSaveBtn"', self.index_html)
        self.assertNotIn('id="openapiKftcCallbackUrl"', self.index_html)
        self.assertNotIn('id="openapiKftcTestbedBadge"', self.index_html)

    def test_other_openapi_controls_stay_available(self):
        for marker in ('userOpenApiModal', 'openapiTossKey', 'openapiKbKey', 'openapiDartKey'):
            self.assertIn(f'id="{marker}"', self.index_html)
        self.assertIn('function renderDartOpenApiStatus', self.wealth_js)

    def test_old_admin_kftc_section_removed_from_notification_dialog(self):
        # Old admin section should no longer exist in notificationSettingsDialog
        self.assertNotIn('id="settingsKftcSection"', self.index_html)
        self.assertNotIn('id="settingsSaveKftc"', self.index_html)
        self.assertNotIn("renderKftcAdmin", self.wealth_settings_js)
        self.assertNotIn("saveKftcAdminSettings", self.wealth_settings_js)

    def test_retired_wealth_handlers_absent_and_no_token_storage(self):
        self.assertNotIn("refreshKftcStatus", self.wealth_js)
        self.assertNotIn("handleStartKftcOAuth", self.wealth_js)
        self.assertNotIn("handleFetchKftcAccounts", self.wealth_js)
        self.assertNotIn("handleDisconnectKftc", self.wealth_js)
        self.assertNotIn("refreshUserKftcOpenApiStatus", self.wealth_js)
        self.assertNotIn("handleSaveUserKftcConfig", self.wealth_js)
        # Ensure token or secrets are never saved into localStorage or sessionStorage
        self.assertNotIn("localStorage.setItem('kftc_token'", self.wealth_js)
        self.assertNotIn("sessionStorage.setItem('kftc_token'", self.wealth_js)


if __name__ == "__main__":
    unittest.main()
