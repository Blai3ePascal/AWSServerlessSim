#!/usr/bin/env python3
"""Validate that a downloaded P05 evidence directory is self-contained.

This regression check intentionally validates the *portable artifact* rather
than only the in-repository paths that produced it.  It catches two classes of
packaging bugs:

1. summary.csv must remain rectangular even when circuit filenames contain
   commas;
2. every entry in SHA256SUMS must resolve relative to the extracted artifact
   root and match the recorded digest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_csv(root: Path) -> None:
    csv_path = root / "summary.csv"
    if not csv_path.is_file():
        raise AssertionError(f"missing {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    if len(rows) < 2:
        raise AssertionError("summary.csv must contain a header and at least one data row")

    width = len(rows[0])
    if width == 0:
        raise AssertionError("summary.csv header is empty")

    for index, row in enumerate(rows[1:], start=2):
        if len(row) != width:
            raise AssertionError(
                f"summary.csv row {index} has {len(row)} columns; expected {width}"
            )


def parse_sha256_line(line: str) -> tuple[str, str]:
    if len(line) < 67:
        raise AssertionError(f"malformed SHA256SUMS line: {line!r}")
    digest = line[:64]
    marker = line[64:66]
    relpath = line[66:]
    if marker not in ("  ", " *"):
        raise AssertionError(f"malformed SHA256SUMS marker: {line!r}")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        raise AssertionError(f"malformed SHA-256 digest: {digest!r}")
    if not relpath:
        raise AssertionError("empty checksum path")
    return digest.lower(), relpath


def validate_checksums(root: Path) -> None:
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise AssertionError(f"missing {sums_path}")

    lines = [line for line in sums_path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        raise AssertionError("SHA256SUMS is empty")

    for line in lines:
        expected, relpath = parse_sha256_line(line)
        candidate = Path(relpath)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise AssertionError(f"checksum path is not artifact-relative: {relpath}")
        path = root / candidate
        if not path.is_file():
            raise AssertionError(
                f"checksum entry does not resolve inside extracted artifact: {relpath}"
            )
        actual = sha256_file(path)
        if actual != expected:
            raise AssertionError(
                f"checksum mismatch for {relpath}: expected {expected}, got {actual}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()

    root = args.artifact_dir.resolve()
    validate_csv(root)
    validate_checksums(root)
    print(f"P05 portable evidence contract PASS: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
