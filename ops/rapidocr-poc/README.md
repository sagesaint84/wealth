# RapidOCR unified native PoC — not a production integration

APP_VERSION remains 2.0.2. Base: `da759990ba606b1063f37aff5479c05fc542c3dc`.
PR #147 and both existing worktrees must remain unchanged. No merge or deployment
is authorized. A successful experiment does not authorize adoption.

## Pinned setup

- Native Ubuntu 24.04 x86_64 / aarch64 runners; Python 3.11, Debian Bookworm
  experiment container. No QEMU and no publishing.
- RapidOCR 3.9.2 (Apache-2.0), ONNX Runtime 1.24.3 (MIT).
- PP-OCRv5 mobile detection, Korean PP-OCRv5 mobile recognition, PP-OCRv4
  mobile 0/180 orientation classifier enabled. This is not arbitrary-angle
  deskew. All model URLs, SHA256 and upstream license references: `models.json`.
- Korean recognition SHA256:
  `cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b`.
- Both 26-package Linux CPython 3.11 wheel locks were downloaded and their
  SHA256 compared with official PyPI release metadata during preparation.
  Container installs use `--require-hashes`, then `pip check`. Missing ARM64
  wheels fail; no alternative version substitution.
- Python image and apt packages are not snapshot-locked; their variability is
  a known reproducibility limitation, independent of the pinned OCR wheels/models.
- Models and all data are prepared before inference. Only the preparation
  container has network access. Native inference uses `--network none`.

## Execution after explicit Git/CI authorization

The dedicated workflow targets a Draft PR against
`codex/v202-ledger-ipo-ocr-import`, not main. It builds only this Dockerfile,
prepares a temporary model/fixture bundle, and runs:

```sh
docker buildx build --platform linux/amd64 -f ops/rapidocr-poc/Dockerfile \
  --tag wealth-rapidocr-poc:amd64 --load .
# Prepare using the same image; output path must not already exist.
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$RUNNER_TEMP/rapidocr-poc,dst=/out" \
  --entrypoint python wealth-rapidocr-poc:amd64 \
  /app/ops/rapidocr-poc/prepare.py --output /out/bundle
python ops/rapidocr-poc/run.py --machine x86_64 \
  --image wealth-rapidocr-poc:amd64 --bundle "$RUNNER_TEMP/rapidocr-poc/bundle"
```

ARM64 uses its native runner, `linux/arm64`, `aarch64`, and its corresponding tag.
The runner checks uname, Python architecture, container architecture and image
platform. No production entrypoint or secrets are used.

## Measurements and interpretation

The launcher applies **RLIMIT_AS 512MiB before heavy imports**, CPU 60 seconds,
file size 20MiB and no core dumps. Each document has a 55-second work budget,
externally killed after 75 seconds. Model loading is included in that budget.
The 2048MiB profile is diagnostic only; it never repairs a failed 512MiB gate.
Both profiles run independently. Each container is capped at 3GiB, 128 PIDs,
with a 256MiB tmpfs. Limits are not changes to Wealth's operating limits.

Worker OS peak RSS (KiB), sampled process-tree RSS/VMS (bytes), cgroup v2
`memory.peak` (bytes), model import/load, first and repeated inference times
are separate metrics. Process-tree peaks are sampled, not exact maxima.
The cumulative cgroup peak includes the controller and sequential work;
concurrent-two-worker sampled peaks are reported separately. Missing cgroup
metrics fail rather than silently becoming zero. Worker exit without a valid
report is `WORKER_EXIT_UNCLASSIFIED`; it is **not automatically called OOM**.

Independent document subprocesses collect remaining results after normal
failures. A financial-write or offline violation stops unsafe follow-up work.
Any required FAIL/BLOCKED/PENDING makes the job fail. Diagnostic profile
failures are also retained. No OCR strings, financial values, full preview
JSON, model files or input images are logged or uploaded as artifacts.

## Accuracy and parser preservation

Existing public fictional bank/card inputs are reused unchanged: PNG/JPG,
scanned PDF and 1800/390/221/135px. Synthetic cancellation, refund and
duplicate-looking rows add semantic coverage. Reconstructed line boxes use
geometry only and preserve OCR text; no syllable joining, comma repair,
sign invention, or amount expectation is used to construct parser input.

Raw engine metrics are distinct from the unchanged Wealth ledger parser's
exact transaction checks. Original/390px require exact rows, dates, parties,
amounts, signs and balances. Below 320px, original parser safety rejection is
required; incorrect values cannot be accepted even with a review label.
Owner/account remain null, yearless dates remain unknown, all candidates
remain review_required, and summary totals are not individual transactions.

National pension history **and** payment-certificate documents have separate
PNG/PDF tests, plus two-page files with distinguishable dates for order checks.
The actual `parse_text(..., ocr=True)` must yield the exact original smoke
expectations, ISO dates and human-review status. No annual or personal expense
inference is added. Financial reader/writer entrypoints are guarded before
parser import; any invocation fails. `/tmp/finance` must stay absent.

No IPO parser is implemented. A future approved integration must use one
common engine for pension, ledger and future IPO with separate domain parsers.
Tesseract is neither removed nor retained as an approved permanent hybrid.

## Local versus native evidence

Local tests cover the harness, strict comparisons, workflow scope, locks,
checksum failure and the real pension text parser with synthetic text.
They are not native OCR evidence. Existing 329 tests are unchanged.

At initial implementation: Linux AMD64/ARM64 execution **PENDING**; 512MiB,
RSS/VMS/cgroup, OCR/PDF and concurrent-worker outcomes **PENDING**.
Local Windows preparation: **21 unit tests passed**, Python syntax and YAML
parsing passed. Official model download/checksums and generation of 19 synthetic
cases passed. These checks did not run native Linux inference or the existing
329-test suite.
The first real Actions result must be reported independently, including failures.
Do not substitute Windows memory measurements for Linux address-space limits.

All temporary CI data belong to `$RUNNER_TEMP/rapidocr-poc`; cleanup runs even
on failure. Per-case temporary raster files are checked after context cleanup.
Policy-blocked old local Temp directories are never touched.
