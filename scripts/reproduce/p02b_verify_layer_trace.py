#!/usr/bin/env python3
"""Verify P02b layer-trace CLI semantics with deterministic one-observable data.

This is a correctness/reproducibility check, not a performance benchmark. It
compares prediction bytes and observable-probability bytes between an ordinary
run and an otherwise identical traced run, then validates JSONL ordering and
schema. GitHub-hosted runner timings are never interpreted as performance data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def assert_ok(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def validate_trace(path: Path, expected_detection_counts: list[int]) -> dict[str, Any]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != len(expected_detection_counts):
        raise RuntimeError(f"expected {len(expected_detection_counts)} JSONL records, got {len(lines)}")

    layer_counts: list[int] = []
    for shot_index, line in enumerate(lines):
        record = json.loads(line)
        if record.get("schema_version") != 1:
            raise RuntimeError("unexpected trace schema version")
        if record.get("record_type") != "tesseract_trellis_layer_trace":
            raise RuntimeError("unexpected trace record_type")
        if record.get("shot_index") != shot_index:
            raise RuntimeError("trace shot ordering is not deterministic")
        if record.get("detection_count") != expected_detection_counts[shot_index]:
            raise RuntimeError("trace detection_count does not match input")
        layers = record.get("layers")
        if not isinstance(layers, list) or not layers:
            raise RuntimeError("trace must contain at least one layer")
        if record.get("num_layers") != len(layers):
            raise RuntimeError("num_layers does not match layers array")
        layer_counts.append(len(layers))

        for layer_index, layer in enumerate(layers):
            if layer.get("layer_index") != layer_index:
                raise RuntimeError("layer indices are not contiguous and ordered")
            active = layer["active_frontier_width"]
            surviving = layer["surviving_frontier_width"]
            beam_in = layer["beam_in"]
            buckets = layer["used_pair_buckets"]
            collapsed = layer["states_after_collapse"]
            kept = layer["states_kept"]
            if active < surviving:
                raise RuntimeError("surviving frontier exceeds active frontier")
            if beam_in < 1:
                raise RuntimeError("beam_in must be positive for a recorded completed layer")
            if buckets > collapsed:
                raise RuntimeError("used pair bucket count exceeds collapsed states")
            if collapsed < kept:
                raise RuntimeError("kept states exceed states after collapse")
            for field in ("expand_seconds", "collapse_seconds", "truncate_seconds"):
                value = layer[field]
                if not isinstance(value, (int, float)) or value < 0:
                    raise RuntimeError(f"invalid nonnegative phase time in {field}")

    return {"records": len(lines), "layer_counts": layer_counts}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    upstream = args.upstream_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = upstream / "bazel-bin/src/tesseract_trellis"
    if not binary.exists():
        raise SystemExit(f"missing built binary: {binary}")

    dem = output / "tiny_one_observable.dem"
    events = output / "events.01"
    dem.write_text(
        """error(0.10) D0\nerror(0.20) D0 L0\nerror(0.15) D0 D1\nerror(0.25) D1\ndetector(0, 0, 0) D0\ndetector(1, 0, 0) D1\n""",
        encoding="utf-8",
    )
    events.write_text("10\n01\n11\n00\n", encoding="utf-8")
    expected_detection_counts = [1, 1, 2, 0]

    baseline_predictions = output / "baseline_predictions.01"
    traced_predictions = output / "traced_predictions.01"
    baseline_probs = output / "baseline_probs.bin"
    traced_probs = output / "traced_probs.bin"
    trace = output / "layer_trace.jsonl"

    common = [
        str(binary),
        "--dem", str(dem),
        "--in", str(events),
        "--in-format", "01",
        "--out-format", "01",
        "--threads", "2",
        "--beam", "64",
        "--ranking-mode", "mass",
    ]

    baseline = run(
        common + ["--out", str(baseline_predictions), "--obs-probs-out", str(baseline_probs)],
        upstream,
    )
    assert_ok(baseline, "baseline decode")
    (output / "baseline.stdout.txt").write_text(baseline.stdout, encoding="utf-8")
    (output / "baseline.stderr.txt").write_text(baseline.stderr, encoding="utf-8")

    if trace.exists():
        raise RuntimeError("trace file exists before tracing was requested")

    traced = run(
        common
        + [
            "--out", str(traced_predictions),
            "--obs-probs-out", str(traced_probs),
            "--layer-stats-out", str(trace),
        ],
        upstream,
    )
    assert_ok(traced, "traced decode")
    (output / "traced.stdout.txt").write_text(traced.stdout, encoding="utf-8")
    (output / "traced.stderr.txt").write_text(traced.stderr, encoding="utf-8")

    if baseline_predictions.read_bytes() != traced_predictions.read_bytes():
        raise RuntimeError("prediction bytes changed when layer tracing was enabled")
    if baseline_probs.read_bytes() != traced_probs.read_bytes():
        raise RuntimeError("observable-probability bytes changed when layer tracing was enabled")

    trace_summary = validate_trace(trace, expected_detection_counts)

    stdout_rejection = run(
        common + ["--out", str(output / "reject.01"), "--layer-stats-out", "-"], upstream
    )
    if stdout_rejection.returncode == 0:
        raise RuntimeError("--layer-stats-out - must be rejected")
    rejection_text = stdout_rejection.stdout + "\n" + stdout_rejection.stderr
    if "--layer-stats-out must be a file path, not stdout" not in rejection_text:
        raise RuntimeError("stdout rejection did not use the expected diagnostic")
    (output / "stdout-rejection.txt").write_text(rejection_text, encoding="utf-8")

    summary = {
        "schema_version": 1,
        "phase": "P02b",
        "benchmark_valid": False,
        "input_shots": len(expected_detection_counts),
        "threads": 2,
        "semantic_equivalence": {
            "prediction_bytes_equal": True,
            "observable_probability_bytes_equal": True,
        },
        "trace": trace_summary,
        "sha256": {
            "dem": sha256(dem),
            "events": sha256(events),
            "baseline_predictions": sha256(baseline_predictions),
            "traced_predictions": sha256(traced_predictions),
            "baseline_probs": sha256(baseline_probs),
            "traced_probs": sha256(traced_probs),
            "layer_trace": sha256(trace),
        },
        "stdout_trace_path_rejected": True,
    }
    (output / "verification-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
