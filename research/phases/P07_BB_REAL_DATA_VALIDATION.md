# P07 — Real bivariate-bicycle data validation

## Status

P07 starts only after the P06 modern multi-observable correctness contract is green.
It does **not** replace P05/P06 and it does not claim performance results.

Frozen public upstream:

- repository: `quantumlib/tesseract-decoder`
- commit: `024db1d3b5b038f565c476dd1b51885271f7b0bf`

Target bivariate-bicycle codes:

- `[[72,12,6]]`
- `[[90,8,10]]`
- `[[108,8,10]]`
- `[[144,12,12]]`

Target physical error probability: `p=0.001`.

The four codes have respectively 12, 8, 8 and 12 logical observables. P07 exercises both
`bivariate_bicycle_X` and `bivariate_bicycle_Z` circuit files, so the input contract expects
eight real `.stim` circuits in total.

## Why P07 exists

P05 and P06 establish correctness on deliberately small models where an exact answer is
available. That is necessary but insufficient: a reconstruction can pass toy cases and still
fail to parse or construct the much larger detector error models used by the real BB data.

P07 therefore introduces real-data integration in stages. The stages are intentionally kept
separate so a failure has a useful meaning.

## P07a — source, provenance and constructor acceptance

P07a is **construction-only**. It is not a decoder benchmark and it does not use wall-clock
measurements as scientific evidence.

The workflow:

1. checks out the exact frozen upstream SHA;
2. discovers `.stim` files from `testdata/bivariatebicyclecodes/` instead of hard-coding their
   long filenames;
3. selects exactly `p=0.001`, the four target `nkd` triples, `r=d`, and one X plus one Z circuit
   per code;
4. checks that the circuit text exposes exactly logical observable ids `0..k-1`;
5. records path, size and SHA-256 for every selected input;
6. reapplies the already-tested P06/P06b public-lineage patch;
7. builds a tiny probe linked against the real Tesseract/Stim libraries;
8. for every selected circuit, uses Stim's `ErrorAnalyzer::circuit_to_detector_error_model`
   with the same conversion arguments used by `tesseract_trellis_main.cc`;
9. constructs `TesseractTrellisDecoder` in the supported experimental configuration
   (`MassOnly`, `beam_eps=0`, beam 15);
10. checks that the constructor reports the same 8/12 observable count as the DEM.

P07a deliberately does **not** modify the decoder kernel. The generated probe is integration
instrumentation only.

## Why not call the public CLI directly in P07a?

At the frozen upstream SHA the public `tesseract_trellis_main.cc` contains a separate CLI-level
check that exits when `num_observables > 1`. P06 changed the library/kernel path, not this command
line policy. Removing that CLI guard is mechanically easy, but doing so in P07a would mix two
questions:

- can the real BB DEM be parsed and accepted by our P06 decoder library?;
- can the public command-line frontend be extended cleanly to expose it?

P07a answers only the first. A later stage can change the CLI explicitly and test actual shots.

## P07a green contract

A green P07a means all of the following are true:

- upstream really is the pinned SHA;
- the real `p=0.001` BB inputs exist in that checkout;
- all four target codes are present in X and Z form;
- the files expose the expected 12/8/8/12 logical observable ids;
- the P06/P06b patch still passes its modern regression and exact multi-observable tests;
- each real circuit is accepted by Stim's circuit-to-DEM conversion;
- the resulting real multi-observable DEM is accepted by our patched Trellis constructor.

It does **not** mean that decoding accuracy on these circuits has been validated, that the private
Google implementation has been reproduced, or that any runtime number is publication-quality.

## P07b — next after P07a

Only after P07a is green, P07b should expose the multi-observable path through a controlled CLI or
purpose-built shot runner and perform deterministic sampled-shot smoke tests. Seeds, circuit
hashes, observable truth, predictions and `low_confidence` must be retained.

P07b should start with very few shots. The purpose is to establish end-to-end behaviour and catch
state/mask explosion before launching a large corpus.

## P07c — later corpus validation

After deterministic smoke tests are stable, increase the corpus and compare error accounting,
`low_confidence`, and logical-mask predictions under frozen settings. Performance work comes only
after this correctness chain is frozen.

## Scientific interpretation

Every P07 GitHub Actions result must carry:

```text
benchmark_valid=false
timing_metrics_interpretable=false
```

GitHub-hosted runners are used here for reproducibility and integration testing, not scientific
performance measurements.

Nothing in P07 proves equivalence to a private/unpublished Google implementation. The work is an
experimental reconstruction based on public code lineage and public test data.
