#!/usr/bin/env python3
"""P04 controlled-host CPU benchmark for Tesseract Trellis.

Two modes are intentionally separated:

* validate: exercises the harness anywhere, including CI, but never creates a
  scientifically valid benchmark.
* benchmark: refuses recognized CI environments and records robust repeated
  measurements from a user-labelled controlled host.

The decoder's own `total_time_seconds` is the primary algorithm-time source.
Wall time, RSS and optional perf counters are kept separately so process/I/O
cost is not confused with `decode_shot` cost.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UPSTREAM_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"
BEAMS = (4, 16, 64)
RANKINGS = ("mass", "future-detcost", "future-active-detcost")

FIXTURES = {
    "stress10": {
        "dem": """error(0.041) D0 D5\nerror(0.047) D1 D6\nerror(0.053) D2 D7\nerror(0.059) D3 D8\nerror(0.061) D4 D9\nerror(0.067) D0 D6 L0\nerror(0.071) D1 D7\nerror(0.073) D2 D8 L0\nerror(0.079) D3 D9\nerror(0.083) D4 D5\nerror(0.089) D0 D7\nerror(0.097) D1 D8 L0\nerror(0.101) D2 D9\nerror(0.103) D3 D5 L0\ndetector(0,0,0) D0\ndetector(1,0,0) D1\ndetector(2,0,0) D2\ndetector(3,0,0) D3\ndetector(4,0,0) D4\ndetector(5,0,0) D5\ndetector(6,0,0) D6\ndetector(7,0,0) D7\ndetector(8,0,0) D8\ndetector(9,0,0) D9\n""",
        "events4": "1000010000\n1100011000\n1010001010\n1110000111\n",
        "detectors": 10,
    },
    "stress12": {
        "dem": """error(0.031) D0 D6\nerror(0.037) D1 D7\nerror(0.043) D2 D8\nerror(0.049) D3 D9\nerror(0.051) D4 D10\nerror(0.057) D5 D11\nerror(0.063) D0 D7 L0\nerror(0.069) D1 D8\nerror(0.071) D2 D9 L0\nerror(0.077) D3 D10\nerror(0.081) D4 D11 L0\nerror(0.087) D5 D6\nerror(0.091) D0 D8 D10\nerror(0.093) D1 D9 D11 L0\nerror(0.099) D2 D6 D10\nerror(0.101) D3 D7 D11\nerror(0.107) D4 D6 D8 L0\nerror(0.109) D5 D7 D9\ndetector(0,0,0) D0\ndetector(1,0,0) D1\ndetector(2,0,0) D2\ndetector(3,0,0) D3\ndetector(4,0,0) D4\ndetector(5,0,0) D5\ndetector(6,0,0) D6\ndetector(7,0,0) D7\ndetector(8,0,0) D8\ndetector(9,0,0) D9\ndetector(10,0,0) D10\ndetector(11,0,0) D11\n""",
        "events4": "100000100000\n110000110000\n101000010100\n110000001111\n",
        "detectors": 12,
    },
}

CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "TF_BUILD", "JENKINS_URL")
PERF_EVENTS = "cycles,instructions,branches,branch-misses,cache-references,cache-misses,task-clock"


def command_text(command: list[str]) -> str:
    """Return an auditable shell-like rendering without using a shell to execute it."""
    import shlex
    return " ".join(shlex.quote(x) for x in command)


def capture(command: list[str], cwd: Path | None = None) -> str | None:
    """Best-effort environment query; absence is evidence and not fatal."""
    try:
        p = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=20, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()


def percentile_nearest(values: list[float], q: float) -> float:
    """Nearest-rank-like percentile with linear index rounding for small repeated samples."""
    if not values: return math.nan
    xs = sorted(values)
    return xs[int(round((len(xs) - 1) * q))]


def robust_summary(values: list[float]) -> dict[str, float]:
    med = statistics.median(values)
    return {
        "min": min(values),
        "median": med,
        "p95": percentile_nearest(values, 0.95),
        "max": max(values),
        "mad": statistics.median(abs(v - med) for v in values),
    }


def parse_gnu_time(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    out: dict[str, Any] = {"raw": text}
    m = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", text)
    if m: out["max_rss_kb"] = int(m.group(1))
    return out


def parse_perf(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(",")
        if len(parts) >= 3:
            rows.append({"value": parts[0].strip(), "unit": parts[1].strip(),
                         "event": parts[2].strip()})
    return {"rows": rows}


def environment(upstream: Path, machine_label: str, mode: str) -> dict[str, Any]:
    ci = {name: os.environ.get(name) for name in CI_ENV_VARS if os.environ.get(name)}
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "machine_label": machine_label,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "recognized_ci": ci,
        "upstream_sha": capture(["git", "rev-parse", "HEAD"], upstream),
        "upstream_status_porcelain": capture(["git", "status", "--porcelain"], upstream),
        "harness_sha": capture(["git", "rev-parse", "HEAD"], Path.cwd()),
        "lscpu": capture(["lscpu"]),
        "memory": capture(["free", "-h"]),
        "uname": capture(["uname", "-a"]),
        "bazel": capture(["bazel", "--version"], upstream),
        "gcc": capture(["gcc", "--version"]),
        "clang": capture(["clang", "--version"]),
        "perf_version": capture(["perf", "--version"]),
        "scaling_governor": capture(["bash", "-lc", "cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort -u"]),
    }


def run_one(binary: Path, upstream: Path, dem: Path, events: Path, beam: int, ranking: str,
            stats: Path, time_file: Path, perf_file: Path | None) -> dict[str, Any]:
    base = [str(binary), "--dem", str(dem), "--in", str(events), "--in-format", "01",
            "--threads", "1", "--beam", str(beam), "--ranking-mode", ranking,
            "--stats-out", str(stats)]
    command = base
    perf_used = False
    if perf_file is not None:
        command = ["perf", "stat", "-x,", "-e", PERF_EVENTS, "-o", str(perf_file), "--"] + command
        perf_used = True
    if Path("/usr/bin/time").exists():
        command = ["/usr/bin/time", "-v", "-o", str(time_file), "--"] + command
    t0 = time.perf_counter_ns()
    p = subprocess.run(command, cwd=upstream, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, check=False)
    wall_s = (time.perf_counter_ns() - t0) / 1e9
    if p.returncode != 0:
        raise RuntimeError(f"benchmark command failed: {command_text(command)}\n{p.stderr}")
    stats_data = json.loads(stats.read_text(encoding="utf-8"))
    return {
        "command": command,
        "returncode": p.returncode,
        "wall_seconds": wall_s,
        "decoder_total_seconds": float(stats_data["total_time_seconds"]),
        "num_shots": int(stats_data["num_shots"]),
        "num_low_confidence": int(stats_data["num_low_confidence"]),
        "gnu_time": parse_gnu_time(time_file),
        "perf": parse_perf(perf_file) if perf_used and perf_file else {},
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("validate", "benchmark"), required=True)
    ap.add_argument("--machine-label", default="validation-run")
    ap.add_argument("--upstream-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--event-block-repeats", type=int, default=250)
    ap.add_argument("--warmups", type=int, default=2)
    ap.add_argument("--repetitions", type=int, default=10)
    ap.add_argument("--with-perf", action="store_true")
    args = ap.parse_args()

    if args.event_block_repeats < 1 or args.warmups < 0 or args.repetitions < 1:
        raise SystemExit("repeat/warmup/repetition counts must be positive (warmups may be zero)")
    recognized_ci = {k: os.environ.get(k) for k in CI_ENV_VARS if os.environ.get(k)}
    if args.mode == "benchmark" and recognized_ci:
        raise SystemExit(f"benchmark mode refuses recognized CI environment: {sorted(recognized_ci)}")

    upstream = args.upstream_dir.resolve(); output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    binary = upstream / "bazel-bin/src/tesseract_trellis"
    actual_sha = capture(["git", "rev-parse", "HEAD"], upstream)
    if actual_sha != UPSTREAM_SHA:
        raise SystemExit(f"expected upstream {UPSTREAM_SHA}, got {actual_sha}")
    if not binary.exists(): raise SystemExit(f"missing binary: {binary}")

    env = environment(upstream, args.machine_label, args.mode)
    benchmark_valid = args.mode == "benchmark" and not recognized_ci
    env["benchmark_valid"] = benchmark_valid
    (output / "environment.json").write_text(json.dumps(env, indent=2, sort_keys=True)+"\n", encoding="utf-8")

    fixtures_dir = output / "fixtures"; raw_dir = output / "raw"
    fixtures_dir.mkdir(exist_ok=True); raw_dir.mkdir(exist_ok=True)
    fixtures = {}
    for name, f in FIXTURES.items():
        dem = fixtures_dir / f"{name}.dem"; events = fixtures_dir / f"{name}.events.01"
        dem.write_text(f["dem"], encoding="utf-8")
        events.write_text(f["events4"] * args.event_block_repeats, encoding="utf-8")
        fixtures[name] = (dem, events, f)

    # CI validation intentionally uses a very small matrix. It tests schemas and
    # command composition, not performance.
    beams = (4,) if args.mode == "validate" else BEAMS
    rankings = ("mass",) if args.mode == "validate" else RANKINGS
    repetitions = 1 if args.mode == "validate" else args.repetitions
    warmups = 0 if args.mode == "validate" else args.warmups

    rows: list[dict[str, Any]] = []
    for fixture, (dem, events, meta) in fixtures.items():
        for beam in beams:
            for ranking in rankings:
                key = f"{fixture}__beam{beam}__{ranking}"
                for w in range(warmups):
                    scratch = raw_dir / f"{key}__warmup{w}"
                    run_one(binary, upstream, dem, events, beam, ranking,
                            scratch.with_suffix(".stats.json"), scratch.with_suffix(".time.txt"), None)
                for rep in range(repetitions):
                    prefix = raw_dir / f"{key}__rep{rep:02d}"
                    perf_file = prefix.with_suffix(".perf.csv") if args.with_perf and shutil.which("perf") else None
                    result = run_one(binary, upstream, dem, events, beam, ranking,
                                     prefix.with_suffix(".stats.json"), prefix.with_suffix(".time.txt"), perf_file)
                    raw = dict(result)
                    stdout = raw.pop("stdout"); stderr = raw.pop("stderr")
                    (prefix.with_suffix(".stdout.txt")).write_text(stdout, encoding="utf-8")
                    (prefix.with_suffix(".stderr.txt")).write_text(stderr, encoding="utf-8")
                    (prefix.with_suffix(".run.json")).write_text(json.dumps(raw, indent=2, sort_keys=True)+"\n", encoding="utf-8")
                    n = result["num_shots"]
                    rows.append({
                        "fixture": fixture, "beam": beam, "ranking": ranking, "repetition": rep,
                        "num_shots": n, "detectors": meta["detectors"],
                        "decoder_us_per_shot": result["decoder_total_seconds"] * 1e6 / n,
                        "wall_us_per_shot": result["wall_seconds"] * 1e6 / n,
                        "max_rss_kb": result["gnu_time"].get("max_rss_kb", ""),
                        "num_low_confidence": result["num_low_confidence"],
                    })

    csv_path = output / "repetitions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys())); writer.writeheader(); writer.writerows(rows)

    summaries = []
    groups = sorted({(r["fixture"], r["beam"], r["ranking"]) for r in rows})
    for fixture, beam, ranking in groups:
        selected = [r for r in rows if (r["fixture"], r["beam"], r["ranking"]) == (fixture, beam, ranking)]
        decoder = robust_summary([float(r["decoder_us_per_shot"]) for r in selected])
        wall = robust_summary([float(r["wall_us_per_shot"]) for r in selected])
        summaries.append({
            "fixture": fixture, "beam": beam, "ranking": ranking,
            "repetitions": len(selected),
            "decoder_us_median": decoder["median"], "decoder_us_p95": decoder["p95"],
            "decoder_us_min": decoder["min"], "decoder_us_max": decoder["max"], "decoder_us_mad": decoder["mad"],
            "wall_us_median": wall["median"], "wall_us_p95": wall["p95"],
            "wall_us_min": wall["min"], "wall_us_max": wall["max"], "wall_us_mad": wall["mad"],
        })
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0].keys())); writer.writeheader(); writer.writerows(summaries)

    manifest = {
        "schema_version": 1, "phase": "P04", "mode": args.mode,
        "benchmark_valid": benchmark_valid, "machine_label": args.machine_label,
        "upstream_sha": actual_sha, "event_block_repeats": args.event_block_repeats,
        "shots_per_configuration": 4 * args.event_block_repeats,
        "warmups": warmups, "repetitions": repetitions,
        "beams": list(beams), "rankings": list(rankings),
        "with_perf_requested": bool(args.with_perf),
        "fixture_sha256": {name: {"dem": sha256(data[0]), "events": sha256(data[1])}
                           for name, data in fixtures.items()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
