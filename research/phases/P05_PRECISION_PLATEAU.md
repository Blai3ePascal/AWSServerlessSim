# P05 - Search-quality and precision-plateau investigation

## Why this phase exists

A decoder can appear to work because every shot returns an answer while still
having poor logical accuracy. This phase separates:

1. search convergence / low-confidence outcomes;
2. logical correctness of confident outcomes;
3. the cost of the search policy.

The immediate goal is to determine whether a logical-rate plateau is primarily
caused by insufficient search exploration or whether it remains after the
current upstream long-beam search heuristics are enabled.

This phase does not claim to solve quantum-code degeneracy. Beam climbing,
multiple detector orders and no-revisit are search heuristics. If the logical
plateau remains after search-quality improvements, the result is evidence that
simply spending more search effort is not enough.

## Upstream revision

Current public main is pinned to:

e7c762eef24161e304ba6fccb856a05b41f88c39

This commit is the direct successor of the previous research baseline and adds
multi-pass decoding (#256). Multi-pass is treated as a separate experiment
because it reweights correlated error mechanisms between two detector
components; it is not assumed to be a general degeneracy fix.

## Important beam-climbing semantic

At the pinned revision, beam climbing executes:

max(det_beam + 1, number_of_detector_orders)

decoder trials per shot, cycling through beam values and detector orders.

Therefore:

- beam=20 + 21 orders -> 21 trials/shot;
- beam=2000 + 20 orders -> 2001 trials/shot.

The latter is not an appropriate first test and can easily multiply an already
expensive experiment by roughly three orders of magnitude.

## Profiles in the runner

scripts/reproduce/p05_tesseract_precision_matrix.py defines:

- reference_short: beam 15, climbing, 16 orders, no-revisit, pqlimit 200k;
- wide_beam: beam 2000, one order, no climbing, pqlimit 1M;
- wide_beam_no_revisit: isolates the no-revisit heuristic on the wide search;
- orders_only: beam 20, 21 full detector-order searches, no climbing;
- climbing_with_revisit: upstream-like climbing/orders while allowing revisits;
- upstream_longbeam: beam 20, climbing, 21 Index orders, no-revisit,
  pqlimit 1M, seed 2,384,753.

The final profile matches the long-beam registry currently present in upstream
src/py/multi_pass_sinter_decoders.py.

## Metrics

For each circuit/profile pair the runner stores the raw CLI stats and derives:

- confidence rate;
- error rate among confident shots;
- conservative failure rate: (num_errors + num_low_confidence) / num_shots;
- conservative per-round failure rate using
  0.5 * (1 - (1 - 2*R_shot) ** (1/r));
- decoder seconds per shot;
- wall time;
- the exact estimated number of decoder trials per shot.

Raw stdout, stderr, command line, circuit SHA-256 and JSON are retained.

## What GitHub Actions validates

CI is used only to show that:

- the pinned current upstream revision builds;
- focused Tesseract and multi-pass tests pass;
- the proposed long-beam flags are accepted by the real CLI;
- a public q=144, p=0.001 BB circuit can be sampled and decoded;
- --stats-out confirms that the requested parameters actually reached the decoder;
- the evidence schema and derived metrics are generated correctly.

CI timing is marked benchmark_valid=false.

## What must be run on Brigit

The useful scientific sweep belongs on controlled/known hardware. A sensible
order is:

1. wide_beam versus wide_beam_no_revisit:
   does no-revisit reduce time without degrading the logical result?
2. orders_only versus upstream_longbeam:
   does beam climbing add accuracy beyond detector-order diversity?
3. climbing_with_revisit versus upstream_longbeam:
   isolate the effect of no-revisit.
4. Repeat across q=144, 180, 216, 288 at the same physical error rate and fixed seeds.

Do not infer a distance trend until each point has enough logical failures to
produce a meaningful estimate and a confidence interval.

## Multi-pass follow-up

The current main branch added multi-pass decoding after the previous pinned
baseline. It is worth testing as an orthogonal control if the monolithic
long-beam profiles still plateau.

The native CLI requires canonical detector-basis tags for multi-pass. The
Python wrapper can infer supported X/Z metadata / the Chromobius
fourth-coordinate convention. Current multi-pass code propagates low-confidence
through Sinter's discard byte, but issue #297 remains relevant to the older
monolithic/file-decoder paths; in particular, decode_via_files has no
decoder-controlled discard channel. For this campaign, conservative logical-rate
measurements therefore stay on the native CLI stats path, where
num_low_confidence is explicit.

## GO / NO-GO

GO to a deeper decoder change only after the search matrix answers:

- Does confidence improve?
- Does logical correctness improve independently of confidence?
- Does increasing search diversity change the distance scaling?
- Does the plateau remain even when search exploration is demonstrably richer?

If confidence becomes approximately 100% but the logical rate still stays near
the physical rate and remains almost independent of distance, increasing
beam/pqlimit again is a weak next step. At that point the experiment should
focus on the decoder objective / treatment of degenerate or correlated
explanations instead of only search breadth.
