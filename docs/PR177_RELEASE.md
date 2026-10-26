# Wealth v2.1.3 — PR #177 release approval (2026-10-26)

PERFORMANCE_GATE=FAIL/HOLD
RELEASE_EXCEPTION=USER_APPROVED_PR177_ONLY

The user explicitly approved release of PR #177 with the existing performance failure as an exception **for this release only**. This does not change any numerical test to PASS, relax the criterion, establish the full cause, or transfer an exception to PR #179 or another release.

## Release scope

- Existing home content is split into **자산 포트폴리오 / 순자산 추이 / 주요지수**, with existing IDs/renderers and financial calculations preserved. The default is 자산 포트폴리오. Native ARIA names, keyboard arrows/Home/End, touch, hash navigation/reload/back remain supported.
- Planning checks the existing hidden tab state instead of reading hidden geometry. `WealthStartup.dashboardRendered(data)` returns immediately when its existing synthetic telemetry opt-in is disabled. ON metrics, visible/loadVisible, API ordering and financial rendering remain covered by regression tests.
- APP_VERSION=2.1.3. Changed core JS revision is 2.1.3-home-perf1; changed planning JS is 2.1.3-home-tabs2. Other revisions, SW, financial APIs/stores and Toss settings are unchanged.
- New synthetic opt-in regression is included in the existing static-transport CI workflow. No pipeline bypass is introduced.

## Validation and CI gates

The final release rerun completed: **270 passed, 51 subtests passed in 244.37s**, including Chromium 320/360/390/768/1280. Actual output is preserved locally; fresh commit/CI/merge/build identities are recorded in PR #177 and the release report. `git diff --check` passed before staging. **Full pytest NOT_RUN.**

A passing local run and `git diff --check` are required before a normal push. The pushed exact HEAD must have SUCCESS for Static transport, IPO schedule, Toss native AMD64 and ARM64 before Ready/Squash Merge. Old HEAD results do not count. No PR #179 merge is authorized. The user's PR177-only exception permits release consideration despite PERFORMANCE_GATE=FAIL/HOLD, not despite failed functional/regression/CI checks.

## Performance evidence preserved

Earlier 360px comparisons both failed. Final minimum-guard experiment used the original helper: Chromium, gzip, HTTP cache disabled, SW bypass; 360px CPU4x/latency40ms/download250000Bps, 1280px CPU1x/20ms/500000Bps. Each of five variants ran 16 times per width, 160 total, with fixed rotation/reversal; no favorable sample selection. A=main, B=original PR, C=planning guard, D=both guards, E=main with the same telemetry guard.

| Width | Variant | FCP median ms | First asset median ms | Readiness median ms |
|---|---|---:|---:|---:|
| 360 | A main | 606 | 3958.00 | 4362.80 |
| 360 | B original PR | 626 | 3882.30 | 4250.95 |
| 360 | C planning guard | 622 | 3843.85 | 4196.55 |
| 360 | D both guards | 628 | 3821.00 | 4183.80 |
| 360 | E main + telemetry guard | 612 | 3873.80 | 4260.90 |
| 1280 | A main | 318 | 1638.55 | 1807.15 |
| 1280 | B original PR | 320 | 1653.00 | 1813.65 |
| 1280 | C planning guard | 320 | 1648.30 | 1818.90 |
| 1280 | D both guards | 320 | 1649.00 | 1827.05 |
| 1280 | E main + telemetry guard | 316 | 1642.25 | 1819.95 |

| Width | Paired contrast | FCP median difference | First asset difference | Readiness difference |
|---|---|---:|---:|---:|
| 360 | E-A | +8.00 | -89.50 | -36.55 |
| 360 | D-E | +12.00 | -52.00 | -109.50 |
| 360 | D-A | +20.00 | -109.75 | -200.55 |
| 1280 | E-A | 0.00 | +10.75 | +17.00 |
| 1280 | D-E | +2.00 | +2.40 | +0.10 |
| 1280 | D-A | +6.00 | +15.15 | -4.30 |

Marginal-median differences and medians of paired differences are distinct and are not interchangeable. At 1280, D-A marginal first-display/readiness differences are +10.45/+19.90ms, failing the unchanged strict BOTH-width gate. D-E paired median 95% diagnostic bootstrap intervals are [-13.90,+17.60]ms for display and [-39.30,+70.10]ms for readiness. E-A intervals are [-6.95,+26.10] and [-4.80,+49.10]ms. Thus the full 10–20ms is not established as tab-specific cost; uncertainty is not an equivalence or PASS claim. Whole first-display root cause remains UNCONFIRMED. A corrected disabled telemetry contract is confirmed, but a universal performance improvement is not.

Historical failed JSONs already tracked in Git remain untouched. Large raw observations, traces, diagnostic temporary copies and local reports remain available locally and are excluded from this release commit. Their exclusion is not deletion or invalidation of the failure history. Old validation/HOLD paragraphs describe their original decision times; this dated explicit user approval supersedes the earlier release block only for PR177.

## Image and Oracle release gates

After a successful squash, verify the actual main merge SHA and its **push-triggered docker-publish.yml** run. Both linux/amd64 and linux/arm64 must build and publish successfully. Verify the image tag against that merge SHA and the manifest index Digest from Actions/registry; never deploy based only on `latest`.

The running Oracle deployment is not reachable from this task without a supplied/trusted SSH route. Repository Compose and historical operating documents describe `/docker/wealth`, service dashboard/container wealth, loopback4829, `./data:/app/data`, Toss binary read-only and Toss config mounts. **These are not a fresh server inspection.** The operator must validate the actual live Compose-file list, mounts, image and file hashes on the server before replacement.

Deploy only dashboard with the existing Compose files plus a dedicated digest-pinning override, `--no-deps --no-build --pull never --force-recreate`, after pulling the exact Digest. Do not alter the existing two Compose files, data, Toss mounts or unrelated services. Keep the previous verified image locally for rollback; no image/volume/system prune, data deletion, or mass backup image creation. Record and compare mounts and file hashes before/after. Do not clean images before verification.

Verify container image ID against the pulled pinned image and RepoDigest against the fixed manifest Digest (these different identifier types need not have the same hash), running state/restarts, HTTP GET `/`=307, JS/CSS GET gzip, and unchanged data/Toss mounts. On failure restore the previous verified image with the same Compose configuration. Never label server deployment PASS without execution.

Authenticated production browser checks are separate: all three exact home tabs, history chart/period/CRUD as authorized, major markets, 360px tab/reload and other financial menus. Synthetic Chromium PASS does not substitute for production smoke. Record unexecuted checks as NOT_RUN.
