# v2.1.4 automated validation

Base: 70acd2719d20c9157069e82a7d33105464aa495d. Branch codex/v214-system-update, isolated worktree v214-system-update. Scope #181 only; #180/#178 reserved for later approved releases.

## Actual local results (2026-10-26)

- Complete expanded selection: **381 passed, 1 skipped, 51 subtests passed in275.23s**. Includes the prior complete270-case home/initialization/chart/owner/market/pension/Toss/IPO/cache/version selection plus updater security/host/release/Chromium and settings suites.
- Skipped case is `test_real_authenticated_unix_ipc_roundtrip_and_bad_key`, because this Windows Python has no UnixStreamServer. It is REQUIRED with no skips in Linux CI; local skip is not IPC PASS.
- Updater + existing settings Chromium initial run:15 passed in50.53s. All320/360/390/768/1280 widths in the expanded rerun as well; admin/role/keyboard exclusions, exact aria relations, safe text, no initial inactive updater requests, readonly check, install progress, confirmation-gated cleanup, reload/reconnect/rollback presentation, overflow and duplicate IDs.
- First expanded run:380 passed /1 failed /1 skipped /51 subtests. The NEW reload test accepted the previous document's readyState before the new navigation DOM existed. Fixed by waiting for changed performance.timeOrigin + initialized actual tab DOM, no sleeps or weaker assertions. The complete expanded rerun above passed. Logs remain local: expanded-local.txt and expanded-final-local.txt. Focused updater rerun before the fix:78 passed /1 skipped (does not replace the full rerun).
- Unit/contract/settings focused run:100 passed /1 skipped. This is additional evidence, not a replacement for the full expanded selection.
- `git diff --check`, new/changed JS `node --check`, installer `bash -n`: PASS.
- Full repository pytest: **NOT_RUN**. No new performance benchmark. PR177 historical FAIL/HOLD and its PR177-only release exception remain unchanged, not inherited as a v2.1.4 PASS or deployment approval.

## Separate Linux execution gates

New `system-update-pr-validation.yml` has independent jobs:

1. Synthetic web security + actual Unix IPC + five Chromium widths + settings/version; every collected case must execute without failure/error/skip. Exact five mobile widths and real Unix IPC case presence are asserted.
2. Actual Docker/Compose on a disposable Linux runner only, two synthetic-image cases: successful replacement/preservation and failed new image automatic rollback. Local Docker build fixture RepoDigests are supplied only by the test adapter; trust verification is independently tested against synthetic immutable GitHub/GHCR documents. No Oracle, financial files or auth credentials. Current/other containers are never test targets outside that dedicated VM (test has explicit GitHub Actions+opt-in preconditions).

At initial Draft creation these Linux gates and existing Static/IPO/Toss AMD64/ARM64 workflows are PENDING. Actual exact-head CI results are recorded in the Draft PR, including any failed attempt; prior HEAD successes are never reused. User approval and latest CI SUCCESS are required before merge.

## Operational gates

HOST_INSTALL=NOT_RUN
ORACLE_DEPLOY=NOT_RUN
USER_BROWSER=NOT_RUN
MERGE_GATE=HOLD
DEPLOY_GATE=HOLD

See [design, threat boundary, bootstrap and rollback](../../SYSTEM_UPDATE.md). Do not start v2.1.5/2.1.6 until this release boundary is confirmed. Local stdout files are reproducibility evidence, excluded from the commit; no protected prior-worktree evidence is changed or deleted.
