"""Exporta el bestiario (con fototaxis) al visor: viewer/bestiario.json, cada especie persiguiendo una luz."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tareas
from ejemplos import piezas_y_bisagras
from galeria import _redondear_cuadros
from genome import bestiario, morph
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
criaturas = []
for k, nombre in enumerate(bestiario.BESTIARIO):
    g = bestiario.especie(nombre)
    assert morph.es_valido(g), nombre
    m, d, r = tareas.compilar_tarea(g, "luz")
    cada = max(1, int(round(1.0 / (30 * m.opt.timestep))))
    res = tareas.evaluar(m, d, r["cerebro"], "luz", grabar_cada=cada, cortar_temprano=False)
    pz, bs = piezas_y_bisagras(m)
    criaturas.append({"etiqueta": nombre, "indice": k, "puesto": k + 1, "aptitud": res["aptitud"], "distancia": res["distancia"],
                      "motivo": res["motivo"], "n_neuronas": len(r["cerebro"]["neuronas"]), "n_piezas": len(pz), "n_dof": r["n_dof"],
                      "tarea": "luz", "luz": res["luz"], "descripcion": bestiario.DESCRIPCIONES[nombre],
                      "cerebro": morph.describir(g), "piezas": pz, "bisagras": bs, "cuadros": _redondear_cuadros(res["cuadros"])})
    print(f"{nombre:18s} {len(pz):2d} piezas, acercamiento {res['aptitud']:+.3f} m/s")
    with open(os.path.join(RAIZ, "runs", "ejemplos", f"bestiario_{nombre}.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, indent=1)
salida = {"meta": {"corrida": "bestiario", "semilla": 0, "generaciones": 0, "poblacion": len(criaturas), "duracion": 6.0,
                   "fps": 30, "cuales": "a mano", "fuente": "etapa3", "etapa": 6},
          "log": [], "generaciones": [{"generacion": 9, "etiqueta": "bestiario", "tarea": "luz", "poblacion": len(criaturas), "criaturas": criaturas}]}
destino = os.path.join(RAIZ, "viewer", "bestiario.json")
json.dump(salida, open(destino, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
print("exportado", destino, round(os.path.getsize(destino) / 1e6, 1), "MB")
