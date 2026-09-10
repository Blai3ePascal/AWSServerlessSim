#!/usr/bin/env python3
import argparse
import json
import random
from pathlib import Path

MASTER_SEED = 20260910
OBS_COUNTS = [2, 8, 12, 32, 64]
REGIMES = [0.001, 0.01, 0.05, 0.15]
MODELS_PER_REGIME = 4
DETECTORS = 3
BEAM_WIDTH = 65536


def mask_targets(prefix: str, mask: int, width: int) -> list[str]:
    return [f"{prefix}{i}" for i in range(width) if (mask >> i) & 1]


def choose_obs_mask(rng: random.Random, n_obs: int, max_bits: int = 3) -> int:
    k = rng.randint(0, min(max_bits, n_obs))
    if k == 0:
        return 0
    bits = rng.sample(range(n_obs), k=k)
    mask = 0
    for bit in bits:
        mask ^= 1 << bit
    return mask


def generate_dem(rng: random.Random, n_obs: int, base_p: float) -> tuple[str, list[dict]]:
    faults: list[dict] = []

    # Basis faults guarantee every 3-detector syndrome has at least one explanation.
    for d in range(DETECTORS):
        p = min(0.30, base_p * (1.0 + 0.17 * (d + 1)))
        obs_mask = choose_obs_mask(rng, n_obs, 2)
        faults.append({"p": p, "det_mask": 1 << d, "obs_mask": obs_mask, "kind": "basis"})

    # Mixed detector/logical faults create competing explanations for the same syndrome.
    for _ in range(8):
        det_mask = rng.randint(1, (1 << DETECTORS) - 1)
        obs_mask = choose_obs_mask(rng, n_obs, 3)
        scale = rng.uniform(0.55, 1.85)
        p = min(0.35, max(1e-8, base_p * scale))
        faults.append({"p": p, "det_mask": det_mask, "obs_mask": obs_mask, "kind": "mixed"})

    # Logical-only faults exercise XOR/aggregation without changing the syndrome.
    for _ in range(2):
        obs_mask = choose_obs_mask(rng, n_obs, 2)
        if obs_mask == 0:
            obs_mask = 1 << rng.randrange(n_obs)
        p = min(0.25, max(1e-8, base_p * rng.uniform(0.4, 1.2)))
        faults.append({"p": p, "det_mask": 0, "obs_mask": obs_mask, "kind": "logical-only"})

    # Sentinel makes count_observables exactly n_obs while having negligible influence.
    faults.append({
        "p": 1e-12,
        "det_mask": 0,
        "obs_mask": 1 << (n_obs - 1),
        "kind": "observable-count-sentinel",
    })

    lines = []
    for fault in faults:
        targets = mask_targets("D", fault["det_mask"], DETECTORS)
        targets += mask_targets("L", fault["obs_mask"], n_obs)
        if not targets:
            raise RuntimeError("generated empty DEM error target list")
        lines.append(f"error({fault['p']:.17g}) " + " ".join(targets))
    for d in range(DETECTORS):
        lines.append(f"detector({d}, 0, 0) D{d}")
    return "\n".join(lines) + "\n", faults


def detections_for_syndrome(syndrome: int) -> str:
    hits = [str(d) for d in range(DETECTORS) if (syndrome >> d) & 1]
    return ",".join(hits) if hits else "-"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--metadata", required=True)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    dem_dir = out_dir / "dems"
    dem_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest)
    metadata_path = Path(args.metadata)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_lines = ["# case_id\tdem_path\tdetections_csv\tbeam_width"]
    models = []
    total_cases = 0

    for n_obs in OBS_COUNTS:
        for regime_index, base_p in enumerate(REGIMES):
            for model_index in range(MODELS_PER_REGIME):
                seed = MASTER_SEED + n_obs * 100000 + regime_index * 1000 + model_index
                rng = random.Random(seed)
                model_id = f"obs{n_obs:02d}_p{regime_index}_m{model_index}"
                dem_text, faults = generate_dem(rng, n_obs, base_p)
                dem_path = dem_dir / f"{model_id}.dem"
                dem_path.write_text(dem_text)

                models.append({
                    "model_id": model_id,
                    "seed": seed,
                    "num_observables": n_obs,
                    "base_probability": base_p,
                    "dem_path": str(dem_path),
                    "faults": faults,
                })

                for syndrome in range(1 << DETECTORS):
                    case_id = f"{model_id}_s{syndrome}"
                    manifest_lines.append(
                        f"{case_id}\t{dem_path}\t{detections_for_syndrome(syndrome)}\t{BEAM_WIDTH}"
                    )
                    total_cases += 1

    manifest_path.write_text("\n".join(manifest_lines) + "\n")
    metadata = {
        "phase": "P06c",
        "master_seed": MASTER_SEED,
        "observable_counts": OBS_COUNTS,
        "probability_regimes": REGIMES,
        "models_per_regime": MODELS_PER_REGIME,
        "detectors": DETECTORS,
        "syndromes_per_model": 1 << DETECTORS,
        "beam_width": BEAM_WIDTH,
        "num_models": len(models),
        "total_cases": total_cases,
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
        "models": models,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(f"generated {len(models)} DEM models and {total_cases} differential cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
