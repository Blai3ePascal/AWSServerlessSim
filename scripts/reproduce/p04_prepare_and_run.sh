#!/usr/bin/env bash
# Prepare the exact P04 instrumented upstream checkout and run a controlled CPU benchmark.
#
# Usage:
#   bash scripts/reproduce/p04_prepare_and_run.sh /path/to/tesseract-decoder RESULTS_DIR MACHINE_LABEL
#
# The upstream directory must already be checked out at the pinned SHA. This
# script never fetches or changes branches, which keeps network and source-state
# changes explicit and auditable.
set -euo pipefail

UPSTREAM=${1:?upstream directory required}
OUT=${2:?output directory required}
LABEL=${3:?machine label required}
EXPECTED=024db1d3b5b038f565c476dd1b51885271f7b0bf

actual=$(git -C "$UPSTREAM" rev-parse HEAD)
if [[ "$actual" != "$EXPECTED" ]]; then
  echo "Expected upstream $EXPECTED but found $actual" >&2
  exit 2
fi
if [[ -n "$(git -C "$UPSTREAM" status --porcelain)" ]]; then
  echo "Upstream checkout must be clean before P02 instrumentation is applied." >&2
  exit 2
fi

mkdir -p "$OUT"
python3 scripts/instrument/apply_p02_layer_stats.py \
  --upstream-dir "$UPSTREAM" --report "$OUT/p02a-patch-report.json"
python3 scripts/instrument/apply_p02b_layer_trace_cli.py \
  --upstream-dir "$UPSTREAM" --report "$OUT/p02b-patch-report.json"
git -C "$UPSTREAM" diff --check
git -C "$UPSTREAM" diff > "$OUT/instrumentation.patch"

(
  cd "$UPSTREAM"
  bazel test //src:tesseract_trellis_tests --test_output=errors
  bazel build -c opt //src:tesseract_trellis
)

python3 scripts/reproduce/p04_controlled_cpu_benchmark.py \
  --mode benchmark \
  --machine-label "$LABEL" \
  --upstream-dir "$UPSTREAM" \
  --output-dir "$OUT/benchmark" \
  --event-block-repeats 250 \
  --warmups 2 \
  --repetitions 10 \
  --with-perf

find "$OUT" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$OUT/SHA256SUMS"
echo "P04 controlled benchmark completed: $OUT"
