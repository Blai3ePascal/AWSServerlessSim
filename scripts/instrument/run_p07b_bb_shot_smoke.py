#!/usr/bin/env python3
"""Run one deterministic real-BB shot per audited P07 input.

A logical mismatch or low-confidence result is DATA, not an infrastructure
failure. This driver fails only when the runner cannot complete or emits an
invalid record. P07b is a smoke/integration phase, not a LER experiment.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BASE_SEED = 7001001


def parse_kv(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in line.strip().split():
        if "=" in token:
            k, v = token.split("=", 1)
            out[k] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--runner", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--logs-dir", required=True)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    upstream = Path(args.upstream_dir).resolve()
    runner = Path(args.runner).resolve()
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    technical_failures = 0
    logical_mismatches = 0
    low_confidence = 0
    nontrivial_syndromes = 0

    for index, item in enumerate(manifest["inputs"]):
        n, k, d = item["n"], item["k"], item["d"]
        basis = item["basis"]
        tag = f"bb_{n}_{k}_{d}_{basis}"
        seed = BASE_SEED + index
        circuit = upstream / item["relative_path"]
        log_path = logs_dir / f"{tag}.log"

        timed_out = False
        try:
            cp = subprocess.run(
                [str(runner), str(circuit), str(seed)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=args.timeout_seconds,
                check=False,
            )
            output = cp.stdout
            returncode = cp.returncode
        except subprocess.TimeoutExpired as ex:
            timed_out = True
            output = (ex.stdout or "") + "\nTIMEOUT\n"
            returncode = 124

        log_path.write_text(output, encoding="utf-8")
        decoded_line = next((ln for ln in output.splitlines() if ln.startswith("status=decoded ")), "")
        fields = parse_kv(decoded_line)

        expected_obs = int(item["k"])
        valid_record = (
            returncode == 0
            and not timed_out
            and fields.get("status") == "decoded"
            and fields.get("seed") == str(seed)
            and fields.get("observables") == str(expected_obs)
            and "truth_mask" in fields
            and "predicted_mask" in fields
            and fields.get("low_confidence") in {"0", "1"}
        )

        truth = int(fields["truth_mask"]) if valid_record else None
        predicted = int(fields["predicted_mask"]) if valid_record else None
        is_low = int(fields["low_confidence"]) if valid_record else None
        hits_count = int(fields.get("hits_count", "0")) if valid_record else None
        logical_match = (truth == predicted) if valid_record else None

        if not valid_record:
            technical_failures += 1
        else:
            if is_low:
                low_confidence += 1
            if not logical_match:
                logical_mismatches += 1
            if hits_count and hits_count > 0:
                nontrivial_syndromes += 1

        row = {
            "tag": tag,
            "nkd": [n, k, d],
            "basis": basis,
            "relative_path": item["relative_path"],
            "sha256": item["sha256"],
            "seed": seed,
            "expected_observables": expected_obs,
            "returncode": returncode,
            "timed_out": timed_out,
            "valid_record": valid_record,
            "truth_mask": truth,
            "predicted_mask": predicted,
            "logical_match": logical_match,
            "low_confidence": is_low,
            "hits_count": hits_count,
            "states_expanded": int(fields["states_expanded"]) if valid_record and "states_expanded" in fields else None,
            "states_merged": int(fields["states_merged"]) if valid_record and "states_merged" in fields else None,
            "max_beam": int(fields["max_beam"]) if valid_record and "max_beam" in fields else None,
            "frontier_width": int(fields["frontier_width"]) if valid_record and "frontier_width" in fields else None,
            "log": str(log_path),
        }
        rows.append(row)
        print(json.dumps(row, sort_keys=True))

    result = {
        "phase": "P07b",
        "kind": "deterministic-real-bb-shot-smoke",
        "input_count": len(rows),
        "technical_failures": technical_failures,
        "logical_mismatches": logical_mismatches,
        "low_confidence": low_confidence,
        "nontrivial_syndromes": nontrivial_syndromes,
        "base_seed": BASE_SEED,
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
        "scientific_ler_valid": False,
        "logical_mismatch_is_ci_failure": False,
        "low_confidence_is_ci_failure": False,
        "records": rows,
    }
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if technical_failures:
        print(f"P07b technical contract FAILED: {technical_failures} invalid/failed runner invocations.")
        return 1
    print(
        "P07b technical contract passed: "
        f"{len(rows)}/{len(rows)} deterministic real-BB shots produced valid records; "
        f"logical_mismatches={logical_mismatches}; low_confidence={low_confidence}; "
        f"nontrivial_syndromes={nontrivial_syndromes}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
