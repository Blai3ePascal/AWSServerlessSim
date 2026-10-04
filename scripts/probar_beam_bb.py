#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
from pathlib import Path

def lee_bits(path):
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--upstream-dir", required=True)
    ap.add_argument("--selection", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--shots", type=int, default=4)
    ap.add_argument("--beams", default="15,64,256,1024")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    binary = Path(args.binary).resolve()
    upstream = Path(args.upstream_dir).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    beams = [int(x) for x in args.beams.split(",") if x]
    referencia = max(beams)

    with Path(args.selection).open(encoding="utf-8") as f:
        circuitos = list(csv.DictReader(f, delimiter="	"))
    if len(circuitos) != 8:
        raise SystemExit(f"Esperaba 8 circuitos y hay {len(circuitos)}")

    filas = []
    pred_por_caso = {}

    for ci, row in enumerate(circuitos):
        caso = f"{row['name']}-{row['basis']}"
        seed = 940000 + ci
        pred_por_caso[caso] = {}
        for beam in beams:
            carpeta = out / caso / f"beam_{beam}"
            carpeta.mkdir(parents=True, exist_ok=True)
            circuito = upstream / row["path"]
            stats = carpeta / "stats.json"
            preds = carpeta / "predicciones.01"
            cmd = [
                str(binary),
                "--circuit", str(circuito),
                "--sample-num-shots", str(args.shots),
                "--sample-seed", str(seed),
                "--threads", "1",
                "--beam", str(beam),
                "--beam-eps", "0",
                "--ranking-mode", "mass",
                "--out", str(preds),
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
                timeout = False
            except subprocess.TimeoutExpired as e:
                p = None
                timeout = True
                (carpeta / "stdout.txt").write_text(e.stdout or "", encoding="utf-8")
                (carpeta / "stderr.txt").write_text(e.stderr or "", encoding="utf-8")
            (carpeta / "comando.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
            if timeout:
                raise RuntimeError(f"{caso} beam={beam}: timeout")
            (carpeta / "stdout.txt").write_text(p.stdout, encoding="utf-8")
            (carpeta / "stderr.txt").write_text(p.stderr, encoding="utf-8")
            if p.returncode != 0:
                raise RuntimeError(f"{caso} beam={beam}: exit {p.returncode}")
            datos = json.loads(stats.read_text(encoding="utf-8"))
            lineas = lee_bits(preds)
            if len(lineas) != args.shots:
                raise RuntimeError(f"{caso} beam={beam}: predicciones {len(lineas)}/{args.shots}")
            if int(datos.get("num_observables", -1)) != int(row["k"]):
                raise RuntimeError(f"{caso} beam={beam}: observables mal")
            pred_por_caso[caso][beam] = lineas
            filas.append({
                "caso": caso,
                "beam": beam,
                "shots": args.shots,
                "seed": seed,
                "errores": int(datos["num_errors"]),
                "low_confidence": int(datos["num_low_confidence"]),
                "fallos_conservadores": int(datos["num_errors"]) + int(datos["num_low_confidence"]),
                "num_observables": int(datos["num_observables"]),
                "circuit_sha256": row["sha256"],
            })

    for fila in filas:
        caso = fila["caso"]
        beam = fila["beam"]
        actuales = pred_por_caso[caso][beam]
        ref = pred_por_caso[caso][referencia]
        fila["predicciones_distintas_frente_beam_max"] = sum(a != b for a, b in zip(actuales, ref))

    totales = {}
    for beam in beams:
        xs = [x for x in filas if x["beam"] == beam]
        totales[str(beam)] = {
            "shots": sum(x["shots"] for x in xs),
            "errores": sum(x["errores"] for x in xs),
            "low_confidence": sum(x["low_confidence"] for x in xs),
            "fallos_conservadores": sum(x["fallos_conservadores"] for x in xs),
            "predicciones_distintas_frente_beam_max": sum(
                x["predicciones_distintas_frente_beam_max"] for x in xs
            ),
        }

    with (out / "barrido_beam_bb.tsv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]), delimiter="	")
        w.writeheader()
        w.writerows(filas)

    resumen = {
        "circuitos": 8,
        "shots_por_circuito_y_beam": args.shots,
        "beams": beams,
        "misma_semilla_por_circuito_en_todos_los_beams": True,
        "totales": totales,
        "benchmark_valido": False,
        "ler_cientifico_valido": False,
    }
    (out / "resumen_beam_bb.json").write_text(
        json.dumps(resumen, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(resumen, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
