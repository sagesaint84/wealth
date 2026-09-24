import unittest
from pathlib import Path


class KftcOpenBankingUITests(unittest.TestCase):
    def setUp(self):
        self.static_dir = Path(__file__).resolve().parents[1] / "app" / "static"
        self.index_html = (self.static_dir / "index.html").read_text(encoding="utf-8")
        self.wealth_js = (self.static_dir / "wealth.js").read_text(encoding="utf-8")
        self.wealth_settings_js = (self.static_dir / "wealth-settings.js").read_text(encoding="utf-8")

    def test_kftc_card_in_index_html(self):
        self.assertIn('id="kftcOpenBankingCard"', self.index_html)
        self.assertIn('id="kftcConnectBtn"', self.index_html)
        self.assertIn('id="kftcCheckStatusBtn"', self.index_html)
        self.assertIn('id="kftcFetchAccountsBtn"', self.index_html)
        self.assertIn('id="kftcDisconnectBtn"', self.index_html)
        self.assertIn('id="kftcEnvBadge"', self.index_html)

    def test_kftc_card_in_user_openapi_modal(self):
        # 🏦 금융결제원 오픈뱅킹 card exists in userOpenApiModal
        self.assertIn('id="openapiKftcSection"', self.index_html)
        self.assertIn('id="openapiKftcEnabled"', self.index_html)
        self.assertIn('id="openapiKftcEnvironment"', self.index_html)
        self.assertIn('id="openapiKftcClientId"', self.index_html)
        self.assertIn('id="openapiKftcClientSecret"', self.index_html)
        self.assertIn('id="openapiKftcClientUseCode"', self.index_html)
        self.assertIn('id="openapiKftcSaveBtn"', self.index_html)
        self.assertIn('id="openapiKftcCallbackUrl"', self.index_html)
        self.assertIn('id="openapiKftcTestbedBadge"', self.index_html)

    def test_old_admin_kftc_section_removed_from_notification_dialog(self):
        # Old admin section should no longer exist in notificationSettingsDialog
        self.assertNotIn('id="settingsKftcSection"', self.index_html)
        self.assertNotIn('id="settingsSaveKftc"', self.index_html)
        self.assertNotIn("renderKftcAdmin", self.wealth_settings_js)
        self.assertNotIn("saveKftcAdminSettings", self.wealth_settings_js)

    def test_wealth_js_has_kftc_methods_and_no_token_storage(self):
        self.assertIn("refreshKftcStatus", self.wealth_js)
        self.assertIn("handleStartKftcOAuth", self.wealth_js)
        self.assertIn("handleFetchKftcAccounts", self.wealth_js)
        self.assertIn("handleDisconnectKftc", self.wealth_js)
        self.assertIn("refreshUserKftcOpenApiStatus", self.wealth_js)
        self.assertIn("handleSaveUserKftcConfig", self.wealth_js)
        # Ensure token or secrets are never saved into localStorage or sessionStorage
        self.assertNotIn("localStorage.setItem('kftc_token'", self.wealth_js)
        self.assertNotIn("sessionStorage.setItem('kftc_token'", self.wealth_js)


if __name__ == "__main__":
    unittest.main()
