"""Reúne los campeones de varias corridas en un archivo de galería para verlos en carrera.

Uso:
    python src/semillas.py --corridas nado01,nado02,nado03,nado04,nado05

Lee runs/<corrida>/campeon_trayectoria.json (exportado a 60 cuadros por
segundo) de cada corrida, se queda con uno de cada dos cuadros y escribe
viewer/semillas.json con el formato de la galería (un solo grupo).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exportar_semillas(corridas: list[str], copiar_a_viewer: bool = True) -> str:
    criaturas = []
    piezas = bisagras = None
    duracion = 10.0
    for k, nombre in enumerate(corridas):
        ruta = os.path.join(RAIZ, "runs", nombre, "campeon_trayectoria.json")
        d = json.load(open(ruta, encoding="utf-8"))
        meta = d["meta"]
        piezas, bisagras, duracion = d["piezas"], d["bisagras"], meta["duracion"]
        cuadros = d["cuadros"][::2] if meta["fps"] == 60 else d["cuadros"]
        criaturas.append({"etiqueta": f"semilla {meta['semilla']}", "indice": k, "puesto": k + 1,
                          "aptitud": meta["aptitud"], "distancia": meta["distancia"], "motivo": "completa",
                          "n_neuronas": meta["n_neuronas"], "corrida": nombre,
                          "descripcion": f"Campeón de la corrida {nombre} (semilla {meta['semilla']}, "
                                         f"generación {meta['generacion'] + 1} de {meta['generaciones']}).",
                          "cerebro": meta["cerebro"], "cuadros": cuadros})
        print(f"{nombre}: aptitud {meta['aptitud']:.3f}, distancia {meta['distancia']:.3f} m, "
              f"{meta['n_neuronas']} neuronas, {len(cuadros)} cuadros")
    salida = {"meta": {"corrida": "semillas", "semilla": 0, "generaciones": 50, "poblacion": len(criaturas),
                       "duracion": duracion, "fps": 30, "cuales": "campeones", "fuente": "semillas"},
              "piezas": piezas, "bisagras": bisagras, "log": [],
              "generaciones": [{"generacion": 50, "poblacion": len(criaturas), "criaturas": criaturas}]}
    destino = os.path.join(RAIZ, "runs", "semillas.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, separators=(",", ":"), ensure_ascii=False)
    if copiar_a_viewer:
        shutil.copyfile(destino, os.path.join(RAIZ, "viewer", "semillas.json"))
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corridas", default="nado01,nado02,nado03,nado04,nado05")
    a = ap.parse_args()
    exportar_semillas(a.corridas.split(","))
