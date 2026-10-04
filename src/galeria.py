"""Galería: vuelve a simular criaturas que no ganaron, desde la población guardada.

Uso:
    python src/galeria.py --nombre nado01 --generaciones 1,10,25,50 --cuales mejor,mediana,peor,azar:4

Escribe runs/<nombre>/galeria.json y una copia en viewer/galeria.json. Cada
generación elegida trae varias criaturas (mejor, mediana, peor y algunas al
azar) con su trayectoria completa, para verlas una a una o en carrera.
Como la física es determinista, la simulación repetida reproduce la aptitud
registrada durante la evolución (salvo las cortadas a los 3 s por quietas, que
aquí se simulan completas).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco  # noqa: E402

import develop  # noqa: E402
import fitness  # noqa: E402
from genome import morph, neural  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _redondear_cuadros(cuadros: list[dict], dec: int = 4) -> list[dict]:
    """Menos decimales: la galería lleva varias criaturas por archivo."""
    return [{"t": c["t"],
             "pos": [[round(v, dec) for v in p] for p in c["pos"]],
             "quat": [[round(v, dec) for v in q] for q in c["quat"]],
             "q": [round(v, 3) for v in c["q"]],
             "ctrl": [round(v, 2) for v in c["ctrl"]],
             "com": [round(v, dec) for v in c["com"]]} for c in cuadros]


def elegir(pob: list[dict], cuales: str, rng: random.Random) -> list[tuple[str, dict]]:
    orden = sorted(pob, key=lambda c: c["aptitud"], reverse=True)
    elegidas: list[tuple[str, dict]] = []
    usados: set[int] = set()
    for item in cuales.split(","):
        item = item.strip()
        if item == "mejor":
            cands = [("mejor", orden[0])]
        elif item == "mediana":
            cands = [("mediana", orden[len(orden) // 2])]
        elif item == "peor":
            cands = [("peor", orden[-1])]
        elif item.startswith("azar"):
            n = int(item.split(":")[1]) if ":" in item else 1
            resto = [c for c in pob if c["indice"] not in usados]
            cands = [("azar", c) for c in rng.sample(resto, min(n, len(resto)))]
        else:
            raise SystemExit("criterio desconocido: " + item)
        for et, c in cands:
            if c["indice"] not in usados:
                usados.add(c["indice"])
                elegidas.append((et, c))
    return elegidas


def exportar_galeria(nombre: str, generaciones: list[int] | None = None,
                     cuales: str = "mejor,mediana,peor,azar:4", fps: int = 30,
                     semilla: int = 0, carpeta_runs: str | None = None,
                     copiar_a_viewer: bool = True) -> str:
    """`generaciones` se numera desde 1, como en el visor. Por defecto 1, 10, 25 y la última."""
    carpeta_runs = carpeta_runs or os.path.join(RAIZ, "runs")
    carpeta = os.path.join(carpeta_runs, nombre)
    with open(os.path.join(carpeta, "config.json"), encoding="utf-8") as f:
        config = json.load(f)
    carpeta_pob = os.path.join(carpeta, "poblacion")
    disponibles = sorted(int(fn[4:7]) for fn in os.listdir(carpeta_pob) if fn.startswith("gen_"))
    if not disponibles:
        raise SystemExit("no hay poblaciones guardadas en " + carpeta_pob)
    if generaciones is None:
        ultima = disponibles[-1] + 1
        generaciones = sorted({g for g in (1, 10, 25, ultima) if g <= ultima})
    rng = random.Random(semilla)
    etapa3 = config.get("etapa") == 3
    tarea = config.get("tarea", "nado")
    if etapa3:
        import develop_morfo as dm
        import tareas
        from ejemplos import piezas_y_bisagras
        model = data = None
        cada = max(1, int(round(1.0 / (fps * dm.PASO_FISICA))))
    else:
        cuerpo = develop.CuerpoFijo()
        model = mujoco.MjModel.from_xml_string(develop.mjcf_cuerpo_fijo(cuerpo))
        data = mujoco.MjData(model)
        cada = max(1, int(round(1.0 / (fps * cuerpo.paso))))
    salida_gens = []
    for gen1 in generaciones:
        gen = gen1 - 1
        if gen not in disponibles:
            print(f"generación {gen1} no guardada, se omite")
            continue
        with open(os.path.join(carpeta_pob, f"gen_{gen:03d}.json"), encoding="utf-8") as f:
            pob = json.load(f)
        orden = sorted(pob, key=lambda c: c["aptitud"], reverse=True)
        puesto = {c["indice"]: k + 1 for k, c in enumerate(orden)}
        criaturas = []
        for et, c in elegir(pob, cuales, rng):
            extra = {}
            if etapa3:
                try:
                    model, data, des = tareas.compilar_tarea(c["genoma"], tarea)
                except ValueError as e:
                    print(f"gen {gen1:3d} {et:8s} #{c['indice']:3d} no compila ({e}), se omite")
                    continue
                cerebro_plano = des["cerebro"]
                pz, bs = piezas_y_bisagras(model)
                extra = {"piezas": pz, "bisagras": bs, "n_piezas": len(pz), "n_dof": des["n_dof"],
                         "tarea": tarea, "descripcion": morph.describir(c["genoma"])}
                r = tareas.evaluar(model, data, cerebro_plano, tarea, duracion=config["duracion"],
                                   grabar_cada=cada, cortar_temprano=False)
                n_neu, desc = len(cerebro_plano["neuronas"]), morph.describir(c["genoma"])
            else:
                r = fitness.evaluar_nado(model, data, c["genoma"], duracion=config["duracion"],
                                         grabar_cada=cada, cortar_temprano=False)
                n_neu, desc = len(c["genoma"]["neuronas"]), neural.describir(c["genoma"])
            criaturas.append(dict({"etiqueta": et, "indice": c["indice"], "puesto": puesto[c["indice"]],
                                   "aptitud": c["aptitud"], "distancia": r["distancia"], "motivo": c["motivo"],
                                   "n_neuronas": n_neu, "cerebro": desc,
                                   "cuadros": _redondear_cuadros(r["cuadros"])}, **extra))
            print(f"gen {gen1:3d} {et:8s} #{c['indice']:3d} puesto {puesto[c['indice']]:3d} "
                  f"aptitud {c['aptitud']:6.3f} distancia {r['distancia']:6.3f}")
        salida_gens.append({"generacion": gen1, "poblacion": len(pob), "criaturas": criaturas})
    log = []
    with open(os.path.join(carpeta, "log.csv"), encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            log.append({k: float(v) for k, v in fila.items()})
    piezas = [] if etapa3 else [{"nombre": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b),
               "size": [float(2 * s) for s in model.geom_size[model.body_geomadr[b]]]}
              for b in range(1, model.nbody)]
    bisagras = [] if etapa3 else [{"nombre": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j),
                 "cuerpo": int(model.jnt_bodyid[j]) - 1, "eje": [float(v) for v in model.jnt_axis[j]],
                 "pos": [float(v) for v in model.jnt_pos[j]], "rango": [float(v) for v in model.jnt_range[j]]}
                for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE]
    salida = {"meta": {"corrida": nombre, "semilla": config["semilla"], "generaciones": config["generaciones"],
                       "poblacion": config["poblacion"], "duracion": config["duracion"], "fps": fps,
                       "cuales": cuales, "semilla_galeria": semilla, "etapa": config.get("etapa", 1), "tarea": tarea},
              "piezas": piezas, "bisagras": bisagras, "log": log, "generaciones": salida_gens}
    destino = os.path.join(carpeta, "galeria.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, separators=(",", ":"), ensure_ascii=False)
    if copiar_a_viewer:
        shutil.copyfile(destino, os.path.join(RAIZ, "viewer", "galeria.json"))
    print(f"exportado {destino}: {sum(len(g['criaturas']) for g in salida_gens)} criaturas, "
          f"{os.path.getsize(destino) / 1e6:.1f} MB")
    return destino


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nombre", default="nado01")
    ap.add_argument("--generaciones", default=None, help="por ejemplo 1,10,25,50 (numeradas desde 1)")
    ap.add_argument("--cuales", default="mejor,mediana,peor,azar:4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--semilla", type=int, default=0, help="semilla para elegir las criaturas al azar")
    a = ap.parse_args()
    gens = [int(x) for x in a.generaciones.split(",")] if a.generaciones else None
    exportar_galeria(a.nombre, gens, a.cuales, a.fps, a.semilla)


if __name__ == "__main__":
    main()
