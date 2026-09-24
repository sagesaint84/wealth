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

    def test_kftc_admin_section_in_settings_dialog(self):
        self.assertIn('id="settingsKftcSection"', self.index_html)
        self.assertIn('id="settingsKftcEnabled"', self.index_html)
        self.assertIn('id="settingsKftcEnvSelect"', self.index_html)
        self.assertIn('id="settingsKftcClientId"', self.index_html)
        self.assertIn('id="settingsKftcClientSecret"', self.index_html)
        self.assertIn('id="settingsSaveKftc"', self.index_html)

    def test_wealth_js_has_kftc_methods_and_no_token_storage(self):
        self.assertIn("refreshKftcStatus", self.wealth_js)
        self.assertIn("handleStartKftcOAuth", self.wealth_js)
        self.assertIn("handleFetchKftcAccounts", self.wealth_js)
        self.assertIn("handleDisconnectKftc", self.wealth_js)
        # Ensure token or secrets are never saved into localStorage or sessionStorage
        self.assertNotIn("localStorage.setItem('kftc_token'", self.wealth_js)
        self.assertNotIn("sessionStorage.setItem('kftc_token'", self.wealth_js)

    def test_wealth_settings_js_has_kftc_admin_handlers(self):
        self.assertIn("renderKftcAdmin", self.wealth_settings_js)
        self.assertIn("saveKftcAdminSettings", self.wealth_settings_js)
        # Empty client_use_code must NOT be added to payload
        self.assertIn("if (client_use_code) payload.client_use_code = client_use_code;", self.wealth_settings_js)
        # UI label check
        self.assertIn("이용기관코드 (client_use_code, 변경할 때만 입력)", self.index_html)


if __name__ == "__main__":
    unittest.main()
