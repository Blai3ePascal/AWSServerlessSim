#!/usr/bin/env bash
set -u
set -o pipefail

UPSTREAM_DIR="${1:-external/tesseract-decoder}"
OUT_DIR="${2:-research/results}"
mkdir -p "$OUT_DIR"

EXPECTED_SHA="024db1d3b5b038f565c476dd1b51885271f7b0bf"
ACTUAL_SHA="$(git -C "$UPSTREAM_DIR" rev-parse HEAD)"

if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
  printf 'sha_check\t2\texpected=%s actual=%s\n' "$EXPECTED_SHA" "$ACTUAL_SHA" > "$OUT_DIR/status.tsv"
  echo "ERROR: upstream SHA mismatch" >&2
  exit 2
fi

STATUS_FILE="$OUT_DIR/status.tsv"
printf 'step\texit_code\tdetail\n' > "$STATUS_FILE"
printf 'sha_check\t0\t%s\n' "$ACTUAL_SHA" >> "$STATUS_FILE"

run_logged() {
  local name="$1"
  shift
  echo "== $name =="
  (
    cd "$UPSTREAM_DIR"
    "$@"
  ) 2>&1 | tee "$OUT_DIR/${name}.log"
  local rc=${PIPESTATUS[0]}
  printf '%s\t%s\t%s\n' "$name" "$rc" "$*" >> "$STATUS_FILE"
  return 0
}

# Explicit binaries make it obvious that both decoder entry points compile.
run_logged bazel_build bazel build //src:tesseract //src:tesseract_trellis

# Run the Trellis-specific tests separately so their result is visible even
# though the complete src/... suite below should include them as well.
run_logged trellis_tests bazel test //src:tesseract_trellis_tests --test_output=errors

# Match the upstream CI test command at the pinned revision.
run_logged upstream_tests bazel test src/... //docs:tutorial_jupytext_sync_test --test_output=errors

python3 - "$STATUS_FILE" "$OUT_DIR/summary.json" <<'PY'
import csv
import json
import sys

status_path, out_path = sys.argv[1:]
rows = []
with open(status_path, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        row["exit_code"] = int(row["exit_code"])
        rows.append(row)

summary = {
    "steps": rows,
    "all_passed": all(r["exit_code"] == 0 for r in rows),
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
    f.write("\n")
PY

if awk -F '\t' 'NR>1 && $2 != 0 {bad=1} END {exit bad ? 0 : 1}' "$STATUS_FILE"; then
  echo "One or more baseline steps failed. See $STATUS_FILE and logs." >&2
  exit 1
fi

echo "All baseline steps passed."
