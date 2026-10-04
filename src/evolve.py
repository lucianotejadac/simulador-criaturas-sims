"""Bucle evolutivo con evaluación en paralelo (multiprocessing, maestro-esclavo).

Uso:
    python src/evolve.py --nombre nado01 --generaciones 50 --poblacion 300 --semilla 1

Parámetros de Sims (1994): población ~300, sobrevive 1/5, descendencia
proporcional a la aptitud, reproducción 40 % asexual / 30 % cruce / 30 % injerto.
Toda cría pasa además por `mutar`.

Registro por generación en runs/<nombre>/log.csv, el campeón de cada
generación en runs/<nombre>/campeon.json y la población completa (genoma y
aptitud de cada criatura) en runs/<nombre>/poblacion/gen_NNN.json, para poder
volver a simular y ver a cualquier criatura, no solo al campeón.
Al terminar exporta la trayectoria del campeón y una galería.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from multiprocessing import Pool, cpu_count

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco  # noqa: E402

import develop  # noqa: E402
import fitness  # noqa: E402
from genome import neural  # noqa: E402

# --- estado del proceso esclavo -------------------------------------------
_model = None
_data = None


def _init_worker(xml: str) -> None:
    global _model, _data
    _model = mujoco.MjModel.from_xml_string(xml)
    _data = mujoco.MjData(_model)


def _evaluar(args: tuple) -> dict:
    genoma, duracion = args
    r = fitness.evaluar_nado(_model, _data, genoma, duracion=duracion)
    r.pop("cuadros", None)
    return r


# --- maestro ---------------------------------------------------------------
def siguiente_generacion(poblacion: list[dict], aptitudes: list[float], rng: random.Random,
                         frac_sobrevive: float = 0.2) -> list[dict]:
    n = len(poblacion)
    orden = sorted(range(n), key=lambda i: aptitudes[i], reverse=True)
    n_sob = max(2, int(n * frac_sobrevive))
    sobrevivientes = [poblacion[i] for i in orden[:n_sob]]
    apt_sob = [max(aptitudes[i], 0.0) for i in orden[:n_sob]]
    total = sum(apt_sob)
    pesos = apt_sob if total > 0 else [1.0] * n_sob

    nueva = [json.loads(json.dumps(g)) for g in sobrevivientes]  # copias limpias
    while len(nueva) < n:
        r = rng.random()
        padre = rng.choices(sobrevivientes, weights=pesos)[0]
        if r < 0.4:
            hijo = neural.mutar(padre, rng)
        elif r < 0.7:
            madre = rng.choices(sobrevivientes, weights=pesos)[0]
            hijo = neural.mutar(neural.cruzar(padre, madre, rng), rng)
        else:
            donante = rng.choices(sobrevivientes, weights=pesos)[0]
            hijo = neural.mutar(neural.injertar(padre, donante, rng), rng)
        if not hijo["neuronas"] and rng.random() < 0.5:
            # Un cerebro vacío (efectores leyendo sensores o constantes) es válido
            # pero poco interesante: la mitad de las veces se le siembra una neurona.
            hijo = neural.mutar(hijo, rng)
        nueva.append(hijo)
    return nueva


def correr(nombre: str, generaciones: int, poblacion: int, semilla: int, procesos: int,
           duracion: float, carpeta_runs: str = "runs") -> dict:
    rng = random.Random(semilla)
    cuerpo = develop.CuerpoFijo()
    xml = develop.mjcf_cuerpo_fijo(cuerpo)
    carpeta = os.path.join(carpeta_runs, nombre)
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"nombre": nombre, "generaciones": generaciones, "poblacion": poblacion,
                   "semilla": semilla, "procesos": procesos, "duracion": duracion,
                   "tarea": "nado", "cuerpo": "cadena4 fija", "k_fuerza": develop.K_FUERZA,
                   "torque_max": cuerpo.torque_max, "paso_fisica": cuerpo.paso,
                   "pasos_cerebro_por_fisica": fitness.PASOS_CEREBRO_POR_FISICA,
                   "mujoco": mujoco.__version__}, f, indent=2, ensure_ascii=False)
    with open(os.path.join(carpeta, "cuerpo.xml"), "w", encoding="utf-8") as f:
        f.write(xml)

    carpeta_pob = os.path.join(carpeta, "poblacion")
    os.makedirs(carpeta_pob, exist_ok=True)
    pob = [neural.genoma_aleatorio(rng, cuerpo.n_dof, cuerpo.n_dof) for _ in range(poblacion)]
    log_path = os.path.join(carpeta, "log.csv")
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["generacion", "mejor", "media", "peor", "mediana",
                                "neuronas_mejor", "sin_movimiento", "inestables", "segundos"])
    mejor_global = {"aptitud": -1.0, "genoma": None, "generacion": -1}
    t0 = time.time()
    with Pool(processes=procesos, initializer=_init_worker, initargs=(xml,)) as pool:
        for gen in range(generaciones):
            t_gen = time.time()
            res = pool.map(_evaluar, [(g, duracion) for g in pob], chunksize=4)
            apt = [r["aptitud"] for r in res]
            with open(os.path.join(carpeta_pob, f"gen_{gen:03d}.json"), "w", encoding="utf-8") as f:
                json.dump([{"indice": i, "aptitud": r["aptitud"], "distancia": r["distancia"],
                            "motivo": r["motivo"], "genoma": g} for i, (g, r) in enumerate(zip(pob, res))],
                          f, separators=(",", ":"))
            i_mejor = max(range(len(apt)), key=apt.__getitem__)
            ordenado = sorted(apt)
            fila = [gen, apt[i_mejor], sum(apt) / len(apt), ordenado[0], ordenado[len(apt) // 2],
                    len(pob[i_mejor]["neuronas"]),
                    sum(r["motivo"] == "sin_movimiento" for r in res),
                    sum(r["motivo"] == "inestable" for r in res), time.time() - t_gen]
            with open(log_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([f"{v:.4f}" if isinstance(v, float) else v for v in fila])
            print(f"gen {gen:3d}  mejor {apt[i_mejor]:7.3f}  media {fila[2]:7.3f}  peor {ordenado[0]:7.3f}"
                  f"  neuronas {fila[5]:2d}  quietas {fila[6]:3d}  inest {fila[7]:2d}  {fila[8]:5.1f} s",
                  flush=True)
            if apt[i_mejor] > mejor_global["aptitud"]:
                mejor_global = {"aptitud": apt[i_mejor], "genoma": pob[i_mejor], "generacion": gen,
                                "distancia": res[i_mejor]["distancia"]}
                with open(os.path.join(carpeta, "campeon.json"), "w", encoding="utf-8") as f:
                    json.dump(mejor_global, f, indent=1)
            if gen < generaciones - 1:
                pob = siguiente_generacion(pob, apt, rng)
    print(f"listo: {generaciones} generaciones en {time.time() - t0:.0f} s; "
          f"mejor {mejor_global['aptitud']:.3f} (gen {mejor_global['generacion']})")
    return mejor_global


def main() -> None:
    ap = argparse.ArgumentParser(description="Evolución del cerebro de un nadador de cuerpo fijo.")
    ap.add_argument("--nombre", default="nado01")
    ap.add_argument("--generaciones", type=int, default=50)
    ap.add_argument("--poblacion", type=int, default=300)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--procesos", type=int, default=max(1, cpu_count() - 1))
    ap.add_argument("--duracion", type=float, default=10.0)
    ap.add_argument("--sin-exportar", action="store_true")
    a = ap.parse_args()
    correr(a.nombre, a.generaciones, a.poblacion, a.semilla, a.procesos, a.duracion)
    if not a.sin_exportar:
        import export
        export.exportar_campeon(a.nombre)
        import galeria
        galeria.exportar_galeria(a.nombre)


if __name__ == "__main__":
    main()
