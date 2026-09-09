#!/usr/bin/env python3
"""Add P04 machine-readable decode timing output after validated P02b.

The patch reuses Tesseract Trellis's existing per-shot decode timers and adds
one outer batch wall timer. It does not add clocks inside `decode_shot` and
serializes timing data only after parallel decoding is complete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

EXPECTED_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Apply one exact source edit; fail if the validated source has drifted."""
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one source anchor, found {count}")
    return text.replace(old, new, 1)


def patch_main(text: str) -> str:
    """Layer a timing-output-only CLI patch onto the validated P02b main file."""
    text = replace_once(
        text,
        '  std::string stats_out_fname = "";\n  std::string layer_stats_out_fname = "";\n\n  size_t num_threads = 1;\n',
        '  std::string stats_out_fname = "";\n  std::string layer_stats_out_fname = "";\n  std::string decode_times_out_fname = "";\n\n  size_t num_threads = 1;\n',
        "Args decode timing path",
    )
    text = replace_once(
        text,
        '    if (layer_stats_out_fname == "-") {\n      throw std::invalid_argument("--layer-stats-out must be a file path, not stdout.");\n    }\n',
        '    if (layer_stats_out_fname == "-") {\n      throw std::invalid_argument("--layer-stats-out must be a file path, not stdout.");\n    }\n    if (decode_times_out_fname == "-") {\n      throw std::invalid_argument("--decode-times-out must be a file path, not stdout.");\n    }\n',
        "timing path validation",
    )
    text = replace_once(
        text,
        '  program.add_argument("--layer-stats-out")\n      .help(\n          "Write one ordered JSON object per decoded shot containing the validated P02 "\n          "per-layer Trellis trace. The file is only created when this option is supplied.")\n      .default_value(std::string(""))\n      .store_into(args.layer_stats_out_fname);\n  program.add_argument("--threads")\n',
        '  program.add_argument("--layer-stats-out")\n      .help(\n          "Write one ordered JSON object per decoded shot containing the validated P02 "\n          "per-layer Trellis trace. The file is only created when this option is supplied.")\n      .default_value(std::string(""))\n      .store_into(args.layer_stats_out_fname);\n  program.add_argument("--decode-times-out")\n      .help(\n          "Write P04 decode timing metadata as JSON after decoding. Per-shot values reuse "\n          "the existing decode_shot timer; no extra timer is added inside the decoder hot path.")\n      .default_value(std::string(""))\n      .store_into(args.decode_times_out_fname);\n  program.add_argument("--threads")\n',
        "CLI decode timing argument",
    )
    text = replace_once(
        text,
        '  std::ofstream layer_stats_out;\n  if (!args.layer_stats_out_fname.empty()) {\n    layer_stats_out.open(args.layer_stats_out_fname, std::ofstream::out);\n    if (!layer_stats_out.is_open()) {\n      std::cerr << "Failed to open " << args.layer_stats_out_fname << std::endl;\n      return EXIT_FAILURE;\n    }\n  }\n\n  size_t shot = parallel_for_shots_in_order(\n',
        '  std::ofstream layer_stats_out;\n  if (!args.layer_stats_out_fname.empty()) {\n    layer_stats_out.open(args.layer_stats_out_fname, std::ofstream::out);\n    if (!layer_stats_out.is_open()) {\n      std::cerr << "Failed to open " << args.layer_stats_out_fname << std::endl;\n      return EXIT_FAILURE;\n    }\n  }\n\n  std::ofstream decode_times_out;\n  if (!args.decode_times_out_fname.empty()) {\n    decode_times_out.open(args.decode_times_out_fname, std::ofstream::out);\n    if (!decode_times_out.is_open()) {\n      std::cerr << "Failed to open " << args.decode_times_out_fname << std::endl;\n      return EXIT_FAILURE;\n    }\n  }\n\n  // This wall interval measures the current batch implementation, including\n  // lazy per-thread decoder construction on first use. The already-existing\n  // per-shot timers below continue to measure decode_shot only.\n  auto batch_start_time = std::chrono::high_resolution_clock::now();\n  size_t shot = parallel_for_shots_in_order(\n',
        "batch timer start and output stream",
    )
    text = replace_once(
        text,
        "      });\n\n  if (layer_stats_out.is_open()) {\n",
        "      });\n  auto batch_stop_time = std::chrono::high_resolution_clock::now();\n  const double batch_decode_wall_seconds =\n      std::chrono::duration_cast<std::chrono::microseconds>(batch_stop_time - batch_start_time)\n          .count() /\n      1e6;\n\n  if (layer_stats_out.is_open()) {\n",
        "batch timer stop",
    )
    text = replace_once(
        text,
        '  if (!args.obs_probs_out_fname.empty()) {\n',
        '  if (decode_times_out.is_open()) {\n    nlohmann::json per_shot_json = nlohmann::json::array();\n    for (size_t shot_index = 0; shot_index < shot; ++shot_index) {\n      per_shot_json.push_back({{"shot_index", shot_index},\n                               {"decode_seconds", decoding_time_seconds[shot_index]},\n                               {"low_confidence", low_confidence[shot_index].load()}});\n    }\n    nlohmann::json timing_json = {\n        {"schema_version", 1},\n        {"record_type", "tesseract_trellis_decode_times"},\n        {"num_shots", shot},\n        {"num_threads", args.num_threads},\n        {"batch_decode_wall_seconds", batch_decode_wall_seconds},\n        {"batch_wall_includes_lazy_decoder_construction", true},\n        {"per_shot", std::move(per_shot_json)},\n    };\n    decode_times_out << timing_json << \'\\n\';\n    if (!decode_times_out) {\n      throw std::runtime_error("Failed to write decode timing metadata.");\n    }\n  }\n\n  if (!args.obs_probs_out_fname.empty()) {\n',
        "timing JSON serialization",
    )
    return replace_once(
        text,
        '                                 {"layer_stats_out", args.layer_stats_out_fname},\n                                 {"sample_seed", args.sample_seed},\n',
        '                                 {"layer_stats_out", args.layer_stats_out_fname},\n                                 {"decode_times_out", args.decode_times_out_fname},\n                                 {"batch_decode_wall_seconds", batch_decode_wall_seconds},\n                                 {"sample_seed", args.sample_seed},\n',
        "stats timing provenance",
    )


def digest(text: str) -> str:
    """Return the SHA-256 of one source version for patch provenance."""
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    upstream = args.upstream_dir.resolve()

    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if actual != EXPECTED_SHA:
        raise SystemExit(f"P04 requires upstream {EXPECTED_SHA}, got {actual}")

    header = (upstream / "src/tesseract_trellis.h").read_text(encoding="utf-8")
    main_path = upstream / "src/tesseract_trellis_main.cc"
    main_text = main_path.read_text(encoding="utf-8")
    if "bool track_layer_stats = false;" not in header or "--layer-stats-out" not in main_text:
        raise SystemExit("P04 timing output requires validated P02a+P02b instrumentation first")
    if "--decode-times-out" in main_text:
        raise SystemExit("P04 timing patch appears to be already applied")

    before = main_text
    after = patch_main(before)
    main_path.write_text(after, encoding="utf-8")
    report = {
        "schema_version": 1,
        "phase": "P04a",
        "upstream_sha": actual,
        "file": "src/tesseract_trellis_main.cc",
        "before_sha256": digest(before),
        "after_sha256": digest(after),
    }
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
