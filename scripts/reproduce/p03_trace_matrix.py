#!/usr/bin/env python3
"""Run the P03 functional Trellis trace matrix on public one-observable circuits.

This runner answers compatibility and structural questions only. It deliberately
marks all wall/phase timings as non-benchmark data because GitHub-hosted runners
are not controlled hardware. The same sampled shots are reused across ranking
modes within each circuit by keeping the sample seed fixed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from statistics import mean, median
from typing import Any

EXPECTED_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"
OBS_RE = re.compile(r"^\s*OBSERVABLE_INCLUDE\((\d+)\)", re.MULTILINE)


def sha256_file(path: Path) -> str:
    """Hash an input or output file so an experiment can identify exact bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def observable_width(text: str) -> int:
    """Return the circuit logical-observable width from Stim declarations.

    Observable indices are zero based, so max(index)+1 is the width. P03 uses
    this as a fail-closed compatibility check and never rewrites observables.
    """
    indices = [int(m.group(1)) for m in OBS_RE.finditer(text)]
    return max(indices) + 1 if indices else 0


def run(command: list[str], cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    """Run one decoder command while preserving failure evidence."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "timed_out": False,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": None,
            "timed_out": True,
            "stdout": exc.stdout if isinstance(exc.stdout, str) else "",
            "stderr": exc.stderr if isinstance(exc.stderr, str) else "",
        }


def load_trace(path: Path, expected_shots: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate P02b JSONL ordering and summarize hardware-independent counts."""
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(records) != expected_shots:
        raise RuntimeError(f"expected {expected_shots} trace records, got {len(records)}")

    all_layers: list[dict[str, Any]] = []
    low_confidence = 0
    per_shot_layers: list[int] = []
    for expected_index, record in enumerate(records):
        if (
            record.get("schema_version") != 1
            or record.get("record_type") != "tesseract_trellis_layer_trace"
        ):
            raise RuntimeError("unexpected P02b trace schema")
        if record.get("shot_index") != expected_index:
            raise RuntimeError("trace shot order is not deterministic")
        layers = record.get("layers")
        if not isinstance(layers, list):
            raise RuntimeError("trace layers must be a list")
        if record.get("num_layers") != len(layers):
            raise RuntimeError("num_layers mismatch")
        if record.get("low_confidence"):
            low_confidence += 1
        per_shot_layers.append(len(layers))
        for expected_layer, layer in enumerate(layers):
            if layer.get("layer_index") != expected_layer:
                raise RuntimeError("layer indices must be contiguous and ordered")
            all_layers.append(layer)

    def values(name: str) -> list[int]:
        return [int(layer[name]) for layer in all_layers]

    def summarize_int(name: str) -> dict[str, Any]:
        data = values(name)
        if not data:
            return {"min": None, "median": None, "mean": None, "max": None}
        return {
            "min": min(data),
            "median": median(data),
            "mean": mean(data),
            "max": max(data),
        }

    structural = {
        "trace_records": len(records),
        "low_confidence_shots": low_confidence,
        "layers_per_shot": per_shot_layers,
        "active_frontier_width": summarize_int("active_frontier_width"),
        "surviving_frontier_width": summarize_int("surviving_frontier_width"),
        "beam_in": summarize_int("beam_in"),
        "used_pair_buckets": summarize_int("used_pair_buckets"),
        "states_after_collapse": summarize_int("states_after_collapse"),
        "states_kept": summarize_int("states_kept"),
    }
    return records, structural


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    upstream = args.upstream_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    actual_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=upstream, text=True
    ).strip()
    if actual_sha != EXPECTED_SHA or actual_sha != manifest["source"]["commit"]:
        raise SystemExit(f"P03 upstream mismatch: expected {EXPECTED_SHA}, got {actual_sha}")

    binary = upstream / "bazel-bin/src/tesseract_trellis"
    if not binary.exists():
        raise SystemExit(f"missing instrumented Trellis binary: {binary}")

    shots = int(manifest["execution"]["sample_num_shots"])
    seed = int(manifest["execution"]["sample_seed"])
    threads = int(manifest["execution"]["threads"])
    beam = int(manifest["execution"]["beam_width"])
    ranking_modes = list(manifest["execution"]["ranking_modes"])

    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": "P03",
        "upstream_sha": actual_sha,
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
        "execution": manifest["execution"],
        "runs": [],
    }
    csv_rows: list[dict[str, Any]] = []
    overall_ok = True

    for case in manifest["cases"]:
        circuit = upstream / case["path"]
        case_text = circuit.read_text(encoding="utf-8")
        width = observable_width(case_text)
        if width != case["expected_observables"] or width != 1:
            raise RuntimeError(
                f"{case['id']}: expected exactly one observable, found {width}; "
                "P03 never rewrites observable semantics"
            )
        circuit_hash = sha256_file(circuit)

        for ranking_mode in ranking_modes:
            run_id = f"{case['id']}__{ranking_mode}"
            run_dir = output / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            predictions = run_dir / "predictions.01"
            probs = run_dir / "observable_probs.bin"
            trace = run_dir / "layer_trace.jsonl"
            stats = run_dir / "decoder_stats.json"

            command = [
                str(binary),
                "--circuit",
                str(circuit),
                "--sample-num-shots",
                str(shots),
                "--sample-seed",
                str(seed),
                "--threads",
                str(threads),
                "--beam",
                str(beam),
                "--ranking-mode",
                ranking_mode,
                "--out",
                str(predictions),
                "--out-format",
                "01",
                "--obs-probs-out",
                str(probs),
                "--layer-stats-out",
                str(trace),
                "--stats-out",
                str(stats),
            ]
            result = run(command, upstream, args.timeout_seconds)
            (run_dir / "stdout.txt").write_text(result["stdout"], encoding="utf-8")
            (run_dir / "stderr.txt").write_text(result["stderr"], encoding="utf-8")
            (run_dir / "command.json").write_text(
                json.dumps(
                    {k: v for k, v in result.items() if k not in {"stdout", "stderr"}},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            run_ok = not result["timed_out"] and result["returncode"] == 0
            structural: dict[str, Any] | None = None
            if run_ok:
                _, structural = load_trace(trace, shots)
            else:
                overall_ok = False

            entry = {
                "run_id": run_id,
                "case_id": case["id"],
                "family": case["family"],
                "distance": case["distance"],
                "qubits": case["qubits"],
                "p": case["p"],
                "basis": case["basis"],
                "ranking_mode": ranking_mode,
                "observables": width,
                "circuit_sha256": circuit_hash,
                "run_ok": run_ok,
                "timed_out": result["timed_out"],
                "returncode": result["returncode"],
                "structural": structural,
            }
            summary["runs"].append(entry)

            if structural is not None:
                csv_rows.append(
                    {
                        "run_id": run_id,
                        "family": case["family"],
                        "distance": case["distance"],
                        "qubits": case["qubits"],
                        "p": case["p"],
                        "basis": case["basis"],
                        "ranking_mode": ranking_mode,
                        "shots": shots,
                        "low_confidence_shots": structural["low_confidence_shots"],
                        "max_active_frontier": structural["active_frontier_width"]["max"],
                        "max_beam_in": structural["beam_in"]["max"],
                        "max_states_after_collapse": structural["states_after_collapse"]["max"],
                        "max_states_kept": structural["states_kept"]["max"],
                    }
                )

    summary["overall_ok"] = overall_ok and all(run["run_ok"] for run in summary["runs"])
    (output / "p03-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if csv_rows:
        with (output / "structural-summary.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)

    return 0 if summary["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
