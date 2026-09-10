#!/usr/bin/env bash
set -euo pipefail

# Rebuild the review state from the exact public Google commit.
# Requirements: git, python3, bazel/bazelisk, network access for the initial
# public clone/Bazel dependency download.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$ROOT/reproduction_work"
RESULTS="$ROOT/reproduction_results"
UPSTREAM_SHA="024db1d3b5b038f565c476dd1b51885271f7b0bf"

rm -rf "$WORK" "$RESULTS"
mkdir -p "$WORK" "$RESULTS/probe-logs" "$RESULTS/shot-logs"

git clone https://github.com/quantumlib/tesseract-decoder.git "$WORK/tesseract"
git -C "$WORK/tesseract" checkout --detach "$UPSTREAM_SHA"
test "$(git -C "$WORK/tesseract" rev-parse HEAD)" = "$UPSTREAM_SHA"

python3 "$ROOT/scripts/audit_p07_bb_real_inputs.py" \
  --upstream-dir "$WORK/tesseract" \
  --out "$RESULTS/input-manifest.json" \
  --paths-out "$RESULTS/selected-input-paths.txt"

python3 "$ROOT/scripts/apply_p06_modern_multiobs.py" \
  --upstream-dir "$WORK/tesseract" \
  --report "$RESULTS/p06-patch-report.json"
python3 "$ROOT/scripts/apply_p06_expected_upstream_contract.py" \
  --upstream-dir "$WORK/tesseract" \
  --report "$RESULTS/p06-upstream-contract-report.json"
python3 "$ROOT/scripts/apply_p06b_modern_multiobs_edge_tests.py" \
  --upstream-dir "$WORK/tesseract" \
  --report "$RESULTS/p06b-edge-report.json"
python3 "$ROOT/scripts/apply_p07_bb_constructor_probe.py" \
  --upstream-dir "$WORK/tesseract" \
  --report "$RESULTS/p07a-probe-report.json"
python3 "$ROOT/scripts/apply_p07b_bb_shot_runner.py" \
  --upstream-dir "$WORK/tesseract" \
  --report "$RESULTS/p07b-runner-report.json"

git -C "$WORK/tesseract" diff --check
git -C "$WORK/tesseract" diff > "$RESULTS/full-review.patch"

(
  cd "$WORK/tesseract"
  bazel build //src:tesseract_trellis //src:tesseract_trellis_modern_multiobs_tests //src:p07_bb_probe //src:p07b_bb_shot_runner
  bazel test //src:tesseract_trellis_tests --test_output=all
  bazel test //src:tesseract_trellis_modern_multiobs_tests --test_output=all
)

python3 "$ROOT/scripts/run_p07_bb_constructor_probes.py" \
  --manifest "$RESULTS/input-manifest.json" \
  --upstream-dir "$WORK/tesseract" \
  --probe "$WORK/tesseract/bazel-bin/src/p07_bb_probe" \
  --out "$RESULTS/p07a-probe-results.json" \
  --logs-dir "$RESULTS/probe-logs" \
  --timeout-seconds 300

python3 "$ROOT/scripts/run_p07b_bb_shot_smoke.py" \
  --manifest "$RESULTS/input-manifest.json" \
  --upstream-dir "$WORK/tesseract" \
  --runner "$WORK/tesseract/bazel-bin/src/p07b_bb_shot_runner" \
  --out "$RESULTS/p07b-shot-results.json" \
  --logs-dir "$RESULTS/shot-logs" \
  --timeout-seconds 600

find "$RESULTS" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$RESULTS/SHA256SUMS"

echo
echo "REVIEW REPRODUCTION COMPLETED"
echo "Results: $RESULTS"
echo "IMPORTANT: this is correctness/integration evidence, not a performance benchmark or a scientific LER estimate."
