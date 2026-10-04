#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
from pathlib import Path

OBJETIVOS = {
    "BB90-Z": 3,
    "BB108-Z": 2,
    "BB144-X": 0,
    "BB144-Z": 0,
}

def bits(path):
    xs = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(xs) != 1:
        raise RuntimeError(f"{path}: esperaba una predicción y hay {len(xs)}")
    return xs[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--selection", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--beams", default="256,512,1024,2048")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    binary = Path(args.binary).resolve()
    upstream = Path(args.upstream_dir).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    beams = [int(x) for x in args.beams.split(",") if x]
    ref = max(beams)

    with Path(args.selection).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    por_nombre = {f"{r['name']}-{r['basis']}": (i, r) for i, r in enumerate(rows)}
    resultados = []

    for caso, shot in OBJETIVOS.items():
        ci, row = por_nombre[caso]
        seed = 940000 + ci
        circuito = upstream / row["path"]
        por_beam = {}
        for beam in beams:
            carpeta = out / caso / f"beam_{beam}"
            carpeta.mkdir(parents=True, exist_ok=True)
            stats = carpeta / "stats.json"
            pred = carpeta / "prediccion.01"
            cmd = [
                str(binary),
                "--circuit", str(circuito),
                "--sample-num-shots", "4",
                "--sample-seed", str(seed),
                "--shot-range-begin", str(shot),
                "--shot-range-end", str(shot + 1),
                "--threads", "1",
                "--beam", str(beam),
                "--beam-eps", "0",
                "--ranking-mode", "mass",
                "--out", str(pred),
                "--out-format", "01",
                "--stats-out", str(stats),
            ]
            try:
                p = subprocess.run(
                    cmd,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=args.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"{caso} shot={shot} beam={beam}: timeout")
            (carpeta / "stdout.txt").write_text(p.stdout, encoding="utf-8")
            (carpeta / "stderr.txt").write_text(p.stderr, encoding="utf-8")
            (carpeta / "comando.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
            if p.returncode != 0:
                raise RuntimeError(f"{caso} shot={shot} beam={beam}: exit {p.returncode}")
            s = json.loads(stats.read_text(encoding="utf-8"))
            if int(s["num_shots"]) != 1:
                raise RuntimeError(f"{caso} shot={shot} beam={beam}: num_shots != 1")
            por_beam[beam] = {
                "prediccion": bits(pred),
                "error": int(s["num_errors"]),
                "low_confidence": int(s["num_low_confidence"]),
            }

        ref_pred = por_beam[ref]["prediccion"]
        estable = None
        for beam in sorted(beams):
            siguientes = [b for b in beams if b >= beam]
            if all(por_beam[b]["prediccion"] == ref_pred for b in siguientes):
                estable = beam
                break

        for beam in beams:
            x = por_beam[beam]
            resultados.append({
                "caso": caso,
                "shot": shot,
                "seed": seed,
                "beam": beam,
                "prediccion": x["prediccion"],
                "error": x["error"],
                "low_confidence": x["low_confidence"],
                "igual_que_beam_max": x["prediccion"] == ref_pred,
                "beam_desde_el_que_estabiliza": estable,
                "circuit_sha256": row["sha256"],
            })

    with (out / "detalle.tsv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(resultados[0]), delimiter="\t")
        w.writeheader()
        w.writerows(resultados)

    casos = {}
    for caso in OBJETIVOS:
        xs = [x for x in resultados if x["caso"] == caso]
        casos[caso] = {
            "shot": xs[0]["shot"],
            "beam_desde_el_que_estabiliza": xs[0]["beam_desde_el_que_estabiliza"],
            "error_en_beam_max": next(x["error"] for x in xs if x["beam"] == ref),
            "low_confidence_en_beam_max": next(x["low_confidence"] for x in xs if x["beam"] == ref),
            "predicciones": {str(x["beam"]): x["prediccion"] for x in xs},
        }

    resumen = {
        "beams": beams,
        "beam_referencia": ref,
        "casos": casos,
        "benchmark_valido": False,
        "ler_cientifico_valido": False,
    }
    (out / "resumen.json").write_text(json.dumps(resumen, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(resumen, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
