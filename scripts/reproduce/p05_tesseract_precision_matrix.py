#!/usr/bin/env python3
"""Run reproducible Tesseract search-quality experiments.

This runner is designed to separate three different questions that are easy to
mix together:

1. Did the decoder return a confident answer?
2. Was the confident answer logically correct?
3. How expensive was the search configuration?

It deliberately keeps low-confidence shots separate from logical errors and
also reports the conservative failure rate (errors + low confidence) / shots.

The profile named "upstream_longbeam" matches the current upstream long-beam
registry at commit e7c762eef24161e304ba6fccb856a05b41f88c39:
beam=20, beam climbing, no-revisit, pqlimit=1,000,000, 21 Index orders,
seed=2,384,753.

Important: beam climbing does not mean "use one beam of this size". In the
pinned implementation it performs max(beam + 1, number_of_orders) decoding
trials per shot, cycling beam values and detector orders. Therefore combining
beam=2000 with beam climbing would imply at least 2001 decoder trials per shot.
This script records that count explicitly and refuses extremely large climbing
profiles unless --allow-expensive-climbing is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

UPSTREAM_SHA = "e7c762eef24161e304ba6fccb856a05b41f88c39"

PROFILES: dict[str, dict[str, Any]] = {
    # A moderate reference configuration using the parameter family reported
    # for BB experiments. It is useful as a lower-cost point, not as a claim of
    # exact reproduction of a specific figure unless all other details match.
    "reference_short": {
        "beam": 15,
        "beam_climbing": True,
        "num_det_orders": 16,
        "det_order_seed": 518278944,
        "no_revisit_dets": True,
        "pqlimit": 200_000,
    },
    # Fran's current high-convergence direction: one very wide search, with no
    # climbing. This remains expensive internally but is only one decoder trial
    # per shot.
    "wide_beam": {
        "beam": 2000,
        "beam_climbing": False,
        "num_det_orders": 1,
        "det_order_seed": 518278944,
        "no_revisit_dets": False,
        "pqlimit": 1_000_000,
    },
    # Same wide search with the no-revisit heuristic isolated as one variable.
    "wide_beam_no_revisit": {
        "beam": 2000,
        "beam_climbing": False,
        "num_det_orders": 1,
        "det_order_seed": 518278944,
        "no_revisit_dets": True,
        "pqlimit": 1_000_000,
    },
    # Twenty-one full beam-20 searches, one per generated Index order, without
    # beam climbing. This isolates detector-order diversity.
    "orders_only": {
        "beam": 20,
        "beam_climbing": False,
        "num_det_orders": 21,
        "det_order_seed": 2_384_753,
        "no_revisit_dets": True,
        "pqlimit": 1_000_000,
    },
    # Same beam/order schedule as the upstream long-beam preset, but with
    # revisiting allowed. This isolates the no-revisit heuristic.
    "climbing_with_revisit": {
        "beam": 20,
        "beam_climbing": True,
        "num_det_orders": 21,
        "det_order_seed": 2_384_753,
        "no_revisit_dets": False,
        "pqlimit": 1_000_000,
    },
    # Current upstream long-beam registry values in
    # src/py/multi_pass_sinter_decoders.py.
    "upstream_longbeam": {
        "beam": 20,
        "beam_climbing": True,
        "num_det_orders": 21,
        "det_order_seed": 2_384_753,
        "no_revisit_dets": True,
        "pqlimit": 1_000_000,
    },
}

FILENAME_RE = re.compile(
    r"(?:^|,)r=(?P<rounds>\d+),d=(?P<distance>\d+),"
    r"p=(?P<physical_rate>[0-9.eE+-]+).*?,q=(?P<q>\d+),"
)


def sha256_file(path: Path) -> str:
    """Return a stable content hash for provenance."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def circuit_metadata(path: Path) -> dict[str, Any]:
    """Extract public filename metadata without inferring missing values."""
    match = FILENAME_RE.search(path.name)
    if not match:
        return {
            "rounds": None,
            "distance": None,
            "physical_rate": None,
            "q": None,
        }
    return {
        "rounds": int(match.group("rounds")),
        "distance": int(match.group("distance")),
        "physical_rate": float(match.group("physical_rate")),
        "q": int(match.group("q")),
    }


def estimated_trials_per_shot(profile: dict[str, Any]) -> int:
    """Mirror the pinned Tesseract beam-climbing trial-count rule."""
    if profile["beam_climbing"]:
        return max(profile["beam"] + 1, profile["num_det_orders"])
    return profile["num_det_orders"]


def conservative_round_rate(failure_rate: float | None, rounds: int | None) -> float | None:
    """Convert shot failure rate to per-round rate using the paper's formula."""
    if failure_rate is None or rounds is None or rounds <= 0:
        return None
    if not (0.0 <= failure_rate < 0.5):
        return None
    return 0.5 * (1.0 - (1.0 - 2.0 * failure_rate) ** (1.0 / rounds))


def run_one(
    *,
    tesseract_bin: Path,
    circuit: Path,
    output_dir: Path,
    profile_name: str,
    profile: dict[str, Any],
    shots: int,
    sample_seed: int,
    threads: int,
    max_errors: int | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run one profile/circuit pair and preserve raw and derived evidence."""
    run_dir = output_dir / circuit.stem / profile_name
    run_dir.mkdir(parents=True, exist_ok=True)
    stats_path = run_dir / "stats.json"

    cmd = [
        str(tesseract_bin),
        "--circuit",
        str(circuit),
        "--sample-num-shots",
        str(shots),
        "--sample-seed",
        str(sample_seed),
        "--threads",
        str(threads),
        "--beam",
        str(profile["beam"]),
        "--pqlimit",
        str(profile["pqlimit"]),
        "--num-det-orders",
        str(profile["num_det_orders"]),
        "--det-order-index",
        "--det-order-seed",
        str(profile["det_order_seed"]),
        "--stats-out",
        str(stats_path),
    ]
    if profile["beam_climbing"]:
        cmd.append("--beam-climbing")
    if profile["no_revisit_dets"]:
        cmd.append("--no-revisit-dets")
    if max_errors is not None:
        cmd.extend(["--max-errors", str(max_errors)])

    command_record = {
        "profile": profile_name,
        "profile_parameters": profile,
        "estimated_decoder_trials_per_shot": estimated_trials_per_shot(profile),
        "command": cmd,
        "command_shell": shlex.join(cmd),
        "circuit": str(circuit),
        "circuit_sha256": sha256_file(circuit),
        "sample_seed": sample_seed,
        "requested_shots": shots,
        "threads": threads,
        "timeout_seconds": timeout_seconds,
    }
    (run_dir / "command.json").write_text(
        json.dumps(command_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
        timed_out = False
        returncode: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""

    wall_seconds = time.perf_counter() - started
    (run_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(stderr, encoding="utf-8")

    stats: dict[str, Any] | None = None
    if stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))

    expected_stats = {
        "det_beam": profile["beam"],
        "beam_climbing": profile["beam_climbing"],
        "no_revisit_dets": profile["no_revisit_dets"],
        "pqlimit": profile["pqlimit"],
        "num_det_orders": profile["num_det_orders"],
        "det_order_seed": profile["det_order_seed"],
        "num_threads": threads,
    }
    stats_match = bool(stats)
    if stats is not None:
        for key, expected in expected_stats.items():
            stats_match &= stats.get(key) == expected

    num_shots = stats.get("num_shots") if stats else None
    num_errors = stats.get("num_errors") if stats else None
    num_low_confidence = stats.get("num_low_confidence") if stats else None

    confident_shots: int | None = None
    conservative_failure_rate: float | None = None
    confident_error_rate: float | None = None
    confidence_rate: float | None = None
    decoder_seconds_per_shot: float | None = None

    if isinstance(num_shots, int) and num_shots > 0:
        if isinstance(num_low_confidence, int):
            confident_shots = num_shots - num_low_confidence
            confidence_rate = confident_shots / num_shots
        if isinstance(num_errors, int) and isinstance(num_low_confidence, int):
            conservative_failure_rate = (num_errors + num_low_confidence) / num_shots
            if confident_shots and confident_shots > 0:
                confident_error_rate = num_errors / confident_shots
        total_decoder_time = stats.get("total_time_seconds") if stats else None
        if isinstance(total_decoder_time, (int, float)):
            decoder_seconds_per_shot = float(total_decoder_time) / num_shots

    metadata = circuit_metadata(circuit)
    result = {
        "profile": profile_name,
        "profile_parameters": profile,
        "estimated_decoder_trials_per_shot": estimated_trials_per_shot(profile),
        "circuit": str(circuit),
        "circuit_sha256": sha256_file(circuit),
        "circuit_metadata": metadata,
        "returncode": returncode,
        "timed_out": timed_out,
        "wall_seconds": wall_seconds,
        "stats_match_expected_configuration": stats_match,
        "stats": stats,
        "derived": {
            "confidence_rate": confidence_rate,
            "confident_error_rate": confident_error_rate,
            "conservative_failure_rate": conservative_failure_rate,
            "conservative_round_failure_rate": conservative_round_rate(
                conservative_failure_rate, metadata["rounds"]
            ),
            "decoder_seconds_per_shot": decoder_seconds_per_shot,
        },
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tesseract-bin", type=Path, required=True)
    parser.add_argument("--circuit", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--profiles",
        default="upstream_longbeam",
        help="Comma-separated profile names. Available: " + ",".join(PROFILES),
    )
    parser.add_argument("--shots", type=int, default=100)
    parser.add_argument("--sample-seed", type=int, default=20261004)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--max-errors", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument(
        "--max-climbing-trials",
        type=int,
        default=128,
        help="Safety guard for beam-climbing trial count.",
    )
    parser.add_argument(
        "--allow-expensive-climbing",
        action="store_true",
        help="Allow beam-climbing profiles above --max-climbing-trials.",
    )
    args = parser.parse_args()

    if args.shots <= 0:
        raise SystemExit("--shots must be positive")
    if args.threads <= 0:
        raise SystemExit("--threads must be positive")

    profile_names = [p.strip() for p in args.profiles.split(",") if p.strip()]
    unknown = [p for p in profile_names if p not in PROFILES]
    if unknown:
        raise SystemExit(f"Unknown profiles: {unknown}")

    for name in profile_names:
        profile = PROFILES[name]
        trials = estimated_trials_per_shot(profile)
        if (
            profile["beam_climbing"]
            and trials > args.max_climbing_trials
            and not args.allow_expensive_climbing
        ):
            raise SystemExit(
                f"Refusing {name}: beam climbing would run {trials} decoder trials "
                "per shot. Use --allow-expensive-climbing only if intentional."
            )

    tesseract_bin = args.tesseract_bin.resolve()
    circuits = [p.resolve() for p in args.circuit]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not tesseract_bin.exists():
        raise SystemExit(f"Missing Tesseract executable: {tesseract_bin}")
    for circuit in circuits:
        if not circuit.exists():
            raise SystemExit(f"Missing circuit: {circuit}")

    all_results: list[dict[str, Any]] = []
    for circuit in circuits:
        for profile_name in profile_names:
            all_results.append(
                run_one(
                    tesseract_bin=tesseract_bin,
                    circuit=circuit,
                    output_dir=output_dir,
                    profile_name=profile_name,
                    profile=PROFILES[profile_name],
                    shots=args.shots,
                    sample_seed=args.sample_seed,
                    threads=args.threads,
                    max_errors=args.max_errors,
                    timeout_seconds=args.timeout_seconds,
                )
            )

    overall_ok = all(
        r["returncode"] == 0
        and not r["timed_out"]
        and r["stats_match_expected_configuration"]
        for r in all_results
    )
    summary = {
        "schema_version": 1,
        "upstream_sha": UPSTREAM_SHA,
        "benchmark_valid": False,
        "purpose": (
            "Search-quality/correctness experiment. GitHub-hosted timings are smoke-only; "
            "controlled Brigit timings must be analyzed separately."
        ),
        "profiles": profile_names,
        "requested_shots": args.shots,
        "sample_seed": args.sample_seed,
        "threads": args.threads,
        "overall_ok": overall_ok,
        "results": all_results,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Compact CSV for quick comparison on Brigit.
    lines = [
        "circuit,profile,q,d,r,p,trials_per_shot,num_shots,num_errors,"
        "num_low_confidence,confidence_rate,confident_error_rate,"
        "conservative_failure_rate,conservative_round_failure_rate,"
        "decoder_seconds_per_shot,wall_seconds"
    ]
    for r in all_results:
        stats = r["stats"] or {}
        meta = r["circuit_metadata"]
        d = r["derived"]
        fields = [
            Path(r["circuit"]).name,
            r["profile"],
            meta["q"],
            meta["distance"],
            meta["rounds"],
            meta["physical_rate"],
            r["estimated_decoder_trials_per_shot"],
            stats.get("num_shots"),
            stats.get("num_errors"),
            stats.get("num_low_confidence"),
            d["confidence_rate"],
            d["confident_error_rate"],
            d["conservative_failure_rate"],
            d["conservative_round_failure_rate"],
            d["decoder_seconds_per_shot"],
            r["wall_seconds"],
        ]
        lines.append(",".join("" if x is None else str(x) for x in fields))
    (output_dir / "summary.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
