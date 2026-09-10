# P03b beam-pressure finding

## Evidence source

- Workflow run: `34449162215`
- Harness commit: `6b330866814802c9b88b52742c50a442c9fc8e01`
- Artifact: `tesseract-p03b-stress-evidence-34449162215`
- Artifact SHA-256: `fb467cf66f0de0b669c98ec499e0c5dc1fc94d2dbfe9240caf44acbea6e8fd7b`
- `benchmark_valid=false`

## Result

P03b passed its deliberately strict beam-pressure contract:

- 18 configuration points;
- 36 executions because every configuration was repeated twice;
- 72 first-repetition shots analyzed;
- 18/18 timing-stripped determinism checks passed;
- all six beam-4 fixture/ranking configurations exhibited real beam pressure;
- maximum active frontier width: 12;
- maximum `beam_in`: 64;
- maximum states after collapse: 128;
- maximum pre-truncation excess: 64 states.

The stress corpus therefore reaches a regime in which Trellis must discard states even at beam 64. For example, some layers reach 128 collapsed states before only 64 are retained.

## Ranking and beam observations

The structural workload depends materially on beam width. For both fixtures the maximum post-collapse population scales from 8 at beam 4, to 32 at beam 16, to 128 at beam 64. This is consistent with the binary expansion/collapse structure and gives us a useful controlled stress family for later profiling.

Ranking mode also affects completion behaviour when the beam is tight:

- `stress10`, beam 4: `mass` produced 2 low-confidence shots, while both future-cost modes produced 1;
- `stress12`, beam 4: `mass` produced 3 low-confidence shots, `future-detcost` 1, and `future-active-detcost` 0;
- at beam 16, future-cost ranking also removed low-confidence cases that remained under `mass` for `stress12`;
- at beam 64 all tested configurations completed without low-confidence shots.

On `stress10` at beam 4, the prediction signature differs between `mass` and the two future-cost modes. This demonstrates that pruning/ranking can change the retained hypothesis set enough to alter the final decision in a stressed case.

## What this does NOT show

These synthetic fixtures do not provide an accuracy benchmark or a physical-device ground truth. Lower low-confidence counts do not by themselves mean higher decoding accuracy, and a changed prediction is not automatically an improvement.

GitHub-hosted timing is not interpreted. P03b supports structural conclusions only.

## Decision

**GO to P04 controlled-hardware profiling.**

P04 will use the same deterministic stress fixtures and decoder configurations, but absolute latency, throughput, memory and hardware-counter claims will only be accepted from a controlled machine. GitHub Actions will validate the harness but will continue to mark its timings invalid for scientific use.
