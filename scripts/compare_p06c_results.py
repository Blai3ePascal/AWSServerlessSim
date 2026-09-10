#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def read_tsv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = {}
        for row in reader:
            case_id = row["case_id"]
            if case_id in rows:
                raise RuntimeError(f"duplicate case_id {case_id} in {path}")
            rows[case_id] = row
        return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--json-report", required=True)
    parser.add_argument("--markdown-report", required=True)
    parser.add_argument("--mismatches-tsv", required=True)
    args = parser.parse_args()

    ref_path = Path(args.reference)
    cand_path = Path(args.candidate)
    metadata = json.loads(Path(args.metadata).read_text())
    ref = read_tsv(ref_path)
    cand = read_tsv(cand_path)

    missing_in_candidate = sorted(set(ref) - set(cand))
    extra_in_candidate = sorted(set(cand) - set(ref))
    mismatches = []
    matched = 0
    by_obs_total = Counter()
    by_obs_mismatch = Counter()
    error_cases = []

    for case_id in sorted(set(ref) & set(cand)):
        r = ref[case_id]
        c = cand[case_id]
        if r["status"] != "OK" or c["status"] != "OK":
            error_cases.append({"case_id": case_id, "reference": r, "candidate": c})

        obs_key = r.get("num_observables", "unknown")
        by_obs_total[obs_key] += 1
        fields = ["status", "num_observables", "predicted_obs_mask", "low_confidence"]
        differences = {field: {"reference": r[field], "candidate": c[field]}
                       for field in fields if r[field] != c[field]}
        if differences:
            mismatches.append({"case_id": case_id, "differences": differences})
            by_obs_mismatch[obs_key] += 1
        else:
            matched += 1

    expected_cases = metadata["total_cases"]
    shape_ok = (
        len(ref) == expected_cases
        and len(cand) == expected_cases
        and not missing_in_candidate
        and not extra_in_candidate
    )
    success = shape_ok and not mismatches and not error_cases

    report = {
        "phase": "P06c",
        "reference": str(ref_path),
        "candidate": str(cand_path),
        "expected_cases": expected_cases,
        "reference_cases": len(ref),
        "candidate_cases": len(cand),
        "matched_cases": matched,
        "mismatch_count": len(mismatches),
        "error_case_count": len(error_cases),
        "missing_in_candidate": missing_in_candidate,
        "extra_in_candidate": extra_in_candidate,
        "cases_by_observable_count": dict(sorted(by_obs_total.items())),
        "mismatches_by_observable_count": dict(sorted(by_obs_mismatch.items())),
        "first_mismatches": mismatches[:50],
        "first_error_cases": error_cases[:50],
        "success": success,
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
    }
    Path(args.json_report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    mismatch_path = Path(args.mismatches_tsv)
    with mismatch_path.open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["case_id", "field", "reference", "candidate"])
        for item in mismatches:
            for field, values in item["differences"].items():
                writer.writerow([item["case_id"], field, values["reference"], values["candidate"]])

    md = []
    md.append("# P06c — resultado diferencial P05 vs P06")
    md.append("")
    if success:
        md.append("## Resultado corto: TODO VERDE")
        md.append("")
        md.append(
            f"Se compararon **{expected_cases} casos** y P05 y P06 dieron exactamente la misma "
            "máscara lógica y el mismo estado `low_confidence` en todos ellos."
        )
    else:
        md.append("## Resultado corto: HAY DIFERENCIAS")
        md.append("")
        md.append(
            f"Hay **{len(mismatches)} discrepancias**, **{len(error_cases)} casos con error**, "
            f"{len(missing_in_candidate)} casos que faltan y {len(extra_in_candidate)} casos extra."
        )
        md.append("El workflow debe quedar rojo hasta entenderlas.")
    md.append("")
    md.append("## Qué hemos comparado")
    md.append("")
    md.append("Por cada caso hemos exigido igualdad exacta de:")
    md.append("")
    md.append("- estado de ejecución (`OK` o error);")
    md.append("- número de observables que ve el decoder;")
    md.append("- `predicted_obs_mask`, es decir, la combinación lógica completa elegida;")
    md.append("- `low_confidence`.")
    md.append("")
    md.append("No estamos comparando tiempos porque GitHub Actions no es nuestro benchmark científico.")
    md.append("")
    md.append("## Reparto de casos")
    md.append("")
    for obs in sorted(by_obs_total, key=lambda x: int(x) if x.isdigit() else 999):
        md.append(
            f"- {obs} observables: {by_obs_total[obs]} casos, "
            f"{by_obs_mismatch.get(obs, 0)} discrepancias."
        )
    md.append("")
    md.append("## Qué significa si está verde")
    md.append("")
    md.append(
        "Significa que, dentro de este corpus reproducible y con poda deliberadamente evitada, "
        "nuestro camino moderno multiobservable P06 reproduce la referencia pública P05. "
        "No significa que sea el código privado de Google ni que tenga su rendimiento."
    )
    md.append("")
    md.append("## Qué significa si está rojo")
    md.append("")
    md.append(
        "Que hemos encontrado un caso concreto donde P05 y P06 no hacen lo mismo. No se tapa: "
        "el `case_id`, el DEM, la semilla y los resultados quedan guardados para poder reproducirlo."
    )
    Path(args.markdown_report).write_text("\n".join(md) + "\n")

    print(json.dumps({
        "expected_cases": expected_cases,
        "matched_cases": matched,
        "mismatches": len(mismatches),
        "errors": len(error_cases),
        "success": success,
    }, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
