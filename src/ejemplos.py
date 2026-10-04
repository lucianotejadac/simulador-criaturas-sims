"""Exporta los genomas diseñados a mano de la Etapa 2 para el visor.

Uso:
    python src/ejemplos.py [--fps 30] [--duracion 10]

Desarrolla cada genoma de `genome/ejemplos.py`, lo simula en el agua con su
cerebro escrito a mano y escribe viewer/ejemplos.json con el mismo formato de
la galería (un solo grupo, cada criatura con sus propias piezas y bisagras).
También deja runs/ejemplos/<nombre>.xml con el MJCF, para inspección.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco  # noqa: E402

import develop_morfo as dm  # noqa: E402
import fitness  # noqa: E402
from galeria import _redondear_cuadros  # noqa: E402
from genome import ejemplos, morph  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DESCRIPCIONES = {
    "cadena4": "La cadena de la Etapa 1 escrita como genoma: cabeza + segmento con límite recursivo 3. "
               "La onda viajera nace de la recursión: cada segmento retarda la oscilación de su madre.",
    "ciempies": "Cuerpo recursivo (4 segmentos) y en cada uno dos patas, la segunda por reflexión. "
                "Las patas reman en fase con la onda de su segmento.",
    "bilateral": "Cabeza con dos aletas de articulación universal (una reflejada) que baten en cuadratura, "
                 "y una cola recursiva de dos piezas que se achica con la escala.",
}


def piezas_y_bisagras(model: mujoco.MjModel) -> tuple[list, list]:
    piezas = [{"nombre": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b),
               "size": [float(2 * s) for s in model.geom_size[model.body_geomadr[b]]]}
              for b in range(1, model.nbody)]
    bisagras = [{"nombre": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j),
                 "cuerpo": int(model.jnt_bodyid[j]) - 1, "eje": [float(v) for v in model.jnt_axis[j]],
                 "pos": [float(v) for v in model.jnt_pos[j]], "rango": [float(v) for v in model.jnt_range[j]]}
                for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE]
    return piezas, bisagras


def exportar_ejemplos(fps: int = 30, duracion: float = 10.0, copiar_a_viewer: bool = True) -> str:
    carpeta = os.path.join(RAIZ, "runs", "ejemplos")
    os.makedirs(carpeta, exist_ok=True)
    criaturas = []
    for nombre, fabrica in ejemplos.EJEMPLOS.items():
        g = fabrica()
        assert morph.es_valido(g), nombre
        model, data, r = dm.compilar(g)
        with open(os.path.join(carpeta, f"{nombre}.xml"), "w", encoding="utf-8") as f:
            f.write(r["xml"])
        with open(os.path.join(carpeta, f"{nombre}.json"), "w", encoding="utf-8") as f:
            json.dump(g, f, indent=1)
        cada = max(1, int(round(1.0 / (fps * model.opt.timestep))))
        res = fitness.evaluar_nado(model, data, r["cerebro"], duracion=duracion,
                                   grabar_cada=cada, cortar_temprano=False)
        piezas, bisagras = piezas_y_bisagras(model)
        criaturas.append({"etiqueta": nombre, "indice": len(criaturas), "puesto": len(criaturas) + 1,
                          "aptitud": res["aptitud"], "distancia": res["distancia"], "motivo": res["motivo"],
                          "n_neuronas": len(r["cerebro"]["neuronas"]), "n_piezas": len(piezas), "n_dof": r["n_dof"],
                          "descripcion": DESCRIPCIONES.get(nombre, ""),
                          "cerebro": morph.describir(g),
                          "piezas": piezas, "bisagras": bisagras,
                          "cuadros": _redondear_cuadros(res["cuadros"])})
        print(f"{nombre:10s} {len(piezas):2d} piezas, {r['n_dof']:2d} dof, {len(r['cerebro']['neuronas']):2d} neuronas, "
              f"distancia {res['distancia']:.3f} m ({res['motivo']})")
    salida = {"meta": {"corrida": "ejemplos", "semilla": 0, "generaciones": 0, "poblacion": len(criaturas),
                       "duracion": duracion, "fps": fps, "cuales": "a mano", "etapa": 2},
              "log": [], "generaciones": [{"generacion": 0, "poblacion": len(criaturas), "criaturas": criaturas}]}
    destino = os.path.join(carpeta, "ejemplos.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, separators=(",", ":"), ensure_ascii=False)
    if copiar_a_viewer:
        import shutil
        shutil.copyfile(destino, os.path.join(RAIZ, "viewer", "ejemplos.json"))
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duracion", type=float, default=10.0)
    a = ap.parse_args()
    exportar_ejemplos(a.fps, a.duracion)
