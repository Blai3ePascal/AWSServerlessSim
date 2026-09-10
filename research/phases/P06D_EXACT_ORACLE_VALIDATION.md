# P06d — Independent exact-oracle validation

## Objective

Validate the public-lineage P05 reference and the modern P06 multi-observable port against an implementation-independent exhaustive probability oracle. P06d tests correctness of complete logical-mask joint-MAP decisions; it is not a performance benchmark and does not claim equivalence to any private implementation.

## Frozen code inputs

- P05 public ancestor: `56996facf54c25e6c08fed19d8902f40e1971f55`.
- P06 modern base: `024db1d3b5b038f565c476dd1b51885271f7b0bf`.
- Research harness parent: P06c commit `60d7a4478d425c9bcab0de53da0e753708a609c3`.

## Corpus

Reuse the deterministic P06c generator: 80 DEMs and 640 syndrome cases spanning 2, 8, 12, 32, and 64 observables, four probability regimes including 0.001, four seeded models per regime, three detectors, and all eight detector syndromes. The decoder beam width remains 65536 to suppress pruning as the variable under study.

## Exact oracle

For each generated DEM, independently enumerate every assignment of its Bernoulli error mechanisms. For each assignment:

1. multiply the present/absent Bernoulli probabilities;
2. XOR detector masks;
3. XOR complete observable masks;
4. accumulate probability by `(detector_syndrome, observable_mask)`.

For each syndrome, choose the complete observable mask with maximum accumulated probability. Exact ties are resolved by the numerically lower mask for deterministic reproducibility. The oracle does not link, import, execute, or derive decisions from either Tesseract decoder.

## Acceptance contract

P06d passes only when all prior P05/P06 correctness suites remain green; corpus shape is exactly 640 cases; every syndrome is reachable; both decoder dump drivers produce exactly 640 rows; and P05 and P06 each match the independent oracle exactly on execution status, observable count, predicted complete logical mask, and low-confidence flag for every case.

Any mismatch is retained in the evidence artifact with its case identifier, generated DEM, seed/fault metadata, oracle result, and both decoder outputs. Evidence includes pinned SHAs, environment metadata, patch diffs, generated corpus, exact-oracle table, decoder tables, comparison summary, mismatch table, logs, and SHA-256 checksums.

## Scope of claims

A green result supports functional correctness of the tested joint-MAP multi-observable semantics for this exhaustive small-model corpus, including the 64-observable representation boundary. It does not establish equivalence with an inaccessible private decoder, does not validate large-code pruning behaviour, and does not establish runtime performance. GitHub-hosted timing data are explicitly non-interpretable as scientific benchmark measurements.
