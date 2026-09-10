#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$PWD/.multiobs64-bb-work}"
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_SHA="024db1d3b5b038f565c476dd1b51885271f7b0bf"

printf '\n=== P08: primero demuestro otra vez que la base 0..64 sigue bien ===\n'
bash "$HARNESS/scripts/build_and_test_tesseract_multiobs64.sh" "$ROOT"

printf '\n=== P08: ahora abro la puerta vieja del CLI para 2..64 observables ===\n'
python3 "$HARNESS/scripts/instrument/apply_p08_cli_multiobs64.py" \
  --upstream-dir "$ROOT/tesseract" \
  --report "$ROOT/p08-cli.json"

git -C "$ROOT/tesseract" diff --check
if grep -q 'currently supports at most one observable' "$ROOT/tesseract/src/tesseract_trellis_main.cc"; then
  echo 'FAIL: sigue viva la barrera vieja del CLI para >1 observable.' >&2
  exit 1
fi
git -C "$ROOT/tesseract" diff --binary > "$ROOT/tesseract-multiobservable64-with-cli.patch"

printf '\n=== P08: busco los BB REALES p=0.001 dentro del upstream congelado ===\n'
python3 "$HARNESS/scripts/find_p08_bb_circuits.py" \
  --upstream-dir "$ROOT/tesseract" \
  --output "$ROOT/selected-circuits.tsv" \
  --json "$ROOT/selected-circuits.json"

test "$(tail -n +2 "$ROOT/selected-circuits.tsv" | wc -l)" = "8"

printf '\n=== P08: compilo el ejecutable real tesseract_trellis con nuestra entrada 0..64 ===\n'
(
  cd "$ROOT/tesseract"
  bazel build //src:tesseract_trellis
)

printf '\n=== P08: paso los 8 BB (X/Z) por el CLI real ===\n'
python3 "$HARNESS/scripts/run_p08_real_bb.py" \
  --upstream-dir "$ROOT/tesseract" \
  --selection "$ROOT/selected-circuits.tsv" \
  --output-dir "$ROOT/p08-real-bb" \
  --shots 1 \
  --beam 1024

python3 - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
report = json.loads((root / 'p08-real-bb' / 'P08_REAL_BB_SUMMARY.json').read_text())
assert report['all_cli_runs_exit_zero'] is True
assert report['all_dem_observable_counts_match'] is True
assert report['observable_pattern'] == [12, 8, 8, 12]
assert report['p'] == 0.001
assert report['upstream_circuits'] == 8
print('PASS: contrato P08 real-BB comprobado.')
PY

printf '\n=== RESULTADO ===\n'
echo "PASS: upstream público fijado en $UPSTREAM_SHA"
echo 'PASS: extensión 0..64 vuelve a pasar tests + oráculo exacto de 640 casos'
echo 'PASS: el CLI real acepta multiobservable (la barrera antigua >1 ya no existe)'
echo 'PASS: BB72/90/108/144, X y Z, p=0.001'
echo 'PASS: patrón de observables leído por el DEM = 12/8/8/12'
echo 'NOTA: esto NO es un benchmark de velocidad y NO afirma equivalencia con código privado.'
echo "Todo queda en: $ROOT"
