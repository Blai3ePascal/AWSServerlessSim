#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

ANCESTOR_SHA = "56996facf54c25e6c08fed19d8902f40e1971f55"


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
    test_path = root / "src" / "tesseract_trellis_multiobs_ref.test.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    cc = cc_path.read_text()

    ctor_old = """  num_detectors = config.dem.count_detectors();\n  num_observables = config.dem.count_observables();\n\n  all_possible_detectors = boost::dynamic_bitset<>(num_detectors);\n"""
    ctor_new = """  num_detectors = config.dem.count_detectors();\n  num_observables = config.dem.count_observables();\n  if (num_observables > 64) {\n    throw std::invalid_argument(\"tesseract_trellis supports at most 64 observables\");\n  }\n\n  all_possible_detectors = boost::dynamic_bitset<>(num_detectors);\n"""
    cc = replace_once(cc, ctor_old, ctor_new, "64-observable constructor bound")

    final_old = """    auto tr0 = std::chrono::high_resolution_clock::now();\n    for (const auto& item : beam_entries) {\n      if (!wide_state_zero(item.state_words)) {\n        continue;\n      }\n      if (item.obs_mask == 0) {\n        total_mass_obs0 += item.mass;\n      } else if (item.obs_mask == 1) {\n        total_mass_obs1 += item.mass;\n      }\n    }\n    if (total_mass_obs0 == 0.0 && total_mass_obs1 == 0.0) {\n      low_confidence_flag = true;\n      return;\n    }\n    predicted_obs_mask = total_mass_obs1 > total_mass_obs0 ? 1 : 0;\n    auto tr1 = std::chrono::high_resolution_clock::now();\n"""
    final_new = """    auto tr0 = std::chrono::high_resolution_clock::now();\n    double best_obs_mass = -1.0;\n    uint64_t best_obs_mask = 0;\n    bool found_valid_final_state = false;\n    for (const auto& item : beam_entries) {\n      if (!wide_state_zero(item.state_words)) {\n        continue;\n      }\n      found_valid_final_state = true;\n      if (item.obs_mask == 0) {\n        total_mass_obs0 += item.mass;\n      } else if (item.obs_mask == 1) {\n        total_mass_obs1 += item.mass;\n      }\n      if (item.mass > best_obs_mass ||\n          (item.mass == best_obs_mass && item.obs_mask < best_obs_mask)) {\n        best_obs_mass = item.mass;\n        best_obs_mask = item.obs_mask;\n      }\n    }\n    if (!found_valid_final_state) {\n      low_confidence_flag = true;\n      return;\n    }\n    predicted_obs_mask = best_obs_mask;\n    auto tr1 = std::chrono::high_resolution_clock::now();\n"""
    cc = replace_once(cc, final_old, final_new, "joint-mask final reconstruction")

    decode_old = """std::vector<int> TesseractTrellisDecoder::decode(const std::vector<uint64_t>& detections) {\n  decode_shot(detections);\n  return predicted_obs_mask ? std::vector<int>{0} : std::vector<int>{};\n}\n"""
    decode_new = """std::vector<int> TesseractTrellisDecoder::decode(const std::vector<uint64_t>& detections) {\n  decode_shot(detections);\n  if (low_confidence_flag) {\n    return {};\n  }\n  std::vector<int> result;\n  result.reserve(num_observables);\n  for (size_t obs = 0; obs < num_observables; ++obs) {\n    if ((predicted_obs_mask >> obs) & 1ULL) {\n      result.push_back((int)obs);\n    }\n  }\n  return result;\n}\n"""
    cc = replace_once(cc, decode_old, decode_new, "multi-observable decode projection")
    cc_path.write_text(cc)

    test_path.write_text(r'''// P05 public-lineage multi-observable reference tests.
#include "tesseract_trellis.h"

#include <gtest/gtest.h>
#include <stdexcept>
#include <vector>

#include "stim.h"

namespace {

TesseractTrellisDecoder decoder_for(const char* dem_text, size_t beam_width = 128) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(dem_text);
  config.beam_width = beam_width;
  return TesseractTrellisDecoder(config);
}

TEST(TesseractTrellisMultiObsRef, PreservesSingleObservableDecision) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L0
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1});
  std::vector<int> expected{0};
  EXPECT_EQ(decoder.decode({0}), expected);
}

TEST(TesseractTrellisMultiObsRef, PredictsJointTwoObservableMask) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{3});
  std::vector<int> expected{0, 1};
  EXPECT_EQ(decoder.decode({0}), expected);
}

TEST(TesseractTrellisMultiObsRef, PreservesBitSevenInEightObservableDem) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L0 L7
    error(0.000001) L6
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, (uint64_t{1} << 0) | (uint64_t{1} << 7));
}

TEST(TesseractTrellisMultiObsRef, PreservesBitElevenInTwelveObservableDem) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L2 L11
    error(0.000001) L10
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, (uint64_t{1} << 2) | (uint64_t{1} << 11));
}

TEST(TesseractTrellisMultiObsRef, AcceptsObservable63AndReturnsIt) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L0 L63
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, (uint64_t{1} << 0) | (uint64_t{1} << 63));
  std::vector<int> expected{0, 63};
  EXPECT_EQ(decoder.decode({0}), expected);
}

TEST(TesseractTrellisMultiObsRef, RejectsObservable64) {
  TesseractTrellisConfig config;
  config.dem = stim::DetectorErrorModel(R"DEM(
    error(0.2) D0 L64
    detector(0, 0, 0) D0
  )DEM");
  EXPECT_THROW(TesseractTrellisDecoder decoder(config), std::invalid_argument);
}

}  // namespace
''')

    build = build_path.read_text()
    marker = "name = \"tesseract_trellis_multiobs_ref_tests\""
    if marker in build:
        raise RuntimeError("P05 test target already exists")
    build += r'''

cc_test(
    name = "tesseract_trellis_multiobs_ref_tests",
    srcs = ["tesseract_trellis_multiobs_ref.test.cc"],
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
        "phase": "P05a",
        "kind": "public-lineage-multiobservable-reference",
        "ancestor_sha": ANCESTOR_SHA,
        "claims_private_equivalence": False,
        "changes": [
            "enforce num_observables <= 64",
            "select maximum-mass complete observable mask at valid final detector state",
            "project all set logical bits from predicted_obs_mask in decode()",
            "add 1/2/8/12/64 observable correctness tests",
        ],
        "benchmark_valid": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
