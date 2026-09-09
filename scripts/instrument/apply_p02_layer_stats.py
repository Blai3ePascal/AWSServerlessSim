#!/usr/bin/env python3
"""Apply P02 per-layer Trellis instrumentation to the exact pinned upstream SHA.

The patch is intentionally deterministic and fails closed: every edit must match
one exact upstream fragment exactly once. The instrumentation is disabled by
default and does not change ranking, probabilities, beam selection, or state
transitions. It records raw layer quantities so derived metrics can be defined
explicitly later.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

EXPECTED_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Replace exactly one anchored source fragment; source drift is an error."""
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def patch_header(text: str) -> str:
    text = replace_once(text, """  bool merge_errors = true;
  bool track_kept_state_stats = false;
  TesseractTrellisRankingMode ranking_mode = TesseractTrellisRankingMode::MassOnly;
""", """  bool merge_errors = true;
  bool track_kept_state_stats = false;
  // Opt-in research trace: normal decoder users do not populate layer records.
  bool track_layer_stats = false;
  TesseractTrellisRankingMode ranking_mode = TesseractTrellisRankingMode::MassOnly;
""", "config trace switch")

    text = replace_once(text, """  TesseractTrellisRankingMode ranking_mode = TesseractTrellisRankingMode::MassOnly;
};

struct TesseractTrellisDecoder {
""", """  TesseractTrellisRankingMode ranking_mode = TesseractTrellisRankingMode::MassOnly;
};

// Raw work observed at one Trellis layer. Derived ratios are intentionally
// kept out of this structure because invalid branches and beam truncation need
// separate denominators during scientific analysis.
struct TesseractTrellisLayerStats {
  size_t layer_index = 0;
  size_t active_frontier_width = 0;
  size_t surviving_frontier_width = 0;
  size_t beam_in = 0;
  size_t used_pair_buckets = 0;
  size_t states_after_collapse = 0;
  size_t states_kept = 0;
  double expand_seconds = 0;
  double collapse_seconds = 0;
  double truncate_seconds = 0;
};

struct TesseractTrellisDecoder {
""", "layer stats structure")

    return replace_once(text, """  double time_truncate_seconds = 0;
  double time_reconstruct_seconds = 0;
  uint64_t predicted_obs_mask = 0;
""", """  double time_truncate_seconds = 0;
  double time_reconstruct_seconds = 0;
  std::vector<TesseractTrellisLayerStats> layer_stats;
  uint64_t predicted_obs_mask = 0;
""", "decoder layer stats vector")


def patch_source(text: str) -> str:
    text = replace_once(text, """  bool toggles_observable = false;
  bool has_retiring_terms = false;
  size_t surviving_term_count = 0;
""", """  bool toggles_observable = false;
  bool has_retiring_terms = false;
  size_t active_frontier_width = 0;
  size_t surviving_frontier_width = 0;
  size_t surviving_term_count = 0;
""", "compiled frontier fields")

    text = replace_once(text, """    CompiledWideLayerTemplate<Words> compiled;
    compiled.q = layer.q;
    compiled.p = layer.p;
""", """    CompiledWideLayerTemplate<Words> compiled;
    compiled.q = layer.q;
    compiled.p = layer.p;
    compiled.active_frontier_width = layer.current_active_detectors.size();
    compiled.surviving_frontier_width = layer.surviving_local_indices.size();
""", "compiled frontier assignment")

    text = replace_once(text, """    const bool compute_penalties =
        decoder->config.ranking_mode != TesseractTrellisRankingMode::MassOnly;
    for (size_t layer_index = 0; layer_index < layers.size(); ++layer_index) {
      const auto& layer = layers[layer_index];

      ensure_pair_bucket_capacity(&pair_buckets, beam_entries.size());
""", """    const bool compute_penalties =
        decoder->config.ranking_mode != TesseractTrellisRankingMode::MassOnly;
    if (decoder->config.track_layer_stats) {
      decoder->layer_stats.reserve(layers.size());
    }
    for (size_t layer_index = 0; layer_index < layers.size(); ++layer_index) {
      const auto& layer = layers[layer_index];
      const size_t beam_in = beam_entries.size();

      ensure_pair_bucket_capacity(&pair_buckets, beam_entries.size());
""", "layer loop entry")

    text = replace_once(text, """      auto t1 = std::chrono::high_resolution_clock::now();
      decoder->time_expand_seconds +=
          std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count() / 1e6;
""", """      auto t1 = std::chrono::high_resolution_clock::now();
      const double layer_expand_seconds =
          std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count() / 1e6;
      decoder->time_expand_seconds += layer_expand_seconds;
""", "per-layer expand time")

    text = replace_once(text, """      beam_entries.swap(next_entries);
      auto t2 = std::chrono::high_resolution_clock::now();
      decoder->time_collapse_seconds +=
          std::chrono::duration_cast<std::chrono::microseconds>(t2 - t2a).count() / 1e6;
""", """      beam_entries.swap(next_entries);
      const size_t states_after_collapse = beam_entries.size();
      auto t2 = std::chrono::high_resolution_clock::now();
      const double layer_collapse_seconds =
          std::chrono::duration_cast<std::chrono::microseconds>(t2 - t2a).count() / 1e6;
      decoder->time_collapse_seconds += layer_collapse_seconds;
""", "per-layer collapse time")

    text = replace_once(text, """      const size_t kept_states =
          keep_top_compiled_states(&beam_entries, decoder->config.beam_width,
                                   decoder->config.beam_eps, decoder->config.ranking_mode);
      normalize_compiled_items(&beam_entries);
      record_kept_state_count(decoder, beam_entries.empty() ? 0 : kept_states);
      if (beam_entries.empty()) {
        decoder->low_confidence_flag = true;
        return;
      }
      decoder->num_states_merged += kept_states;
      decoder->max_beam_size_seen = std::max(decoder->max_beam_size_seen, kept_states);
      auto t3 = std::chrono::high_resolution_clock::now();
      decoder->time_truncate_seconds +=
          std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count() / 1e6;
""", """      const size_t kept_states =
          keep_top_compiled_states(&beam_entries, decoder->config.beam_width,
                                   decoder->config.beam_eps, decoder->config.ranking_mode);
      normalize_compiled_items(&beam_entries);
      record_kept_state_count(decoder, beam_entries.empty() ? 0 : kept_states);
      if (beam_entries.empty()) {
        auto t3 = std::chrono::high_resolution_clock::now();
        const double layer_truncate_seconds =
            std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count() / 1e6;
        decoder->time_truncate_seconds += layer_truncate_seconds;
        if (decoder->config.track_layer_stats) {
          decoder->layer_stats.push_back({layer_index, layer.active_frontier_width,
                                          layer.surviving_frontier_width, beam_in,
                                          used_bucket_indices.size(), states_after_collapse, 0,
                                          layer_expand_seconds, layer_collapse_seconds,
                                          layer_truncate_seconds});
        }
        decoder->low_confidence_flag = true;
        return;
      }
      decoder->num_states_merged += kept_states;
      decoder->max_beam_size_seen = std::max(decoder->max_beam_size_seen, kept_states);
      auto t3 = std::chrono::high_resolution_clock::now();
      const double layer_truncate_seconds =
          std::chrono::duration_cast<std::chrono::microseconds>(t3 - t2).count() / 1e6;
      decoder->time_truncate_seconds += layer_truncate_seconds;
      if (decoder->config.track_layer_stats) {
        decoder->layer_stats.push_back({layer_index, layer.active_frontier_width,
                                        layer.surviving_frontier_width, beam_in,
                                        used_bucket_indices.size(), states_after_collapse,
                                        beam_entries.size(), layer_expand_seconds,
                                        layer_collapse_seconds, layer_truncate_seconds});
      }
""", "layer trace record")

    return replace_once(text, """  time_reconstruct_seconds = 0;
  predicted_obs_mask = 0;
""", """  time_reconstruct_seconds = 0;
  // Avoid stale data if a decoder configuration changes between shots.
  // clear() does not allocate.
  layer_stats.clear();
  predicted_obs_mask = 0;
""", "trace reset")


def patch_tests(text: str) -> str:
    marker = "\n}  // namespace tesseract_decoder\n"
    if text.count(marker) != 1:
        raise RuntimeError("test namespace terminator is not unique")
    test = r'''

TEST(TesseractTrellisDecoderTest, LayerStatsAreOptionalAndPreserveDecodeSemantics) {
  stim::DetectorErrorModel dem(R"DEM(
    error(0.10) D0 L0
    error(0.15) D0 D1
    error(0.20) D1 L0
    detector(0, 0, 0) D0
    detector(1, 0, 0) D1
  )DEM");

  TesseractTrellisConfig baseline_config;
  baseline_config.dem = dem;
  baseline_config.beam_width = 64;
  TesseractTrellisDecoder baseline(baseline_config);
  baseline.decode_shot({0});
  ASSERT_FALSE(baseline.low_confidence_flag);
  EXPECT_TRUE(baseline.layer_stats.empty());

  TesseractTrellisConfig traced_config = baseline_config;
  traced_config.track_layer_stats = true;
  TesseractTrellisDecoder traced(traced_config);
  traced.decode_shot({0});

  EXPECT_EQ(traced.low_confidence_flag, baseline.low_confidence_flag);
  EXPECT_EQ(traced.predicted_obs_mask, baseline.predicted_obs_mask);
  EXPECT_NEAR(traced.observable_probability(), baseline.observable_probability(), 1e-15);
  ASSERT_EQ(traced.layer_stats.size(), traced.errors.size());

  double expand_sum = 0;
  double collapse_sum = 0;
  double truncate_sum = 0;
  for (size_t k = 0; k < traced.layer_stats.size(); ++k) {
    const auto& stats = traced.layer_stats[k];
    EXPECT_EQ(stats.layer_index, k);
    EXPECT_GE(stats.active_frontier_width, stats.surviving_frontier_width);
    EXPECT_GE(stats.beam_in, 1);
    EXPECT_LE(stats.used_pair_buckets, stats.states_after_collapse);
    EXPECT_GE(stats.states_after_collapse, stats.states_kept);
    expand_sum += stats.expand_seconds;
    collapse_sum += stats.collapse_seconds;
    truncate_sum += stats.truncate_seconds;
  }
  EXPECT_NEAR(expand_sum, traced.time_expand_seconds, 1e-15);
  EXPECT_NEAR(collapse_sum, traced.time_collapse_seconds, 1e-15);
  EXPECT_NEAR(truncate_sum, traced.time_truncate_seconds, 1e-15);
}
'''
    return text.replace(marker, test + marker, 1)


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
        raise SystemExit(f"P02 requires upstream {EXPECTED_SHA}, got {actual}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=upstream, text=True).strip():
        raise SystemExit("P02 requires a clean upstream checkout")

    patchers = {
        "src/tesseract_trellis.h": patch_header,
        "src/tesseract_trellis.cc": patch_source,
        "src/tesseract_trellis.test.cc": patch_tests,
    }
    report = {"schema_version": 1, "phase": "P02", "upstream_sha": actual, "files": {}}
    for relative, patcher in patchers.items():
        path = upstream / relative
        before = path.read_text(encoding="utf-8")
        after = patcher(before)
        path.write_text(after, encoding="utf-8")
        report["files"][relative] = {
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
