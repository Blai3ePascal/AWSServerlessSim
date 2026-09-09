#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO="https://github.com/quantumlib/tesseract-decoder.git"
UPSTREAM_SHA="024db1d3b5b038f565c476dd1b51885271f7b0bf"
DEST="${1:-external/tesseract-decoder}"

mkdir -p "$(dirname "$DEST")"

if [[ ! -d "$DEST/.git" ]]; then
  git clone "$UPSTREAM_REPO" "$DEST"
fi

git -C "$DEST" fetch --tags --prune origin
git -C "$DEST" checkout --detach "$UPSTREAM_SHA"

actual_sha="$(git -C "$DEST" rev-parse HEAD)"
if [[ "$actual_sha" != "$UPSTREAM_SHA" ]]; then
  echo "ERROR: expected $UPSTREAM_SHA but checked out $actual_sha" >&2
  exit 2
fi

printf 'Pinned upstream checkout verified: %s\n' "$actual_sha"
