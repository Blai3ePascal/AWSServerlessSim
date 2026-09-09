# Known upstream limitations relevant to the baseline

This document records constraints already observed in the pinned upstream revision. They are treated as experimental conditions, not silently repaired during P00.

## 1. Trellis and multiple logical observables

The public `tesseract_trellis` CLI in the pinned `main` revision rejects detector error models with more than one observable. Upstream also contains a test that intentionally verifies this rejection.

Consequence: the bivariate-bicycle examples discussed with collaborators that expose 8 or 12 logical observables cannot be assumed to be direct Trellis inputs. We must first confirm the intended workflow (projection, transformed DEM, separate-observable runs, or an extension of Trellis semantics).

P00 rule: do not implement a guessed multi-observable transformation.

## 2. `low-confidence` and Sinter

Upstream issue #297 documents a risk that Sinter integrations do not preserve Tesseract's `low-confidence` status. Published Tesseract methodology treats low-confidence outcomes conservatively when reporting logical failure.

Consequence: Sinter aggregate logical-error counts are not used as the baseline source of truth while this limitation remains unresolved. Initial correctness work must preserve at least:

- number of shots;
- number of logical errors;
- number of low-confidence results;
- decoder output / observable prediction when available.

P00/P01 rule: prefer the native C++ execution path for reference results and keep `low-confidence` separate.

Reference: https://github.com/quantumlib/tesseract-decoder/issues/297

## 3. Figure-2 reproduction parameters are not defaults

A reproduction of a published figure must use the parameters reported by the paper, rather than assuming current CLI defaults are historically identical. Configuration and input-noise probability must be recorded explicitly in each run manifest.

## 4. GitHub-hosted runners are not benchmark hardware

GitHub Actions is appropriate here for clean-room compilation, tests, deterministic functional checks and artifact generation. Hosted-runner execution time must not be used as a scientific CPU/GPU performance result.

## 5. P00 intentionally changes no decoder code

If build or upstream tests fail, the first artifact must preserve the exact failing command, exit code and log. A later phase may propose a fix only after the failure has a minimal reproduction or regression test.
