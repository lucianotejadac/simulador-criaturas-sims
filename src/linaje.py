"""Linaje: el campeón de varias generaciones de una corrida, para verlos en carrera.

Uso:
    python src/linaje.py --corridas pez-cam01,pez-cam02 --generaciones 1,10,20,30,40,50,60

Lee runs/<corrida>/poblacion/gen_NNN.json, toma la mejor criatura de cada
generación pedida, la vuelve a simular y escribe viewer/linaje.json con el
formato de la galería: un grupo por corrida, una criatura por generación, cada
una con sus piezas y bisagras (los cuerpos cambian de generación en generación).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil

import tareas
from ejemplos import piezas_y_bisagras
from galeria import _redondear_cuadros
from genome import morph

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def grupo_linaje(nombre: str, generaciones: list[int], numero: int, fps: int = 30) -> dict | None:
    carpeta = os.path.join(RAIZ, "runs", nombre)
    config = json.load(open(os.path.join(carpeta, "config.json"), encoding="utf-8"))
    tarea = config["tarea"]
    log = [{k: float(v) for k, v in fila.items()} for fila in csv.DictReader(open(os.path.join(carpeta, "log.csv"), encoding="utf-8"))]
    criaturas = []
    for gen1 in generaciones:
        ruta = os.path.join(carpeta, "poblacion", f"gen_{gen1 - 1:03d}.json")
        if not os.path.exists(ruta):
            print(f"{nombre}: generación {gen1} no guardada, se omite")
            continue
        pob = json.load(open(ruta, encoding="utf-8"))
        mejor = max(pob, key=lambda c: c["aptitud"])
        try:
            model, data, des = tareas.compilar_tarea(mejor["genoma"], tarea)
        except ValueError as e:
            print(f"{nombre} gen {gen1}: no compila ({e})")
            continue
        cada = max(1, int(round(1.0 / (fps * model.opt.timestep))))
        res = tareas.evaluar(model, data, des["cerebro"], tarea, duracion=config["duracion"],
                             grabar_cada=cada, cortar_temprano=False)
        piezas, bisagras = piezas_y_bisagras(model)
        criaturas.append({"etiqueta": f"gen {gen1}", "indice": len(criaturas), "puesto": len(criaturas) + 1,
                          "aptitud": mejor["aptitud"], "distancia": res["distancia"], "motivo": mejor["motivo"],
                          "n_neuronas": len(des["cerebro"]["neuronas"]), "n_piezas": len(piezas), "n_dof": des["n_dof"],
                          "corrida": nombre, "tarea": tarea, "generacion": gen1, "generaciones": config["generaciones"],
                          "descripcion": f"Mejor criatura de la generación {gen1} de {nombre} ({tarea}"
                                         f"{', desde el ancestro ' + config['ancestro'] if config.get('ancestro') else ''}): "
                                         f"{len(piezas)} piezas, {des['n_dof']} grados de libertad.",
                          "cerebro": morph.describir(mejor["genoma"]), "piezas": piezas, "bisagras": bisagras,
                          "log": [{k: fila[k] for k in ("generacion", "mejor", "media", "peor", "mediana")} for fila in log],
                          "cuadros": _redondear_cuadros(res["cuadros"])})
        print(f"{nombre} gen {gen1:3d}: aptitud {mejor['aptitud']:.3f}, distancia {res['distancia']:.3f} m, "
              f"{len(piezas)} piezas, {des['n_dof']} dof")
    if not criaturas:
        return None
    return {"generacion": numero, "etiqueta": f"{nombre} · {tarea}", "tarea": tarea, "poblacion": len(criaturas),
            "criaturas": criaturas}


def exportar_linaje(corridas: list[str], generaciones: list[int], salida: str = "linaje.json",
                    copiar_a_viewer: bool = True) -> str:
    grupos = [g for k, nombre in enumerate(corridas) if (g := grupo_linaje(nombre, generaciones, k + 1))]
    datos = {"meta": {"corrida": "linaje", "semilla": 0, "generaciones": 0, "poblacion": 0, "duracion": 10.0,
                      "fps": 30, "cuales": "mejor por generación", "fuente": "linaje", "etapa": 4},
             "log": [], "generaciones": grupos}
    destino = os.path.join(RAIZ, "runs", salida)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(datos, f, separators=(",", ":"), ensure_ascii=False)
    if copiar_a_viewer:
        shutil.copyfile(destino, os.path.join(RAIZ, "viewer", salida))
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridas", required=True)
    ap.add_argument("--generaciones", default="1,10,20,30,40,50,60")
    ap.add_argument("--salida", default="linaje.json")
    a = ap.parse_args()
    exportar_linaje(a.corridas.split(","), [int(x) for x in a.generaciones.split(",")], a.salida)
