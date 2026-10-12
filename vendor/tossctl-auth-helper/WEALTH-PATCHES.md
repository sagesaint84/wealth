# Vendored tossctl authentication helper

Source: <https://github.com/JungHoonGhae/tossinvest-cli/tree/v0.50.3/auth-helper>

Upstream tag: **v0.50.3**

Immutable source commit: **152d6a5242b9e05ea975991df68a93c1d040bec7**

The package files and `pyproject.toml` are copied from that commit. `LICENSE`
preserves the upstream MIT license and copyright. Docker does not clone or
download a mutable upstream branch during its build.

Wealth modifications are limited to `tossctl_auth_helper/cli.py`:

1. `browser_launch_options()` replaces the fixed Chrome channel at the existing
   `chromium.launch` call. `TOSSCTL_AUTH_HELPER_BROWSER_CHANNEL` overrides the
   channel. Without an override, upstream's `chrome` default remains intact.
   The Wealth image sets `chromium`, using the full Playwright Chromium binary
   in new headless mode on AMD64 and ARM64.
2. With `TOSSCTL_AUTH_HELPER_QUIET=1`, `log()` suppresses upstream diagnostics
   (including decoded QR URLs and answer letters), and `emit()` replaces raw
   error messages with a generic error. This additional output-only adaptation
   is required by Wealth's sensitive-output contract; it changes neither
   authentication decisions nor the successful Go/helper JSON protocol.
   Without quiet mode, upstream diagnostics remain available.

3. Wealth supplies `TOSSCTL_AUTH_CONFIRMATION_FILE` only in the per-attempt
   subprocess environment. QRState writes a private, atomic 0600 JSON file
   containing `answer_letter` and the SHA256 of its QR PNG. A refreshed QR clears
   the old letter before writing; mismatched/invalid data is not published.
   Confirmation letters are never printed, including when quiet mode is off.
   Normal helper exit removes this file; Wealth also removes it on terminal
   attempt cleanup. The Go binary and its arguments are unchanged.

QR selection/capture/rotation, required cookie and local-storage checks, the
persistent-session TTL threshold and second confirmation, storage-state file
permissions/writes, User-Agent capture, polling and timeout logic are unchanged.
Cancellation remains owned by Wealth/Go. Full descendant termination is NOT
guaranteed by the existing leader-PID lifecycle; see the runtime README risk.

The upstream dependency range is retained in `pyproject.toml` for provenance.
The image instead installs the exact runtime dependency versions from
`ops/toss-auth/requirements.txt` into a separate venv. The Go CLI imports this
vendored package from `TOSSCTL_AUTH_HELPER_DIR`; no runtime package install is
needed.
