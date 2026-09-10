#!/usr/bin/env python3
"""Run the patched Tesseract Trellis CLI on the selected real BB circuits.

This is an integration/correctness smoke test, NOT a performance benchmark.
GitHub runner timings are deliberately not interpreted scientifically.
"""

import argparse
import csv
import json
import subprocess
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--selection", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--shots", type=int, default=1)
    ap.add_argument("--beam", type=int, default=1024)
    args = ap.parse_args()

    root = Path(args.upstream_dir).resolve()
    binary = root / "bazel-bin" / "src" / "tesseract_trellis"
    if not binary.is_file():
        raise SystemExit(f"Missing built CLI: {binary}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with Path(args.selection).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if len(rows) != 8:
        raise SystemExit(f"Expected 8 selected X/Z circuits, got {len(rows)}")

    summary = []
    for index, row in enumerate(rows):
        case = f"{row['name']}-{row['basis']}"
        circuit = root / row["path"]
        stats_path = out_dir / f"{case}.stats.json"
        stdout_path = out_dir / f"{case}.stdout.log"
        stderr_path = out_dir / f"{case}.stderr.log"
        seed = 800000 + index
        cmd = [
            str(binary),
            "--circuit", str(circuit),
            "--sample-num-shots", str(args.shots),
            "--sample-seed", str(seed),
            "--threads", "1",
            "--beam", str(args.beam),
            "--beam-eps", "0",
            "--ranking-mode", "mass",
            "--stats-out", str(stats_path),
        ]
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout_path.write_text(proc.stdout, encoding="utf-8")
        stderr_path.write_text(proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise SystemExit(
                f"{case}: CLI failed with exit {proc.returncode}. See {stderr_path}.\n{proc.stderr[-4000:]}"
            )
        if not stats_path.is_file():
            raise SystemExit(f"{case}: CLI returned success but did not write stats")
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        expected_obs = int(row["k"])
        actual_obs = int(stats.get("num_observables", -1))
        if actual_obs != expected_obs:
            raise SystemExit(f"{case}: DEM reports {actual_obs} observables, expected {expected_obs}")
        if int(stats.get("num_shots", -1)) != args.shots:
            raise SystemExit(f"{case}: decoded shot count does not match requested count")

        item = {
            "case": case,
            "n": int(row["n"]),
            "k": expected_obs,
            "d": int(row["d"]),
            "basis": row["basis"],
            "p": float(row["p"]),
            "circuit_sha256": row["sha256"],
            "seed": seed,
            "shots": args.shots,
            "beam": args.beam,
            "ranking_mode": "mass",
            "num_observables_from_dem": actual_obs,
            "num_low_confidence": int(stats["num_low_confidence"]),
            "num_errors_excluding_low_confidence": int(stats["num_errors"]),
            "exit_code": proc.returncode,
            "benchmark_valid": False,
        }
        summary.append(item)
        print(
            f"PASS {case}: [[{item['n']},{item['k']},{item['d']}]] p={item['p']} "
            f"obs={actual_obs} shots={args.shots} low_conf={item['num_low_confidence']} "
            f"errors={item['num_errors_excluding_low_confidence']}"
        )

    family_pattern = []
    for name in ("BB72", "BB90", "BB108", "BB144"):
        family_rows = [x for x in summary if x["case"].startswith(name + "-")]
        if len(family_rows) != 2:
            raise SystemExit(f"{name}: expected X and Z results")
        if family_rows[0]["k"] != family_rows[1]["k"]:
            raise SystemExit(f"{name}: X/Z observable counts disagree")
        family_pattern.append(family_rows[0]["k"])
    if family_pattern != [12, 8, 8, 12]:
        raise SystemExit(f"Wrong BB observable pattern: {family_pattern}")

    report = {
        "phase": "P08",
        "purpose": "real public BB integration test for independently reconstructed 0..64-observable Trellis",
        "upstream_circuits": 8,
        "families": ["[[72,12,6]]", "[[90,8,10]]", "[[108,8,10]]", "[[144,12,12]]"],
        "observable_pattern": family_pattern,
        "p": 0.001,
        "all_cli_runs_exit_zero": True,
        "all_dem_observable_counts_match": True,
        "benchmark_valid": False,
        "private_equivalence_claimed": False,
        "results": summary,
    }
    (out_dir / "P08_REAL_BB_SUMMARY.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("PASS: all 8 real BB X/Z circuits ran through the multiobservable Trellis CLI")
    print("PASS: DEM observable pattern is exactly 12/8/8/12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
