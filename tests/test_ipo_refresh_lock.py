from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ipo.orchestrator import IpoRefreshAlreadyRunning, _refresh_file_lock


def _hold_lock(directory: str, ready, release) -> None:
    from app.services.ipo import store
    store.get_ipo_data_dir = lambda: Path(directory)
    with _refresh_file_lock():
        ready.set()
        release.wait(10)


class IpoRefreshLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.patch = patch("app.services.ipo.store.get_ipo_data_dir", return_value=self.path)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_same_process_contention_fails_fast(self):
        with _refresh_file_lock():
            with self.assertRaises(IpoRefreshAlreadyRunning):
                with _refresh_file_lock():
                    pass

    def test_lock_releases_after_normal_and_exception_exit(self):
        with _refresh_file_lock():
            pass
        with _refresh_file_lock():
            pass
        with self.assertRaisesRegex(RuntimeError, "test"):
            with _refresh_file_lock():
                raise RuntimeError("test")
        with _refresh_file_lock():
            pass

    def test_cross_process_contention_and_release(self):
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        child = context.Process(target=_hold_lock, args=(str(self.path), ready, release))
        child.start()
        self.assertTrue(ready.wait(10))
        with self.assertRaises(IpoRefreshAlreadyRunning):
            with _refresh_file_lock():
                pass
        release.set(); child.join(10)
        self.assertEqual(child.exitcode, 0)
        with _refresh_file_lock():
            pass
