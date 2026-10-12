# Toss WTS browser authentication image runtime

## Image contract

- Python 3.11 on explicit Debian Bookworm (`python:3.11-slim-bookworm`).
- Auth-only venv: `/opt/toss-auth/venv`; Wealth's application interpreter and
  `requirements.txt` remain separate.
- Playwright 1.58.0, with exact transitive runtime pins. Its CLI installs the
  matching full Chromium revision and OS libraries at image build time using
  `install --with-deps --no-shell chromium`.
- `PLAYWRIGHT_BROWSERS_PATH=/opt/toss-auth/ms-playwright` is the same at build
  and runtime. No browser downloads, apt installs, or pip installs happen at
  container startup/login.
- `TOSSCTL_AUTH_HELPER_PYTHON=/opt/toss-auth/venv/bin/python`
- `TOSSCTL_AUTH_HELPER_DIR=/opt/toss-auth/helper`
- `TOSSCTL_AUTH_HELPER_BROWSER_CHANNEL=chromium`
- `TOSSCTL_AUTH_HELPER_QUIET=1` suppresses helper QR/auth diagnostics and raw
  error messages. Do not disable it in production or enable Playwright debug
  logging when handling authentication.
- Vendored upstream v0.50.3 commit/license/patch details are in
  `vendor/tossctl-auth-helper/WEALTH-PATCHES.md`.

The existing `linux/amd64,linux/arm64` publication workflow is unchanged.
Playwright selects the target-platform binary; there is no amd64-only Chrome
package or hardcoded Chromium executable path. The existing executable bind
mount `/opt/toss-wts/tossctl` is unchanged. The helper lives outside that mount.

## Session and security boundaries

The Wealth service now passes a unique private confirmation-file path through
the subprocess environment. The existing CLI argv remains
`--config-dir <user-config> auth login --headless --link --qr-output <private-png>`.
Sessions remain at `/app/data/toss-wts/users/<username>/config/session.json`.
No fixed global storage-state path is introduced; the Go CLI derives it from
each user's config/cache directory. Existing session files are neither removed
nor migrated by this image change.

Per-user login/extend locks, duplicate-attempt rejection, QR ownership checks,
timeouts, cancellation, terminal cleanup and private QR serving remain in the
existing services. Owner-authenticated pending status responses expose only the
current confirmation letter and QR digest with `Cache-Control: no-store`.
The UI waits for the matching QR image before displaying the letter. Cancel
termination uncertainty keeps the attempt UI active. Wealth discards original
authentication subprocess streams.
Success still requires an actual `auth status` reporting **active AND valid**;
an exit code of zero or a newly generated QR image is insufficient.

## Linux attempt process boundary (implementation, not validated)

The actual tree is Go tossctl → Python helper → Playwright driver → Chromium.
Playwright 1.58 launches Chromium detached on POSIX (a separate process group):
<https://github.com/microsoft/playwright/blob/v1.58.0/packages/playwright-core/src/server/utils/processLauncher.ts>.
Consequently, `killpg` around tossctl cannot establish complete cleanup.
Linux now runs each CLI under a dedicated Python supervisor from
`app/services/toss_wts_auth_process.py`. It enables `PR_SET_CHILD_SUBREAPER`
before spawning the CLI; orphaned descendants are adopted even after `setsid`.
See <https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html>.
No cgroup, root capability, privileged mode or Docker configuration change is
required by this design. Actual kernel/seccomp availability remains untested.
The supervisor probes subreaper and pidfd support/permission before CLI spawn;
failure starts no Toss authentication process.

Only the supervisor's bounded direct/adopted child list is examined (1024 limit),
not the container's PID table. PPID/starttime is checked around `pidfd_open`;
signals go to pinned pidfds, never names, broad groups or unverified PIDs.
SIGTERM requests supervisor cleanup; children receive TERM then KILL after a
two-second grace. The web service never KILLs the supervisor, because doing so
could abandon detached children. Reaping continues until `waitpid` reports
`ECHILD` after CLI exit. Only then is a private 0600 completion receipt written.
Normal helper success explicitly closes the browser and exits Playwright's
context; the supervisor also removes any remaining descendants on CLI exit.

The receipt is bound to username, attempt UUID, private nonce, Linux boot ID and
supervisor PID/starttime. Finalization additionally requires supervisor exit;
`auth status` must still report active AND valid for success. The pre-spawn
marker prevents duplicate login during crash/setup windows. Managed marker
removal is serialized with login/extend under the existing per-user lock and
requires matching proof. Invalid/unreadable markers and old Linux PID-only
markers fail closed; the old 360-second age rule never removes them on Linux.
There is one narrowly scoped exception for an unused reservation: known
fork/exec failure errno from standard CPython `Popen`, before it returns a
process object, can release that attempt's `pid=0` reservation. The caller is
still inside its original auth lock; recovery does not acquire it again.
Username, attempt UUID, private token, boot ID, boundary kind, login type and
unset PID starttime must match exactly. Unknown errno, preparation I/O failure,
corrupt/mismatched markers and failures after a process object was returned
keep the guard closed. Injected test launchers must model the same standard
Popen failure contract; an adapter that spawns and then raises cannot be treated
as a definite execution failure. Only the generic spawn error is exposed.
Windows keeps the existing login mock/leader path; it is not a certified Windows
process-tree implementation.

On web-server restart, the independent supervisor may continue and produce
proof; its own 300-second deadline also requests cleanup without a live polling
client. Absent proof never implies completion. Supervisor SIGKILL, receipt/write
failure, missing procfs, denied signals, boot-ID mismatch, a crash between
reservation and metadata commit, or missing starttime can leave an indefinitely
blocked attempt. Ownership cannot then be safely reconstructed, and the service
does not kill guessed processes or silently expire the marker. Operator recovery
must establish that the attempt's descendants exited before clearing its guard.
The supervisor remains alive on uncertain child termination, while the API
returns pending after its bounded wait. This trades availability for safety.
Do not treat this unexecuted implementation as production-certified cleanup.

## Validation code (not executed during implementation)

`tests/test_toss_wts_auth_runtime.py` adds Docker/helper wiring and mock-based
security/channel/session contract tests. Existing login, session and user-scope
tests remain unchanged and cover lock contention, timeout/cancel, QR ownership,
cleanup and session verification. Run them using the project's isolated
synthetic source-copy procedure, without production `data/`, `.env` or secrets.
`tests/test_toss_wts_confirmation.py` adds owner isolation, QR/letter rotation,
digest binding, terminal artifact cleanup, safe UI transport, private spawn
environment and signal-error uncertainty tests. These tests do not establish
full process-tree termination; no real browser/process-tree test was executed.
`tests/test_toss_wts_auth_process.py` adds mocked parent-only exit, child signal
failure, PID reuse/foreign ownership, stale/corrupt guard, restart, rollback,
concurrent re-login protection and normal cleanup coverage. A Linux-only test
uses detached synthetic Python descendants, no browser, network or Toss account.
Its capability failures are test failures, not an unconditional success bypass.
Reservation recovery tests cover definite spawn failure followed by retry,
owner/attempt/token mismatches, corruption, unknown errors, nested-lock refusal
and preserving guards after supervisor setup failure. None were executed here.

The Dockerfile includes an unconditional, network-disabled build smoke:
`RUN --network=none ... browser_smoke.py`. It uses the helper's exact browser
launch options and only launches/closes Chromium: no page creation, navigation,
QR generation or Toss request. Original diagnostics are suppressed; failures
report only exception class/CPU architecture and exit nonzero. No architecture
skip, retry-until-pass, or unconditional success fallback is provided.

Neither image builds nor any validation command was executed in this task.
Both architecture builds and actual QR authentication remain unverified.
QEMU can differ from native ARM64 in Chromium startup, signals and shared-memory
behavior. If the smoke fails under emulation, preserve that failure and inspect
it on a native ARM64 builder; do not bypass the smoke or assume native success.

Python's base tag and Debian repositories receive security updates. Auth Python
dependencies and the corresponding browser revision are pinned, but the entire
OS image is not a bit-for-bit frozen Debian snapshot.

Before deployment approval, an authorized operator must build both targets,
recreate the container with the unchanged volumes, and perform a real QR login
privately. Check PNG generation, phone confirmation of persistent login,
`auth status` active/valid, cancellation/timeouts, user isolation and session
persistence after recreation. Never paste QR URLs, cookie values, session files,
XSRF tokens, storage-state contents or raw subprocess output into logs/reports.
