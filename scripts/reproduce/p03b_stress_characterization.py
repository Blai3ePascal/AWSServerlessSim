#!/usr/bin/env python3
"""P03b deterministic beam-pressure stress characterization.

This script uses only structural counts from the P02 JSONL trace. It runs every
configuration twice and requires prediction bytes plus timing-stripped traces to
match exactly. Absolute timing is never analyzed on the shared CI runner.
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
TIMING_FIELDS = {"expand_seconds", "collapse_seconds", "truncate_seconds"}

FIXTURES = {
    "stress10": {
        "dem": """error(0.041) D0 D5\nerror(0.047) D1 D6\nerror(0.053) D2 D7\nerror(0.059) D3 D8\nerror(0.061) D4 D9\nerror(0.067) D0 D6 L0\nerror(0.071) D1 D7\nerror(0.073) D2 D8 L0\nerror(0.079) D3 D9\nerror(0.083) D4 D5\nerror(0.089) D0 D7\nerror(0.097) D1 D8 L0\nerror(0.101) D2 D9\nerror(0.103) D3 D5 L0\ndetector(0,0,0) D0\ndetector(1,0,0) D1\ndetector(2,0,0) D2\ndetector(3,0,0) D3\ndetector(4,0,0) D4\ndetector(5,0,0) D5\ndetector(6,0,0) D6\ndetector(7,0,0) D7\ndetector(8,0,0) D8\ndetector(9,0,0) D9\n""",
        "events": "1000010000\n1100011000\n1010001010\n1110000111\n",
    },
    "stress12": {
        "dem": """error(0.031) D0 D6\nerror(0.037) D1 D7\nerror(0.043) D2 D8\nerror(0.049) D3 D9\nerror(0.051) D4 D10\nerror(0.057) D5 D11\nerror(0.063) D0 D7 L0\nerror(0.069) D1 D8\nerror(0.071) D2 D9 L0\nerror(0.077) D3 D10\nerror(0.081) D4 D11 L0\nerror(0.087) D5 D6\nerror(0.091) D0 D8 D10\nerror(0.093) D1 D9 D11 L0\nerror(0.099) D2 D6 D10\nerror(0.101) D3 D7 D11\nerror(0.107) D4 D6 D8 L0\nerror(0.109) D5 D7 D9\ndetector(0,0,0) D0\ndetector(1,0,0) D1\ndetector(2,0,0) D2\ndetector(3,0,0) D3\ndetector(4,0,0) D4\ndetector(5,0,0) D5\ndetector(6,0,0) D6\ndetector(7,0,0) D7\ndetector(8,0,0) D8\ndetector(9,0,0) D9\ndetector(10,0,0) D10\ndetector(11,0,0) D11\n""",
        "events": "100000100000\n110000110000\n101000010100\n110000001111\n",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)


def load_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_structural(records: list[dict[str, Any]]) -> bytes:
    clean = []
    for record in records:
        r = dict(record)
        r["layers"] = [{k: v for k, v in layer.items() if k not in TIMING_FIELDS}
                       for layer in record["layers"]]
        clean.append(r)
    return (json.dumps(clean, sort_keys=True, separators=(",", ":")) + "\n").encode()


def cv(values: list[float]) -> float:
    if not values: return 0.0
    m = mean(values)
    if m == 0: return 0.0
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values)) / m


def validate(record: dict[str, Any]) -> None:
    if record.get("schema_version") != 1:
        raise RuntimeError("unexpected trace schema")
    layers = record.get("layers", [])
    if record.get("num_layers") != len(layers) or not layers:
        raise RuntimeError("missing/inconsistent layers")
    for i, layer in enumerate(layers):
        if layer["layer_index"] != i: raise RuntimeError("unordered layers")
        if layer["active_frontier_width"] < layer["surviving_frontier_width"]:
            raise RuntimeError("frontier invariant failed")
        if layer["beam_in"] < 1: raise RuntimeError("beam invariant failed")
        if layer["used_pair_buckets"] > layer["states_after_collapse"]:
            raise RuntimeError("bucket invariant failed")
        if layer["states_after_collapse"] < layer["states_kept"]:
            raise RuntimeError("retention invariant failed")


def metrics(fixture: str, beam: int, ranking: str, record: dict[str, Any]) -> dict[str, Any]:
    validate(record)
    layers = record["layers"]
    active = [x["active_frontier_width"] for x in layers]
    collapsed = [x["states_after_collapse"] for x in layers]
    kept = [x["states_kept"] for x in layers]
    truncating = sum(c > k for c, k in zip(collapsed, kept))
    saturated = sum(k == beam for k in kept)
    pressure = sum(c > k and k == beam for c, k in zip(collapsed, kept))
    retention = [k / c for c, k in zip(collapsed, kept) if c > 0]
    return {
        "fixture": fixture,
        "beam": beam,
        "ranking": ranking,
        "shot_index": record["shot_index"],
        "detection_count": record["detection_count"],
        "low_confidence": int(bool(record["low_confidence"])),
        "predicted_obs_mask": record["predicted_obs_mask"],
        "num_layers": len(layers),
        "max_active_frontier": max(active),
        "max_beam_in": max(x["beam_in"] for x in layers),
        "max_states_after_collapse": max(collapsed),
        "total_states_after_collapse": sum(collapsed),
        "cv_active_frontier": cv([float(x) for x in active]),
        "cv_states_after_collapse": cv([float(x) for x in collapsed]),
        "mean_retention_fraction": mean(retention) if retention else 0.0,
        "truncating_layers": truncating,
        "beam_saturated_layers": saturated,
        "beam_pressure_layers": pressure,
        "beam_pressure_fraction": pressure / len(layers),
        "max_pretruncation_excess": max((c-k for c,k in zip(collapsed, kept)), default=0),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    upstream = args.upstream_dir.resolve(); output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = upstream / "bazel-bin/src/tesseract_trellis"
    if not binary.exists(): raise SystemExit(f"missing binary {binary}")

    fixture_dir = output / "fixtures"; raw_dir = output / "raw"
    fixture_dir.mkdir(exist_ok=True); raw_dir.mkdir(exist_ok=True)
    paths = {}
    for name, fixture in FIXTURES.items():
        dem = fixture_dir / f"{name}.dem"; events = fixture_dir / f"{name}.events.01"
        dem.write_text(fixture["dem"], encoding="utf-8")
        events.write_text(fixture["events"], encoding="utf-8")
        paths[name] = (dem, events)

    rows = []; configs = []; determinism = 0
    for fixture, (dem, events) in paths.items():
        for beam in BEAMS:
            for ranking in RANKINGS:
                key = f"{fixture}__beam{beam}__{ranking}"
                rep_data = []
                for rep in (1, 2):
                    trace = raw_dir / f"{key}__rep{rep}.jsonl"
                    pred = raw_dir / f"{key}__rep{rep}.predictions.01"
                    cmd = [str(binary), "--dem", str(dem), "--in", str(events),
                           "--in-format", "01", "--out", str(pred), "--out-format", "01",
                           "--threads", "1", "--beam", str(beam), "--ranking-mode", ranking,
                           "--layer-stats-out", str(trace)]
                    result = run(cmd, upstream)
                    (raw_dir / f"{key}__rep{rep}.run.json").write_text(json.dumps({
                        "command": cmd, "returncode": result.returncode,
                        "benchmark_valid": False, "stdout": result.stdout, "stderr": result.stderr
                    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                    if result.returncode != 0:
                        raise RuntimeError(f"{key} rep {rep} failed: {result.stderr}")
                    records = load_trace(trace)
                    if len(records) != 4: raise RuntimeError(f"{key}: expected 4 shots")
                    for r in records: validate(r)
                    rep_data.append((pred, records))
                pred1, rec1 = rep_data[0]; pred2, rec2 = rep_data[1]
                if pred1.read_bytes() != pred2.read_bytes():
                    raise RuntimeError(f"{key}: prediction determinism failed")
                if canonical_structural(rec1) != canonical_structural(rec2):
                    raise RuntimeError(f"{key}: structural determinism failed")
                determinism += 1
                shot_rows = [metrics(fixture, beam, ranking, r) for r in rec1]
                rows.extend(shot_rows)
                configs.append({
                    "fixture": fixture, "beam": beam, "ranking": ranking,
                    "shots": 4,
                    "low_confidence_shots": sum(r["low_confidence"] for r in shot_rows),
                    "beam_pressure_shots": sum(r["beam_pressure_layers"] > 0 for r in shot_rows),
                    "total_beam_pressure_layers": sum(r["beam_pressure_layers"] for r in shot_rows),
                    "max_beam_pressure_fraction": max(r["beam_pressure_fraction"] for r in shot_rows),
                    "max_active_frontier": max(r["max_active_frontier"] for r in shot_rows),
                    "max_beam_in": max(r["max_beam_in"] for r in shot_rows),
                    "max_states_after_collapse": max(r["max_states_after_collapse"] for r in shot_rows),
                    "max_pretruncation_excess": max(r["max_pretruncation_excess"] for r in shot_rows),
                    "prediction_signature": pred1.read_text(encoding="utf-8").replace("\n", "|"),
                })

    write_csv(output / "shot_metrics.csv", rows)
    write_csv(output / "configuration_summary.csv", configs)
    beam4_pressure = [c for c in configs if c["beam"] == 4 and c["total_beam_pressure_layers"] > 0]
    summary = {
        "schema_version": 1, "phase": "P03b", "benchmark_valid": False,
        "configuration_points": len(configs), "runs": len(configs)*2,
        "shots_analyzed": len(rows), "determinism_checks_passed": determinism,
        "beam4_pressure_configurations": len(beam4_pressure),
        "beam4_pressure_observed": bool(beam4_pressure),
        "max_active_frontier": max(r["max_active_frontier"] for r in rows),
        "max_beam_in": max(r["max_beam_in"] for r in rows),
        "max_states_after_collapse": max(r["max_states_after_collapse"] for r in rows),
        "max_pretruncation_excess": max(r["max_pretruncation_excess"] for r in rows),
        "fixture_sha256": {n: {"dem": sha256(p[0]), "events": sha256(p[1])} for n,p in paths.items()},
        "timing_interpretation_allowed": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n",
                                         encoding="utf-8")
    if not beam4_pressure:
        raise RuntimeError("P03b NO-GO: stress corpus never created actual beam-4 truncation pressure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
