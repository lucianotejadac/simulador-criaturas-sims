"""Exporta la trayectoria del campeón de una corrida a JSON para el visor.

Uso:
    python src/export.py --nombre nado01 [--fps 60]

Escribe runs/<nombre>/campeon_trayectoria.json y una copia en viewer/campeon.json.
El visor (viewer/index.html) lee ese archivo con fetch, así que funciona en
GitHub Pages o con un servidor local (`python -m http.server` en viewer/).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco  # noqa: E402

import develop  # noqa: E402
import fitness  # noqa: E402
from genome import neural  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exportar_campeon(nombre: str, fps: int = 60, carpeta_runs: str | None = None,
                     copiar_a_viewer: bool = True) -> str:
    carpeta_runs = carpeta_runs or os.path.join(RAIZ, "runs")
    carpeta = os.path.join(carpeta_runs, nombre)
    with open(os.path.join(carpeta, "campeon.json"), encoding="utf-8") as f:
        campeon = json.load(f)
    with open(os.path.join(carpeta, "config.json"), encoding="utf-8") as f:
        config = json.load(f)
    cuerpo = develop.CuerpoFijo()
    xml = develop.mjcf_cuerpo_fijo(cuerpo)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    cada = max(1, int(round(1.0 / (fps * cuerpo.paso))))
    r = fitness.evaluar_nado(model, data, campeon["genoma"], duracion=config["duracion"],
                             grabar_cada=cada, cortar_temprano=False)
    log = []
    with open(os.path.join(carpeta, "log.csv"), encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            log.append({k: float(v) for k, v in fila.items()})
    piezas = []
    for b in range(1, model.nbody):
        g = model.body_geomadr[b]
        piezas.append({"nombre": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b),
                       "size": [float(2 * s) for s in model.geom_size[g]]})
    bisagras = []
    for j in range(model.njnt):
        if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE:
            bisagras.append({"nombre": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j),
                             "cuerpo": int(model.jnt_bodyid[j]) - 1,
                             "eje": [float(v) for v in model.jnt_axis[j]],
                             "pos": [float(v) for v in model.jnt_pos[j]],
                             "rango": [float(v) for v in model.jnt_range[j]]})
    salida = {
        "meta": {
            "corrida": nombre, "semilla": config["semilla"], "generacion": campeon["generacion"],
            "generaciones": config["generaciones"], "poblacion": config["poblacion"],
            "aptitud": campeon["aptitud"], "distancia": r["distancia"],
            "duracion": config["duracion"], "fps": fps, "mujoco": config.get("mujoco"),
            "tarea": "nado", "torque_max": config.get("torque_max"),
            "n_neuronas": len(campeon["genoma"]["neuronas"]),
            "cerebro": neural.describir(campeon["genoma"]),
        },
        "genoma": campeon["genoma"],
        "piezas": piezas,
        "bisagras": bisagras,
        "log": log,
        "cuadros": r["cuadros"],
    }
    destino = os.path.join(carpeta, "campeon_trayectoria.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, separators=(",", ":"), ensure_ascii=False)
    if copiar_a_viewer:
        shutil.copyfile(destino, os.path.join(RAIZ, "viewer", "campeon.json"))
    print(f"exportado {destino}: {len(r['cuadros'])} cuadros, distancia {r['distancia']:.3f} m")
    return destino


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nombre", default="nado01")
    ap.add_argument("--fps", type=int, default=60)
    a = ap.parse_args()
    exportar_campeon(a.nombre, a.fps)


if __name__ == "__main__":
    main()
