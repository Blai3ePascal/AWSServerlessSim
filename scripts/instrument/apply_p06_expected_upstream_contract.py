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
    test_path = root / "src" / "tesseract_trellis.test.cc"
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    text = test_path.read_text()
    old = r'''TEST(TesseractTrellisDecoderTest, RejectsMoreThanOneObservable) {
  stim::DetectorErrorModel dem(R"DEM(
    error(0.1) D0 L0
    error(0.1) D0 L1
    detector(0, 0, 0) D0
  )DEM");

  TesseractTrellisConfig config;
  config.dem = dem;

  try {
    TesseractTrellisDecoder decoder(config);
    FAIL() << "Expected TesseractTrellisDecoder construction to fail.";
  } catch (const std::invalid_argument& err) {
    EXPECT_NE(std::string(err.what()).find("supports at most one observable"), std::string::npos);
  }
}
'''
    new = r'''TEST(TesseractTrellisDecoderTest, AllowsMultipleObservablesInExperimentalMassOnlyPath) {
  // This is the one upstream expectation that P06 intentionally changes.
  // The old test asserted that construction must fail for L0+L1. P06 exists
  // specifically to remove that restriction while preserving the rest of
  // the upstream regression suite.
  stim::DetectorErrorModel dem(R"DEM(
    error(0.1) D0 L0
    error(0.1) D0 L1
    detector(0, 0, 0) D0
  )DEM");

  TesseractTrellisConfig config;
  config.dem = dem;
  config.ranking_mode = TesseractTrellisRankingMode::MassOnly;

  TesseractTrellisDecoder decoder(config);
  decoder.decode_shot({0});
  EXPECT_FALSE(decoder.low_confidence_flag);
}
'''
    text = replace_once(text, old, new, "replace deliberate one-observable restriction test")
    test_path.write_text(text)

    report = {
        "phase": "P06a",
        "kind": "expected-upstream-contract-change",
        "changed_test": "RejectsMoreThanOneObservable",
        "new_test": "AllowsMultipleObservablesInExperimentalMassOnlyPath",
        "reason": "P06 deliberately removes the one-observable constructor restriction",
        "other_upstream_test_expectations_changed": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
