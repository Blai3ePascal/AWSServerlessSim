#!/usr/bin/env python3
"""Freeze exact P04 detection-event workloads with the Stim revision pinned upstream.

The output events and observable flips become primary experimental inputs. A
seed alone is not treated as sufficient provenance because Stim documents that
seeded results can differ across versions and machine architectures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_TESSERACT_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"
EXPECTED_STIM_SHA = "bd60b73525fd5a9b30839020eb7554ad369e4337"
OBS_RE = re.compile(r"^\s*OBSERVABLE_INCLUDE\((\d+)\)", re.MULTILINE)


def sha256_file(path: Path) -> str:
    """Hash exact workload bytes so later benchmarks can reject drift."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def observable_width(text: str) -> int:
    """Return circuit observable width from zero-indexed OBSERVABLE_INCLUDE ids."""
    indices = [int(m.group(1)) for m in OBS_RE.finditer(text)]
    return max(indices) + 1 if indices else 0


def count_records(path: Path) -> int:
    """Count dense 01 records; every frozen shot must produce exactly one line."""
    with path.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.rstrip("\n\r") or line in {"\n", "\r\n"})


def run_checked(command: list[str], cwd: Path, log_path: Path) -> None:
    """Run Stim through Bazel and preserve stdout/stderr even on failure."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"workload generation failed with {completed.returncode}; see {log_path}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--shots", type=int)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    upstream = args.upstream_dir.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    actual_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=upstream, text=True
    ).strip()
    if actual_sha != EXPECTED_TESSERACT_SHA:
        raise SystemExit(
            f"P04 workload freeze requires Tesseract {EXPECTED_TESSERACT_SHA}, got {actual_sha}"
        )

    module_text = (upstream / "MODULE.bazel").read_text(encoding="utf-8")
    if EXPECTED_STIM_SHA not in module_text:
        raise SystemExit(
            f"expected Stim pin {EXPECTED_STIM_SHA} is not present in upstream MODULE.bazel"
        )

    shots = args.shots if args.shots is not None else int(config["freeze"]["shots"])
    seed = args.seed if args.seed is not None else int(config["freeze"]["seed"])
    if shots < 1:
        raise SystemExit("--shots must be positive")

    frozen: dict[str, Any] = {
        "schema_version": 1,
        "phase": "P04",
        "record_type": "frozen_trellis_workload_manifest",
        "tesseract_sha": actual_sha,
        "stim_sha": EXPECTED_STIM_SHA,
        "shots": shots,
        "seed": seed,
        "format": "01",
        "cases": [],
    }

    for case in config["cases"]:
        circuit = upstream / case["path"]
        if not circuit.exists():
            raise RuntimeError(f"missing circuit: {circuit}")
        text = circuit.read_text(encoding="utf-8")
        width = observable_width(text)
        if width != 1:
            raise RuntimeError(
                f"{case['id']} has {width} observables; P04 does not rewrite observable semantics"
            )

        case_dir = output / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        events = case_dir / "events.01"
        observables = case_dir / "observables.01"
        log = case_dir / "stim-detect.log"

        command = [
            "bazel",
            "run",
            "@stim//:stim",
            "--",
            "detect",
            "--shots",
            str(shots),
            "--seed",
            str(seed),
            "--in",
            str(circuit),
            "--out",
            str(events),
            "--out_format",
            "01",
            "--obs_out",
            str(observables),
            "--obs_out_format",
            "01",
        ]
        run_checked(command, upstream, log)

        event_records = count_records(events)
        observable_records = count_records(observables)
        if event_records != shots or observable_records != shots:
            raise RuntimeError(
                f"{case['id']}: expected {shots} records, got events={event_records}, "
                f"observables={observable_records}"
            )

        frozen["cases"].append(
            {
                "id": case["id"],
                "role": case["role"],
                "family": case["family"],
                "distance": case["distance"],
                "qubits": case["qubits"],
                "p": case["p"],
                "basis": case["basis"],
                "circuit_path": case["path"],
                "circuit_sha256": sha256_file(circuit),
                "events_path": f"{case['id']}/events.01",
                "events_sha256": sha256_file(events),
                "observables_path": f"{case['id']}/observables.01",
                "observables_sha256": sha256_file(observables),
                "records": shots,
                "generation_command": command,
            }
        )

    manifest_path = output / "frozen-workloads.json"
    manifest_path.write_text(
        json.dumps(frozen, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
