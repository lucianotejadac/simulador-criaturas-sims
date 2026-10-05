"""Etapa 3: coevolución de cuerpo y cerebro (genoma morfológico) para nado o caminata.

Uso:
    python src/evolve_morfo.py --nombre morfo-nado01 --tarea nado --semilla 1
    python src/evolve_morfo.py --nombre morfo-cam01 --tarea caminata --semilla 1

Cada esclavo desarrolla y compila el MJCF de la criatura que recibe y la
evalúa. En el maestro, las crías que no desarrollan un cuerpo válido
(demasiadas piezas, sin grados de libertad, interpenetradas o que no se
asientan) se descartan y se vuelven a generar, como en Sims.
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
import develop_morfo as dm  # noqa: E402
import fitness  # noqa: E402
import tareas  # noqa: E402
from genome import morph  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_INTENTOS = 40
UMBRAL_SOSPECHA_NADO = 0.05  # verificación incondicional: con umbral 8 la población se quedó en 7.98
                             # y con umbral 1 en 0.998 (BITACORA 0013); solo se exime a las quietas


def _evaluar(args: tuple) -> dict:
    genoma, tarea, duracion = args
    try:
        model, data, r = tareas.compilar_tarea(genoma, tarea)
    except ValueError as e:
        return {"aptitud": 0.0, "distancia": 0.0, "motivo": "invalido:" + str(e), "n_piezas": 0, "n_dof": 0}
    res = tareas.evaluar(model, data, r["cerebro"], tarea, duracion=duracion)
    if tarea in ("nado", "luz") and res["aptitud"] > (UMBRAL_SOSPECHA_NADO if tarea == "nado" else 0.005):
        # Todo nadador que avanza se reevalúa a la mitad del paso: si no es
        # consistente, es un artefacto numérico y no cuenta (BITACORA 0011).
        m2, d2, r2 = tareas.compilar_tarea(genoma, tarea, dm.PASO_FISICA / 2)
        res2 = tareas.evaluar(m2, d2, r2["cerebro"], tarea, duracion=duracion)
        res["aptitudes_pasos"] = [res["aptitud"], res2["aptitud"]]
        if res2["aptitud"] < res["aptitud"] / 2:
            res = {"aptitud": 0.0, "distancia": res2["distancia"], "motivo": "inconsistente",
                   "aptitudes_pasos": res["aptitudes_pasos"]}
        elif res2["aptitud"] < res["aptitud"]:
            res2["aptitudes_pasos"] = res["aptitudes_pasos"]
            res = res2
    if tarea == "caminata" and res["aptitud"] > 0:
        # Aptitud robusta: la menor entre tres pasos de integración, para que no se
        # premie lo que solo funciona por el error de integración (BITACORA 0010).
        aptitudes = [res["aptitud"]]
        for paso in tareas.PASOS_CAMINATA[1:]:
            m2, d2, r2 = tareas.compilar_tarea(genoma, tarea, paso)
            res2 = tareas.evaluar(m2, d2, r2["cerebro"], tarea, duracion=duracion)
            aptitudes.append(res2["aptitud"])
            if res2["aptitud"] < res["aptitud"]:
                res = res2
        res["aptitudes_pasos"] = aptitudes
    res.pop("cuadros", None)
    res["n_piezas"] = len(r["piezas"])
    res["n_dof"] = r["n_dof"]
    res["n_neuronas"] = len(r["cerebro"]["neuronas"])
    return res


def cuerpo_valido(g: dict, tarea: str) -> bool:
    if not morph.es_valido(g):
        return False
    try:
        tareas.compilar_tarea(g, tarea)
    except ValueError:
        return False
    return True


def cria_valida(fabrica, rng: random.Random, tarea: str, contador: dict) -> dict:
    for _ in range(MAX_INTENTOS):
        h = fabrica()
        if cuerpo_valido(h, tarea):
            return h
        contador["rechazadas"] += 1
    contador["forzadas"] += 1
    return h


def siguiente_generacion(pob: list, apt: list, rng: random.Random, tarea: str, contador: dict,
                         frac_sobrevive: float = 0.2) -> list:
    n = len(pob)
    orden = sorted(range(n), key=lambda i: apt[i], reverse=True)
    n_sob = max(2, int(n * frac_sobrevive))
    sob = [pob[i] for i in orden[:n_sob]]
    pesos = [max(apt[i], 0.0) for i in orden[:n_sob]]
    if sum(pesos) <= 0:
        pesos = [1.0] * n_sob
    nueva = [json.loads(json.dumps(g)) for g in sob]
    while len(nueva) < n:
        r = rng.random()
        padre = rng.choices(sob, weights=pesos)[0]
        if r < 0.4:
            fab = lambda: morph.mutar(padre, rng)  # noqa: E731
        elif r < 0.7:
            madre = rng.choices(sob, weights=pesos)[0]
            fab = lambda: morph.mutar(morph.cruzar(padre, madre, rng), rng)  # noqa: E731
        else:
            donante = rng.choices(sob, weights=pesos)[0]
            fab = lambda: morph.mutar(morph.injertar(padre, donante, rng), rng)  # noqa: E731
        nueva.append(cria_valida(fab, rng, tarea, contador))
    return nueva


def poblacion_inicial(rng: random.Random, poblacion: int, tarea: str, contador: dict,
                      ancestro: str | None) -> list:
    """Genomas aleatorios, o el ancestro más mutantes suyos (1 a 3 mutaciones)."""
    if not ancestro:
        return [cria_valida(lambda: morph.genoma_aleatorio(rng), rng, tarea, contador) for _ in range(poblacion)]
    from genome import ejemplos
    base = ejemplos.EJEMPLOS[ancestro]()
    if not cuerpo_valido(base, tarea):
        raise SystemExit(f"el ancestro {ancestro} no es válido para {tarea}")

    def mutante():
        g = base
        for _ in range(rng.randint(1, 3)):
            g = morph.mutar(g, rng)
        return g
    return [json.loads(json.dumps(base))] + [cria_valida(mutante, rng, tarea, contador) for _ in range(poblacion - 1)]


def correr(nombre: str, tarea: str, generaciones: int, poblacion: int, semilla: int,
           procesos: int, duracion: float, ancestro: str | None = None) -> dict:
    rng = random.Random(semilla)
    carpeta = os.path.join(RAIZ, "runs", nombre)
    os.makedirs(os.path.join(carpeta, "poblacion"), exist_ok=True)
    with open(os.path.join(carpeta, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"nombre": nombre, "etapa": 3, "tarea": tarea, "generaciones": generaciones,
                   "poblacion": poblacion, "semilla": semilla, "procesos": procesos, "duracion": duracion,
                   "cuerpo": "genoma morfológico", "ancestro": ancestro, "k_fuerza": develop.K_FUERZA,
                   "paso_fisica": dm.PASO_FISICA,
                   "pasos_cerebro_por_fisica": fitness.PASOS_CEREBRO_POR_FISICA,
                   "mujoco": mujoco.__version__}, f, indent=2, ensure_ascii=False)
    contador = {"rechazadas": 0, "forzadas": 0}
    pob = poblacion_inicial(rng, poblacion, tarea, contador, ancestro)
    print(f"población inicial{' desde ' + ancestro if ancestro else ''}: "
          f"{contador['rechazadas']} genomas rechazados para llenar {poblacion}", flush=True)
    log_path = os.path.join(carpeta, "log.csv")
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["generacion", "mejor", "media", "peor", "mediana", "piezas_mejor",
                                "neuronas_mejor", "sin_movimiento", "inestables", "invalidas", "no_asentadas",
                                "rechazadas", "piezas_media", "segundos"])
    mejor_global = {"aptitud": -1.0}
    t0 = time.time()
    cache: dict[str, dict] = {}   # aptitud por genoma: la física es determinista (BITACORA 0019)
    with Pool(processes=procesos) as pool:
        for gen in range(generaciones):
            t_gen = time.time()
            claves = [json.dumps(g, sort_keys=True, separators=(",", ":")) for g in pob]
            nuevos = [i for i, c in enumerate(claves) if c not in cache]
            calculados = pool.map(_evaluar, [(pob[i], tarea, duracion) for i in nuevos], chunksize=2)
            for i, r in zip(nuevos, calculados):
                cache[claves[i]] = r
            res = [cache[c] for c in claves]
            if len(cache) > 20 * poblacion:
                cache = {c: cache[c] for c in claves}
            apt = [r["aptitud"] for r in res]
            with open(os.path.join(carpeta, "poblacion", f"gen_{gen:03d}.json"), "w", encoding="utf-8") as f:
                json.dump([{"indice": i, "aptitud": r["aptitud"], "distancia": r["distancia"], "motivo": r["motivo"],
                            "n_piezas": r["n_piezas"], "genoma": g} for i, (g, r) in enumerate(zip(pob, res))],
                          f, separators=(",", ":"))
            i_mejor = max(range(len(apt)), key=apt.__getitem__)
            orden = sorted(apt)
            fila = [gen, apt[i_mejor], sum(apt) / len(apt), orden[0], orden[len(apt) // 2],
                    res[i_mejor]["n_piezas"], res[i_mejor].get("n_neuronas", 0),
                    sum(r["motivo"] == "sin_movimiento" for r in res),
                    sum(r["motivo"] in ("inestable", "inconsistente") for r in res),
                    sum(r["motivo"].startswith("invalido") for r in res),
                    sum(r["motivo"] == "no_asentada" for r in res),
                    contador["rechazadas"], sum(r["n_piezas"] for r in res) / len(res), time.time() - t_gen]
            with open(log_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([f"{v:.4f}" if isinstance(v, float) else v for v in fila])
            print(f"gen {gen:3d}  mejor {apt[i_mejor]:7.3f}  media {fila[2]:6.3f}  mediana {fila[4]:6.3f}  "
                  f"piezas {fila[5]:2d} (media {fila[12]:4.1f})  neuronas {fila[6]:2d}  quietas {fila[7]:3d}  "
                  f"inest {fila[8]:2d}  inval {fila[9]:2d}  no_asent {fila[10]:3d}  rech {fila[11]:4d}  {fila[13]:5.1f} s",
                  flush=True)
            contador["rechazadas"] = 0
            if apt[i_mejor] > mejor_global["aptitud"]:
                mejor_global = {"aptitud": apt[i_mejor], "genoma": pob[i_mejor], "generacion": gen,
                                "distancia": res[i_mejor]["distancia"], "n_piezas": res[i_mejor]["n_piezas"],
                                "motivo": res[i_mejor]["motivo"]}
                with open(os.path.join(carpeta, "campeon.json"), "w", encoding="utf-8") as f:
                    json.dump(mejor_global, f, indent=1)
            if gen < generaciones - 1:
                pob = siguiente_generacion(pob, apt, rng, tarea, contador)
    print(f"listo: {generaciones} generaciones en {time.time() - t0:.0f} s; "
          f"mejor {mejor_global['aptitud']:.3f} (gen {mejor_global['generacion']})", flush=True)
    return mejor_global


def exportar_campeon(nombre: str, fps: int = 60, copiar_a_viewer: bool = False) -> str:
    """Trayectoria del campeón en el formato "campeon" del visor, con sus propias piezas."""
    from ejemplos import piezas_y_bisagras
    carpeta = os.path.join(RAIZ, "runs", nombre)
    campeon = json.load(open(os.path.join(carpeta, "campeon.json"), encoding="utf-8"))
    config = json.load(open(os.path.join(carpeta, "config.json"), encoding="utf-8"))
    tarea = config["tarea"]
    model, data, r = tareas.compilar_tarea(campeon["genoma"], tarea)
    with open(os.path.join(carpeta, "campeon.xml"), "w", encoding="utf-8") as f:
        f.write(r["xml"])
    cada = max(1, int(round(1.0 / (fps * model.opt.timestep))))
    res = tareas.evaluar(model, data, r["cerebro"], tarea, duracion=config["duracion"],
                         grabar_cada=cada, cortar_temprano=False)
    log = [{k: float(v) for k, v in fila.items()} for fila in csv.DictReader(open(os.path.join(carpeta, "log.csv"), encoding="utf-8"))]
    piezas, bisagras = piezas_y_bisagras(model)
    salida = {"meta": {"corrida": nombre, "etapa": 3, "tarea": tarea, "semilla": config["semilla"],
                       "generacion": campeon["generacion"], "generaciones": config["generaciones"],
                       "poblacion": config["poblacion"], "aptitud": campeon["aptitud"], "distancia": res["distancia"],
                       "duracion": config["duracion"], "fps": fps, "mujoco": config.get("mujoco"),
                       "n_neuronas": len(r["cerebro"]["neuronas"]), "n_piezas": len(piezas), "n_dof": r["n_dof"],
                       "cerebro": morph.describir(campeon["genoma"]), "torque_max": None,
                       "luz": res.get("luz"), "velocidades": res.get("velocidades")},
              "genoma": r["cerebro"], "genoma_morfo": campeon["genoma"],
              "piezas": piezas, "bisagras": bisagras, "log": log, "cuadros": res["cuadros"]}
    destino = os.path.join(carpeta, "campeon_trayectoria.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(salida, f, separators=(",", ":"), ensure_ascii=False)
    print(f"exportado {destino}: {len(res['cuadros'])} cuadros, distancia {res['distancia']:.3f} m, "
          f"{len(piezas)} piezas ({res['motivo']})")
    return destino


def main() -> None:
    ap = argparse.ArgumentParser(description="Coevolución cuerpo + cerebro (Etapa 3).")
    ap.add_argument("--nombre", default="morfo-nado01")
    ap.add_argument("--tarea", choices=["nado", "caminata", "luz"], default="nado")
    ap.add_argument("--generaciones", type=int, default=60)
    ap.add_argument("--poblacion", type=int, default=200)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--procesos", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--duracion", type=float, default=10.0)
    ap.add_argument("--ancestro", default=None, help="genoma de genome/ejemplos.py para sembrar la población (p. ej. pez)")
    ap.add_argument("--sin-exportar", action="store_true")
    a = ap.parse_args()
    correr(a.nombre, a.tarea, a.generaciones, a.poblacion, a.semilla, a.procesos, a.duracion, a.ancestro)
    if not a.sin_exportar:
        exportar_campeon(a.nombre)


if __name__ == "__main__":
    main()
