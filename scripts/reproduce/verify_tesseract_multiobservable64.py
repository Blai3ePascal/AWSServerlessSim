#!/usr/bin/env python3
"""Build and test the independent 0..64-observable Trellis extension from scratch.

Typical use:

    python3 scripts/reproduce/verify_tesseract_multiobservable64.py

The script creates an isolated checkout of the exact upstream commit, applies
our reproducible transformations, runs upstream-compatible regressions plus all
multi-observable correctness/mode tests, and writes the resulting patch and
reports under the chosen work directory.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

UPSTREAM_URL = "https://github.com/quantumlib/tesseract-decoder.git"
UPSTREAM_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"
MARKER = ".multiobs64-verifier-workdir"


def run(cmd, *, cwd=None):
    print("+", " ".join(str(x) for x in cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def require_tool(name: str):
    if shutil.which(name) is None:
        raise SystemExit(f"ERROR: required tool not found in PATH: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--work-dir",
        default=".work/tesseract-multiobservable64",
        help="isolated checkout/output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="reuse an existing verifier-owned work directory instead of recreating it",
    )
    args = parser.parse_args()

    harness = Path(__file__).resolve().parents[2]
    work = (harness / args.work_dir).resolve() if not Path(args.work_dir).is_absolute() else Path(args.work_dir).resolve()
    checkout = work / "tesseract-decoder"
    reports = work / "reports"

    for tool in ("git", "bazel"):
        require_tool(tool)

    if work.exists() and not args.keep_existing:
        marker = work / MARKER
        if not marker.exists():
            raise SystemExit(
                f"ERROR: refusing to delete non-verifier directory {work}. "
                f"Remove it yourself or choose another --work-dir."
            )
        shutil.rmtree(work)

    work.mkdir(parents=True, exist_ok=True)
    (work / MARKER).write_text("owned by verify_tesseract_multiobservable64.py\n")
    reports.mkdir(parents=True, exist_ok=True)

    if not checkout.exists():
        run(["git", "clone", "--filter=blob:none", "--no-checkout", UPSTREAM_URL, str(checkout)])
    run(["git", "fetch", "--depth=1", "origin", UPSTREAM_SHA], cwd=checkout)
    run(["git", "checkout", "--detach", UPSTREAM_SHA], cwd=checkout)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    if actual != UPSTREAM_SHA:
        raise SystemExit(f"ERROR: upstream SHA mismatch: expected {UPSTREAM_SHA}, got {actual}")

    python = sys.executable
    transforms = [
        ("scripts/instrument/apply_p06_modern_multiobs.py", "p06-patch-report.json"),
        ("scripts/instrument/apply_p06_expected_upstream_contract.py", "p06-upstream-contract-report.json"),
        ("scripts/instrument/apply_p06b_modern_multiobs_edge_tests.py", "p06b-edge-report.json"),
        ("scripts/instrument/apply_p07_complete_multiobs64_modes.py", "p07-complete-modes-report.json"),
    ]
    for script_rel, report_name in transforms:
        script = harness / script_rel
        if not script.exists():
            raise SystemExit(f"ERROR: missing harness script: {script}")
        run([
            python,
            str(script),
            "--upstream-dir",
            str(checkout),
            "--report",
            str(reports / report_name),
        ])

    run(["git", "diff", "--check"], cwd=checkout)
    patch = subprocess.check_output(["git", "diff", "--binary"], cwd=checkout)
    (reports / "tesseract-multiobservable64.patch").write_bytes(patch)
    (reports / "UPSTREAM_SHA.txt").write_text(UPSTREAM_SHA + "\n")

    run([
        "bazel",
        "test",
        "//src:tesseract_trellis_tests",
        "//src:tesseract_trellis_modern_multiobs_tests",
        "//src:tesseract_trellis_multiobs64_modes_tests",
        "--test_output=errors",
    ], cwd=checkout)

    print("\nSUCCESS: independent Tesseract Trellis 0..64-observable extension built and tested.")
    print(f"Pinned upstream: {UPSTREAM_SHA}")
    print(f"Patch: {reports / 'tesseract-multiobservable64.patch'}")
    print(f"Reports: {reports}")
    print("For the 640-case independent exact-oracle validation, run the GitHub Actions workflow")
    print("'Tesseract multiobservable64 production validation'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
