# P04 benchmark-harness validation

## Evidence source

- Workflow run: `34449695689`
- Harness commit: `78f7fcc2aa4912ed7891536203ae76d259714b46`
- Artifact: `tesseract-p04-harness-validation-34449695689`
- Artifact SHA-256: `6b84813cfe5bac1b98a9df2719b0459846fb294e9de558cbf3b28f0912704bf6`

## Result

The P04 harness-validation workflow passed all steps:

- exact upstream checkout;
- deterministic P02a/P02b instrumentation;
- focused Trellis regression tests;
- optimized `-c opt` Trellis build;
- validation-mode execution and schema checks;
- explicit proof that benchmark mode refuses to execute in GitHub Actions;
- evidence packaging and checksum generation.

The validation artifact confirms:

- `mode = validate`;
- `benchmark_valid = false` in both manifest and environment records;
- CI detection includes `CI=true` and `GITHUB_ACTIONS=true`;
- upstream SHA is exactly `024db1d3b5b038f565c476dd1b51885271f7b0bf`;
- fixture hashes and raw repetition files are preserved.

The upstream checkout is intentionally dirty *after* instrumentation because P02 modifies four files reproducibly. That dirty state is captured as evidence and is not an uncontrolled source modification; the patch reports and generated diff identify it exactly.

## Interpretation

This run validates the benchmark procedure, not Trellis performance. Its timing values must not appear in a paper, comparison table, speedup claim or hardware-selection model.

The methodological separation is now enforced in code rather than by convention: a recognized CI environment cannot produce `benchmark_valid=true` through the supported benchmark mode.

## Portability hardening after validation

Two practical hardening changes are made after this validation:

1. Linux `perf` is preflighted before the controlled run. If counters are unavailable because of permissions, the reason is preserved and the benchmark continues without hardware counters instead of failing the primary latency experiment.
2. A native PowerShell preparation wrapper is provided for controlled Windows hosts. It performs the same SHA/cleanliness checks, applies the same instrumentation, runs the same tests and optimized build, executes the same Python benchmark harness, and writes a SHA-256 manifest. Linux-only perf counters are not requested from that wrapper.

## Decision

**P04 harness: GO. P04 performance experiment: pending controlled-host execution.**

No P05 optimization or speedup claim should be accepted until a `benchmark_valid=true` P04 artifact from a controlled host has been reviewed.
