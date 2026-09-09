#!/usr/bin/env python3
"""Expose validated P02 Trellis layer records through an opt-in JSONL CLI output.

This patch is deliberately layered on top of P02a. It only modifies
`tesseract_trellis_main.cc`; the Trellis algorithm and the P02a instrumentation
remain unchanged. Worker threads copy their trace into an indexed per-shot
container, and serialization occurs only after decoding completes so JSONL
ordering does not depend on thread scheduling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

EXPECTED_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Replace one exact source anchor and fail closed if upstream drifted."""
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_main(text: str) -> str:
    text = replace_once(
        text,
        """  std::string dem_out_fname = \"\";\n  std::string stats_out_fname = \"\";\n\n  size_t num_threads = 1;\n""",
        """  std::string dem_out_fname = \"\";\n  std::string stats_out_fname = \"\";\n  std::string layer_stats_out_fname = \"\";\n\n  size_t num_threads = 1;\n""",
        "Args layer trace path",
    )

    text = replace_once(
        text,
        """    if (obs_probs_out_fname == \"-\") {\n      throw std::invalid_argument(\"--obs-probs-out must be a file path, not stdout.\");\n    }\n""",
        """    if (obs_probs_out_fname == \"-\") {\n      throw std::invalid_argument(\"--obs-probs-out must be a file path, not stdout.\");\n    }\n    if (layer_stats_out_fname == \"-\") {\n      throw std::invalid_argument(\"--layer-stats-out must be a file path, not stdout.\");\n    }\n""",
        "trace path validation",
    )

    text = replace_once(
        text,
        """    config.verbose = verbose;\n    config.track_kept_state_stats = print_stats;\n    config.ranking_mode = parse_ranking_mode(ranking_mode);\n""",
        """    config.verbose = verbose;\n    config.track_kept_state_stats = print_stats;\n    // Layer tracing is research-only and remains disabled unless an explicit\n    // output path is requested. This keeps normal decoder runs on the P02a\n    // non-tracing path.\n    config.track_layer_stats = !layer_stats_out_fname.empty();\n    config.ranking_mode = parse_ranking_mode(ranking_mode);\n""",
        "enable tracing only when requested",
    )

    text = replace_once(
        text,
        """  program.add_argument(\"--stats-out\")\n      .default_value(std::string(\"\"))\n      .store_into(args.stats_out_fname);\n  program.add_argument(\"--threads\")\n""",
        """  program.add_argument(\"--stats-out\")\n      .default_value(std::string(\"\"))\n      .store_into(args.stats_out_fname);\n  program.add_argument(\"--layer-stats-out\")\n      .help(\n          \"Write one ordered JSON object per decoded shot containing the validated P02 \"\n          \"per-layer Trellis trace. The file is only created when this option is supplied.\")\n      .default_value(std::string(\"\"))\n      .store_into(args.layer_stats_out_fname);\n  program.add_argument(\"--threads\")\n""",
        "CLI layer trace argument",
    )

    text = replace_once(
        text,
        """  std::vector<double> time_truncate_per_shot(shots.size());\n  std::vector<double> time_reconstruct_per_shot(shots.size());\n  std::vector<std::atomic<bool>> low_confidence(shots.size());\n""",
        """  std::vector<double> time_truncate_per_shot(shots.size());\n  std::vector<double> time_reconstruct_per_shot(shots.size());\n  // Each worker writes only to its shot index. The JSON file itself is written\n  // after parallel decoding, which makes record order independent of thread\n  // scheduling and avoids shared-stream synchronization in the hot path.\n  std::vector<std::vector<TesseractTrellisLayerStats>> layer_stats_per_shot(shots.size());\n  std::vector<std::atomic<bool>> low_confidence(shots.size());\n""",
        "per-shot trace storage",
    )

    text = replace_once(
        text,
        """  if (!args.obs_probs_out_fname.empty() && num_observables != 1) {\n    std::cerr << \"--obs-probs-out requires a DEM with exactly one observable.\" << std::endl;\n    return EXIT_FAILURE;\n  }\n\n  size_t shot = parallel_for_shots_in_order(\n""",
        """  if (!args.obs_probs_out_fname.empty() && num_observables != 1) {\n    std::cerr << \"--obs-probs-out requires a DEM with exactly one observable.\" << std::endl;\n    return EXIT_FAILURE;\n  }\n\n  std::ofstream layer_stats_out;\n  if (!args.layer_stats_out_fname.empty()) {\n    layer_stats_out.open(args.layer_stats_out_fname, std::ofstream::out);\n    if (!layer_stats_out.is_open()) {\n      std::cerr << \"Failed to open \" << args.layer_stats_out_fname << std::endl;\n      return EXIT_FAILURE;\n    }\n  }\n\n  size_t shot = parallel_for_shots_in_order(\n""",
        "open trace before decoding",
    )

    text = replace_once(
        text,
        """        time_collapse_per_shot[shot_index] = decoder.time_collapse_seconds;\n        time_truncate_per_shot[shot_index] = decoder.time_truncate_seconds;\n        time_reconstruct_per_shot[shot_index] = decoder.time_reconstruct_seconds;\n      },\n""",
        """        time_collapse_per_shot[shot_index] = decoder.time_collapse_seconds;\n        time_truncate_per_shot[shot_index] = decoder.time_truncate_seconds;\n        time_reconstruct_per_shot[shot_index] = decoder.time_reconstruct_seconds;\n        if (config.track_layer_stats) {\n          layer_stats_per_shot[shot_index] = decoder.layer_stats;\n        }\n      },\n""",
        "copy trace out of worker decoder",
    )

    text = replace_once(
        text,
        """      });\n\n  if (!args.obs_probs_out_fname.empty()) {\n""",
        """      });\n\n  if (layer_stats_out.is_open()) {\n    for (size_t shot_index = 0; shot_index < shot; ++shot_index) {\n      nlohmann::json layers_json = nlohmann::json::array();\n      for (const auto& layer : layer_stats_per_shot[shot_index]) {\n        layers_json.push_back({{\"layer_index\", layer.layer_index},\n                               {\"active_frontier_width\", layer.active_frontier_width},\n                               {\"surviving_frontier_width\", layer.surviving_frontier_width},\n                               {\"beam_in\", layer.beam_in},\n                               {\"used_pair_buckets\", layer.used_pair_buckets},\n                               {\"states_after_collapse\", layer.states_after_collapse},\n                               {\"states_kept\", layer.states_kept},\n                               {\"expand_seconds\", layer.expand_seconds},\n                               {\"collapse_seconds\", layer.collapse_seconds},\n                               {\"truncate_seconds\", layer.truncate_seconds}});\n      }\n      nlohmann::json trace_record = {\n          {\"schema_version\", 1},\n          {\"record_type\", \"tesseract_trellis_layer_trace\"},\n          {\"shot_index\", shot_index},\n          {\"detection_count\", shots[shot_index].hits.size()},\n          {\"low_confidence\", low_confidence[shot_index].load()},\n          {\"predicted_obs_mask\", obs_predicted[shot_index]},\n          {\"num_layers\", layers_json.size()},\n          {\"layers\", std::move(layers_json)},\n      };\n      layer_stats_out << trace_record << '\\n';\n    }\n    if (!layer_stats_out) {\n      throw std::runtime_error(\"Failed to write layer stats trace.\");\n    }\n  }\n\n  if (!args.obs_probs_out_fname.empty()) {\n""",
        "ordered JSONL serialization",
    )

    return replace_once(
        text,
        """                                 {\"merge_errors\", config.merge_errors},\n                                 {\"obs_probs_out\", args.obs_probs_out_fname},\n                                 {\"sample_seed\", args.sample_seed},\n""",
        """                                 {\"merge_errors\", config.merge_errors},\n                                 {\"obs_probs_out\", args.obs_probs_out_fname},\n                                 {\"layer_stats_out\", args.layer_stats_out_fname},\n                                 {\"sample_seed\", args.sample_seed},\n""",
        "stats provenance for trace path",
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    upstream = args.upstream_dir.resolve()

    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if actual != EXPECTED_SHA:
        raise SystemExit(f"P02b requires upstream {EXPECTED_SHA}, got {actual}")

    header = (upstream / "src/tesseract_trellis.h").read_text(encoding="utf-8")
    if "bool track_layer_stats = false;" not in header or "struct TesseractTrellisLayerStats" not in header:
        raise SystemExit("P02b requires the validated P02a layer instrumentation to be applied first")

    main_path = upstream / "src/tesseract_trellis_main.cc"
    if subprocess.run(
        ["git", "diff", "--quiet", "--", "src/tesseract_trellis_main.cc"], cwd=upstream
    ).returncode != 0:
        raise SystemExit("P02b requires an otherwise-unmodified tesseract_trellis_main.cc")

    before = main_path.read_text(encoding="utf-8")
    after = patch_main(before)
    main_path.write_text(after, encoding="utf-8")

    report = {
        "schema_version": 1,
        "phase": "P02b",
        "upstream_sha": actual,
        "file": "src/tesseract_trellis_main.cc",
        "before_sha256": digest(before),
        "after_sha256": digest(after),
    }
    data = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        output = args.report.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
