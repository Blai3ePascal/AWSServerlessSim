# P00 - Reproducible upstream baseline

## Question

Can the pinned public Tesseract revision be built and tested on a clean machine without changing decoder source code?

## Frozen input

`quantumlib/tesseract-decoder@024db1d3b5b038f565c476dd1b51885271f7b0bf`

## Procedure

1. Checkout the exact SHA.
2. Record OS, CPU, memory and tool versions.
3. Build `//src:tesseract` and `//src:tesseract_trellis`.
4. Run `//src:tesseract_trellis_tests` explicitly.
5. Run the same Bazel test command used by upstream CI at this revision: `bazel test src/... //docs:tutorial_jupytext_sync_test`.
6. Save stdout/stderr, exit codes, provenance and SHA-256 checksums.
7. Upload the evidence directory regardless of pass/fail.

## PASS

- checked-out SHA equals the frozen SHA;
- both CPU decoder binaries build;
- Trellis-specific tests pass;
- complete upstream test command passes;
- evidence artifact is generated.

## FAIL

Any build/test failure is a valid P00 result if preserved reproducibly. Do not patch the decoder in this phase.

## Not measured in P00

- decoder speed;
- throughput;
- 1 ms real-time feasibility;
- CPU/GPU crossover;
- scientific LER reproduction;
- multi-observable Trellis behavior.

Those require controlled inputs and, for timing, controlled hardware.
