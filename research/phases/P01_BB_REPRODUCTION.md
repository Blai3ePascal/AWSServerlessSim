# P01 - Public BB reproduction and compatibility foundation

## Objective

Establish a reproducible, unmodified bivariate-bicycle (BB) input corpus and verify what the pinned upstream Tesseract and Tesseract Trellis executables actually accept before any optimisation or semantic transformation is attempted.

## Upstream revision

- Repository: `quantumlib/tesseract-decoder`
- Commit: `024db1d3b5b038f565c476dd1b51885271f7b0bf`
- Public corpus directory: `testdata/bivariatebicyclecodes`

The four smoke cases are pinned in `research/experiments/configs/p01_bb_public_corpus.json` and use the exact public upstream `p=0.0001` X-basis circuits for q=144, 180, 216 and 288.

## Hypotheses

1. The corpus metadata in the manifest matches the checked-out Stim circuits exactly.
2. Tesseract original can perform at least one deterministic smoke decode on each selected circuit without modifying its logical observables.
3. Tesseract Trellis rejects these exact circuits for the specific known reason that the current implementation supports at most one logical observable.
4. No timing measured on GitHub-hosted runners is suitable for a performance claim.

## Reproduction contract

P01 MUST:

- use the exact upstream SHA above;
- record the exact circuit SHA-256 used for every run;
- derive observable width from the Stim circuit instead of inferring it from q, n, k or d;
- use a fixed sample seed;
- preserve stdout, stderr, command, return code and timeout state;
- treat the Trellis multi-observable rejection as a compatibility result, not as a failed research phase;
- fail if Trellis crashes or fails for a reason different from the expected multi-observable diagnostic;
- never rewrite, select, collapse or combine logical observables to force compatibility.

## Smoke parameters

The original decoder smoke uses one sampled shot, one CPU thread, beam 1, one Index detector order and a bounded priority queue. These parameters are deliberately chosen to answer only a binary reproduction question: can the original executable process the public circuit in a clean environment?

They are **not** benchmark parameters.

Trellis is invoked on the same unmodified circuit. Its expected rejection must include the upstream diagnostic `tesseract_trellis currently supports at most one observable`.

## Evidence

The P01 GitHub Actions workflow uploads:

- `summary.json`;
- per-case command metadata;
- per-case stdout and stderr for both executables;
- Tesseract original stats JSON when produced;
- circuit SHA-256 values;
- harness/upstream provenance;
- a SHA-256 manifest over the evidence directory.

## GO / NO-GO

P01 is **GO** for later instrumentation only if:

- all four public circuit metadata checks pass;
- all four original-decoder smoke runs complete successfully; and
- all four Trellis invocations reject for the documented multi-observable reason.

A timeout or unrelated decoder error is not silently accepted. It is a P01 result that must be investigated before optimisation.

## Known semantic blocker for Trellis

The selected BB circuits contain 8 or 12 logical observables, while the current Trellis implementation supports at most one. Resolving that mismatch is a separate scientific/algorithmic question and requires an explicit, justified observable semantics. P01 does not attempt it.

## Privacy boundary

This phase contains only information already present in the public upstream repository. Collaborator-only inputs, unpublished measurements, private notes and unpublished parameter choices must not be committed while the harness repository remains public.
