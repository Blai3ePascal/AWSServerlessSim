#!/usr/bin/env python3
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
    test_path = root / "src" / "tesseract_trellis_modern_multiobs.test.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    text = test_path.read_text()
    marker = """}  // namespace\n}  // namespace tesseract_decoder\n"""
    extra_tests = r'''
TEST(TesseractTrellisModernMultiObs, EqualMassTieBreakUsesLowerLogicalMask) {
  auto decoder = decoder_for(R"DEM(
    error(0.5) D0 L0
    error(0.5) D0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  ASSERT_FALSE(decoder.low_confidence_flag);
  // Given D0, masks 1 and 2 have exactly the same mass. Our deterministic
  // contract chooses the numerically lower complete logical mask.
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1});
}

TEST(TesseractTrellisModernMultiObs, AggregatesMultipleExplanationsBeforeChoosingMask) {
  auto decoder = decoder_for(R"DEM(
    error(0.2) D0 L0
    error(0.2) D0 L0
    error(0.3) D0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  ASSERT_FALSE(decoder.low_confidence_flag);
  // The two indistinguishable L0 mechanisms together contribute 0.224 to
  // the D0/L0 explanation, while the L1 explanation contributes 0.204.
  // This catches implementations that choose one path instead of summing
  // probability mass for the complete logical mask.
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1});
}

TEST(TesseractTrellisModernMultiObs, DecodeReturnsAllSetLogicalBitsInOrder) {
  auto decoder = decoder_for(R"DEM(
    error(0.1) D0
    error(0.2) D0 L2 L11
    error(0.000001) L10
    detector(0, 0, 0) D0
  )DEM");
  std::vector<int> expected{2, 11};
  EXPECT_EQ(decoder.decode({0}), expected);
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, (uint64_t{1} << 2) | (uint64_t{1} << 11));
}

TEST(TesseractTrellisModernMultiObs, DuplicateDetectorHitsCancelByParity) {
  auto decoder = decoder_for(R"DEM(
    error(0.2) D0 L0 L1
    detector(0, 0, 0) D0
  )DEM");
  const auto zero_syndrome = decoder.decode({});
  ASSERT_FALSE(decoder.low_confidence_flag);
  const auto duplicated_hit = decoder.decode({0, 0});
  ASSERT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(duplicated_hit, zero_syndrome);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{0});
}

TEST(TesseractTrellisModernMultiObs, InvalidDetectorStillSetsLowConfidence) {
  auto decoder = decoder_for(R"DEM(
    error(0.2) D0 L0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({7});
  EXPECT_TRUE(decoder.low_confidence_flag);
}

'''
    text = replace_once(text, marker, extra_tests + marker, "append P06b edge tests")
    test_path.write_text(text)

    report = {
        "phase": "P06b",
        "kind": "modern-multiobservable-edge-tests",
        "kernel_changes": False,
        "added_tests": [
            "equal-mass deterministic lower-mask tie break",
            "aggregate multiple explanations before joint-mask selection",
            "decode projects all set high logical bits in ascending order",
            "duplicate detector hits cancel by parity",
            "invalid detector still sets low confidence",
        ],
        "benchmark_valid": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
