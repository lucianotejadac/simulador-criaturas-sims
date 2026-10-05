"""Etapa 5: coevolución de dos especies que compiten por un cubo.

Uso:
    python src/evolve_duelo.py --nombre duelo01 --semilla 1 --ancestro pez

Cada generación, cada individuo de la especie A se enfrenta al campeón de la
especie B de la generación anterior, y cada individuo de B al campeón de A
(Sims, 1994: "all versus best"). La aptitud es la de `arena.enfrentar_robusto`.
Las dos especies parten del mismo ancestro con flujos aleatorios distintos.

Deja en runs/<nombre>/: config.json, log.csv (mejor, media y mediana de cada
especie, aptitud del campeón contra el campeón rival), poblacion/gen_NNN_A.json
y _B.json, campeones.json y, al final, duelos.json para el visor (el
enfrentamiento entre los campeones de las generaciones elegidas).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys
import time
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco  # noqa: E402

import arena  # noqa: E402
import evolve_morfo as em  # noqa: E402
from ejemplos import piezas_y_bisagras  # noqa: E402
from galeria import _redondear_cuadros  # noqa: E402
from genome import morph  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERACIONES_DUELOS = (1, 10, 25, 50)


def _duelo(args: tuple) -> dict:
    genoma, rival, yo_primero = args
    pareja = [genoma, rival] if yo_primero else [rival, genoma]
    try:
        r = arena.enfrentar_robusto(pareja)
    except ValueError as e:
        return {"aptitud": 0.0, "motivo": "invalido:" + str(e)}
    i = 0 if yo_primero else 1
    return {"aptitud": r["aptitudes"][i], "aptitud_rival": r["aptitudes"][1 - i], "motivo": r["motivo"],
            "distancia": r.get("distancias", [0, 0])[i], "toco": r.get("contactos", [False, False])[i],
            "n_piezas": r.get("n_cuerpos", [0, 0])[i]}


def correr(nombre: str, generaciones: int, poblacion: int, semilla: int, procesos: int,
           ancestro: str) -> None:
    rng_a, rng_b = random.Random(semilla * 1000 + 1), random.Random(semilla * 1000 + 2)
    carpeta = os.path.join(RAIZ, "runs", nombre)
    os.makedirs(os.path.join(carpeta, "poblacion"), exist_ok=True)
    with open(os.path.join(carpeta, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"nombre": nombre, "etapa": 5, "tarea": "duelo", "generaciones": generaciones,
                   "poblacion": poblacion, "semilla": semilla, "procesos": procesos, "ancestro": ancestro,
                   "duracion": arena.DURACION, "distancia_cubo": arena.DISTANCIA, "lado_cubo": arena.LADO_CUBO,
                   "bono_contacto": arena.BONO_CONTACTO, "mujoco": mujoco.__version__}, f, indent=2, ensure_ascii=False)
    contador = {"rechazadas": 0, "forzadas": 0}
    pobs = {"A": em.poblacion_inicial(rng_a, poblacion, "caminata", contador, ancestro),
            "B": em.poblacion_inicial(rng_b, poblacion, "caminata", contador, ancestro)}
    campeones = {"A": pobs["A"][0], "B": pobs["B"][0]}   # el ancestro, al principio
    log_path = os.path.join(carpeta, "log.csv")
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["generacion", "mejor_A", "media_A", "mediana_A", "mejor_B", "media_B", "mediana_B",
                                "campeon_A_vs_B", "piezas_A", "piezas_B", "tocan_A", "tocan_B", "segundos"])
    historia = []
    t0 = time.time()
    with Pool(processes=procesos) as pool:
        for gen in range(generaciones):
            t_gen = time.time()
            res = {}
            for esp, rival_esp, primero in (("A", "B", True), ("B", "A", False)):
                res[esp] = pool.map(_duelo, [(g, campeones[rival_esp], primero) for g in pobs[esp]], chunksize=2)
            apt = {esp: [r["aptitud"] for r in res[esp]] for esp in ("A", "B")}
            mejor = {esp: max(range(poblacion), key=apt[esp].__getitem__) for esp in ("A", "B")}
            for esp in ("A", "B"):
                with open(os.path.join(carpeta, "poblacion", f"gen_{gen:03d}_{esp}.json"), "w", encoding="utf-8") as f:
                    json.dump([{"indice": i, "aptitud": r["aptitud"], "motivo": r["motivo"], "n_piezas": r.get("n_piezas", 0),
                                "genoma": g} for i, (g, r) in enumerate(zip(pobs[esp], res[esp]))], f, separators=(",", ":"))
            nuevos = {esp: pobs[esp][mejor[esp]] for esp in ("A", "B")}
            cabeza = arena.enfrentar_robusto([nuevos["A"], nuevos["B"]])
            fila = [gen]
            for esp in ("A", "B"):
                o = sorted(apt[esp])
                fila += [apt[esp][mejor[esp]], sum(apt[esp]) / poblacion, o[poblacion // 2]]
            fila += [cabeza["aptitudes"][0], res["A"][mejor["A"]].get("n_piezas", 0), res["B"][mejor["B"]].get("n_piezas", 0),
                     sum(r.get("toco", False) for r in res["A"]), sum(r.get("toco", False) for r in res["B"]),
                     time.time() - t_gen]
            with open(log_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([f"{v:.4f}" if isinstance(v, float) else v for v in fila])
            print(f"gen {gen:3d}  A mejor {fila[1]:6.3f} media {fila[2]:6.3f} | B mejor {fila[4]:6.3f} media {fila[5]:6.3f} | "
                  f"campeones A-B {fila[7]:+.3f} | piezas {fila[8]:2d}/{fila[9]:2d} | tocan {fila[10]:3d}/{fila[11]:3d} | {fila[12]:5.1f} s", flush=True)
            historia.append({"generacion": gen + 1, "A": nuevos["A"], "B": nuevos["B"],
                             "aptitud_A": apt["A"][mejor["A"]], "aptitud_B": apt["B"][mejor["B"]], "cabeza": cabeza["aptitudes"]})
            campeones = nuevos
            with open(os.path.join(carpeta, "campeones.json"), "w", encoding="utf-8") as f:
                json.dump({"generacion": gen, "A": campeones["A"], "B": campeones["B"],
                           "aptitud_A": apt["A"][mejor["A"]], "aptitud_B": apt["B"][mejor["B"]]}, f, indent=1)
            if gen < generaciones - 1:
                pobs["A"] = em.siguiente_generacion(pobs["A"], apt["A"], rng_a, "caminata", contador)
                pobs["B"] = em.siguiente_generacion(pobs["B"], apt["B"], rng_b, "caminata", contador)
    with open(os.path.join(carpeta, "historia_campeones.json"), "w", encoding="utf-8") as f:
        json.dump(historia, f, separators=(",", ":"))
    print(f"listo: {generaciones} generaciones en {time.time() - t0:.0f} s", flush=True)


def exportar_duelos(nombre: str, generaciones=GENERACIONES_DUELOS, fps: int = 30, salida: str | None = None,
                    copiar_a_viewer: bool = True) -> str:
    """El enfrentamiento entre los campeones A y B de cada generación elegida, para el visor."""
    carpeta = os.path.join(RAIZ, "runs", nombre)
    historia = json.load(open(os.path.join(carpeta, "historia_campeones.json"), encoding="utf-8"))
    log = [{k: float(v) for k, v in fila.items()} for fila in csv.DictReader(open(os.path.join(carpeta, "log.csv"), encoding="utf-8"))]
    por_gen = {h["generacion"]: h for h in historia}
    grupos = []
    for k, gen1 in enumerate(g for g in generaciones if g in por_gen):
        h = por_gen[gen1]
        cada = max(1, int(round(1.0 / (fps * arena.PASOS[0]))))
        r = arena.enfrentar([h["A"], h["B"]], arena.PASOS[0], grabar_cada=cada)
        model = r["model"]
        criaturas = []
        n_acum = 0
        for i, (esp, des) in enumerate(zip(("A", "B"), r["desarrollos"])):
            n = len(des["piezas"])
            pz_todas, bs_todas = piezas_y_bisagras(model)
            prefijo = esp + "_"
            piezas = [p for p in pz_todas if p["nombre"].startswith(prefijo)]
            bisagras = [dict(b, cuerpo=b["cuerpo"] - (1 + n_acum)) for b in bs_todas if b["nombre"].startswith(prefijo)]
            cuadros = [{"t": c["t"], "pos": c["pos"][n_acum:n_acum + n], "quat": c["quat"][n_acum:n_acum + n],
                        "q": [], "ctrl": [], "com": c["com"][i]} for c in r["cuadros"]]
            criaturas.append({"etiqueta": f"especie {esp}", "indice": i, "puesto": i + 1,
                              "aptitud": r["aptitudes"][i], "distancia": r["distancias"][i], "motivo": r["motivo"],
                              "n_neuronas": len(des["cerebro"]["neuronas"]), "n_piezas": n, "n_dof": des["n_dof"],
                              "corrida": nombre, "tarea": "duelo", "generacion": gen1, "generaciones": len(historia),
                              "toco": r["contactos"][i],
                              "descripcion": f"Campeón de la especie {esp} en la generación {gen1} de {nombre}: "
                                             f"{n} piezas, {des['n_dof']} grados de libertad; "
                                             f"{'tocó' if r['contactos'][i] else 'no tocó'} el cubo, "
                                             f"terminó a {r['distancias'][i]:.2f} m.",
                              "cerebro": morph.describir(h[esp]), "piezas": piezas, "bisagras": bisagras,
                              "log": [{"generacion": f["generacion"], "mejor": f["mejor_" + esp], "media": f["media_" + esp],
                                       "peor": 0.0, "mediana": f["mediana_" + esp]} for f in log],
                              "cuadros": _redondear_cuadros(cuadros)})
            n_acum += n
        grupos.append({"generacion": k + 1, "etiqueta": f"{nombre} · gen {gen1}", "tarea": "duelo", "escena_comun": True,
                       "cubo": {"size": [arena.LADO_CUBO] * 3, "cuadros": [c["cubo"] for c in r["cuadros"]]},
                       "poblacion": 2, "criaturas": criaturas})
        print(f"{nombre} gen {gen1}: A {r['aptitudes'][0]:+.3f} ({r['distancias'][0]:.2f} m) vs B {r['aptitudes'][1]:+.3f} "
              f"({r['distancias'][1]:.2f} m), contactos {r['contactos']}")
    datos = {"meta": {"corrida": nombre, "semilla": 0, "generaciones": len(historia), "poblacion": 2,
                      "duracion": arena.DURACION, "fps": fps, "cuales": "campeones A y B", "fuente": "duelos", "etapa": 5},
             "log": [], "generaciones": grupos}
    destino = os.path.join(carpeta, "duelos.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(datos, f, separators=(",", ":"), ensure_ascii=False)
    if copiar_a_viewer:
        shutil.copyfile(destino, os.path.join(RAIZ, "viewer", salida or "duelos.json"))
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB")
    return destino


def main() -> None:
    ap = argparse.ArgumentParser(description="Coevolución de dos especies por un cubo (Etapa 5).")
    ap.add_argument("--nombre", default="duelo01")
    ap.add_argument("--generaciones", type=int, default=50)
    ap.add_argument("--poblacion", type=int, default=100)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--procesos", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--ancestro", default="pez")
    ap.add_argument("--sin-exportar", action="store_true")
    a = ap.parse_args()
    correr(a.nombre, a.generaciones, a.poblacion, a.semilla, a.procesos, a.ancestro)
    if not a.sin_exportar:
        exportar_duelos(a.nombre)


if __name__ == "__main__":
    main()
