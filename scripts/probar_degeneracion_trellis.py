#!/usr/bin/env python3
import argparse
import csv
import json
import random
import subprocess
from collections import defaultdict
from pathlib import Path

def bitline(mask, width):
    return "".join("1" if (mask >> i) & 1 else "0" for i in range(width))

def linemask(line):
    mask = 0
    for i, c in enumerate(line.strip()):
        if c == "1":
            mask |= 1 << i
    return mask

def exacto(faults, detectors):
    masas = [defaultdict(float) for _ in range(1 << detectors)]
    mejor_camino = [(-1.0, 0) for _ in range(1 << detectors)]
    for assignment in range(1 << len(faults)):
        dmask = 0
        omask = 0
        ptotal = 1.0
        for i, f in enumerate(faults):
            presente = (assignment >> i) & 1
            p = f["p"]
            if presente:
                ptotal *= p
                dmask ^= f["d"]
                omask ^= f["o"]
            else:
                ptotal *= 1.0 - p
        masas[dmask][omask] += ptotal
        pvieja, ovieja = mejor_camino[dmask]
        if ptotal > pvieja or (ptotal == pvieja and omask < ovieja):
            mejor_camino[dmask] = (ptotal, omask)
    out = {}
    for s in range(1 << detectors):
        if not masas[s]:
            continue
        mejor_masa = max(masas[s].values())
        joint = min(m for m, v in masas[s].items() if v == mejor_masa)
        out[s] = {
            "joint": joint,
            "single": mejor_camino[s][1],
            "joint_mass": mejor_masa,
            "single_path_mass": mejor_camino[s][0],
            "clases": len(masas[s]),
        }
    return out

def genera(seed, detectors=3, observables=4, faults_n=10):
    rng = random.Random(seed)
    disponibles = [(d, o) for d in range(1, 1 << detectors) for o in range(1 << observables)]
    rng.shuffle(disponibles)
    elegidos = disponibles[:faults_n]
    if not any(o & (1 << (observables - 1)) for _, o in elegidos):
        d, o = elegidos[0]
        elegidos[0] = (d, o | (1 << (observables - 1)))
    probs = [0.035, 0.055, 0.08, 0.11, 0.145, 0.18, 0.22, 0.27, 0.31, 0.36]
    rng.shuffle(probs)
    return [{"p": probs[i], "d": d, "o": o} for i, (d, o) in enumerate(elegidos)]

def dem_text(faults, detectors):
    lines = []
    for f in faults:
        partes = [f"error({f['p']:.12g})"]
        partes += [f"D{i}" for i in range(detectors) if (f["d"] >> i) & 1]
        partes += [f"L{i}" for i in range(64) if (f["o"] >> i) & 1]
        lines.append(" ".join(partes))
    for i in range(detectors):
        lines.append(f"detector({i}, 0, 0) D{i}")
    return "\n".join(lines) + "\n"

def ejecuta(binary, dem, syndromes, detectors, observables, beam, carpeta):
    carpeta.mkdir(parents=True, exist_ok=True)
    entrada = carpeta / "syndromes.01"
    salida = carpeta / "predicciones.01"
    stats = carpeta / "stats.json"
    entrada.write_text("\n".join(bitline(s, detectors) for s in syndromes) + "\n", encoding="utf-8")
    cmd = [
        str(binary),
        "--dem", str(dem),
        "--in", str(entrada),
        "--in-format", "01",
        "--out", str(salida),
        "--out-format", "01",
        "--threads", "1",
        "--beam", str(beam),
        "--beam-eps", "0",
        "--ranking-mode", "mass",
        "--stats-out", str(stats),
    ]
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    (carpeta / "stdout.txt").write_text(p.stdout, encoding="utf-8")
    (carpeta / "stderr.txt").write_text(p.stderr, encoding="utf-8")
    (carpeta / "comando.txt").write_text(" ".join(cmd) + "\n", encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"{dem.name} beam={beam} terminó con {p.returncode}")
    lineas = [x.strip() for x in salida.read_text(encoding="utf-8").splitlines() if x.strip()]
    if len(lineas) != len(syndromes):
        raise RuntimeError(f"{dem.name} beam={beam}: {len(lineas)} salidas para {len(syndromes)} casos")
    if any(len(x) != observables for x in lineas):
        raise RuntimeError(f"{dem.name} beam={beam}: ancho lógico inesperado")
    return [linemask(x) for x in lineas]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--casos", type=int, default=32)
    ap.add_argument("--beams", default="1,2,4,16,65536")
    args = ap.parse_args()

    binary = Path(args.binary).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    modelos = out / "modelos"
    modelos.mkdir(exist_ok=True)
    beams = [int(x) for x in args.beams.split(",") if x]
    if 65536 not in beams:
        raise SystemExit("Hace falta beam 65536 como referencia sin poda útil")

    seleccionados = []
    seed = 910000
    while len(seleccionados) < args.casos and seed < 920000:
        faults = genera(seed)
        respuestas = exacto(faults, 3)
        retos = [s for s, r in respuestas.items() if r["joint"] != r["single"]]
        if retos:
            seleccionados.append((seed, faults, respuestas, retos))
        seed += 1

    if len(seleccionados) < args.casos:
        raise SystemExit(f"Sólo encontré {len(seleccionados)} modelos degenerados")

    filas = []
    por_beam = {b: {"casos": 0, "joint_ok": 0, "single_ok": 0} for b in beams}
    predicciones = {}

    for modelo_i, (seed, faults, respuestas, retos) in enumerate(seleccionados):
        mid = f"modelo_{modelo_i:03d}_{seed}"
        dem = modelos / f"{mid}.dem"
        dem.write_text(dem_text(faults, 3), encoding="utf-8")
        predicciones[mid] = {}
        for beam in beams:
            predicciones[mid][beam] = ejecuta(
                binary, dem, retos, 3, 4, beam, out / "ejecuciones" / mid / f"beam_{beam}"
            )
        for pos, syndrome in enumerate(retos):
            r = respuestas[syndrome]
            fila = {
                "modelo": mid,
                "seed": seed,
                "syndrome": syndrome,
                "joint": r["joint"],
                "single": r["single"],
                "joint_mass": r["joint_mass"],
                "single_path_mass": r["single_path_mass"],
                "clases": r["clases"],
            }
            for beam in beams:
                pred = predicciones[mid][beam][pos]
                fila[f"beam_{beam}"] = pred
                por_beam[beam]["casos"] += 1
                por_beam[beam]["joint_ok"] += int(pred == r["joint"])
                por_beam[beam]["single_ok"] += int(pred == r["single"])
            filas.append(fila)

    referencia = 65536
    for beam in beams:
        cambios = 0
        for fila in filas:
            cambios += int(fila[f"beam_{beam}"] != fila[f"beam_{referencia}"])
        por_beam[beam]["cambios_frente_65536"] = cambios

    campos = list(filas[0])
    with (out / "casos_degenerados.tsv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, delimiter="\t")
        w.writeheader()
        w.writerows(filas)

    total = len(filas)
    wide_ok = por_beam[referencia]["joint_ok"]
    resumen = {
        "modelos": len(seleccionados),
        "casos_degenerados": total,
        "regla": "sumar masa por clase lógica completa y escoger la clase con más masa",
        "casos_donde_joint_y_mejor_camino_individual_difieren": total,
        "beam_65536_joint_ok": wide_ok,
        "beam_65536_single_ok": por_beam[referencia]["single_ok"],
        "por_beam": {str(k): v for k, v in por_beam.items()},
        "benchmark_valido": False,
    }
    (out / "resumen_degeneracion.json").write_text(
        json.dumps(resumen, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(resumen, indent=2, sort_keys=True))
    if total < args.casos:
        return 1
    if wide_ok != total:
        return 1
    if por_beam[referencia]["single_ok"] != 0:
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
