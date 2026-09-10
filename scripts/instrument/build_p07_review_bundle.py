#!/usr/bin/env python3
"""Build the self-contained reviewer ZIP for P07.

The bundle contains reviewer docs, exact instrumentation scripts, selected real
BB inputs, all current P07B results, the full patch, and a clean patched source
tree. It deliberately excludes .git and Bazel output symlinks/directories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

UPSTREAM_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"

SCRIPT_FILES = [
    "audit_p07_bb_real_inputs.py",
    "apply_p06_modern_multiobs.py",
    "apply_p06_expected_upstream_contract.py",
    "apply_p06b_modern_multiobs_edge_tests.py",
    "apply_p07_bb_constructor_probe.py",
    "run_p07_bb_constructor_probes.py",
    "apply_p07b_bb_shot_runner.py",
    "run_p07b_bb_shot_smoke.py",
    "build_p07_review_bundle.py",
]

DOC_FILES = [
    "research/P05_EXPLICADO_PARA_NO_TENER_QUE_ACORDARME.md",
    "research/P06_EXPLICADO_PARA_NO_TENER_QUE_ACORDARME.md",
    "research/P07_EXPLICADO_PARA_NO_TENER_QUE_ACORDARME.md",
    "research/phases/P06_MODERN_MULTIOBSERVABLE_PORT_DESIGN.md",
    "research/phases/P07_BB_REAL_DATA_VALIDATION.md",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ignore_source(directory: str, names: list[str]) -> set[str]:
    ignored = {".git"}
    ignored.update(n for n in names if n.startswith("bazel-"))
    return ignored


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--bundle-dir", required=True)
    ap.add_argument("--zip-out", required=True)
    args = ap.parse_args()

    repo = Path(args.repo_root).resolve()
    upstream = Path(args.upstream_dir).resolve()
    results = Path(args.results_dir).resolve()
    bundle = Path(args.bundle_dir).resolve()
    zip_out = Path(args.zip_out).resolve()

    if not (results / "input-manifest.json").exists():
        raise RuntimeError("input-manifest.json is required before building review bundle")
    if not (results / "full-review.patch").exists():
        raise RuntimeError("full-review.patch is required before building review bundle")

    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    (bundle / "scripts").mkdir()
    (bundle / "docs").mkdir()
    (bundle / "results").mkdir()
    (bundle / "inputs").mkdir()

    shutil.copy2(repo / "research/P07_REVIEW_PACKAGE_README.md", bundle / "README_FIRST.md")
    shutil.copy2(repo / "research/P07_REPRODUCE_REVIEW.sh", bundle / "REPRODUCE.sh")

    for name in SCRIPT_FILES:
        src = repo / "scripts/instrument" / name
        if not src.exists():
            raise RuntimeError(f"Missing required review script: {src}")
        shutil.copy2(src, bundle / "scripts" / name)

    for rel in DOC_FILES:
        src = repo / rel
        if src.exists():
            shutil.copy2(src, bundle / "docs" / src.name)

    for src in sorted(results.iterdir()):
        if src.name in {"review_bundle", zip_out.name, zip_out.name + ".sha256"}:
            continue
        dst = bundle / "results" / src.name
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copy2(src, dst)

    manifest = json.loads((results / "input-manifest.json").read_text(encoding="utf-8"))
    for item in manifest["inputs"]:
        src = upstream / item["relative_path"]
        tag = f"bb_{item['n']}_{item['k']}_{item['d']}_{item['basis']}.stim"
        shutil.copy2(src, bundle / "inputs" / tag)
    shutil.copy2(results / "input-manifest.json", bundle / "inputs" / "ORIGINAL_PATHS_AND_HASHES.json")

    (bundle / "UPSTREAM_SHA.txt").write_text(UPSTREAM_SHA + "\n", encoding="utf-8")
    (bundle / "CHECKPOINTS.txt").write_text(
        "P06b successful modern multiobservable checkpoint:\n"
        "  run=34457465386\n"
        "  tests=12/12\n\n"
        "P07a successful real-BB construction checkpoint:\n"
        "  run=34473973542\n"
        "  harness_commit=aab3dea73759a738e15f970722ca12c435fd3831\n"
        "  circuits=8/8\n"
        "  artifact=10150753712\n"
        "  artifact_sha256=8074b99bf492c156b07f5c7d56c352d5a8e90d906871d6737311b0a4f100ecfe\n\n"
        "P07b:\n"
        "  See results/p07b-shot-results.json from this bundle/run.\n"
        "  benchmark_valid=false\n"
        "  timing_metrics_interpretable=false\n"
        "  scientific_ler_valid=false\n",
        encoding="utf-8",
    )

    shutil.copytree(upstream, bundle / "patched_source", ignore=ignore_source)

    checksum_lines = []
    for path in sorted(p for p in bundle.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        checksum_lines.append(f"{sha256(path)}  {path.relative_to(bundle).as_posix()}")
    (bundle / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    zip_out.parent.mkdir(parents=True, exist_ok=True)
    if zip_out.exists():
        zip_out.unlink()
    root_name = "tesseract_multiobservable_review_bundle"
    with zipfile.ZipFile(zip_out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
            z.write(path, Path(root_name) / path.relative_to(bundle))

    digest = sha256(zip_out)
    Path(str(zip_out) + ".sha256").write_text(f"{digest}  {zip_out.name}\n", encoding="utf-8")
    print(json.dumps({
        "status": "bundle_built",
        "zip": str(zip_out),
        "zip_bytes": zip_out.stat().st_size,
        "zip_sha256": digest,
        "upstream_sha": UPSTREAM_SHA,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
