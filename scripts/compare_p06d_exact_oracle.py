#!/usr/bin/env python3
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

FIELDS = ["status", "num_observables", "predicted_obs_mask", "low_confidence"]


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


def differences(expected: dict[str, str], actual: dict[str, str]) -> dict:
    return {
        field: {"expected": expected[field], "actual": actual[field]}
        for field in FIELDS
        if expected[field] != actual[field]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle", required=True)
    parser.add_argument("--p05", required=True)
    parser.add_argument("--p06", required=True)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--json-report", required=True)
    parser.add_argument("--markdown-report", required=True)
    parser.add_argument("--mismatches-tsv", required=True)
    args = parser.parse_args()

    oracle = read_tsv(Path(args.oracle))
    p05 = read_tsv(Path(args.p05))
    p06 = read_tsv(Path(args.p06))
    metadata = json.loads(Path(args.metadata).read_text())
    expected_cases = int(metadata["total_cases"])

    all_ids = set(oracle)
    shape = {
        "oracle": len(oracle),
        "p05": len(p05),
        "p06": len(p06),
        "missing_p05": sorted(all_ids - set(p05)),
        "extra_p05": sorted(set(p05) - all_ids),
        "missing_p06": sorted(all_ids - set(p06)),
        "extra_p06": sorted(set(p06) - all_ids),
    }

    p05_mismatches = []
    p06_mismatches = []
    p05_matched = 0
    p06_matched = 0
    by_obs_total = Counter()
    by_obs_p05_bad = Counter()
    by_obs_p06_bad = Counter()

    for case_id in sorted(all_ids & set(p05) & set(p06)):
        expected = oracle[case_id]
        obs = expected["num_observables"]
        by_obs_total[obs] += 1

        d05 = differences(expected, p05[case_id])
        if d05:
            p05_mismatches.append({"case_id": case_id, "differences": d05})
            by_obs_p05_bad[obs] += 1
        else:
            p05_matched += 1

        d06 = differences(expected, p06[case_id])
        if d06:
            p06_mismatches.append({"case_id": case_id, "differences": d06})
            by_obs_p06_bad[obs] += 1
        else:
            p06_matched += 1

    shape_ok = (
        len(oracle) == expected_cases
        and len(p05) == expected_cases
        and len(p06) == expected_cases
        and not shape["missing_p05"]
        and not shape["extra_p05"]
        and not shape["missing_p06"]
        and not shape["extra_p06"]
    )
    success = shape_ok and not p05_mismatches and not p06_mismatches

    report = {
        "phase": "P06d",
        "kind": "independent-exact-oracle-validation",
        "expected_cases": expected_cases,
        "shape": shape,
        "p05_matched_exact": p05_matched,
        "p06_matched_exact": p06_matched,
        "p05_mismatch_count": len(p05_mismatches),
        "p06_mismatch_count": len(p06_mismatches),
        "cases_by_observable_count": dict(sorted(by_obs_total.items(), key=lambda x: int(x[0]))),
        "p05_mismatches_by_observable_count": dict(sorted(by_obs_p05_bad.items(), key=lambda x: int(x[0]))),
        "p06_mismatches_by_observable_count": dict(sorted(by_obs_p06_bad.items(), key=lambda x: int(x[0]))),
        "first_p05_mismatches": p05_mismatches[:50],
        "first_p06_mismatches": p06_mismatches[:50],
        "success": success,
        "claims_private_equivalence": False,
        "benchmark_valid": False,
        "timing_metrics_interpretable": False,
    }
    Path(args.json_report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    with Path(args.mismatches_tsv).open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["implementation", "case_id", "field", "expected", "actual"])
        for impl, items in (("P05", p05_mismatches), ("P06", p06_mismatches)):
            for item in items:
                for field, values in item["differences"].items():
                    writer.writerow([impl, item["case_id"], field, values["expected"], values["actual"]])

    md = ["# P06d — resultado contra un oráculo exacto independiente", ""]
    if success:
        md += [
            "## Resultado corto: TODO VERDE",
            "",
            f"El oráculo exacto calculó la respuesta correcta de **{expected_cases} casos** sin usar código de Tesseract.",
            f"P05 coincidió con él en **{p05_matched}/{expected_cases}** casos.",
            f"P06 coincidió con él en **{p06_matched}/{expected_cases}** casos.",
            "",
            "Dicho en castellano: ya no estamos comprobando sólo que dos versiones nuestras se copien bien. Tenemos un tercer juez que enumera todas las combinaciones de fallos y ambos decoders llegan a la misma respuesta.",
        ]
    else:
        md += [
            "## Resultado corto: HAY ALGO QUE MIRAR",
            "",
            f"P05 tiene **{len(p05_mismatches)}** diferencias respecto al oráculo exacto.",
            f"P06 tiene **{len(p06_mismatches)}** diferencias respecto al oráculo exacto.",
            "No se tapa ninguna: los casos concretos quedan guardados en `mismatches.tsv`.",
        ]
    md += [
        "",
        "## Qué hace el oráculo",
        "",
        "Para cada DEM prueba todas las combinaciones posibles de errores independientes. En cada combinación hace XOR de detectores y observables, calcula su probabilidad, agrupa por síndrome y máscara lógica completa, y escoge la máscara conjunta con mayor masa de probabilidad. Si hubiera un empate exacto, escoge la máscara numéricamente menor para que el resultado sea reproducible.",
        "",
        "## Reparto",
        "",
    ]
    for obs in sorted(by_obs_total, key=int):
        md.append(
            f"- {obs} observables: {by_obs_total[obs]} casos; "
            f"P05 mal={by_obs_p05_bad.get(obs, 0)}, P06 mal={by_obs_p06_bad.get(obs, 0)}."
        )
    md += [
        "",
        "## Lo que NO demuestra",
        "",
        "No demuestra que P06 sea la implementación privada que mencionó Fran ni que tenga su rendimiento. Demuestra corrección funcional de la decisión joint-MAP en este corpus exacto y reproducible. Los tiempos de GitHub Actions no son benchmark científico.",
    ]
    Path(args.markdown_report).write_text("\n".join(md) + "\n")

    print(json.dumps({
        "cases": expected_cases,
        "p05_exact": p05_matched,
        "p06_exact": p06_matched,
        "p05_mismatches": len(p05_mismatches),
        "p06_mismatches": len(p06_mismatches),
        "success": success,
    }, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
