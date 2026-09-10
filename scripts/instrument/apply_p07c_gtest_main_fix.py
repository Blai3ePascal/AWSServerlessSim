#!/usr/bin/env python3
"""Fix the generated P07 cc_test target to link gtest_main.

P07 originally generated a valid test translation unit without defining main().
Upstream Tesseract test targets link @gtest//:gtest_main, so the production
multiobservable64 target must do the same. This patch is intentionally tiny and
is covered by the release workflow.
"""

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    build_path = Path(args.upstream_dir) / "src" / "BUILD"
    text = build_path.read_text()
    old = '''    deps = [\n        ":libtesseract_trellis",\n        "@gtest",\n        "@stim",\n    ],\n)\n'''
    new = '''    deps = [\n        ":libtesseract_trellis",\n        "@gtest",\n        "@gtest//:gtest_main",\n        "@stim",\n    ],\n)\n'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one P07 test target dependency block, found {count}")
    build_path.write_text(text.replace(old, new, 1))

    report = {
        "phase": "P07c",
        "kind": "test-linkage-fix",
        "change": "add @gtest//:gtest_main to tesseract_trellis_multiobs64_modes_tests",
        "production_decoder_semantics_changed": False,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
