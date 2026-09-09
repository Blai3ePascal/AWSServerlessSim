# Tesseract / Trellis reproducibility baseline

This branch is an isolated research harness. It does **not** modify the decoder implementation.

## Purpose

Establish a reproducible, evidence-first baseline for `quantumlib/tesseract-decoder` before any optimization, parallelization, GPU work, serverless deployment, or algorithmic change.

Pinned upstream revision:

- repository: `quantumlib/tesseract-decoder`
- commit: `024db1d3b5b038f565c476dd1b51885271f7b0bf`

## P00 exit criteria

P00 is complete only when a clean machine can:

1. fetch the exact upstream commit;
2. verify the checkout SHA;
3. build the original Tesseract and Trellis CPU executables;
4. run the upstream Bazel test suite, including Trellis tests;
5. preserve environment information, logs, exit codes and checksums as an artifact;
6. document any failure without silently patching upstream.

GitHub-hosted runners are used for build/test reproducibility only. Their timing results are **not** treated as scientific performance measurements.

## Correctness rules for later phases

- No optimization is accepted before a serial reference exists.
- Real `.stim` / DEM inputs are preferred over mocks for scientific regression tests.
- `low-confidence` outcomes must remain visible and must not be silently counted as success.
- Every discovered bug becomes a failing regression test before it is fixed.
- Parallel CPU/GPU implementations must be compared against the serial reference per input, not only by aggregate LER.
- Trellis multi-observable support must not be invented locally until the intended semantics are confirmed with the collaborators.

## Layout

- `manifest/upstream.json`: pinned upstream provenance.
- `docs/KNOWN_LIMITATIONS.md`: verified constraints that affect the baseline.
- `scripts/bootstrap_tesseract.sh`: exact checkout helper for local/CI use.
- `scripts/capture_environment.sh`: records execution environment.
- `scripts/run_baseline.sh`: build/test runner with persistent logs and exit codes.
- `.github/workflows/tesseract-baseline.yml`: clean GitHub Actions validation.

The workflow uploads the generated `research/results/` directory as a ZIP artifact even when a build or test fails, so failures remain inspectable.