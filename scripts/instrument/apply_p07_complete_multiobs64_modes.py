#!/usr/bin/env python3
"""Complete the P06 multi-observable Trellis path for the modern pinned upstream.

This script is deliberately applied *after* apply_p06_modern_multiobs.py.  P06
established and independently validated the joint-observable-mask semantics.
P07 keeps that semantics but removes the temporary MassOnly/beam_eps=0
restriction by reproducing the modern detector-state ranking contract for the
2..64 observable path.
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
    cc_path = root / "src" / "tesseract_trellis.cc"
    build_path = root / "src" / "BUILD"
    p06_test_path = root / "src" / "tesseract_trellis_modern_multiobs.test.cc"
    p07_test_path = root / "src" / "tesseract_trellis_multiobs64_modes.test.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    cc = cc_path.read_text()
    block_start = cc.find("struct GenericMultiObsEntry {")
    block_end = cc.find("std::unique_ptr<TesseractTrellisWideKernelBase> build_compiled_wide_kernel(")
    if block_start < 0 or block_end < 0 or block_start >= block_end:
        raise RuntimeError("P07 requires the P06 GenericMultiObsKernel to be present exactly once")

    generic_kernel = r'''struct GenericMultiObsEntry {
  std::vector<uint64_t> state_words;
  uint64_t obs_mask = 0;
  double mass = 0.0;
  double penalty = 0.0;
};

bool generic_state_less(const std::vector<uint64_t>& a, const std::vector<uint64_t>& b) {
  if (a.size() != b.size()) {
    return a.size() < b.size();
  }
  for (size_t k = a.size(); k-- > 0;) {
    if (a[k] != b[k]) {
      return a[k] < b[k];
    }
  }
  return false;
}

bool generic_state_zero(const std::vector<uint64_t>& state_words) {
  for (uint64_t word : state_words) {
    if (word != 0) {
      return false;
    }
  }
  return true;
}

bool generic_state_bit(const std::vector<uint64_t>& state_words, size_t bit) {
  const size_t word = bit >> 6;
  if (word >= state_words.size()) {
    return false;
  }
  return ((state_words[word] >> (bit & 63)) & 1ULL) != 0;
}

void generic_toggle_bit(std::vector<uint64_t>* state_words, size_t bit) {
  const size_t word = bit >> 6;
  if (state_words->size() <= word) {
    state_words->resize(word + 1, 0);
  }
  (*state_words)[word] ^= uint64_t{1} << (bit & 63);
}

std::vector<uint64_t> generic_project_state(
    const std::vector<uint64_t>& state_words,
    const std::vector<uint32_t>& surviving_local_indices) {
  std::vector<uint64_t> result(num_state_words(surviving_local_indices.size()), 0);
  for (size_t dst = 0; dst < surviving_local_indices.size(); ++dst) {
    if (generic_state_bit(state_words, (size_t)surviving_local_indices[dst])) {
      result[dst >> 6] |= uint64_t{1} << (dst & 63);
    }
  }
  while (!result.empty() && result.back() == 0) {
    result.pop_back();
  }
  return result;
}

struct GenericBranchPenaltyUpdate {
  bool absent_valid = true;
  bool present_valid = true;
  double absent_penalty = 0.0;
  double present_penalty = 0.0;
};

GenericBranchPenaltyUpdate generic_branch_penalty_update(
    const std::vector<uint64_t>& state_words, double current_penalty,
    const std::vector<uint64_t>& actual_detector_words,
    const TesseractTrellisWideLayerTemplate& layer, bool compute_penalties) {
  GenericBranchPenaltyUpdate update;
  update.absent_penalty = compute_penalties ? current_penalty : 0.0;
  update.present_penalty = compute_penalties ? current_penalty : 0.0;

  const auto& transition = layer.detcost_transition;
  for (size_t k = 0; k < transition.fault_local_indices.size(); ++k) {
    const size_t local = (size_t)transition.fault_local_indices[k];
    const bool was_active_before = local < layer.previous_width;
    const bool state_bit = was_active_before && generic_state_bit(state_words, local);
    const size_t detector = (size_t)layer.current_active_detectors[local];
    const bool target_bit =
        (actual_detector_words[detector_word_index(detector)] & detector_word_mask(detector)) != 0;
    const bool mismatch = state_bit ^ target_bit;
    const bool survives = transition.next_local_indices[k] >= 0;

    if (survives) {
      if (compute_penalties) {
        const double prev_contrib = was_active_before && mismatch ? transition.current_costs[k] : 0.0;
        const double next_contrib = mismatch ? transition.next_costs[k] : 0.0;
        update.absent_penalty += next_contrib - prev_contrib;
        update.present_penalty += (transition.next_costs[k] - next_contrib) - prev_contrib;
      }
    } else {
      if (mismatch) {
        update.absent_valid = false;
      } else {
        update.present_valid = false;
      }
      if (compute_penalties) {
        const double prev_contrib = was_active_before && mismatch ? transition.current_costs[k] : 0.0;
        update.absent_penalty -= prev_contrib;
        update.present_penalty -= prev_contrib;
      }
    }
  }
  return update;
}

void merge_generic_entries(std::vector<GenericMultiObsEntry>* entries) {
  if (entries->empty()) {
    return;
  }
  std::sort(entries->begin(), entries->end(), [](const auto& a, const auto& b) {
    if (generic_state_less(a.state_words, b.state_words)) {
      return true;
    }
    if (generic_state_less(b.state_words, a.state_words)) {
      return false;
    }
    return a.obs_mask < b.obs_mask;
  });
  size_t out = 0;
  for (size_t i = 1; i < entries->size(); ++i) {
    if ((*entries)[i].state_words == (*entries)[out].state_words &&
        (*entries)[i].obs_mask == (*entries)[out].obs_mask) {
      (*entries)[out].mass += (*entries)[i].mass;
    } else {
      ++out;
      if (out != i) {
        (*entries)[out] = std::move((*entries)[i]);
      }
    }
  }
  entries->resize(out + 1);
}

size_t keep_top_generic_detector_states(std::vector<GenericMultiObsEntry>* entries,
                                        size_t beam_width, double beam_eps,
                                        TesseractTrellisRankingMode ranking_mode) {
  if (entries->empty()) {
    return 0;
  }

  struct StateSummary {
    std::vector<uint64_t> state_words;
    double mass = 0.0;
    double penalty = 0.0;
    double score = -INF;
  };

  std::vector<StateSummary> states;
  for (const auto& entry : *entries) {
    if (states.empty() || states.back().state_words != entry.state_words) {
      states.push_back({entry.state_words, entry.mass, entry.penalty, -INF});
    } else {
      states.back().mass += entry.mass;
    }
  }
  const size_t original_state_count = states.size();

  double total_mass = 0.0;
  for (auto& state : states) {
    state.score = score_mass_and_penalty(state.mass, state.penalty, ranking_mode);
    if (beam_eps > 0.0) {
      total_mass += state.mass;
    }
  }

  auto score_greater = [](const StateSummary& a, const StateSummary& b) {
    if (a.score != b.score) {
      return a.score > b.score;
    }
    return generic_state_less(a.state_words, b.state_words);
  };

  if (states.size() > beam_width) {
    std::nth_element(states.begin(), states.begin() + beam_width, states.end(), score_greater);
    states.resize(beam_width);
  } else if (beam_eps <= 0.0) {
    return states.size();
  }

  if (beam_eps > 0.0 && total_mass > 0.0 && !states.empty()) {
    std::sort(states.begin(), states.end(), score_greater);
    const double retained_target_mass = total_mass * (1.0 - beam_eps);
    double retained_mass = 0.0;
    size_t keep_count = 0;
    while (keep_count < states.size()) {
      retained_mass += states[keep_count].mass;
      ++keep_count;
      if (retained_mass >= retained_target_mass) {
        break;
      }
    }
    states.resize(keep_count);
  }

  if (states.size() == original_state_count) {
    return states.size();
  }

  std::sort(states.begin(), states.end(), [](const StateSummary& a, const StateSummary& b) {
    return generic_state_less(a.state_words, b.state_words);
  });
  auto selected = [&states](const std::vector<uint64_t>& state_words) {
    auto it = std::lower_bound(
        states.begin(), states.end(), state_words,
        [](const StateSummary& a, const std::vector<uint64_t>& b) {
          return generic_state_less(a.state_words, b);
        });
    return it != states.end() && it->state_words == state_words;
  };

  size_t out = 0;
  for (size_t i = 0; i < entries->size(); ++i) {
    if (!selected((*entries)[i].state_words)) {
      continue;
    }
    if (out != i) {
      (*entries)[out] = std::move((*entries)[i]);
    }
    ++out;
  }
  entries->resize(out);
  return states.size();
}

void normalize_generic_entries(std::vector<GenericMultiObsEntry>* entries) {
  double total = 0.0;
  for (const auto& entry : *entries) {
    total += entry.mass;
  }
  if (total <= 0.0) {
    entries->clear();
    return;
  }
  for (auto& entry : *entries) {
    entry.mass /= total;
  }
}

struct GenericMultiObsKernel final : TesseractTrellisWideKernelBase {
  explicit GenericMultiObsKernel(std::vector<TesseractTrellisWideLayerTemplate> layers_,
                                 size_t max_frontier_width_)
      : layers(std::move(layers_)), max_frontier_width(max_frontier_width_) {}

  void decode_shot(TesseractTrellisDecoder* decoder,
                   const std::vector<uint64_t>& detections) const override {
    auto& actual_detector_words = decoder->actual_detector_words_scratch;
    std::fill(actual_detector_words.begin(), actual_detector_words.end(), 0);
    for (uint64_t d : detections) {
      if (d >= decoder->num_detectors) {
        decoder->low_confidence_flag = true;
        return;
      }
      const size_t word = detector_word_index((size_t)d);
      const uint64_t mask = detector_word_mask((size_t)d);
      if ((decoder->all_possible_detector_words[word] & mask) == 0) {
        decoder->low_confidence_flag = true;
        return;
      }
      actual_detector_words[word] ^= mask;
    }

    decoder->max_frontier_width_seen = max_frontier_width;
    const bool compute_penalties =
        decoder->config.ranking_mode != TesseractTrellisRankingMode::MassOnly;
    double initial_penalty = 0.0;
    if (compute_penalties && !layers.empty()) {
      for (int detector : layers.front().current_active_detectors) {
        const size_t d = (size_t)detector;
        const bool target_bit =
            (actual_detector_words[detector_word_index(d)] & detector_word_mask(d)) != 0;
        if (!target_bit) {
          continue;
        }
        const double cost = decoder->initial_future_detcost[d];
        if (cost == INF) {
          initial_penalty = INF;
          break;
        }
        initial_penalty += cost;
      }
    }

    std::vector<GenericMultiObsEntry> beam_entries{{{}, 0, 1.0, initial_penalty}};
    std::vector<GenericMultiObsEntry> next_entries;
    decoder->max_beam_size_seen = 1;

    for (const auto& layer : layers) {
      next_entries.clear();
      next_entries.reserve(beam_entries.size() * 2);
      for (const auto& item : beam_entries) {
        ++decoder->num_states_expanded;
        const auto update = generic_branch_penalty_update(
            item.state_words, item.penalty, actual_detector_words, layer, compute_penalties);

        if (update.absent_valid && layer.q != 0.0) {
          next_entries.push_back(
              {generic_project_state(item.state_words, layer.surviving_local_indices),
               item.obs_mask, item.mass * layer.q, update.absent_penalty});
        }

        if (update.present_valid && layer.p != 0.0) {
          std::vector<uint64_t> toggled = item.state_words;
          for (uint32_t local : layer.detcost_transition.fault_local_indices) {
            generic_toggle_bit(&toggled, (size_t)local);
          }
          next_entries.push_back(
              {generic_project_state(toggled, layer.surviving_local_indices),
               item.obs_mask ^ layer.obs_mask, item.mass * layer.p, update.present_penalty});
        }
      }

      beam_entries.swap(next_entries);
      merge_generic_entries(&beam_entries);
      const size_t kept_states = keep_top_generic_detector_states(
          &beam_entries, decoder->config.beam_width, decoder->config.beam_eps,
          decoder->config.ranking_mode);
      normalize_generic_entries(&beam_entries);
      record_kept_state_count(decoder, beam_entries.empty() ? 0 : kept_states);
      if (beam_entries.empty()) {
        decoder->low_confidence_flag = true;
        return;
      }
      decoder->num_states_merged += kept_states;
      decoder->max_beam_size_seen = std::max(decoder->max_beam_size_seen, kept_states);
    }

    std::map<uint64_t, double> final_masses;
    for (const auto& item : beam_entries) {
      if (generic_state_zero(item.state_words)) {
        final_masses[item.obs_mask] += item.mass;
      }
    }
    if (final_masses.empty()) {
      decoder->low_confidence_flag = true;
      return;
    }

    double best_mass = -1.0;
    uint64_t best_mask = 0;
    for (const auto& [mask, mass] : final_masses) {
      if (mask == 0) {
        decoder->total_mass_obs0 += mass;
      } else if (mask == 1) {
        decoder->total_mass_obs1 += mass;
      }
      if (mass > best_mass || (mass == best_mass && mask < best_mask)) {
        best_mass = mass;
        best_mask = mask;
      }
    }
    decoder->predicted_obs_mask = best_mask;
  }

  std::vector<TesseractTrellisWideLayerTemplate> layers;
  size_t max_frontier_width;
};

'''
    cc = cc[:block_start] + generic_kernel + cc[block_end:]

    temporary_guards = '''  if (num_observables > 1 && config.ranking_mode != TesseractTrellisRankingMode::MassOnly) {
    throw std::invalid_argument("experimental multi-observable path currently supports MassOnly ranking");
  }
  if (num_observables > 1 && config.beam_eps != 0.0) {
    throw std::invalid_argument("experimental multi-observable path currently requires beam_eps=0");
  }
'''
    cc = replace_once(cc, temporary_guards, "", "remove temporary P06 mode restrictions")
    cc_path.write_text(cc)

    p06_tests = p06_test_path.read_text()
    obsolete_test = r'''TEST(TesseractTrellisModernMultiObs, RejectsUnsupportedExperimentalRankingForNow) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(R"DEM(
    error(0.2) D0 L0 L1
    detector(0, 0, 0) D0
  )DEM");
  config.ranking_mode = TesseractTrellisRankingMode::FutureDetcostRanked;
  EXPECT_THROW(TesseractTrellisDecoder decoder(config), std::invalid_argument);
}
'''
    replacement_test = r'''TEST(TesseractTrellisModernMultiObs, RankedModesAreSupported) {
  for (auto mode : {TesseractTrellisRankingMode::FutureDetcostRanked,
                    TesseractTrellisRankingMode::FutureActiveDetcostRanked}) {
    TesseractTrellisConfig config;
    config.dem = stim::DetectorErrorModel(R"DEM(
      error(0.1) D0
      error(0.2) D0 L0 L1
      detector(0, 0, 0) D0
    )DEM");
    config.beam_width = 1024;
    config.ranking_mode = mode;
    TesseractTrellisDecoder decoder(config);
    decoder.decode_shot({0});
    ASSERT_FALSE(decoder.low_confidence_flag);
    EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{3});
  }
}
'''
    p06_tests = replace_once(p06_tests, obsolete_test, replacement_test,
                             "replace obsolete ranking rejection test")
    p06_test_path.write_text(p06_tests)

    p07_test_path.write_text(r'''// P07 completeness tests for the modern 2..64-observable path.
#include "tesseract_trellis.h"

#include <gtest/gtest.h>
#include <vector>

#include "stim.h"

namespace tesseract_decoder {
namespace {

TesseractTrellisDecoder decoder_for_mode(const char* dem_text,
                                         TesseractTrellisRankingMode mode,
                                         double beam_eps = 0.0,
                                         size_t beam_width = 1024) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(dem_text);
  config.beam_width = beam_width;
  config.beam_eps = beam_eps;
  config.ranking_mode = mode;
  return TesseractTrellisDecoder(config);
}

TEST(TesseractTrellisMultiObs64Modes, AllModernRankingModesPreserveJointMaskWithoutPruning) {
  constexpr const char* dem = R"DEM(
    error(0.13) D0 L0
    error(0.21) D1 L1
    error(0.17) D0 D1 L0 L1
    error(0.09) D0 L2
    error(0.12) D1 L0 L2
    detector(0, 0, 0) D0
    detector(1, 0, 0) D1
  )DEM";
  for (auto mode : {TesseractTrellisRankingMode::MassOnly,
                    TesseractTrellisRankingMode::FutureDetcostRanked,
                    TesseractTrellisRankingMode::FutureActiveDetcostRanked}) {
    auto decoder = decoder_for_mode(dem, mode, 0.0, 65536);
    for (std::vector<uint64_t> syndrome : {std::vector<uint64_t>{}, {0}, {1}, {0, 1}}) {
      decoder.decode_shot(syndrome);
      EXPECT_FALSE(decoder.low_confidence_flag);
    }
  }
}

TEST(TesseractTrellisMultiObs64Modes, BeamEpsIsAcceptedForMultipleObservables) {
  auto decoder = decoder_for_mode(R"DEM(
    error(0.10) L0
    error(0.20) L1
  )DEM", TesseractTrellisRankingMode::MassOnly, 0.25, 1);
  decoder.decode_shot({});
  ASSERT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{0});
}

TEST(TesseractTrellisMultiObs64Modes, BeamWidthCountsDetectorStatesNotLogicalMasks) {
  auto decoder = decoder_for_mode(R"DEM(
    error(0.40) L0
    error(0.30) L1
    error(0.20) L2
  )DEM", TesseractTrellisRankingMode::MassOnly, 0.0, 1);
  decoder.decode_shot({});
  ASSERT_FALSE(decoder.low_confidence_flag);
  // There is only one detector state but eight possible logical masks. A
  // beam width of one must preserve the whole distribution for that state.
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{0});
}

TEST(TesseractTrellisMultiObs64Modes, RankedModePreservesObservable63) {
  auto decoder = decoder_for_mode(R"DEM(
    error(0.1) D0
    error(0.2) D0 L0 L63
    detector(0, 0, 0) D0
  )DEM", TesseractTrellisRankingMode::FutureDetcostRanked);
  EXPECT_EQ(decoder.decode({0}), (std::vector<int>{0, 63}));
  EXPECT_FALSE(decoder.low_confidence_flag);
}

TEST(TesseractTrellisMultiObs64Modes, DecodeShotsReturnsCompleteMasks) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(R"DEM(
    error(0.1) D0
    error(0.2) D0 L2 L11
    error(0.000001) L10
    detector(0, 0, 0) D0
  )DEM");
  config.ranking_mode = TesseractTrellisRankingMode::FutureActiveDetcostRanked;
  TesseractTrellisDecoder decoder(config);
  std::vector<stim::SparseShot> shots(2);
  shots[0].hits = {0};
  shots[1].hits = {};
  std::vector<std::vector<int>> predicted;
  decoder.decode_shots(shots, predicted);
  ASSERT_EQ(predicted.size(), 2u);
  EXPECT_EQ(predicted[0], (std::vector<int>{2, 11}));
  EXPECT_EQ(predicted[1], (std::vector<int>{}));
}

}  // namespace
}  // namespace tesseract_decoder
''')

    build = build_path.read_text()
    if 'name = "tesseract_trellis_multiobs64_modes_tests"' in build:
        raise RuntimeError("P07 test target already exists")
    build += r'''

cc_test(
    name = "tesseract_trellis_multiobs64_modes_tests",
    srcs = ["tesseract_trellis_multiobs64_modes.test.cc"],
    copts = OPT_COPTS,
    linkopts = OPT_LINKOPTS,
    deps = [
        ":libtesseract_trellis",
        "@gtest",
        "@stim",
    ],
)
'''
    build_path.write_text(build)

    report = {
        "phase": "P07",
        "kind": "complete-modern-multiobservable64-modes",
        "upstream_contract": "apply after P06 on 024db1d3b5b038f565c476dd1b51885271f7b0bf",
        "observable_range": "0..64",
        "multiobservable_semantics": "joint-MAP complete uint64_t logical mask",
        "beam_unit": "detector state; logical masks sharing a detector state do not consume beam slots",
        "ranking_modes": ["MassOnly", "FutureDetcostRanked", "FutureActiveDetcostRanked"],
        "beam_eps_supported": True,
        "observable_probability_multiobs": "NaN by design; no single scalar probability represents a complete mask",
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
