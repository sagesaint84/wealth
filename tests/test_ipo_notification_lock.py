from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.ipo.notifier import IpoNotificationAlreadyRunning, notification_state_lock


class IpoNotificationLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "notification_state.json"

    def test_same_process_contention_fails_fast_and_releases(self):
        with notification_state_lock(self.state):
            with self.assertRaises(IpoNotificationAlreadyRunning):
                with notification_state_lock(self.state):
                    pass
        with notification_state_lock(self.state):
            pass

    def test_exception_does_not_leak_lock(self):
        with self.assertRaisesRegex(RuntimeError, "test"):
            with notification_state_lock(self.state):
                raise RuntimeError("test")
        with notification_state_lock(self.state):
            pass
