# P03 initial structural finding

## Evidence source

- Workflow run: `34448737359`
- Harness commit: `fb3063bbbc494739ee2cf7e578a89c8f9ef346e5`
- Artifact: `tesseract-p03-structural-evidence-34448737359`
- Artifact SHA-256: `0cc85ede0df2f19d2d37c306a1d103c671fed3c4d747820db1e8f27e74a1517d`
- `benchmark_valid=false`

## Result

P03 completed all 27 configuration points twice, producing 108 analyzed shots and passing all 27 timing-stripped structural determinism checks.

The initial synthetic fixtures were intentionally small, and the result shows they are **too small to study beam/ranking pressure**:

- maximum active frontier width: 5;
- maximum `beam_in`: 4;
- maximum `states_after_collapse`: 4;
- mean retention fraction: 1.0 for every fixture/configuration;
- beam widths 4, 16 and 64 therefore produced identical count summaries;
- the three ranking modes also produced identical count summaries on this corpus;
- no shot was low confidence.

Layer-to-layer structure was nevertheless nonuniform. The largest observed coefficient of variation was approximately 0.399 for active-frontier width and 0.490 for states-after-collapse. This confirms that the trace can expose structural irregularity, but the corpus does not yet create enough state pressure to evaluate truncation or ranking choices.

## Interpretation

This is a useful negative result, not evidence that beam width or ranking mode are unimportant. The experiment never reached the regime in which those controls are forced to choose between more states than can be retained.

No CPU/GPU, latency, throughput or scalability conclusion is supported by this run. GitHub-hosted timing remains excluded from interpretation.

## Decision

**GO to P03b stress characterization.**

P03b must construct deterministic one-observable fixtures with longer-lived overlapping frontiers and enough alternative state paths to force at least the beam-4 configuration to truncate states. If even deliberately stressed synthetic cases fail to create beam pressure, the instrumentation/metric definitions should be re-examined before moving to controlled-hardware profiling.
