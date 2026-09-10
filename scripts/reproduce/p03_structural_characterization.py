#!/usr/bin/env python3
"""Run P03 structural characterization of instrumented Tesseract Trellis.

The script intentionally derives conclusions only from deterministic counts in
P02 layer traces. Timing fields are retained as raw evidence but excluded from
all metrics because shared CI runners are not controlled benchmark hardware.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path
from statistics import mean
from typing import Any

BEAMS = (4, 16, 64)
RANKINGS = ("mass", "future-detcost", "future-active-detcost")

FIXTURES = {
    "chain4": {
        "dem": """error(0.08) D0\nerror(0.10) D0 D1\nerror(0.12) D1 D2\nerror(0.14) D2 D3\nerror(0.16) D3 L0\ndetector(0,0,0) D0\ndetector(1,0,0) D1\ndetector(2,0,0) D2\ndetector(3,0,0) D3\n""",
        "events": "1000\n0100\n1010\n1111\n",
    },
    "branch6": {
        "dem": """error(0.07) D0 D2\nerror(0.08) D0 D3 L0\nerror(0.09) D1 D2\nerror(0.10) D1 D4\nerror(0.11) D2 D5\nerror(0.12) D3 D4\nerror(0.13) D4 D5 L0\nerror(0.06) D5\ndetector(0,0,0) D0\ndetector(1,0,0) D1\ndetector(2,0,0) D2\ndetector(3,0,0) D3\ndetector(4,0,0) D4\ndetector(5,0,0) D5\n""",
        "events": "100000\n001001\n110010\n111111\n",
    },
    "retire8": {
        "dem": """error(0.05) D0 D4\nerror(0.06) D1 D4\nerror(0.07) D0 D2 D5\nerror(0.08) D1 D3 D5 L0\nerror(0.09) D2 D6\nerror(0.10) D3 D6\nerror(0.11) D4 D7\nerror(0.12) D5 D7\nerror(0.13) D6\nerror(0.14) D7 L0\ndetector(0,0,0) D0\ndetector(1,0,0) D1\ndetector(2,0,0) D2\ndetector(3,0,0) D3\ndetector(4,0,0) D4\ndetector(5,0,0) D5\ndetector(6,0,0) D6\ndetector(7,0,0) D7\n""",
        "events": "10000000\n00001100\n10100101\n11111111\n",
    },
}

TIMING_FIELDS = {"expand_seconds", "collapse_seconds", "truncate_seconds"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def cv(values: list[float]) -> float:
    """Population coefficient of variation; zero when the mean is zero."""
    if not values:
        return 0.0
    m = mean(values)
    if m == 0:
        return 0.0
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / m


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)


def load_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_structural_trace(records: list[dict[str, Any]]) -> bytes:
    """Canonicalize a trace after removing timing-only fields."""
    cleaned: list[dict[str, Any]] = []
    for record in records:
        copy = dict(record)
        layers = []
        for layer in record["layers"]:
            layers.append({k: v for k, v in layer.items() if k not in TIMING_FIELDS})
        copy["layers"] = layers
        cleaned.append(copy)
    return (json.dumps(cleaned, sort_keys=True, separators=(",", ":")) + "\n").encode()


def validate_record(record: dict[str, Any]) -> None:
    if record.get("schema_version") != 1 or record.get("record_type") != "tesseract_trellis_layer_trace":
        raise RuntimeError("invalid P02 trace schema")
    layers = record.get("layers")
    if not isinstance(layers, list) or record.get("num_layers") != len(layers):
        raise RuntimeError("invalid layer array")
    for i, layer in enumerate(layers):
        if layer["layer_index"] != i:
            raise RuntimeError("non-contiguous layer index")
        if layer["active_frontier_width"] < layer["surviving_frontier_width"]:
            raise RuntimeError("surviving frontier exceeds active frontier")
        if layer["beam_in"] < 1:
            raise RuntimeError("beam_in must be positive")
        if layer["used_pair_buckets"] > layer["states_after_collapse"]:
            raise RuntimeError("pair buckets exceed collapsed states")
        if layer["states_after_collapse"] < layer["states_kept"]:
            raise RuntimeError("kept states exceed collapsed states")


def shot_metrics(fixture: str, beam: int, ranking: str, record: dict[str, Any]) -> dict[str, Any]:
    validate_record(record)
    layers = record["layers"]
    active = [float(x["active_frontier_width"]) for x in layers]
    beam_in = [float(x["beam_in"]) for x in layers]
    collapsed = [float(x["states_after_collapse"]) for x in layers]
    kept = [float(x["states_kept"]) for x in layers]
    retention = [k / c for k, c in zip(kept, collapsed) if c > 0]
    expansion = [c / b for c, b in zip(collapsed, beam_in) if b > 0]
    return {
        "fixture": fixture,
        "beam": beam,
        "ranking": ranking,
        "shot_index": record["shot_index"],
        "detection_count": record["detection_count"],
        "low_confidence": int(bool(record["low_confidence"])),
        "predicted_obs_mask": record["predicted_obs_mask"],
        "num_layers": len(layers),
        "max_active_frontier": int(max(active, default=0)),
        "mean_active_frontier": mean(active) if active else 0.0,
        "cv_active_frontier": cv(active),
        "max_beam_in": int(max(beam_in, default=0)),
        "max_states_after_collapse": int(max(collapsed, default=0)),
        "total_states_after_collapse": int(sum(collapsed)),
        "cv_states_after_collapse": cv(collapsed),
        "mean_retention_fraction": mean(retention) if retention else 0.0,
        "min_retention_fraction": min(retention, default=0.0),
        "mean_collapse_expansion_factor": mean(expansion) if expansion else 0.0,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"cannot write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


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
        raise SystemExit(f"missing instrumented binary: {binary}")

    fixtures_dir = output / "fixtures"
    raw_dir = output / "raw"
    fixtures_dir.mkdir(exist_ok=True)
    raw_dir.mkdir(exist_ok=True)

    fixture_paths: dict[str, tuple[Path, Path]] = {}
    for name, content in FIXTURES.items():
        dem = fixtures_dir / f"{name}.dem"
        events = fixtures_dir / f"{name}.events.01"
        dem.write_text(content["dem"], encoding="utf-8")
        events.write_text(content["events"], encoding="utf-8")
        fixture_paths[name] = (dem, events)

    all_rows: list[dict[str, Any]] = []
    config_summaries: list[dict[str, Any]] = []
    determinism_checks = 0

    for fixture, (dem, events) in fixture_paths.items():
        for beam in BEAMS:
            for ranking in RANKINGS:
                config_name = f"{fixture}__beam{beam}__{ranking}"
                reps: list[tuple[Path, Path, list[dict[str, Any]]]] = []
                for rep in (1, 2):
                    trace = raw_dir / f"{config_name}__rep{rep}.jsonl"
                    predictions = raw_dir / f"{config_name}__rep{rep}.predictions.01"
                    command = [
                        str(binary), "--dem", str(dem), "--in", str(events),
                        "--in-format", "01", "--out", str(predictions), "--out-format", "01",
                        "--threads", "1", "--beam", str(beam), "--ranking-mode", ranking,
                        "--layer-stats-out", str(trace),
                    ]
                    result = run(command, upstream)
                    metadata = {
                        "command": command,
                        "returncode": result.returncode,
                        "benchmark_valid": False,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                    (raw_dir / f"{config_name}__rep{rep}.run.json").write_text(
                        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                    if result.returncode != 0:
                        raise RuntimeError(f"{config_name} rep {rep} failed: {result.stderr}")
                    records = load_trace(trace)
                    if len(records) != 4:
                        raise RuntimeError(f"{config_name}: expected four shots, got {len(records)}")
                    for record in records:
                        validate_record(record)
                    reps.append((trace, predictions, records))

                trace1, pred1, records1 = reps[0]
                trace2, pred2, records2 = reps[1]
                if pred1.read_bytes() != pred2.read_bytes():
                    raise RuntimeError(f"{config_name}: predictions are not deterministic")
                if canonical_structural_trace(records1) != canonical_structural_trace(records2):
                    raise RuntimeError(f"{config_name}: timing-stripped structural trace differs")
                determinism_checks += 1

                rows = [shot_metrics(fixture, beam, ranking, r) for r in records1]
                all_rows.extend(rows)
                config_summaries.append({
                    "fixture": fixture,
                    "beam": beam,
                    "ranking": ranking,
                    "shots": len(rows),
                    "low_confidence_shots": sum(r["low_confidence"] for r in rows),
                    "max_active_frontier": max(r["max_active_frontier"] for r in rows),
                    "max_beam_in": max(r["max_beam_in"] for r in rows),
                    "max_states_after_collapse": max(r["max_states_after_collapse"] for r in rows),
                    "mean_total_states_after_collapse": mean(r["total_states_after_collapse"] for r in rows),
                    "mean_cv_active_frontier": mean(r["cv_active_frontier"] for r in rows),
                    "mean_cv_states_after_collapse": mean(r["cv_states_after_collapse"] for r in rows),
                    "mean_retention_fraction": mean(r["mean_retention_fraction"] for r in rows),
                    "mean_collapse_expansion_factor": mean(r["mean_collapse_expansion_factor"] for r in rows),
                })

    write_csv(output / "shot_metrics.csv", all_rows)
    write_csv(output / "configuration_summary.csv", config_summaries)

    summary = {
        "schema_version": 1,
        "phase": "P03",
        "benchmark_valid": False,
        "fixtures": sorted(FIXTURES),
        "beam_widths": list(BEAMS),
        "ranking_modes": list(RANKINGS),
        "configuration_points": len(config_summaries),
        "runs": len(config_summaries) * 2,
        "shots_analyzed": len(all_rows),
        "determinism_checks_passed": determinism_checks,
        "structural_extrema": {
            "max_active_frontier": max(r["max_active_frontier"] for r in all_rows),
            "max_beam_in": max(r["max_beam_in"] for r in all_rows),
            "max_states_after_collapse": max(r["max_states_after_collapse"] for r in all_rows),
            "max_cv_active_frontier": max(r["cv_active_frontier"] for r in all_rows),
            "max_cv_states_after_collapse": max(r["cv_states_after_collapse"] for r in all_rows),
        },
        "fixture_sha256": {
            name: {"dem": sha256(paths[0]), "events": sha256(paths[1])}
            for name, paths in fixture_paths.items()
        },
        "timing_interpretation_allowed": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
