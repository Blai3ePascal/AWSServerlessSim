#!/usr/bin/env python3
"""Append P07b tests comparing the multi-observable path to the original 1-observable kernel.

The two DEMs are detector-equivalent; the multi-observable DEM only adds an
ultra-low-probability logical-only L1 sentinel.  This forces the new 2..64 path
while keeping the detector-state ranking problem effectively identical, so we
can exercise beam_width, beam_eps and all ranking modes against the original
compiled kernel.
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
    test_path = root / "src" / "tesseract_trellis_multiobs64_modes.test.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    text = test_path.read_text()
    marker = """}  // namespace\n}  // namespace tesseract_decoder\n"""
    extra = r'''
TEST(TesseractTrellisMultiObs64Modes, PruningAndRankingMatchOriginalDetectorStateKernel) {
  constexpr const char* one_observable_dem = R"DEM(
    error(0.11) D0
    error(0.17) D1 L0
    error(0.07) D0 D1 L0
    error(0.05) D0
    detector(0, 0, 0) D0
    detector(1, 0, 0) D1
  )DEM";
  constexpr const char* two_observable_dem = R"DEM(
    error(0.11) D0
    error(0.17) D1 L0
    error(0.07) D0 D1 L0
    error(0.05) D0
    error(0.000000000001) L1
    detector(0, 0, 0) D0
    detector(1, 0, 0) D1
  )DEM";

  const std::vector<std::vector<uint64_t>> syndromes{{}, {0}, {1}, {0, 1}};
  for (auto mode : {TesseractTrellisRankingMode::MassOnly,
                    TesseractTrellisRankingMode::FutureDetcostRanked,
                    TesseractTrellisRankingMode::FutureActiveDetcostRanked}) {
    for (double beam_eps : {0.0, 0.20}) {
      for (size_t beam_width : {size_t{1}, size_t{2}}) {
        auto original = decoder_for_mode(one_observable_dem, mode, beam_eps, beam_width);
        auto extended = decoder_for_mode(two_observable_dem, mode, beam_eps, beam_width);
        ASSERT_EQ(original.num_observables, 1u);
        ASSERT_EQ(extended.num_observables, 2u);
        for (const auto& syndrome : syndromes) {
          original.decode_shot(syndrome);
          extended.decode_shot(syndrome);
          EXPECT_EQ(extended.low_confidence_flag, original.low_confidence_flag)
              << "beam_width=" << beam_width << " beam_eps=" << beam_eps;
          if (!original.low_confidence_flag) {
            EXPECT_EQ(extended.predicted_obs_mask & uint64_t{1}, original.predicted_obs_mask)
                << "beam_width=" << beam_width << " beam_eps=" << beam_eps;
            EXPECT_EQ(extended.predicted_obs_mask & ~uint64_t{1}, uint64_t{0})
                << "unexpected sentinel observable; beam_width=" << beam_width
                << " beam_eps=" << beam_eps;
          }
        }
      }
    }
  }
}

'''
    text = replace_once(text, marker, extra + marker, "append P07b mode-equivalence test")
    test_path.write_text(text)

    report = {
        "phase": "P07b",
        "kind": "multiobservable-pruning-ranking-equivalence",
        "kernel_changes": False,
        "comparison": "original compiled 1-observable path vs forced 2-observable path",
        "ranking_modes": ["MassOnly", "FutureDetcostRanked", "FutureActiveDetcostRanked"],
        "beam_widths": [1, 2],
        "beam_eps": [0.0, 0.2],
        "syndromes": 4,
        "comparisons": 48,
        "benchmark_valid": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
