"""Image-build-only Chromium launch/close check. No auth, page, or network use."""
from __future__ import annotations

import contextlib
import os
import platform
import sys


def main() -> int:
    helper_dir = os.environ["TOSSCTL_AUTH_HELPER_DIR"]
    sys.path.insert(0, helper_dir)
    try:
        # Suppress original driver/browser diagnostics; report only failure type.
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            from playwright.sync_api import sync_playwright
            from tossctl_auth_helper.cli import browser_launch_options

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(**browser_launch_options(headless=True))
                browser.close()
    except Exception as exc:
        print(f"Toss auth Chromium startup failed: {type(exc).__name__}; platform={platform.machine()}", file=sys.stderr)
        return 1
    print(f"Toss auth Chromium launch/close ready; platform={platform.machine()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
