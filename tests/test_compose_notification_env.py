from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = (ROOT / "docker-compose.yml", ROOT / "docker-compose.ghcr.yml")
EXPECTED = (
    "DISCORD_WEBHOOK_URL: \${DISCORD_WEBHOOK_URL:-}",
    "DISCORD_WEALTH_USERNAME: \${DISCORD_WEALTH_USERNAME:-}",
    "KAKAO_REST_API_KEY: \${KAKAO_REST_API_KEY:-}",
    "KAKAO_CLIENT_SECRET: \${KAKAO_CLIENT_SECRET:-}",
)


class ComposeNotificationEnvTests(unittest.TestCase):
    def test_notification_provider_env_is_forwarded_without_hardcoded_secrets(self):
        for path in FILES:
            text = path.read_text(encoding="utf-8")
            self.assertIn("environment:", text, path.name)
            for line in EXPECTED:
                self.assertIn(line, text, f"{path.name}: missing {line}")
            self.assertNotIn("https://discord.com/api/webhooks/", text)
            self.assertNotIn("KAKAO_REST_API_KEY: REST", text)
            self.assertNotIn("KAKAO_CLIENT_SECRET: SECRET", text)


if __name__ == "__main__":
    unittest.main()
