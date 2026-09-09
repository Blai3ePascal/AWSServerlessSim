# P02b - Machine-readable Trellis layer trace

## Objective

Expose the P02a per-layer instrumentation through a deterministic, opt-in CLI output suitable for later scientific analysis without changing Trellis decoding semantics or introducing concurrent file writes in the decoder workers.

P02b is still instrumentation validation. It is **not** a performance benchmark and does not make performance claims from GitHub-hosted runners.

## Dependency and upstream pin

- Upstream: `quantumlib/tesseract-decoder`
- Commit: `024db1d3b5b038f565c476dd1b51885271f7b0bf`
- Required first step: apply the already validated P02a instrumentation with `scripts/instrument/apply_p02_layer_stats.py`
- P02b patcher: `scripts/instrument/apply_p02b_layer_trace_cli.py`

P02b refuses to run unless the P02a trace switch and layer-stat structure are present. It also refuses to touch a `tesseract_trellis_main.cc` that already differs from the pinned upstream file.

## CLI

New optional argument:

```text
--layer-stats-out PATH
```

Rules:

- absent: tracing remains disabled and no trace file is created;
- present: P02a `track_layer_stats` is enabled and the requested file is opened before decoding;
- `-` is rejected so JSONL cannot collide with prediction or stats output on stdout.

The path is recorded in the existing stats JSON as provenance when `--stats-out` is used.

## Threading and determinism

The current CLI parallelizes over shots. P02b deliberately does **not** write JSON from worker threads.

Each worker copies `decoder.layer_stats` only into `layer_stats_per_shot[shot_index]`, a location unique to that shot. After `parallel_for_shots_in_order` has completed, the main thread serializes indices `0..shot-1` sequentially.

This gives deterministic record ordering independent of thread scheduling and keeps stream synchronization out of the decoder hot path.

## JSONL schema v1

One JSON object is written per decoded shot:

- `schema_version`: `1`
- `record_type`: `tesseract_trellis_layer_trace`
- `shot_index`
- `detection_count`
- `low_confidence`
- `predicted_obs_mask`
- `num_layers`
- `layers`: ordered array of P02a records

Each layer contains:

- `layer_index`
- `active_frontier_width`
- `surviving_frontier_width`
- `beam_in`
- `used_pair_buckets`
- `states_after_collapse`
- `states_kept`
- `expand_seconds`
- `collapse_seconds`
- `truncate_seconds`

No derived duplicate/merge ratio is stored. Later analysis must define denominators explicitly.

## Deterministic semantic verification

`scripts/reproduce/p02b_verify_layer_trace.py` creates a tiny two-detector, one-observable DEM and four fixed `01` syndrome records. It runs the CLI twice with two threads:

1. ordinary decode, no tracing;
2. identical decode with `--layer-stats-out`.

The verifier requires byte-for-byte equality of:

- logical prediction output;
- binary observable-probability output.

It then validates:

- exactly one JSONL record per input shot;
- shot records remain in input order even with two worker threads;
- `detection_count` matches each input record;
- layer indices are contiguous and ordered;
- frontier and state-count relationships are sane;
- phase times are nonnegative;
- `--layer-stats-out -` is rejected with the expected diagnostic.

The verification summary explicitly records `benchmark_valid=false`.

## GO / NO-GO

P02b is **GO** only if:

1. P02a and P02b deterministic patchers apply to the exact pinned upstream revision;
2. `git diff --check` passes;
3. Trellis focused tests pass;
4. the instrumented CLI builds;
5. prediction and observable-probability bytes are identical with tracing off/on;
6. JSONL schema/order checks pass with `--threads 2`;
7. the complete upstream `//src/...` test set passes;
8. an evidence artifact with patches, logs, verification summary, provenance and SHA-256 manifest is uploaded.

A failure in any item is a NO-GO for P03 characterization.

## After P02b

P03 can begin only on workloads Trellis accepts without changing observable semantics. Initial characterization should vary beam width, ranking mode, syndrome/workload structure and shot distribution, and should analyze per-layer irregularity. Real benchmark numbers must come from controlled hardware, not GitHub-hosted runners.

## Privacy boundary

P02b uses only public upstream code and a synthetic one-observable correctness fixture. It contains no collaborator-only inputs, unpublished measurements or private parameter sets. The research harness repository remains public until visibility can be changed and verified.
