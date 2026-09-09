#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-research/results}"
UPSTREAM_DIR="${2:-external/tesseract-decoder}"
mkdir -p "$OUT_DIR"

{
  echo "captured_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "runner_os=${RUNNER_OS:-local}"
  echo "runner_arch=${RUNNER_ARCH:-unknown}"
  echo "kernel=$(uname -a)"
  echo "upstream_sha=$(git -C "$UPSTREAM_DIR" rev-parse HEAD 2>/dev/null || echo unavailable)"
  echo
  echo "== CPU =="
  command -v lscpu >/dev/null && lscpu || true
  echo
  echo "== Memory =="
  command -v free >/dev/null && free -h || true
  echo
  echo "== Toolchain =="
  git --version || true
  gcc --version 2>/dev/null | head -n 1 || true
  clang --version 2>/dev/null | head -n 1 || true
  cmake --version 2>/dev/null | head -n 1 || true
  python3 --version || true
  bazel --version 2>/dev/null || true
} > "$OUT_DIR/environment.txt" 2>&1

python3 - "$OUT_DIR/environment.json" "$UPSTREAM_DIR" <<'PY'
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

out, upstream = sys.argv[1:]

def cmd(*args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"unavailable: {exc}"

data = {
    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
    "platform": platform.platform(),
    "machine": platform.machine(),
    "processor": platform.processor(),
    "python": platform.python_version(),
    "runner_os": os.environ.get("RUNNER_OS", "local"),
    "runner_arch": os.environ.get("RUNNER_ARCH", "unknown"),
    "git": cmd("git", "--version"),
    "bazel": cmd("bazel", "--version"),
    "cmake": cmd("cmake", "--version").splitlines()[0],
    "upstream_sha": cmd("git", "-C", upstream, "rev-parse", "HEAD"),
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, sort_keys=True)
    f.write("\n")
PY
