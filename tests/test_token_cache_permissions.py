import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.secure_files import atomic_write_private_json


class TokenCachePermissionTests(unittest.TestCase):
    CACHE_NAMES = (
        "kb_token_cache.json",
        "kis_token_cache.json",
        "kiwoom_token_cache.json",
        "nhplug_token_cache.json",
    )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.user_dir = Path(self.temp.name) / "user"
        self.user_dir.mkdir()
        if os.name == "posix":
            os.chmod(self.user_dir, 0o700)

    def test_all_provider_cache_shapes_are_atomic_and_private(self):
        for name in self.CACHE_NAMES:
            with self.subTest(name=name):
                target = self.user_dir / name
                atomic_write_private_json(target, {
                    "app_key_prefix": "fixture",
                    "access_token": "synthetic-token",
                    "expires_at": 12345.0,
                })
                self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["access_token"], "synthetic-token")
                self.assertFalse(list(self.user_dir.glob(f".{name}.*.tmp")))
                if os.name == "posix":
                    self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                    self.assertEqual(stat.S_IMODE(self.user_dir.stat().st_mode), 0o700)

    def test_failed_replace_preserves_old_cache_and_cleans_temp(self):
        target = self.user_dir / "kis_token_cache.json"
        atomic_write_private_json(target, {"access_token": "old"})
        before = target.read_bytes()
        with patch("app.services.secure_files.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                atomic_write_private_json(target, {"access_token": "new"})
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(self.user_dir.glob(".kis_token_cache.json.*.tmp")))

    def test_provider_writers_no_longer_use_write_text(self):
        root = Path(__file__).resolve().parents[1] / "app" / "services"
        for name in ("kb_openapi.py", "kis_openapi.py", "kiwoom_openapi.py", "nhplug_openapi.py"):
            source = (root / name).read_text(encoding="utf-8")
            self.assertNotIn("token_cache_file.write_text", source)
            self.assertIn("atomic_write_private_json", source)


if __name__ == "__main__":
    unittest.main()
