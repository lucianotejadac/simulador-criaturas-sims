"""Reúne los campeones de las corridas de la Etapa 3 para el visor.

Uso:
    python src/etapa3.py --nado morfo-nado01,morfo-nado02 --caminata morfo-cam01,morfo-cam02

Lee runs/<corrida>/campeon_trayectoria.json de cada corrida (exportado por
evolve_morfo.py a 60 cuadros por segundo), se queda con uno de cada dos
cuadros y escribe viewer/etapa3.json: un grupo por tarea, cada criatura con
sus propias piezas y bisagras, para verlas una a una o en carrera.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def grupo(tarea: str, corridas: list[str], numero: int) -> dict | None:
    criaturas = []
    for k, nombre in enumerate(corridas):
        ruta = os.path.join(RAIZ, "runs", nombre, "campeon_trayectoria.json")
        if not os.path.exists(ruta):
            print(f"{nombre}: sin campeon_trayectoria.json, se omite")
            continue
        d = json.load(open(ruta, encoding="utf-8"))
        meta = d["meta"]
        cuadros = d["cuadros"][::2] if meta["fps"] == 60 else d["cuadros"]
        criaturas.append({"etiqueta": f"semilla {meta['semilla']}", "indice": k, "puesto": k + 1,
                          "aptitud": meta["aptitud"], "distancia": meta["distancia"], "motivo": "completa",
                          "n_neuronas": meta["n_neuronas"], "n_piezas": meta["n_piezas"], "n_dof": meta["n_dof"],
                          "corrida": nombre, "tarea": tarea,
                          "descripcion": f"Campeón de {nombre} ({tarea}, semilla {meta['semilla']}, "
                                         f"generación {meta['generacion'] + 1} de {meta['generaciones']}): "
                                         f"{meta['n_piezas']} piezas, {meta['n_dof']} grados de libertad.",
                          "cerebro": meta["cerebro"], "piezas": d["piezas"], "bisagras": d["bisagras"],
                          "generacion": meta["generacion"] + 1, "generaciones": meta["generaciones"],
                          "log": [{k: fila[k] for k in ("generacion", "mejor", "media", "peor", "mediana")} for fila in d["log"]],
                          "cuadros": cuadros})
        print(f"{nombre}: {tarea}, aptitud {meta['aptitud']:.3f}, distancia {meta['distancia']:.3f} m, "
              f"{meta['n_piezas']} piezas, {meta['n_neuronas']} neuronas")
    if not criaturas:
        return None
    criaturas.sort(key=lambda c: c["aptitud"], reverse=True)
    for k, c in enumerate(criaturas):
        c["puesto"] = k + 1
    return {"generacion": numero, "etiqueta": tarea, "tarea": tarea, "poblacion": len(criaturas),
            "criaturas": criaturas}


def exportar_etapa3(nado: list[str], caminata: list[str], copiar_a_viewer: bool = True,
                    extras: list[tuple[str, str, list[str]]] | None = None) -> str:
    """`extras`: grupos adicionales (etiqueta, tarea, corridas), p. ej. los peces en tierra."""
    grupos = [g for g in (grupo("nado", nado, 1), grupo("caminata", caminata, 2)) if g]
    for k, (etiqueta, tarea, corridas) in enumerate(extras or []):
        g = grupo(tarea, corridas, 3 + k)
        if g:
            g["etiqueta"] = etiqueta
            grupos.append(g)
    salida = {"meta": {"corrida": "etapa3", "semilla": 0, "generaciones": 0, "poblacion": 0,
                       "duracion": 10.0, "fps": 30, "cuales": "campeones", "fuente": "etapa3", "etapa": 3},
              "log": [], "generaciones": grupos}
    destino = os.path.join(RAIZ, "runs", "etapa3.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, separators=(",", ":"), ensure_ascii=False)
    if copiar_a_viewer:
        shutil.copyfile(destino, os.path.join(RAIZ, "viewer", "etapa3.json"))
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nado", default="")
    ap.add_argument("--caminata", default="")
    ap.add_argument("--extra", action="append", default=[], help='"etiqueta:tarea:corrida1,corrida2"')
    a = ap.parse_args()
    extras = []
    for e in a.extra:
        etiqueta, tarea, corridas = e.split(":")
        extras.append((etiqueta, tarea, corridas.split(",")))
    exportar_etapa3([x for x in a.nado.split(",") if x], [x for x in a.caminata.split(",") if x], extras=extras)
