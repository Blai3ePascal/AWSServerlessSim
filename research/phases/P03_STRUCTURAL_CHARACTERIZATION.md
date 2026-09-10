# P03 - Structural Trellis characterization

## Objective

Use the validated P02 layer trace to characterize how Trellis work evolves across layers and decoder configurations before attempting any optimization.

P03 deliberately separates two kinds of evidence:

1. **Structural evidence**, which is valid on a GitHub-hosted runner: frontier widths, beam sizes, collapsed-state counts, retained-state counts, layer-to-layer irregularity, and deterministic relationships between configurations.
2. **Performance evidence**, which is *not* valid on a shared GitHub runner: absolute latency, throughput, CPU utilization, cache behavior, memory bandwidth, and tail-latency claims.

The P03 GitHub workflow therefore records timing fields only because they are part of the P02 schema, but marks the complete experiment `benchmark_valid=false` and excludes timing from every derived conclusion.

## Upstream pin and instrumentation

- Upstream: `quantumlib/tesseract-decoder`
- Commit: `024db1d3b5b038f565c476dd1b51885271f7b0bf`
- P02a patch: `scripts/instrument/apply_p02_layer_stats.py`
- P02b patch: `scripts/instrument/apply_p02b_layer_trace_cli.py`

P03 does not modify the Trellis algorithm beyond those already validated instrumentation patches.

## Public/synthetic workload policy

The research harness repository is still public. P03 therefore uses only deterministic synthetic DEMs created by the experiment script itself. No collaborator-only circuit, unpublished parameter set, private measurement, or unpublished claim is committed.

The fixtures are not intended to model a specific device. They are controlled probes designed to exercise distinct Trellis structures:

- `chain4`: narrow, mostly local detector propagation;
- `branch6`: overlapping faults that create branching and state collapse;
- `retire8`: a wider active frontier with staggered detector retirement.

Every fixture has at most one logical observable, so Trellis accepts it without changing observable semantics.

## Configuration matrix

For each fixture P03 runs all combinations of:

- beam width: `4`, `16`, `64`;
- ranking mode: `mass`, `future-detcost`, `future-active-detcost`;
- four deterministic syndrome records per fixture;
- two identical repetitions of every configuration.

All runs use one decoder thread. Inter-shot scaling is intentionally excluded from this phase so structural differences are not mixed with scheduling effects.

## Structural metrics

For every shot the analysis derives only count-based metrics:

- number of recorded layers;
- maximum and mean active frontier width;
- coefficient of variation of active frontier width across layers;
- maximum `beam_in`;
- maximum and total `states_after_collapse`;
- coefficient of variation of `states_after_collapse` across layers;
- mean and minimum retention fraction, defined explicitly as `states_kept / states_after_collapse` when the denominator is nonzero;
- mean collapse expansion factor, defined as `states_after_collapse / beam_in`;
- low-confidence flag and predicted observable.

The term `duplicate ratio` is intentionally not used. A reduced number of collapsed states can arise from equivalent-state collapse, invalid branches, or other structural effects, and P03 does not conflate them.

## Determinism contract

Each configuration is executed twice. P03 strips the three timing fields from every layer and requires the remaining JSON trace to be byte-equivalent after canonical JSON serialization. Prediction files must also be byte-identical.

This verifies that structural traces are stable enough to serve as experimental input for later analysis while allowing wall-clock timing to vary naturally.

## Derived outputs

The P03 artifact contains:

- generated synthetic DEMs and syndrome files;
- raw JSONL trace for every matrix point and repetition;
- prediction output for every run;
- per-run command metadata;
- `shot_metrics.csv` with one row per shot/configuration;
- `configuration_summary.csv` aggregated over the four shots;
- `summary.json` with matrix size, deterministic-equivalence checks, and extrema;
- provenance and SHA-256 manifests.

## GO / NO-GO

P03 structural characterization is **GO** if:

1. P02a/P02b patches apply cleanly to the pinned upstream SHA;
2. the instrumented Trellis CLI builds;
3. all 27 configuration points complete twice;
4. predictions and timing-stripped traces are deterministic across repetitions;
5. all structural invariants in the P02 schema remain valid;
6. `shot_metrics.csv` and `configuration_summary.csv` are generated without NaN/undefined count metrics;
7. the focused Trellis test target still passes;
8. the evidence artifact is uploaded.

A failure is a NO-GO for optimization until explained.

## What P03 can decide

P03 can tell us whether there is meaningful layer-to-layer irregularity and whether beam/ranking choices change the amount and distribution of structural work. It can identify candidate phases and workload shapes worth profiling on controlled hardware.

P03 cannot tell us whether CPU, GPU, CUDA, multinode, cloud, or serverless is faster. Those decisions require P04 controlled-hardware measurement.

## Next phase

P04 should run the same trace schema on controlled hardware and add:

- repeated wall-time distributions;
- CPU counters and memory metrics;
- RSS/peak allocation measurements;
- thread-count sweeps for intra-shot work if implemented;
- later, GPU metrics on a system with a real supported backend.

Absolute latency and throughput claims begin only there.
