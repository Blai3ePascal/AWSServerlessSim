#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_SHA="024db1d3b5b038f565c476dd1b51885271f7b0bf"
ANCESTOR_SHA="56996facf54c25e6c08fed19d8902f40e1971f55"
ROOT="${1:-$PWD/.multiobs64-work}"
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rm -rf "$ROOT"
mkdir -p "$ROOT"

echo "[1/8] Cloning pinned public Tesseract upstream"
git clone https://github.com/quantumlib/tesseract-decoder.git "$ROOT/tesseract"
git -C "$ROOT/tesseract" checkout --detach "$UPSTREAM_SHA"
test "$(git -C "$ROOT/tesseract" rev-parse HEAD)" = "$UPSTREAM_SHA"

echo "[2/8] Applying independently reconstructed 0..64 observable extension"
python3 "$HARNESS/scripts/instrument/apply_p06_modern_multiobs.py" \
  --upstream-dir "$ROOT/tesseract" --report "$ROOT/p06.json"
python3 "$HARNESS/scripts/instrument/apply_p06_expected_upstream_contract.py" \
  --upstream-dir "$ROOT/tesseract" --report "$ROOT/p06-contract.json"
python3 "$HARNESS/scripts/instrument/apply_p06b_modern_multiobs_edge_tests.py" \
  --upstream-dir "$ROOT/tesseract" --report "$ROOT/p06b.json"
python3 "$HARNESS/scripts/instrument/apply_p07_complete_multiobs64_modes.py" \
  --upstream-dir "$ROOT/tesseract" --report "$ROOT/p07.json"
python3 "$HARNESS/scripts/instrument/apply_p07b_mode_equivalence_tests.py" \
  --upstream-dir "$ROOT/tesseract" --report "$ROOT/p07b.json"
python3 "$HARNESS/scripts/instrument/apply_p07c_gtest_main_fix.py" \
  --upstream-dir "$ROOT/tesseract" --report "$ROOT/p07c.json"
python3 "$HARNESS/scripts/instrument/apply_p06c_diff_driver.py" \
  --upstream-dir "$ROOT/tesseract" --kind modern --report "$ROOT/diff-driver.json"

echo "[3/8] Checking generated patch"
git -C "$ROOT/tesseract" diff --check
git -C "$ROOT/tesseract" diff --binary > "$ROOT/tesseract-multiobservable64.patch"

echo "[4/8] Building and running upstream + extension tests"
(
  cd "$ROOT/tesseract"
  bazel test \
    //src:tesseract_trellis_tests \
    //src:tesseract_trellis_modern_multiobs_tests \
    //src:tesseract_trellis_multiobs64_modes_tests \
    --test_output=errors
  bazel build //src:tesseract_trellis_diff_dump
)

echo "[5/8] Generating deterministic exactness corpus (640 cases, includes p=0.001)"
python3 "$HARNESS/scripts/generate_p06c_corpus.py" \
  --output-dir "$ROOT/corpus" \
  --manifest "$ROOT/corpus/manifest.tsv" \
  --metadata "$ROOT/corpus/corpus.json"
test "$(grep -vc '^#' "$ROOT/corpus/manifest.tsv")" = "640"

echo "[6/8] Computing independent exact probabilistic oracle"
python3 "$HARNESS/scripts/compute_p06d_exact_oracle.py" \
  --metadata "$ROOT/corpus/corpus.json" \
  --output "$ROOT/exact-oracle.tsv" \
  --summary "$ROOT/exact-oracle-summary.json"

echo "[7/8] Dumping decoder results"
"$ROOT/tesseract/bazel-bin/src/tesseract_trellis_diff_dump" \
  "$ROOT/corpus/manifest.tsv" "$ROOT/production-results.tsv"

echo "[8/8] Verifying production decoder directly against the independent oracle"
python3 "$HARNESS/scripts/compare_p06d_exact_oracle.py" \
  --oracle "$ROOT/exact-oracle.tsv" \
  --p05 "$ROOT/production-results.tsv" \
  --p06 "$ROOT/production-results.tsv" \
  --metadata "$ROOT/corpus/corpus.json" \
  --json-report "$ROOT/exact-validation-summary.json" \
  --markdown-report "$ROOT/EXACT_VALIDATION_RESULT.md" \
  --mismatches-tsv "$ROOT/mismatches.tsv"

grep -q '"success": true' "$ROOT/exact-validation-summary.json"

echo
echo "PASS: Tesseract extension built from public SHA $UPSTREAM_SHA"
echo "PASS: original Trellis regression suite + multiobservable suites"
echo "PASS: independent exact oracle comparison over 640 deterministic cases"
echo "PASS: observable counts include 2, 8, 12, 32 and 64"
echo "Artifacts: $ROOT"
