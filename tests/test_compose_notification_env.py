from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = (ROOT / "docker-compose.yml", ROOT / "docker-compose.ghcr.yml")
FORBIDDEN = (
    "DISCORD_WEBHOOK_URL",
    "DISCORD_WEALTH_USERNAME",
    "KAKAO_REST_API_KEY",
    "KAKAO_CLIENT_SECRET",
)


class ComposeNotificationEnvTests(unittest.TestCase):
    def test_user_notification_secrets_are_not_injected_via_compose(self):
        for path in FILES:
            text = path.read_text(encoding="utf-8")
            for name in FORBIDDEN:
                self.assertNotIn(name, text, f"{path.name}: leaked env contract {name}")
            self.assertNotIn("https://discord.com/api/webhooks/", text)


if __name__ == "__main__":
    unittest.main()
