# P02 - Trellis per-layer instrumentation foundation

## Objective

Add the smallest useful opt-in instrumentation to Tesseract Trellis so later experiments can explain *where* work, state growth and pruning occur inside a shot instead of relying only on shot-level totals.

P02 is instrumentation, not optimisation. Decoder decisions must remain unchanged.

## Upstream revision

- Repository: `quantumlib/tesseract-decoder`
- Commit: `024db1d3b5b038f565c476dd1b51885271f7b0bf`
- Patch mechanism: `scripts/instrument/apply_p02_layer_stats.py`

The patcher refuses to run on another SHA or on a dirty upstream checkout. Every source edit is an exact-one textual replacement, so source drift fails closed instead of producing a guessed patch.

## Why this instrumentation is needed

The upstream Trellis decoder already exposes useful shot-level measurements:

- states expanded and merged;
- maximum beam size;
- maximum frontier width;
- kept-state distribution;
- aggregate expand, collapse, truncate and reconstruct times.

Those totals are insufficient to answer the systems questions we care about. Trellis is layer dependent and potentially highly irregular. Two shots with the same total time can have very different frontier growth, candidate pressure and pruning behaviour.

P02 therefore adds one optional raw record per completed layer.

## Raw fields

Each `TesseractTrellisLayerStats` record contains:

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

These fields intentionally avoid labels such as `duplicate_ratio`. Such ratios will be derived later with an explicit denominator because invalid branches, equivalent states and beam truncation are distinct phenomena.

## Low-perturbation design

- Instrumentation is disabled by default through `track_layer_stats=false`.
- The layer vector is empty when tracing is disabled.
- No new clock calls are introduced on the normal successful path. The patch reuses the timestamps already taken by upstream Trellis for aggregate phase timing.
- The existing aggregate timing positions are preserved on the successful path.
- No ranking, probability, beam-selection, state-transition or observable logic is changed.
- The compiled layer stores only two extra static sizes needed to report the current and surviving frontier widths.

This phase establishes semantic non-interference. Quantifying tracing overhead on realistic workloads belongs to the next instrumentation-validation step and must be done on controlled hardware, not GitHub-hosted runners.

## Regression test added by P02

`LayerStatsAreOptionalAndPreserveDecodeSemantics` decodes the same deterministic syndrome twice:

1. baseline configuration with tracing disabled;
2. identical configuration with per-layer tracing enabled.

The test requires:

- equal low-confidence state;
- equal predicted observable;
- equal observable probability within numerical tolerance;
- no layer records when tracing is disabled;
- one ordered layer record per retained Trellis fault/layer in the test model;
- sane monotonic relationships between frontier/state counts;
- the sum of per-layer expand/collapse/truncate time to equal the existing aggregate counters.

The full upstream test suite is then run after the focused Trellis test.

## Evidence artifact

GitHub Actions stores:

- `patch-report.json` with before/after SHA-256 for every modified upstream file;
- the exact generated `instrumentation.patch`;
- focused Trellis test log;
- full upstream test log;
- harness and upstream commit provenance;
- this phase document;
- `SHA256SUMS` over the evidence directory.

GitHub-hosted runner timings are explicitly **not** benchmark data.

## GO / NO-GO

P02a is **GO** only if:

1. the deterministic patch applies to the exact pinned SHA;
2. `git diff --check` passes;
3. `//src:tesseract_trellis_tests` passes with the new equivalence test;
4. the complete `//src/...` upstream test set passes;
5. the evidence artifact is generated.

Any semantic mismatch, source-anchor drift or test regression is a NO-GO for performance work.

## Next step after P02a

P02b will expose the validated records through a research-only machine-readable output path and measure instrumentation overhead on controlled hardware. Only after that will P03 run a workload matrix for characterization.

## Privacy boundary

This phase modifies only public upstream source through a public, reproducible research patch. It contains no collaborator-only data or unpublished measurements. Such material must remain outside the repository until its visibility is private and verified.
