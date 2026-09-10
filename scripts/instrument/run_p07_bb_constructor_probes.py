#!/usr/bin/env python3
"""Run the P07 construction probe over the audited real BB inputs.

No timing is recorded: GitHub-hosted runner timing is explicitly not scientific
evidence for this project.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

OBS_RE = re.compile(r"(?:^|\s)observables=(\d+)(?:\s|$)")
STATUS_RE = re.compile(r"(?:^|\s)status=constructed(?:\s|$)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--logs-dir", required=True)
    ap.add_argument("--timeout-seconds", type=int, default=180)
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    upstream = Path(args.upstream_dir).resolve()
    probe = Path(args.probe).resolve()
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if manifest.get("selected_count") != 8:
        raise RuntimeError(f"Expected 8 audited inputs, got {manifest.get('selected_count')}")
    if not probe.is_file():
        raise RuntimeError(f"Probe binary does not exist: {probe}")

    results = []
    failures = []
    for item in manifest["inputs"]:
        n = int(item["n"])
        k = int(item["k"])
        d = int(item["d"])
        basis = str(item["basis"])
        circuit = upstream / item["relative_path"]
        tag = f"bb_{n}_{k}_{d}_{basis}"
        log_path = logs_dir / f"{tag}.log"

        try:
            proc = subprocess.run(
                [str(probe), str(circuit)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=args.timeout_seconds,
                check=False,
            )
            timed_out = False
            stdout = proc.stdout
            stderr = proc.stderr
            returncode = proc.returncode
        except subprocess.TimeoutExpired as ex:
            timed_out = True
            stdout = ex.stdout or ""
            stderr = ex.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            returncode = None

        combined = (
            f"tag={tag}\n"
            f"expected_observables={k}\n"
            f"circuit={item['relative_path']}\n"
            f"sha256={item['sha256']}\n"
            f"timed_out={str(timed_out).lower()}\n"
            f"returncode={returncode}\n"
            "--- stdout ---\n"
            f"{stdout}"
            "\n--- stderr ---\n"
            f"{stderr}"
        )
        log_path.write_text(combined, encoding="utf-8")

        obs_match = OBS_RE.search(stdout)
        observed_k = int(obs_match.group(1)) if obs_match else None
        status_ok = STATUS_RE.search(stdout) is not None
        ok = (
            not timed_out
            and returncode == 0
            and status_ok
            and observed_k == k
        )
        result = {
            "tag": tag,
            "nkd": [n, k, d],
            "basis": basis,
            "relative_path": item["relative_path"],
            "sha256": item["sha256"],
            "expected_observables": k,
            "observed_observables": observed_k,
            "status_constructed": status_ok,
            "returncode": returncode,
            "timed_out": timed_out,
            "ok": ok,
            "log": str(log_path),
        }
        results.append(result)
        if not ok:
            failures.append(tag)
        print(json.dumps(result, sort_keys=True))

    report = {
        "phase": "P07a",
        "kind": "real-bb-constructor-probe-results",
        "probe_count": len(results),
        "passed": sum(1 for x in results if x["ok"]),
        "failed": failures,
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
        "results": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if failures:
        raise RuntimeError(f"P07 constructor probes failed: {failures}")
    if len(results) != 8:
        raise RuntimeError(f"Expected 8 P07 constructor probes, ran {len(results)}")
    print("P07a constructor probe contract passed: 8/8 real BB circuits constructed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
