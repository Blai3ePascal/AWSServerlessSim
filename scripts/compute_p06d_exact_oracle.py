#!/usr/bin/env python3
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def exact_model_answers(model: dict, detectors: int) -> dict[int, dict]:
    faults = model["faults"]
    if len(faults) > 20:
        raise RuntimeError(
            f"{model['model_id']}: {len(faults)} faults is too large for the exact exhaustive oracle"
        )

    # Independent oracle: enumerate every Bernoulli assignment represented by the
    # generated DEM. We do not call either Tesseract implementation here.
    masses = [defaultdict(float) for _ in range(1 << detectors)]
    assignments = 1 << len(faults)
    for assignment in range(assignments):
        det_mask = 0
        obs_mask = 0
        probability = 1.0
        for k, fault in enumerate(faults):
            present = (assignment >> k) & 1
            p = float(fault["p"])
            if present:
                probability *= p
                det_mask ^= int(fault["det_mask"])
                obs_mask ^= int(fault["obs_mask"])
            else:
                probability *= 1.0 - p
        masses[det_mask][obs_mask] += probability

    answers = {}
    for syndrome in range(1 << detectors):
        distribution = masses[syndrome]
        conditioning_mass = sum(distribution.values())
        if conditioning_mass <= 0.0:
            answers[syndrome] = {
                "status": "UNREACHABLE",
                "predicted_obs_mask": 0,
                "low_confidence": 1,
                "conditioning_mass": 0.0,
                "best_joint_mass": 0.0,
                "distinct_logical_masks": 0,
            }
            continue

        # Same scientific decision rule being tested: joint MAP over the complete
        # logical mask. Exact equality is broken deterministically toward lower mask.
        best_mask = 0
        best_mass = -1.0
        for mask, mass in distribution.items():
            if mass > best_mass or (mass == best_mass and mask < best_mask):
                best_mask = mask
                best_mass = mass
        answers[syndrome] = {
            "status": "OK",
            "predicted_obs_mask": best_mask,
            "low_confidence": 0,
            "conditioning_mass": conditioning_mass,
            "best_joint_mass": best_mass,
            "distinct_logical_masks": len(distribution),
        }
    return answers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    metadata = json.loads(Path(args.metadata).read_text())
    detectors = int(metadata["detectors"])
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    model_summaries = []
    rows = []
    assignment_count = 0
    for model in metadata["models"]:
        answers = exact_model_answers(model, detectors)
        assignment_count += 1 << len(model["faults"])
        for syndrome, answer in sorted(answers.items()):
            rows.append({
                "case_id": f"{model['model_id']}_s{syndrome}",
                "status": answer["status"],
                "num_observables": int(model["num_observables"]),
                "predicted_obs_mask": answer["predicted_obs_mask"],
                "low_confidence": answer["low_confidence"],
                "conditioning_mass": f"{answer['conditioning_mass']:.17g}",
                "best_joint_mass": f"{answer['best_joint_mass']:.17g}",
                "distinct_logical_masks": answer["distinct_logical_masks"],
            })
        model_summaries.append({
            "model_id": model["model_id"],
            "num_observables": model["num_observables"],
            "num_faults": len(model["faults"]),
            "assignments_enumerated": 1 << len(model["faults"]),
        })

    fields = [
        "case_id",
        "status",
        "num_observables",
        "predicted_obs_mask",
        "low_confidence",
        "conditioning_mass",
        "best_joint_mass",
        "distinct_logical_masks",
    ]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    expected_cases = int(metadata["total_cases"])
    if len(rows) != expected_cases:
        raise RuntimeError(f"oracle produced {len(rows)} rows, expected {expected_cases}")
    unreachable = sum(row["status"] != "OK" for row in rows)
    summary = {
        "phase": "P06d",
        "kind": "independent-exhaustive-joint-map-oracle",
        "input_phase": metadata.get("phase"),
        "models": len(metadata["models"]),
        "cases": len(rows),
        "assignments_enumerated_total": assignment_count,
        "unreachable_cases": unreachable,
        "decision_rule": "joint MAP over complete observable mask; exact ties choose lower mask",
        "uses_tesseract_code": False,
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
        "model_summaries": model_summaries,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "models": len(metadata["models"]),
        "cases": len(rows),
        "assignments": assignment_count,
        "unreachable": unreachable,
    }, sort_keys=True))
    return 0 if unreachable == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
