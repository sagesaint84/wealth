# v2.1.5 #184 validation

Base f6b966b2efaddd76a7def323da45277f8e4651d1; branch codex/v215-updater-permissions, isolated worktree. Latest user policy explicitly permits delegated cleanup; earlier admin-only cleanup is superseded.

## Executed locally

- Expanded complete selected suite: **445 passed, 1 skipped, 51 subtests passed in330.26s**. Includes prior home/initialization/owner/financial chart/pension/Toss/IPO/cache/version/settings scope plus persisted-permission, stable-ID/user-management/auth-session and updater tests.
- Final permission+Chromium suite after approval-type guard and admin presentation/role-parent synchronization changes: **55 passed in51.87s**. This includes the extra malformed preview-token case; counts are overlapping independent runs, not summed.
- Follow-up own-password error text Chrome case:1 passed, no install starts. Final bound-session/permission/API/identity suite: **67 passed in10.66s**, including distinct random login sid and same-user/different-session preview rejection. No host protocol change; all exact-head CI rerun after the follow-ups.
- Pending-password route enforcement: final auth/permission/API subset **71 passed in12.16s**; two routes reject non-pending forced changes without DB mutation, both legitimate pending flows still succeed. Actual admin initial-password completion and delegated reauth-error Chromium cases **2 passed**; UI re-reads server capability after completion. These are additional overlapping focused checks, not aggregated counts.
- Focused user storage/security/host/contract scope: **156 passed, 1 skipped**. Actual DB API/authorization/version subset:71 passed.
- Actual admin/admin role Chromium320/360/390/768/1280: 5 passed; delegated sagesaint/user exercises install+confirm+preview+cleanup at all five widths. Plain sagesaint/other lack UI; revoke hides UI, new calls denied, mock started host job unchanged. ARIA/keyboard/hash/reload/no duplicate IDs/whole-page overflow and no eager admin financial reads asserted. Final focused run includes all these cases.
- Initial Chrome expansion:5 failures /18 passed. Fixture initially opened admin directly at #settings while asserting no updater status request; direct #settings legitimately selects the new admin updater. Corrected default-admin scenario to #home and retained direct #settings reload coverage; all5 actual-admin cases then passed. No sleep or weaker no-eager assertion.
- First permission-test draft accidentally used a definition-time target UUID default despite per-test randomized IDs; six positive grant/inactive scenarios were correctly refused by target-bound approval checks. Fixture now resolves the current target ID per call; all71 passed. No authorization bypass added.
- Windows skip is actual Unix IPC, required with no skips in Linux CI. Local Docker execution NOT_RUN; real disposable Docker job must rerun. Linux IPC test now also sends a delegated UUID actor and unchanged cleanup shape to the existing worker; normal safety refusal is expected before installation confirmation.
- git diff --check and changed JS node --check PASS. app/updater/*, ops/wealth-updater/* and original Compose have **empty source diff**. Worker reinstall not required.
- Full repository pytest **NOT_RUN**. No new performance benchmark. PR177 numerical FAIL/HOLD and its one-release exception remain separate historical evidence.

## CI and operational boundaries

Exact Draft HEAD checks must be read from Actions: Static, IPO, Toss AMD64+ARM64, synthetic web/security/real Linux IPC/Chromium, and two actual Docker/Compose replacement/rollback cases. CI pins five real-admin and five delegated width scenarios and forbids skips. Actual run/job IDs and failures are preserved in PR history; no past HEAD result is reused.

USER_APPROVAL=PENDING
MERGE=HOLD
ORACLE_APP_DEPLOY=NOT_RUN
WORKER_REINSTALL=NOT_REQUIRED / NOT_RUN
ACTUAL_IMAGE_DELETION=NOT_RUN

Operator-reported v2.1.4 Oracle bootstrap is recorded in Issue184, not a server inspection by this task. v2.1.5 requires approved digest-pinned manual **app-only** deployment; first production one-click upgrade is v2.1.6. Existing worktree logs/249 prior performance files/financial/Toss/Compose/images untouched. Small stdout evidence remains local, excluded from the commit. [Security/rollout contract](../../UPDATER_PERMISSIONS_V215.md).
