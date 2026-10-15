# Native offline pension and ledger OCR smoke

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

New images have 1800px width, 64px font and generous margins/line spacing. New
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
