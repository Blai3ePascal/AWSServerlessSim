# P03 - Functional and structural Trellis characterization

## Objective

Use the validated P02b machine-readable layer trace on a small public corpus that Tesseract Trellis accepts natively, and establish reproducible structural differences across code families and ranking modes before any performance optimisation.

P03 is **not** a hardware benchmark. GitHub-hosted phase timings are preserved as raw evidence but explicitly marked non-interpretable for performance claims.

## Gate from P02b

P03 starts from the P02b-green harness commit:

- harness commit: `332712de70f31c33991242081c495c2f59c5d47a`
- P02b workflow run: `34406534227`
- P02b evidence artifact SHA-256: `2349eb832f373d753c5cc24945b901f7f92c7ecafc1628c7e955522e91af33f8`
- pinned upstream: `quantumlib/tesseract-decoder@024db1d3b5b038f565c476dd1b51885271f7b0bf`

The validated P02a and P02b patchers are reapplied to a clean checkout. P03 does not introduce a new decoder algorithm patch.

## Research questions for this phase

P03 asks only structural/compatibility questions:

1. Do several public one-observable code families run through current Trellis without changing logical-observable semantics?
2. How do frontier width and state population evolve across layers for different circuit families and sizes?
3. Do the three existing Trellis ranking modes expose materially different beam/state-retention patterns on the **same sampled shots**?
4. Which code/family combinations are suitable candidates for controlled-hardware characterization in the next phase?

P03 does not answer CPU/GPU speedup, latency, throughput, cost, cache behaviour or real-time feasibility.

## Public corpus

The manifest `research/experiments/configs/p03_public_one_observable_matrix.json` contains six public upstream circuits at `p=0.001`, X basis:

| Family | d=3 | d=5 |
| --- | --- | --- |
| Rotated surface code | q=17 | q=49 |
| Midout color code | q=9 | q=23 |
| Superdense color code | q=13 | q=37 |

Before invoking Trellis, the runner derives the logical-observable width from `OBSERVABLE_INCLUDE(n)` declarations and requires it to be exactly one. A mismatch is a hard failure. P03 never selects, combines, removes or rewrites observables.

Bivariate-bicycle circuits are intentionally excluded because the public q=144/180/216/288 cases validated in P01 contain 12/8/8/12 observables and current Trellis supports at most one.

## Controlled experimental factors

For every circuit:

- sampled shots: `3`
- sample seed: `20260909`
- threads: `2`
- beam width: `64`
- ranking modes:
  - `mass`
  - `future-detcost`
  - `future-active-detcost`

The sample seed is identical across ranking modes for a given circuit so each mode sees the same sampled syndrome sequence. This prevents workload sampling from being conflated with ranking-mode differences.

The matrix contains 18 decoder runs and 54 decoded shots in total.

## Measurements interpreted in P03

P03 summarizes only count/state fields that do not depend on runner clock quality:

- number of layer trace records;
- low-confidence shot count;
- layers per shot;
- active frontier width;
- surviving frontier width;
- beam size entering each layer;
- used pair-bucket count;
- states after collapse;
- states retained after truncation.

For each structural field, the runner records min, median, mean and max across all recorded layers of the run. A compact CSV additionally captures maxima useful for comparing the 18 cells.

## Timing policy

P02b JSONL contains per-layer `expand_seconds`, `collapse_seconds` and `truncate_seconds`, and the CLI stats contain additional timing fields. These bytes remain in the evidence artifact for debugging and provenance.

However:

- `benchmark_valid=false`
- `timing_metrics_interpretable=false`

No speedup, latency, throughput, percentile or crossover claim may be made from P03 Actions data. Controlled-hardware timings belong to P04.

## Runner contract

`scripts/reproduce/p03_trace_matrix.py` must:

1. verify the exact upstream SHA;
2. require the instrumented Trellis binary to exist;
3. verify every manifest circuit has exactly one observable;
4. hash every circuit used;
5. execute all circuit × ranking-mode cells with fixed experiment parameters;
6. preserve stdout, stderr, exact command, return code and timeout state per cell;
7. validate P02b JSONL schema and deterministic shot/layer ordering;
8. produce `p03-summary.json` and `structural-summary.csv`;
9. fail the workflow if any cell times out or returns non-zero.

Low-confidence shots are **recorded**, not automatically treated as a harness failure, because they may be an algorithm/configuration result worth studying.

## Evidence artifact

The P03 workflow stores:

- exact public corpus manifest;
- exact applied P02a+P02b `instrumentation.patch`;
- focused Trellis test log;
- build log;
- per-cell decoder commands, stdout/stderr, predictions, observable probabilities, stats and JSONL traces;
- `p03-summary.json`;
- `structural-summary.csv`;
- harness/upstream provenance;
- P03 phase document;
- diagram source and rendered SVG;
- SHA-256 manifest over the artifact.

## GO / NO-GO

P03 is **GO** for controlled-hardware characterization only if:

1. the exact pinned upstream checkout is used;
2. P02a+P02b instrumentation applies cleanly and `git diff --check` passes;
3. focused Trellis tests pass;
4. the instrumented CLI builds;
5. all six circuits are confirmed as exactly one observable;
6. all 18 functional runs complete without timeout/non-zero exit;
7. all JSONL traces pass schema and order validation;
8. the evidence artifact is uploaded and checksummed.

A code family may still be a poor P04 candidate if it consistently produces low-confidence outcomes or trivial structural traces; that is a scientific selection result, not something to hide.

## Next phase

P04 will move performance measurement to controlled hardware. It should begin with the P03 cells that show meaningful structural pressure and then measure repeated-run distributions, CPU affinity, memory, cache/microarchitectural counters and eventually CPU/GPU comparisons. P04 must preserve the exact circuit hashes, seeds and decoder configuration selected from P03.

## Privacy boundary

Everything committed in P03 is derived from public upstream circuits and public decoder code. No collaborator-only circuit, unpublished benchmark, private parameter choice or unpublished claim is committed while `Blai3ePascal/AWSServerlessSim` remains public.
