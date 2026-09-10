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
    test_path = root / "src" / "tesseract_trellis_multiobs_ref.test.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    text = test_path.read_text()
    text = replace_once(
        text,
        '#include <stdexcept>\n#include <vector>\n',
        '#include <cmath>\n#include <map>\n#include <stdexcept>\n#include <vector>\n',
        "extra test includes",
    )

    marker = "\n}  // namespace\n"
    extra = r'''

struct ExactFault {
  double p;
  uint64_t detector_mask;
  uint64_t observable_mask;
};

uint64_t exact_joint_map(const std::vector<ExactFault>& faults, uint64_t target_detector_mask) {
  if (faults.size() >= 63) {
    throw std::invalid_argument("exact test oracle is only for tiny test cases");
  }
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

std::vector<uint64_t> detections_from_mask(uint64_t detector_mask) {
  std::vector<uint64_t> detections;
  for (uint64_t d = 0; d < 64; ++d) {
    if ((detector_mask >> d) & 1ULL) {
      detections.push_back(d);
    }
  }
  return detections;
}

TEST(TesseractTrellisMultiObsRef, LogicalXorCanCancelARepeatedObservable) {
  auto decoder = decoder_for(R"DEM(
    error(0.9) L3
    error(0.9) L3
  )DEM");
  decoder.decode_shot({});
  EXPECT_FALSE(decoder.low_confidence_flag);
  // Most probability is both faults happening. L3 XOR L3 = no logical flip.
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{0});
}

TEST(TesseractTrellisMultiObsRef, CompetingLogicalMasksForSameSyndromePickHigherJointMass) {
  auto decoder = decoder_for(R"DEM(
    error(0.25) D0 L1
    error(0.10) D0 L2
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1} << 1);
}

TEST(TesseractTrellisMultiObsRef, JointMapIsNotTheSameAsDecodingEachLogicalBitSeparately) {
  auto decoder = decoder_for(R"DEM(
    error(0.35) D0
    error(0.38) D0 L0
    error(0.35) D0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  // Conditioned on D0=1 the joint masses are approximately:
  // mask 00 = 0.2883, mask 01 = 0.3282, mask 10 = 0.2883, mask 11 = 0.0952.
  // So the joint MAP is L0. But each bit marginal is below 0.5, which would
  // incorrectly give mask 00 if we decoded the bits independently.
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1});
}

TEST(TesseractTrellisMultiObsRef, EqualMassTieBreakIsDeterministicAndUsesLowerMask) {
  auto decoder = decoder_for(R"DEM(
    error(0.2) D0 L0
    error(0.2) D0 L1
    detector(0, 0, 0) D0
  )DEM");
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1});
}

TEST(TesseractTrellisMultiObsRef, LogicalOnlyFaultWorksWithoutAnyDetector) {
  auto decoder = decoder_for(R"DEM(
    error(0.8) L5
  )DEM");
  decoder.decode_shot({});
  EXPECT_FALSE(decoder.low_confidence_flag);
  EXPECT_EQ(decoder.predicted_obs_mask, uint64_t{1} << 5);
}

TEST(TesseractTrellisMultiObsRef, MatchesTinyExactEnumeratorForAllTwoDetectorSyndromes) {
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
  )DEM", 1024);

  for (uint64_t syndrome = 0; syndrome < 4; ++syndrome) {
    const auto detections = detections_from_mask(syndrome);
    decoder.decode_shot(detections);
    ASSERT_FALSE(decoder.low_confidence_flag) << "syndrome=" << syndrome;
    EXPECT_EQ(decoder.predicted_obs_mask, exact_joint_map(faults, syndrome))
        << "syndrome=" << syndrome;
  }
}
'''
    text = replace_once(text, marker, extra + marker, "append P05b edge tests")
    test_path.write_text(text)

    report = {
        "phase": "P05b",
        "kind": "adversarial-correctness-tests",
        "claims_private_equivalence": False,
        "tests_added": [
            "observable XOR cancellation",
            "competing masks conditioned on one syndrome",
            "joint-MAP differs from independent-bit decoding",
            "deterministic equal-mass tie break",
            "logical-only fault without detectors",
            "exact exhaustive oracle over all syndromes of a tiny two-detector model",
        ],
        "benchmark_valid": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
