# Native offline pension OCR smoke

The existing Toss auth PR workflow builds one image on each native GitHub-hosted
Linux runner (`ubuntu-24.04` / amd64, `ubuntu-24.04-arm` / arm64). It then runs
this smoke against that same loaded image. No QEMU, publication or credentials
are used; the main image publication workflow is unchanged.

The runner installs Ubuntu's public `fonts-nanum` package. `generate_fixtures.py`
uses NanumGothic and Pillow to generate a public fictional Korean PNG and a
one-page scanned PDF under `$RUNNER_TEMP`. No personal fonts or documents are
used. The PDF deliberately has no text layer, exercising the OCR fallback.

The container has no network, a read-only root filesystem, no capabilities,
and only the synthetic fixture directory mounted read-only. Intermediates live
in private temporary directories in container-local `/tmp`. The smoke checks
architecture, Poppler, Korean/English/OSD Tesseract data, actual Korean recognition,
and the production `national_pension_document` worker including its resource
limits, JSON date contract and human-review status. It does not invoke portfolio
lookup, preview persistence or import apply. Missing tools, wrong architecture,
recognition errors or worker failures fail the CI job. Raw OCR output and
fixtures are not uploaded as artifacts.

This is an environment/decoder smoke, not approval to deploy, and does not
replace the synthetic import API, validation, ownership and RMW regression tests.
Confirmed on 2026-10-14: [Actions run 38493482329, attempt #8](https://github.com/sagesaint84/wealth/actions/runs/38493482329/attempts/8)
succeeded on both native amd64 and arm64 jobs, including image build,
network-disabled Chromium smoke, Poppler, kor/eng/osd language data, synthetic
Korean PNG/PDF OCR and the production document worker smoke. No real personal
pension documents were used. Codex did not rerun these checks for this documentation update.

PR #144 remains Draft/unmerged as checked on that date. Oracle ARM64 v2.0.2
deployment and live verification have not been performed; production remains
v2.0.1 according to the user. Document-format recognition rates, real personal
document accuracy, production CPU/memory and image-size measurements are not
established by this CI success.
