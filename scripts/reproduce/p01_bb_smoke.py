#!/usr/bin/env python3
"""P01 public BB smoke reproduction for Tesseract/Trellis.

What this script does
---------------------
1. Verifies that the checked-out upstream repository is exactly the commit pinned
   by the public corpus manifest.
2. Verifies that every selected Stim circuit exists and contains the expected
   number of logical observables.
3. Runs one deterministic, deliberately small Tesseract-original decode per
   circuit. This is a compatibility/reproduction smoke test, not a performance
   benchmark.
4. Invokes Tesseract Trellis on the same unmodified circuit and verifies the
   current, documented incompatibility with multi-observable DEMs.
5. Writes raw stdout/stderr, commands, return codes, elapsed wall time and a
   machine-readable summary so later phases can audit exactly what happened.

Why it exists
-------------
P01 must establish a scientifically defensible input/correctness foundation
before any optimisation. In particular, it must never collapse or rewrite the
logical observables in these BB circuits merely to make Trellis accept them.

The timings emitted here MUST NOT be used as benchmark numbers. GitHub-hosted
runners are intentionally treated only as clean reproducibility environments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

OBS_RE = re.compile(r"^\s*OBSERVABLE_INCLUDE\((\d+)\)", re.MULTILINE)
TRELLIS_MULTI_OBS_MESSAGE = "tesseract_trellis currently supports at most one observable"


def sha256_file(path: Path) -> str:
    """Return a content hash so the exact circuit used by a run is auditable."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_command(command: list[str], cwd: Path, timeout_s: int) -> dict[str, Any]:
    """Execute one command and preserve enough evidence to reproduce failures.

    The function intentionally captures stdout and stderr separately. A timeout
    is recorded as data instead of losing the partial output. Later phases can
    therefore distinguish an algorithm/compatibility failure from an execution
    budget chosen for this smoke test.
    """
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "timed_out": False,
            "elapsed_wall_seconds": time.perf_counter() - started,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "timed_out": True,
            "elapsed_wall_seconds": time.perf_counter() - started,
            "stdout": exc.stdout if isinstance(exc.stdout, str) else "",
            "stderr": exc.stderr if isinstance(exc.stderr, str) else "",
        }


def observable_count(circuit_text: str) -> int:
    """Infer Stim's logical-observable width from OBSERVABLE_INCLUDE indices.

    Stim observables are zero-indexed, so the width is max(index)+1. Returning
    zero when no declaration exists mirrors the natural meaning of an empty
    observable set and avoids guessing from code parameters such as k.
    """
    indices = [int(match.group(1)) for match in OBS_RE.finditer(circuit_text)]
    return max(indices) + 1 if indices else 0


def save_run(run_dir: Path, name: str, result: dict[str, Any]) -> None:
    """Store raw process streams separately from compact machine metadata."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"{name}.stdout.txt").write_text(result["stdout"], encoding="utf-8")
    (run_dir / f"{name}.stderr.txt").write_text(result["stderr"], encoding="utf-8")
    metadata = {k: v for k, v in result.items() if k not in {"stdout", "stderr"}}
    (run_dir / f"{name}.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--sample-seed", type=int, default=20260909)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_sha = manifest["source"]["commit"]
    upstream = args.upstream_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    actual_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=upstream, text=True
    ).strip()
    if actual_sha != expected_sha:
        raise SystemExit(
            f"Upstream SHA mismatch: expected {expected_sha}, got {actual_sha}"
        )

    tesseract = upstream / "bazel-bin/src/tesseract"
    trellis = upstream / "bazel-bin/src/tesseract_trellis"
    for binary in (tesseract, trellis):
        if not binary.exists():
            raise SystemExit(f"Missing binary: {binary}. Build both decoders first.")

    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": "P01",
        "upstream_sha": actual_sha,
        "sample_seed": args.sample_seed,
        "timeout_seconds": args.timeout_seconds,
        "benchmark_valid": False,
        "cases": [],
    }
    overall_ok = True

    for case in manifest["cases"]:
        circuit = upstream / case["path"]
        case_dir = output / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)

        if not circuit.exists():
            summary["cases"].append({"id": case["id"], "error": "missing circuit"})
            overall_ok = False
            continue

        text = circuit.read_text(encoding="utf-8")
        observed_width = observable_count(text)
        metadata_ok = observed_width == case["expected_observables"]

        original_stats = case_dir / "tesseract_original_stats.json"
        original_cmd = [
            str(tesseract),
            "--circuit", str(circuit),
            "--sample-num-shots", "1",
            "--sample-seed", str(args.sample_seed),
            "--threads", "1",
            "--beam", "1",
            "--num-det-orders", "1",
            "--det-order-index",
            "--pqlimit", "10000",
            "--stats-out", str(original_stats),
            "--print-stats",
        ]
        original = run_command(original_cmd, upstream, args.timeout_seconds)
        save_run(case_dir, "tesseract_original", original)
        original_ok = (not original["timed_out"]) and original["returncode"] == 0

        # Trellis is invoked on the exact same circuit. For this public corpus,
        # rejection is the expected result because all four cases contain more
        # than one observable. We require the upstream diagnostic to be present;
        # an arbitrary crash or unrelated failure is NOT counted as success.
        trellis_cmd = [
            str(trellis),
            "--circuit", str(circuit),
            "--sample-num-shots", "1",
            "--sample-seed", str(args.sample_seed),
            "--threads", "1",
            "--beam", "16",
        ]
        trellis_result = run_command(trellis_cmd, upstream, args.timeout_seconds)
        save_run(case_dir, "tesseract_trellis", trellis_result)
        diagnostic_text = trellis_result["stdout"] + "\n" + trellis_result["stderr"]
        trellis_expected_rejection = (
            not trellis_result["timed_out"]
            and trellis_result["returncode"] not in (None, 0)
            and TRELLIS_MULTI_OBS_MESSAGE in diagnostic_text
        )

        case_summary = {
            "id": case["id"],
            "path": case["path"],
            "q": case["q"],
            "n": case["n"],
            "k": case["k"],
            "d": case["d"],
            "rounds": case["rounds"],
            "p": case["p"],
            "circuit_sha256": sha256_file(circuit),
            "expected_observables": case["expected_observables"],
            "observed_observables": observed_width,
            "metadata_ok": metadata_ok,
            "tesseract_original_smoke_ok": original_ok,
            "tesseract_trellis_expected_multi_observable_rejection": trellis_expected_rejection,
        }
        summary["cases"].append(case_summary)
        overall_ok &= metadata_ok and original_ok and trellis_expected_rejection

    summary["overall_ok"] = overall_ok
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # A non-zero exit means the reproducibility contract was violated: missing
    # corpus metadata, failed original smoke run, or a Trellis failure different
    # from the known multi-observable incompatibility.
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
