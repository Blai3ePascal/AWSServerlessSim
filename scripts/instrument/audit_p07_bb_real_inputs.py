#!/usr/bin/env python3
"""Audit the real bivariate-bicycle Stim inputs used by P07.

This script deliberately discovers files from the frozen upstream checkout instead
of hard-coding the very long filenames. It fails closed: P07 only continues when
all four target [[n,k,d]] codes exist at p=0.001 in both X and Z memory bases,
with r=d and the expected observable ids present in the circuit text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

TARGETS = (
    (72, 12, 6),
    (90, 8, 10),
    (108, 8, 10),
    (144, 12, 12),
)
EXPECTED_BASES = ("X", "Z")
TARGET_P = Decimal("0.001")

NKD_RE = re.compile(r"(?:^|,)nkd=\[\[(\d+),(\d+),(\d+)\]\](?:,|$)")
P_RE = re.compile(r"(?:^|,)p=([^,]+)(?:,|$)")
R_RE = re.compile(r"(?:^|,)r=(\d+)(?:,|$)")
D_RE = re.compile(r"(?:^|,)d=(\d+)(?:,|$)")
BASIS_RE = re.compile(r"(?:^|,)c=bivariate_bicycle_([XZ])(?:,|$)")
OBS_RE = re.compile(r"\bOBSERVABLE_INCLUDE\((\d+)\)")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def one(regex: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    m = regex.search(text)
    if m is None:
        raise RuntimeError(f"Could not parse {label} from filename: {text}")
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--paths-out", required=True)
    args = ap.parse_args()

    root = Path(args.upstream_dir).resolve()
    data_dir = root / "testdata" / "bivariatebicyclecodes"
    if not data_dir.is_dir():
        raise RuntimeError(f"Missing BB testdata directory: {data_dir}")

    selected: dict[tuple[tuple[int, int, int], str], dict[str, object]] = {}
    all_p001 = 0

    for path in sorted(data_dir.glob("*.stim")):
        name = path.name
        pm = P_RE.search(name)
        if pm is None:
            continue
        try:
            p = Decimal(pm.group(1))
        except InvalidOperation:
            raise RuntimeError(f"Invalid p in filename: {name}")
        if p != TARGET_P:
            continue
        all_p001 += 1

        nkdm = NKD_RE.search(name)
        basism = BASIS_RE.search(name)
        if nkdm is None or basism is None:
            continue
        nkd = tuple(map(int, nkdm.groups()))
        if nkd not in TARGETS:
            continue
        basis = basism.group(1)
        r = int(one(R_RE, name, "r").group(1))
        filename_d = int(one(D_RE, name, "d").group(1))
        n, k, code_d = nkd
        if filename_d != code_d:
            raise RuntimeError(f"Filename d={filename_d} disagrees with nkd={nkd}: {name}")
        if r != code_d:
            raise RuntimeError(f"P07 expects r=d for {nkd}, got r={r}: {name}")

        text = path.read_text(encoding="utf-8")
        observable_ids = sorted({int(x) for x in OBS_RE.findall(text)})
        expected_ids = list(range(k))
        if observable_ids != expected_ids:
            raise RuntimeError(
                f"Observable ids for {nkd}/{basis} are {observable_ids}; expected {expected_ids}"
            )

        key = (nkd, basis)
        if key in selected:
            raise RuntimeError(
                f"Ambiguous P07 input: more than one p=0.001 file for {nkd}/{basis}: "
                f"{selected[key]['path']} and {path}"
            )
        selected[key] = {
            "n": n,
            "k": k,
            "d": code_d,
            "rounds": r,
            "p": "0.001",
            "basis": basis,
            "relative_path": str(path.relative_to(root)),
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "observable_ids": observable_ids,
        }

    expected_keys = {(nkd, basis) for nkd in TARGETS for basis in EXPECTED_BASES}
    missing = sorted(expected_keys - set(selected))
    extra = sorted(set(selected) - expected_keys)
    if missing or extra:
        raise RuntimeError(f"P07 BB input contract failed: missing={missing}, extra={extra}")

    ordered = [selected[(nkd, basis)] for nkd in TARGETS for basis in EXPECTED_BASES]
    report = {
        "phase": "P07a",
        "kind": "real-bb-input-audit",
        "upstream_dir": str(root),
        "target_p": "0.001",
        "selection_rule": "exact nkd target, p=0.001, r=d, one X and one Z circuit per code",
        "target_codes": [list(x) for x in TARGETS],
        "expected_observable_counts": [12, 8, 8, 12],
        "all_p001_stim_files_seen": all_p001,
        "selected_count": len(ordered),
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
        "inputs": ordered,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    paths_out = Path(args.paths_out)
    paths_out.parent.mkdir(parents=True, exist_ok=True)
    paths_out.write_text("\n".join(item["path"] for item in ordered) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
