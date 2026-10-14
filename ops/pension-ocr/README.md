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
These additions have not been executed by Codex; both native CI jobs must be
run and reviewed separately.
