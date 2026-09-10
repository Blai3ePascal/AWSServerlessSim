#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

MODERN_SHA = "024db1d3b5b038f565c476dd1b51885271f7b0bf"


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
    test_path = root / "src" / "tesseract_trellis_modern_multiobs.test.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    cc = cc_path.read_text()
    cc = replace_once(cc, '#include <limits>\n#include <numeric>\n#include <queue>\n',
                      '#include <limits>\n#include <map>\n#include <numeric>\n#include <queue>\n',
                      "add map include")

    insertion_marker = """std::unique_ptr<TesseractTrellisWideKernelBase> build_compiled_wide_kernel(\n"""
    generic_kernel = r'''
struct GenericMultiObsEntry {
  std::vector<uint64_t> state_words;
  uint64_t obs_mask = 0;
  double mass = 0.0;
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

bool generic_retiring_detectors_match(
    const std::vector<uint64_t>& state_words,
    const TesseractTrellisWideLayerTemplate& layer,
    const std::vector<uint64_t>& actual_detector_words) {
  std::vector<uint8_t> survives(layer.current_active_detectors.size(), 0);
  for (uint32_t local : layer.surviving_local_indices) {
    survives[(size_t)local] = 1;
  }
  for (size_t local = 0; local < layer.current_active_detectors.size(); ++local) {
    if (survives[local]) {
      continue;
    }
    const size_t detector = (size_t)layer.current_active_detectors[local];
    const bool actual =
        (actual_detector_words[detector_word_index(detector)] & detector_word_mask(detector)) != 0;
    if (generic_state_bit(state_words, local) != actual) {
      return false;
    }
  }
  return true;
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
                                        size_t beam_width) {
  if (entries->empty()) {
    return 0;
  }

  struct StateMass {
    std::vector<uint64_t> state_words;
    double mass = 0.0;
  };

  std::vector<StateMass> states;
  for (const auto& entry : *entries) {
    if (states.empty() || states.back().state_words != entry.state_words) {
      states.push_back({entry.state_words, entry.mass});
    } else {
      states.back().mass += entry.mass;
    }
  }

  if (states.size() <= beam_width) {
    return states.size();
  }

  std::nth_element(states.begin(), states.begin() + beam_width, states.end(),
                   [](const StateMass& a, const StateMass& b) {
                     if (a.mass != b.mass) {
                       return a.mass > b.mass;
                     }
                     return generic_state_less(a.state_words, b.state_words);
                   });
  states.resize(beam_width);
  std::sort(states.begin(), states.end(), [](const StateMass& a, const StateMass& b) {
    return generic_state_less(a.state_words, b.state_words);
  });

  auto selected = [&states](const std::vector<uint64_t>& state_words) {
    auto it = std::lower_bound(
        states.begin(), states.end(), state_words,
        [](const StateMass& a, const std::vector<uint64_t>& b) {
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
    std::vector<GenericMultiObsEntry> beam_entries{{{}, 0, 1.0}};
    std::vector<GenericMultiObsEntry> next_entries;
    decoder->max_beam_size_seen = 1;

    for (const auto& layer : layers) {
      next_entries.clear();
      next_entries.reserve(beam_entries.size() * 2);
      for (const auto& item : beam_entries) {
        ++decoder->num_states_expanded;

        if (layer.q != 0.0 &&
            generic_retiring_detectors_match(item.state_words, layer, actual_detector_words)) {
          next_entries.push_back(
              {generic_project_state(item.state_words, layer.surviving_local_indices),
               item.obs_mask, item.mass * layer.q});
        }

        if (layer.p != 0.0) {
          std::vector<uint64_t> toggled = item.state_words;
          for (uint32_t local : layer.detcost_transition.fault_local_indices) {
            generic_toggle_bit(&toggled, (size_t)local);
          }
          if (generic_retiring_detectors_match(toggled, layer, actual_detector_words)) {
            next_entries.push_back(
                {generic_project_state(toggled, layer.surviving_local_indices),
                 item.obs_mask ^ layer.obs_mask, item.mass * layer.p});
          }
        }
      }

      beam_entries.swap(next_entries);
      merge_generic_entries(&beam_entries);
      const size_t kept_states =
          keep_top_generic_detector_states(&beam_entries, decoder->config.beam_width);
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
    cc = replace_once(cc, insertion_marker, generic_kernel + insertion_marker,
                      "insert generic multi-observable kernel")

    ctor_guard_old = '''  num_observables = config.dem.count_observables();
  if (num_observables > 1) {
    throw std::invalid_argument("tesseract_trellis currently supports at most one observable");
  }
'''
    ctor_guard_new = '''  num_observables = config.dem.count_observables();
  if (num_observables > 64) {
    throw std::invalid_argument("tesseract_trellis supports at most 64 observables");
  }
  if (num_observables > 1 && config.ranking_mode != TesseractTrellisRankingMode::MassOnly) {
    throw std::invalid_argument("experimental multi-observable path currently supports MassOnly ranking");
  }
  if (num_observables > 1 && config.beam_eps != 0.0) {
    throw std::invalid_argument("experimental multi-observable path currently requires beam_eps=0");
  }
'''
    cc = replace_once(cc, ctor_guard_old, ctor_guard_new, "modern constructor observable guard")

    kernel_build_old = '''  prepare_projected_fault_masks(&wide_layer_templates);
  wide_kernel =
      build_compiled_wide_kernel(wide_layer_templates, wide_frontier_width, initial_future_detcost);
  wide_layer_templates.clear();
'''
    kernel_build_new = '''  prepare_projected_fault_masks(&wide_layer_templates);
  if (num_observables <= 1) {
    wide_kernel = build_compiled_wide_kernel(wide_layer_templates, wide_frontier_width,
                                             initial_future_detcost);
  } else {
    wide_kernel = std::make_unique<GenericMultiObsKernel>(wide_layer_templates, wide_frontier_width);
  }
  wide_layer_templates.clear();
'''
    cc = replace_once(cc, kernel_build_old, kernel_build_new, "dispatch modern kernel by observables")

    prob_old = '''double TesseractTrellisDecoder::observable_probability() const {
  const double total_mass = total_mass_obs0 + total_mass_obs1;
'''
    prob_new = '''double TesseractTrellisDecoder::observable_probability() const {
  if (num_observables > 1) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double total_mass = total_mass_obs0 + total_mass_obs1;
'''
    cc = replace_once(cc, prob_old, prob_new, "multi-observable probability is intentionally undefined")

    decode_old = '''std::vector<int> TesseractTrellisDecoder::decode(const std::vector<uint64_t>& detections) {
  decode_shot(detections);
  return predicted_obs_mask ? std::vector<int>{0} : std::vector<int>{};
}
'''
    decode_new = '''std::vector<int> TesseractTrellisDecoder::decode(const std::vector<uint64_t>& detections) {
  decode_shot(detections);
  if (low_confidence_flag) {
    return {};
  }
  std::vector<int> result;
  for (size_t obs = 0; obs < num_observables; ++obs) {
    if ((predicted_obs_mask >> obs) & 1ULL) {
      result.push_back((int)obs);
    }
  }
  return result;
}
'''
    cc = replace_once(cc, decode_old, decode_new, "project modern predicted joint mask")
    cc_path.write_text(cc)

    test_path.write_text(r'''// P06 modern multi-observable correctness tests.
#include "tesseract_trellis.h"

#include <gtest/gtest.h>
#include <cmath>
#include <map>
#include <stdexcept>
#include <vector>

#include "stim.h"

namespace tesseract_decoder {
namespace {

TesseractTrellisDecoder decoder_for(const char* dem_text, size_t beam_width = 1024) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(dem_text);
  config.beam_width = beam_width;
  config.ranking_mode = TesseractTrellisRankingMode::MassOnly;
  return TesseractTrellisDecoder(config);
}

struct ExactFault {
  double p;
  uint64_t detector_mask;
  uint64_t observable_mask;
};

uint64_t exact_joint_map(const std::vector<ExactFault>& faults, uint64_t target_detector_mask) {
  std::map<uint64_t, double> masses;
  const uint64_t assignments = uint64_t{1} << faults.size();
  for (uint64_t assignment = 0; assignment < assignments; ++assignment) {
    uint64_t detector_mask = 0;
    uint64_t observable_mask = 0;
    double probability = 1.0;
    for (size_t k = 0; k < faults.size(); ++k) {
      const bool present = (assignment >> k) & 1ULL;
      probability *= present ? faults[k].p : (1.0 - faults[k].p);
      if (present) {
        detector_mask ^= faults[k].detector_mask;
        observable_mask ^= faults[k].observable_mask;
      }
    }
    if (detector_mask == target_detector_mask) {
      masses[observable_mask] += probability;
    }
  }
  double best_mass = -1.0;
  uint64_t best_mask = 0;
  for (const auto& [mask, mass] : masses) {
    if (mass > best_mass || (mass == best_mass && mask < best_mask)) {
      best_mass = mass;
      best_mask = mask;
    }
  }
  return best_mask;
}

std::vector<uint64_t> detections_from_mask(uint64_t mask) {
  std::vector<uint64_t> result;
  for (uint64_t d = 0; d < 64; ++d) {
    if ((mask >> d) & 1ULL) result.push_back(d);
  }
  return result;
}

TEST(TesseractTrellisModernMultiObs, PreservesJointTwoObservableMask) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  ASSERT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{3});
  EXPECT_EQ(decoder.decode({0}), (std::vector<int>{0, 1}));
  EXPECT_TRUE(std::isnan(decoder.observable_probability()));
}

TEST(TesseractTrellisModernMultiObs, XorCancellationWorks) {
  auto decoder = decoder_for(R"DEM(
    error(0.9) L3
    error(0.9) L3
  )DEM");
  decoder.decode_shot({});
  ASSERT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{0});
}

TEST(TesseractTrellisModernMultiObs, JointMapDiffersFromIndependentBits) {
  auto decoder = decoder_for(R"DEM(
    error(0.35) D0
    error(0.38) D0 L0
    error(0.35) D0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  ASSERT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1});
}

TEST(TesseractTrellisModernMultiObs, AcceptsObservable63) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L0 L63
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  ASSERT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, (uint64_t{1} << 0) | (uint64_t{1} << 63));
}

TEST(TesseractTrellisModernMultiObs, RejectsObservable64) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(R"DEM(
    error(0.2) D0 L64
    detector(0, 0, 0) D0
  )DEM");
  EXPECT_THROW(TesseractTrellisDecoder decoder(config), std::invalid_argument);
}

TEST(TesseractTrellisModernMultiObs, RejectsUnsupportedExperimentalRankingForNow) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(R"DEM(
    error(0.2) D0 L0 L1
    detector(0, 0, 0) D0
  )DEM");
  config.ranking_mode = TesseractTrellisRankingMode::FutureDetcostRanked;
  EXPECT_THROW(TesseractTrellisDecoder decoder(config), std::invalid_argument);
}

TEST(TesseractTrellisModernMultiObs, MatchesExactEnumeratorForAllTinySyndromes) {
  const std::vector<ExactFault> faults{
      {0.13, 0b01, 0b001},
      {0.21, 0b10, 0b010},
      {0.17, 0b11, 0b011},
      {0.09, 0b01, 0b100},
      {0.12, 0b10, 0b101},
  };
  auto decoder = decoder_for(R"DEM(
    error(0.13) D0 L0
    error(0.21) D1 L1
    error(0.17) D0 D1 L0 L1
    error(0.09) D0 L2
    error(0.12) D1 L0 L2
    detector(0, 0, 0) D0
    detector(1, 0, 0) D1
  )DEM");

  for (uint64_t syndrome = 0; syndrome < 4; ++syndrome) {
    decoder.decode_shot(detections_from_mask(syndrome));
    ASSERT_FALSE(decoder.low_confidence_flag) << "syndrome=" << syndrome;
    EXPECT_EQ(decoder.predicted_obs_mask, exact_joint_map(faults, syndrome))
        << "syndrome=" << syndrome;
  }
}

}  // namespace
}  // namespace tesseract_decoder
''')

    build = build_path.read_text()
    if 'name = "tesseract_trellis_modern_multiobs_tests"' in build:
        raise RuntimeError("P06 test target already exists")
    build += r'''

cc_test(
    name = "tesseract_trellis_modern_multiobs_tests",
    srcs = ["tesseract_trellis_modern_multiobs.test.cc"],
    copts = OPT_COPTS,
    linkopts = OPT_LINKOPTS,
    deps = [
        ":libtesseract_trellis",
        "@gtest",
        "@gtest//:gtest_main",
        "@stim//:stim_lib",
    ],
)
'''
    build_path.write_text(build)

    report = {
        "phase": "P06a",
        "kind": "modern-separate-multiobservable-correctness-kernel",
        "modern_sha": MODERN_SHA,
        "claims_private_equivalence": False,
        "single_observable_fast_path_replaced": False,
        "multiobs_current_limits": {
            "ranking_mode": "MassOnly",
            "beam_eps": 0.0,
            "max_observables": 64,
        },
        "benchmark_valid": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
