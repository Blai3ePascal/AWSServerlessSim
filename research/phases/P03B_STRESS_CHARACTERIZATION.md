# P03b - Beam-pressure stress characterization

## Objective

Extend P03 with deterministic one-observable synthetic fixtures that deliberately keep more detectors active across overlapping faults. The purpose is to reach a structural regime where beam width and ranking can actually affect state retention.

This remains a structural experiment. `benchmark_valid=false`; timing fields are raw trace evidence only and are not interpreted.

## Motivation from P03

The initial P03 matrix passed completely but never exceeded `beam_in=4` or `states_after_collapse=4`, and every layer retained all states. Consequently beam 4/16/64 and the three ranking modes had no opportunity to diverge.

P03b treats that as a corpus limitation and increases structural pressure rather than inventing conclusions from an unsaturated beam.

## Fixtures

Two synthetic DEMs are generated at runtime:

- `stress10`: 10 detectors and 14 overlapping pair faults with long cross-frontier lifetimes;
- `stress12`: 12 detectors and 18 pair/triple faults with staggered retirement and one logical observable.

All syndrome records are constructed from XOR combinations of explicitly present faults, so each test syndrome has at least one known explanation in the DEM.

## Matrix

For each fixture:

- beam widths: 4, 16, 64;
- rankings: mass, future-detcost, future-active-detcost;
- four fixed syndrome records;
- two repetitions per configuration;
- one CPU decoder thread.

This gives 18 configuration points, 36 runs and 72 analyzed first-repetition shots.

## Additional pressure metrics

P03b keeps the P03 structural metrics and adds:

- `truncating_layers`: layers where `states_after_collapse > states_kept`;
- `beam_saturated_layers`: layers where `states_kept == beam_width`;
- `beam_pressure_layers`: layers where both conditions hold;
- pressure fraction: `beam_pressure_layers / num_layers`;
- maximum pre-truncation excess: `states_after_collapse - states_kept`;
- prediction signature per configuration so ranking/beam-induced semantic differences are visible rather than hidden.

A beam-saturated layer alone is not sufficient evidence of truncation: exact equality can occur naturally. P03b therefore distinguishes saturation from actual pressure.

## Determinism

As in P03, each configuration is run twice. Prediction bytes and the timing-stripped structural trace must match exactly between repetitions.

## GO / NO-GO

P03b is GO if:

1. all deterministic fixtures are accepted by Trellis;
2. all 18 configurations complete twice;
3. structural determinism holds for every configuration;
4. at least one beam-4 configuration exhibits a `beam_pressure_layer`;
5. focused Trellis regression tests pass;
6. the evidence artifact is uploaded with provenance and checksums.

If condition 4 does not occur, P03b is scientifically valid but **NO-GO for using this synthetic corpus to study beam/ranking effects**. We would then need a richer public one-observable workload or a privately held collaborator workload after repository visibility is secured.
