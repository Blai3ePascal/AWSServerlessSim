#!/usr/bin/env python3
"""Find the real public BB circuit files used for P08.

Nothing is downloaded by this script and no filename is invented. It scans the
pinned Tesseract checkout and selects X/Z circuits by metadata encoded in the
upstream filenames. It fails loudly if the expected 12/8/8/12 families are not
there.
"""

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

TARGETS = [
    {"name": "BB72", "n": 72, "k": 12, "d": 6},
    {"name": "BB90", "n": 90, "k": 8, "d": 10},
    {"name": "BB108", "n": 108, "k": 8, "d": 10},
    {"name": "BB144", "n": 144, "k": 12, "d": 12},
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def observable_include_count(path: Path) -> int:
    # Circuit num_observables is max OBSERVABLE_INCLUDE index + 1.  This is a
    # preflight check only; the patched CLI later verifies the DEM's own count.
    max_index = -1
    pattern = re.compile(r"\bOBSERVABLE_INCLUDE\((\d+)\)")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            for match in pattern.finditer(line):
                max_index = max(max_index, int(match.group(1)))
    return max_index + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--json", required=True)
    args = ap.parse_args()

    root = Path(args.upstream_dir).resolve()
    data_dir = root / "testdata" / "bivariatebicyclecodes"
    if not data_dir.is_dir():
        raise SystemExit(f"Missing upstream BB directory: {data_dir}")

    files = sorted(data_dir.glob("*.stim"))
    selected = []
    for target in TARGETS:
        nkd = f"nkd=[[{target['n']},{target['k']},{target['d']}]]"
        round_tag = f"r={target['d']},d={target['d']},"
        for basis in ("X", "Z"):
            tags = [
                "p=0.001,",
                f"c=bivariate_bicycle_{basis},",
                nkd,
                round_tag,
            ]
            matches = [p for p in files if all(tag in p.name for tag in tags)]
            if len(matches) != 1:
                broader = [p.name for p in files if "p=0.001," in p.name and nkd in p.name and f"c=bivariate_bicycle_{basis}," in p.name]
                raise SystemExit(
                    f"Expected exactly one {target['name']} {basis} p=0.001 r=d circuit, found {len(matches)}. "
                    f"Broader candidates: {broader}"
                )
            path = matches[0]
            preflight_obs = observable_include_count(path)
            if preflight_obs != target["k"]:
                raise SystemExit(
                    f"{path.name}: filename says k={target['k']} but OBSERVABLE_INCLUDE implies {preflight_obs} observables"
                )
            selected.append({
                **target,
                "basis": basis,
                "p": 0.001,
                "rounds": target["d"],
                "path": str(path.relative_to(root)),
                "sha256": sha256(path),
                "preflight_observables": preflight_obs,
            })

    if [x["k"] for x in selected[::2]] != [12, 8, 8, 12]:
        raise SystemExit("Internal target contract is not 12/8/8/12")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "n", "k", "d", "basis", "p", "rounds", "preflight_observables", "sha256", "path"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(selected)

    meta = {
        "source": "quantumlib/tesseract-decoder pinned checkout",
        "selection": "p=0.001, X and Z, r=d, exact [[n,k,d]]",
        "expected_k_by_family": [12, 8, 8, 12],
        "selected_count": len(selected),
        "circuits": selected,
    }
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("P08 selected real public circuits:")
    for x in selected:
        print(f"  {x['name']} {x['basis']}: [[{x['n']},{x['k']},{x['d']}]], p={x['p']}, obs={x['preflight_observables']}")
    print(f"PASS: selected {len(selected)} real p=0.001 BB circuits; family k pattern is 12/8/8/12")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
