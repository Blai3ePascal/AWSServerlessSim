# P04 - Controlled-hardware CPU profiling

## Objective

Measure Tesseract Trellis latency and resource behaviour on a controlled CPU host using the deterministic P03b beam-pressure workloads. This is the first phase in which absolute performance numbers may become scientifically interpretable.

P04 does **not** yet implement intra-shot parallelism. It establishes the single-thread CPU baseline against which later CPU-parallel, GPU and distributed variants must be compared.

## Why P04 cannot be a GitHub Actions benchmark

Shared CI runners have variable placement, frequency, contention and virtualization. Their timings are useful for smoke tests only. The P04 benchmark runner therefore has two modes:

- `validate`: allowed on CI and used only to prove the harness executes and produces a valid schema;
- `benchmark`: refuses to run when common CI environment variables are present and emits `benchmark_valid=true` only for an explicitly labelled controlled host.

A user can still run `validate` anywhere. Performance claims require `benchmark` mode.

## Measurements

For each fixture / beam / ranking configuration P04 records:

1. **Decoder-internal time** from upstream `--stats-out` / `total_time_seconds`. This is especially useful because upstream starts timing after per-thread decoder construction and measures `decode_shot` itself.
2. **End-to-end wall time** around the executable, which includes process startup, file parsing, decoder construction, output and scheduling overhead.
3. **Peak RSS** through GNU `/usr/bin/time -v` when available.
4. **Optional Linux perf counters** when `perf` is installed and usable:
   - cycles;
   - instructions;
   - branches;
   - branch-misses;
   - cache-references;
   - cache-misses;
   - task-clock.
5. Structural context from the same fixture metadata: beam, ranking, detector count and number of shots.

The primary CPU-latency metric for P04 is decoder-internal microseconds per shot at `--threads 1`. End-to-end time is reported separately and must never be substituted silently.

## Workload amplification

The four deterministic syndrome records of each P03b fixture are repeated to create a larger event file. Repetition count is explicit in the run manifest. This reduces process-start noise while preserving an exactly reproducible syndrome mixture.

P04 does not use sampled random syndromes yet. A later phase can add seeded sampling once a public, semantically suitable one-observable circuit corpus is selected.

## Repetitions and warm-up

A controlled benchmark performs:

- configurable warm-up executions that are not included in statistics;
- at least 10 measured repetitions by default;
- one decoder thread;
- a pinned upstream commit and deterministic P02 instrumentation patch;
- identical event bytes for every compared configuration.

The harness reports median, p95, minimum, maximum and median absolute deviation for decoder time per shot and wall time per shot. Raw repetitions are retained.

## Environment capture

Every benchmark result directory contains:

- hostname and user-supplied machine label;
- UTC timestamp;
- OS/kernel and architecture;
- CPU model, sockets, cores and threads when `lscpu` is available;
- memory summary;
- governor/frequency information when readable;
- Bazel version;
- upstream SHA and dirty state;
- harness SHA when available;
- compiler version where discoverable;
- `perf` availability and permission status;
- exact command lines;
- fixture SHA-256 values.

The machine label is descriptive, not trusted evidence by itself; the captured environment is the evidence.

## Statistical policy

P04 is an engineering characterization rather than a hypothesis-test paper experiment. It therefore preserves all raw repetitions and reports robust descriptive statistics instead of hiding variation behind a mean.

No result is accepted as `benchmark_valid=true` if:

- the run occurs in recognized CI;
- fewer than the requested repetitions finish;
- the upstream SHA differs from the pinned revision;
- any compared execution returns nonzero;
- the workload bytes differ across repetitions;
- the host changes during the run according to captured identity fields.

## GO / NO-GO

P04 is GO to CPU optimization/intra-shot work if controlled-host data shows a sufficiently expensive and repeatable Trellis workload to profile, and if phase decomposition / structural evidence identifies a meaningful compute region rather than process overhead dominating the experiment.

P04 is not a promise that intra-shot parallelization will help. If decoder time is too small, dominated by serial collapse/truncation, or unstable relative to measurement noise, that is a valid NO-GO result and the project should move to larger public/private workloads before optimizing.

## Relationship to later phases

- P05: CPU intra-shot parallelism and resource-allocation study, conditional on P04.
- P06: CPU architecture/NUMA/SIMD ablations where justified.
- P07: controlled Metal benchmark and CUDA/NVIDIA experimental backend.
- P08: adaptive backend/resource selection only if measured crossovers exist.
- P09: multinode only if local work per layer is large enough to amortize communication.

## Privacy boundary

The P04 harness and P03b synthetic workloads are public-safe. Private collaborator workloads and unpublished measurements must not be committed while `AWSServerlessSim` remains public.
