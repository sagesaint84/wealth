# Native offline pension and ledger OCR smoke

Second hotfix (2026-10-15): run 38706993038 failed exact party recognition in
bank PNG on both platforms, after image/Chromium/pension OCR and ledger type,
review-state and two-row checks. No amount/balance or later ledger document
completion is inferred from that run.

The ledger worker now opts into bounded line OCR after the full-page TSV. The
common decoder invokes it on that exact oriented/scaled page before replacing
its pixels for the next PDF page. Pension does not opt in. No fixture values or
smoke assertions change. Crops are source pixels, never synthesized text.
Page/TSV sizes must match; source width >=320px, <=16M pixels, glyph height >=12,
unclipped disjoint line bounds (<=3000x220px) and source confidence >=30 are
required. A single fresh PSM 7 TSV line needs confidence >=90 and valid geometry.
Actual normal word spaces are preserved; no global Hangul space removal occurs.
Conflicting valid numbers/signs, damaged signs, multiple amounts or unclear
results invalidate the candidate rather than selecting a convenient value.

Limits are document-wide: at most 8 line calls, cumulative 12s, max 3s/call and
20KB output/call; all decoder commands share a 55s deadline. Exceeding a limit
fails closed. Existing 75s coordinator group timeout, CPU 60s, memory 512MiB
and concurrency 2 remain. Crop files are 0600 and unlinked in finally, including
tool errors/timeouts. Public responses still contain only reviewed candidates;
raw page/crop text and source paths are not logged. No financial storage is added.
Local tests are mock/pixel-geometry tests; real native accuracy requires the new
commit's CI. The previous snapshots below are historical.

Final local isolated regression: **278 passed / 0 failed / 0 skipped / 2 warnings**,
134.14s (245 existing + 33 new cases). Python syntax/diff checks passed and owned
test directories were removed. JS is unchanged. This is not real local OCR;
the new commit's native CI remains the authority for all four exact ledger cases.

PR #147 hotfix status (2026-10-15): [run 38705054241](https://github.com/sagesaint84/wealth/actions/runs/38705054241)
failed on both native platforms in the first bank PNG type assertion, after
successful image/Chromium and pension PNG/PDF worker checks. The coordinator
already validates `review_required`; the combined error did not identify the
type's structural cause. No original OCR text was logged, so the complete native
cause is not established by those logs.

Synthetic TSV reproduces the date gate failing for `10 월 14 일`. The parser now
accepts horizontal unit spacing without inferring a year, and leaves syllable-split
parties unverified. Numeric/sign repair remains forbidden. Ledger fixtures alone
use the public NanumGothic Bold face at 80px, with whitespace between transaction
amounts and their currency unit; numbers, exact expectations and party names are
unchanged. The pension fixture retains its original font/layout.

Type and review-state failures are separate. On a type mismatch only, a bounded
real decoder subprocess reports allowlisted Boolean date/money/header/TSV-line
evidence. It never logs OCR text or preview JSON. All exact assertions remain.
The new commit's native run must pass all four ledger inputs before claiming
native ledger OCR success. Local Windows tests are not actual OCR execution.
No storage/IPO OCR or deployment is introduced. The following O1.2 pre-PR snapshot
is historical; see the new run for the final hotfix result.

Hotfix local isolated regression: **245 passed, 0 failed, 0 skipped, 2 warnings**
(137.58s), preserving the 221 existing checks and adding 24 cases. Python syntax
and diff checks passed; owned test directories were removed. JS is unchanged.
This is not native OCR evidence; the new commit's AMD64/ARM64 checks are separate.

O1.2 development status (2026-10-15): the bank/card smoke below is implemented,
but actual native **amd64 and arm64 execution is PENDING**. Local Windows contract
tests use synthetic inputs and mock tool/preview responses; Tesseract is absent.
They are not evidence of Korean OCR recognition success. Production remains
v2.0.2 according to the user's completed PR #145/#146 rollout records; this
OCR branch extension has not been deployed. The existing operating image is
`ghcr.io/sagesaint84/wealth:d98336a` (user-provided record; no server access here).
This is the pre-PR validation snapshot; subsequent native results belong to
the Draft PR/Actions run, not to the historical pension-only success below.

The existing Toss auth PR workflow builds one image on each native GitHub-hosted
Linux runner (`ubuntu-24.04` / amd64, `ubuntu-24.04-arm` / arm64). It then runs
this smoke against that same loaded image. No QEMU, publication or credentials
are used; the main image publication workflow is unchanged.

The runner installs Ubuntu's public `fonts-nanum` package. `generate_fixtures.py`
uses NanumGothic and Pillow to generate public fictional inputs under
`$RUNNER_TEMP`. No personal fonts or documents are used. Each PDF is image-only;
the ledger smoke also checks `pdftotext` produces no text before invoking OCR.

| Inputs | Synthetic source contract |
| --- | --- |
| `synthetic.png`, `synthetic.pdf` | Existing pension phrase/amount/month/date fixture; unchanged |
| `bank.png`, `bank.pdf` | Dark background, yearless October 14/13, two transactions: +1,234,567 and -234,567 KRW; separate balances 11,234,567 and 11,000,000; top current balance 11,000,000 |
| `card.jpg`, `card.pdf` | White background, yearless October 14/13, fictional cafe/bookstore approvals of 12,345 and 23,456 KRW; top monthly total 35,801 |

Public ledger values use deliberately fictional digit patterns and are not
copied from a user's screenshot. Exact expectations were updated together;
they still reject every wrong digit or sign instead of accepting OCR mistakes.

Ledger images have 1800px width, 80px bold font and generous margins/line spacing. New
fixture files are explicitly mode 0644 so the existing non-root container can
read the read-only mount. Nothing is generated or committed in the repository.
The existing generator command and workflow already include `ops/pension-ocr/**`
in their trigger, so no workflow, Dockerfile, package or extra image build is needed.

The container has no network, a read-only root filesystem, no capabilities,
and only the synthetic fixture directory mounted read-only. Intermediates live
in private temporary directories in container-local `/tmp`. The smoke checks
architecture, Poppler, Korean/English/OSD Tesseract data, actual Korean recognition,
and the existing production `national_pension_document` worker including its
resource limits, JSON date contract and human-review status. These checks and
their exact expected values remain in place.

After the pension checks, four ledger cases call the real
`ledger_document_import.preview()` coordinator. It starts the production
`ledger_document` worker, which uses common `document_extraction` and real
Tesseract TSV/Poppler. The smoke requires exactly two rows for each input,
exact source party names, amount strings, signs/directions, bank balances and
times, October month/day with year and complete date null, `year_missing`,
`review_required`, owner/account null and OCR coordinates. Card approvals retain
unknown direction and do not become income. Extra total/balance rows or any
wrong digit fail; OCR output is never used to derive a replacement expectation.

Each ledger case uses a private directory (0700), temporary input copies (0600)
and explicitly isolated synthetic data. Sentinel ledger/portfolio files must
remain byte-identical and no user/other data paths may appear. No actual user
directory, financial API, persistence/apply path or portfolio lookup is used.
The coordinator's input directory must be empty on return, and the outer smoke
copies are removed before PASS is printed. Cleanup also runs on failure. The
read-only runner fixtures themselves remain owned by the CI job lifecycle;
the smoke never changes or deletes that mount.

Missing tools, wrong architecture, a PDF text layer, recognition errors, worker
failures, unexpected financial/user paths or cleanup failure fail the job. Logs
contain only fixed diagnostic/success messages, not raw OCR, original documents
or preview JSON. Fixtures/results are not uploaded as artifacts. Existing
`--network none --read-only --cap-drop ALL --security-opt no-new-privileges`,
non-root UID and private container `/tmp` settings remain unchanged. The smoke
runs serially; temporary environment/temp-root scoping is restored after each
case. Linux worker timeout/process cleanup comes from the existing coordinator.

This is an environment/decoder smoke, not approval to deploy, and does not
replace the synthetic import API, validation, ownership and RMW regression tests.
Confirmed on 2026-10-14: [Actions run 38493482329, attempt #8](https://github.com/sagesaint84/wealth/actions/runs/38493482329/attempts/8)
succeeded on both native amd64 and arm64 jobs, including image build,
network-disabled Chromium smoke, Poppler, kor/eng/osd language data, synthetic
Korean PNG/PDF OCR and the production document worker smoke. No real personal
pension documents were used. Those historical native checks have not been rerun for O1.2.

Historical handoff before the PR #144 rollout recorded Draft/unmerged and
production v2.0.1. That is not the current operating status: the later user
records confirm v2.0.2 rollout, including PR #145/#146. The historical native
CI success above covers the pension smoke at that time, not the new O1.2
ledger cases. Document-format recognition rates, real personal document
accuracy, production CPU/memory and image-size measurements are not established.

Before O2 storage work, run the unchanged PR workflow on both native platforms
and investigate any exact-value failure without changing the parser or
expectations to accept an OCR error. General bank/card format coverage,
low-resolution/cropped inputs, duplicate reconciliation and owner/account
confirmation remain separate acceptance work. No saving or IPO OCR is added here.
