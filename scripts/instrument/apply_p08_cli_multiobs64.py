#!/usr/bin/env python3
"""Remove the stale one-observable CLI gate after the 0..64 Trellis kernel is installed.

This is intentionally a tiny patch. The decoder class already enforces the real
0..64 contract. The public CLI still had an old early-exit for >1 observable,
which made the new kernel impossible to use from a real .stim circuit.
"""

import argparse
import json
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    root = Path(args.upstream_dir)
    main_path = root / "src" / "tesseract_trellis_main.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    text = main_path.read_text()

    stale_gate = '''  if (num_observables > 1) {\n    std::cerr << "tesseract_trellis currently supports at most one observable; DEM has "\n              << num_observables << "." << std::endl;\n    return EXIT_FAILURE;\n  }\n'''
    replacement = '''  if (num_observables > 64) {\n    std::cerr << "tesseract_trellis supports at most 64 observables (L0..L63); DEM has "\n              << num_observables << "." << std::endl;\n    return EXIT_FAILURE;\n  }\n'''
    text = replace_once(text, stale_gate, replacement, "replace stale CLI observable gate")

    old_probability = '''        obs_probability_predicted[shot_index] = decoder.observable_probability();\n'''
    new_probability = '''        obs_probability_predicted[shot_index] =\n            num_observables == 1 ? decoder.observable_probability()\n                                 : std::numeric_limits<double>::quiet_NaN();\n'''
    text = replace_once(
        text, old_probability, new_probability,
        "avoid presenting one-observable marginal probability for multiobservable runs")

    old_stats = '''                                 {"num_threads", args.num_threads},\n                                 {"num_low_confidence", num_low_confidence},\n'''
    new_stats = '''                                 {"num_threads", args.num_threads},\n                                 {"num_observables", num_observables},\n                                 {"num_low_confidence", num_low_confidence},\n'''
    text = replace_once(text, old_stats, new_stats, "record observable count in CLI stats")

    main_path.write_text(text)

    report = {
        "phase": "P08-cli",
        "purpose": "make the validated 0..64 decoder reachable from the public tesseract_trellis CLI",
        "old_cli_limit": 1,
        "new_cli_limit": 64,
        "probability_output_policy": "observable_probability() remains one-observable-only; multiobservable CLI stores NaN internally and --obs-probs-out remains rejected unless exactly one observable",
        "stats_addition": "num_observables",
        "private_code_used": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
