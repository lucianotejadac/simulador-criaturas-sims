"""Etapa 6: ecosistema. Varias especies conviven en un acuario con comida (luces).

No hay generaciones ni aptitud. Cada criatura tiene energía: la gasta por
existir (proporcional a su masa) y por mover sus articulaciones (proporcional
al torque que aplica), y la gana al tocar una luz-comida, que reaparece en
otro lugar. Si supera un umbral se reproduce (una hija mutada a su lado, y
cede la mitad de su energía); si llega a cero o a la edad máxima, muere.

MuJoCo no puede agregar ni quitar cuerpos en medio de una simulación: el
mundo se recompila en épocas de T_EPOCA segundos. Entre épocas se aplican
nacimientos y muertes; cada sobreviviente conserva posición, orientación,
ángulos articulares y energía. El estado interno del cerebro se reinicia
(BITACORA 0021).

Uso:
    python src/ecosistema.py --nombre eco01 --semilla 1 --epocas 30 --especies anguila,pez,remador
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

import brain  # noqa: E402
import develop_morfo as dm  # noqa: E402
from ejemplos import piezas_y_bisagras  # noqa: E402
from fitness import PASOS_CEREBRO_POR_FISICA  # noqa: E402
from fluido import ArrastrePorCara  # noqa: E402
from galeria import _redondear_cuadros  # noqa: E402
from genome import bestiario, morph  # noqa: E402
from luz import sensores_luz  # noqa: E402
from tareas import TAU_ACTIVACION  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- reglas de vida ---
T_EPOCA = 20.0            # s simulados entre recompilaciones
RADIO_COMIDA = 5.0        # m: la comida aparece dentro de este radio
N_COMIDA = 8
RADIO_COMER = 0.35        # m del centro de masa a la luz para comerla
ENERGIA_INICIAL = 100.0
ENERGIA_COMIDA = 60.0
UMBRAL_REPRODUCCION = 160.0
ENERGIA_CRIA = 60.0
COSTO_MASA = 0.03         # energía por segundo y por kg
COSTO_TORQUE = 0.004      # energía por segundo y por N·m de torque aplicado
EDAD_MAXIMA = 400.0       # s
POBLACION_MAXIMA = 36
MUTACIONES_CRIA = (1, 2)


class Individuo:
    def __init__(self, ident: int, especie: str, genoma: dict, pos, quat, energia: float, madre: int | None,
                 nacimiento: float):
        self.id = ident
        self.especie = especie
        self.genoma = genoma
        self.pos = np.array(pos, dtype=float)
        self.quat = np.array(quat, dtype=float)
        self.qpos_art = None          # ángulos articulares al final de la época
        self.energia = energia
        self.madre = madre
        self.nacimiento = nacimiento
        self.comidas = 0
        self.hijas = 0
        self.prefijo = f"c{ident}_"
        self.des = None


def mjcf_acuario(individuos: list[Individuo], paso: float) -> str:
    out = ['<mujoco model="acuario">\n',
           '  <compiler angle="degree" autolimits="true"/>\n',
           f'  <option timestep="{paso:.6f}" gravity="0 0 0" integrator="implicitfast"/>\n',
           '  <default>\n',
           f'    <geom type="box" density="{dm.DENSIDAD_PIEZAS}" rgba="0.85 0.89 0.92 1"/>\n',
           '    <joint type="hinge"/>\n',
           '    <motor ctrlrange="-1 1"/>\n',
           '  </default>\n  <worldbody>\n']
    actuadores: list[str] = []
    for ind in individuos:
        dm.escribir_cuerpo(out, actuadores, ind.des["_piezas"][0], 0, ind.prefijo, dm.K_FUERZA,
                           tuple(ind.pos), tuple(ind.quat))
    out.append("  </worldbody>\n  <actuator>\n")
    out.extend(actuadores)
    out.append("  </actuator>\n</mujoco>\n")
    return "".join(out)


class Vivo:
    """Índices de un individuo dentro del modelo compartido de la época."""

    def __init__(self, model, ind: Individuo):
        p = ind.prefijo
        self.ind = ind
        self.cuerpos = np.array([b for b in range(model.nbody)
                                 if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) or "").startswith(p)])
        bis = [j for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE
               and (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) or "").startswith(p)]
        self.qpos_idx = np.array([int(model.jnt_qposadr[j]) for j in bis], dtype=int)
        self.lim = np.array([max(abs(float(model.jnt_range[j][1])), 1e-3) for j in bis])
        raiz = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, p + "raiz")
        self.raiz_q = int(model.jnt_qposadr[raiz])
        self.ctrl_idx = np.array([a for a in range(model.nu)
                                  if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a) or "").startswith("m_" + p)], dtype=int)
        self.gear = np.abs(model.actuator_gear[self.ctrl_idx, 0])
        self.masas = model.body_mass[self.cuerpos]
        self.masa = float(self.masas.sum())
        self.espejos = np.array(ind.des["cerebro"]["espejos"], dtype=bool)
        self.cerebro = brain.crear(ind.des["cerebro"], model.opt.timestep / PASOS_CEREBRO_POR_FISICA)
        self.n_sens = ind.des["cerebro"]["n_sensores"]

    def com(self, data) -> np.ndarray:
        return (self.masas[:, None] * data.xpos[self.cuerpos]).sum(0) / self.masa

    def sensores(self, data, luz: np.ndarray) -> np.ndarray:
        q = np.clip(data.qpos[self.qpos_idx] / self.lim, -1.0, 1.0)
        # dirección a la luz en el marco de cada pieza propia
        pos = data.xpos[self.cuerpos]
        d = luz[None, :] - pos
        d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        R = data.xmat[self.cuerpos].reshape(-1, 3, 3)
        loc = np.einsum("nji,nj->ni", R, d)
        loc[:, 1] *= np.where(self.espejos, -1.0, 1.0)
        return np.concatenate([q, loc.reshape(-1)])


def correr(nombre: str, semilla: int, epocas: int, especies: list[str], por_especie: int,
           grabar_epocas: tuple[int, ...] = (), fps: int = 10) -> None:
    rng = random.Random(semilla)
    nrng = np.random.default_rng(semilla)
    carpeta = os.path.join(RAIZ, "runs", nombre)
    os.makedirs(carpeta, exist_ok=True)
    paso = dm.PASO_FISICA
    # población inicial: anillo de individuos, por especie
    individuos: list[Individuo] = []
    siguiente_id = 0
    n_total = len(especies) * por_especie
    for k, esp in enumerate(especies):
        for j in range(por_especie):
            ang = 2 * math.pi * (k * por_especie + j) / n_total
            pos = (3.0 * math.cos(ang), 3.0 * math.sin(ang), 0.0)
            yaw = ang + math.pi   # mirando al centro
            quat = (math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2))
            g = bestiario.especie(esp)
            ind = Individuo(siguiente_id, esp, g, pos, quat, ENERGIA_INICIAL, None, 0.0)
            ind.des = dm.desarrollar(g, gravedad=False, paso=paso)
            individuos.append(ind)
            siguiente_id += 1
    comida = nrng.uniform(-RADIO_COMIDA, RADIO_COMIDA, size=(N_COMIDA, 3))
    comida[:, 2] = 0.0
    historia = []
    grabaciones = []
    t_global = 0.0
    t0 = time.time()
    config = {"nombre": nombre, "etapa": 6, "semilla": semilla, "epocas": epocas, "t_epoca": T_EPOCA,
              "especies": especies, "por_especie": por_especie, "reglas": {
                  "radio_comida": RADIO_COMIDA, "n_comida": N_COMIDA, "radio_comer": RADIO_COMER,
                  "energia_inicial": ENERGIA_INICIAL, "energia_comida": ENERGIA_COMIDA,
                  "umbral_reproduccion": UMBRAL_REPRODUCCION, "energia_cria": ENERGIA_CRIA,
                  "costo_masa": COSTO_MASA, "costo_torque": COSTO_TORQUE, "edad_maxima": EDAD_MAXIMA,
                  "poblacion_maxima": POBLACION_MAXIMA}}
    json.dump(config, open(os.path.join(carpeta, "config.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    for epoca in range(epocas):
        if not individuos:
            print(f"época {epoca}: extinción total", flush=True)
            break
        t_ep = time.time()
        xml = mjcf_acuario(individuos, paso)
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        vivos = [Vivo(model, ind) for ind in individuos]
        for v in vivos:
            if v.ind.qpos_art is not None and len(v.ind.qpos_art) == len(v.qpos_idx):
                data.qpos[v.qpos_idx] = v.ind.qpos_art
        mujoco.mj_forward(model, data)
        arrastre = ArrastrePorCara(model)
        dt = model.opt.timestep
        n_pasos = int(round(T_EPOCA / dt))
        grabar = epoca in grabar_epocas
        cada = max(1, int(round(1.0 / (fps * dt))))
        cuadros = {v.ind.id: [] for v in vivos}
        cuadros_comida = []
        nacimientos, muertes, comidas = 0, 0, 0
        for k in range(n_pasos):
            for v in vivos:
                com = v.com(data)
                # comida más cercana
                dist = np.linalg.norm(comida[:, :2] - com[None, :2], axis=1)
                j = int(dist.argmin())
                if dist[j] < RADIO_COMER:
                    v.ind.energia += ENERGIA_COMIDA
                    v.ind.comidas += 1
                    comidas += 1
                    comida[j] = nrng.uniform(-RADIO_COMIDA, RADIO_COMIDA, size=3)
                    comida[j, 2] = 0.0
                    j = int(np.linalg.norm(comida[:, :2] - com[None, :2], axis=1).argmin())
                sens = v.sensores(data, comida[j])
                salida = v.cerebro.pasos(PASOS_CEREBRO_POR_FISICA, sens)
                data.ctrl[v.ctrl_idx] += (np.asarray(salida) - data.ctrl[v.ctrl_idx]) * min(1.0, dt / TAU_ACTIVACION)
                torque = float(np.abs(data.ctrl[v.ctrl_idx] * v.gear).sum())
                v.ind.energia -= (COSTO_MASA * v.masa + COSTO_TORQUE * torque) * dt
            arrastre.aplicar(model, data)
            mujoco.mj_step(model, data)
            if grabar and k % cada == 0:
                for v in vivos:
                    cuadros[v.ind.id].append({"t": round(float(k * dt), 3),
                                              "pos": [[round(float(x), 4) for x in data.xpos[b]] for b in v.cuerpos],
                                              "quat": [[round(float(x), 4) for x in data.xquat[b]] for b in v.cuerpos],
                                              "q": [], "ctrl": [], "com": [round(float(x), 4) for x in v.com(data)]})
                cuadros_comida.append([[round(float(x), 3) for x in c] for c in comida])
        if data.warning.number.sum() > 0:
            print(f"época {epoca}: advertencia de MuJoCo {data.warning.number.tolist()}", flush=True)
        t_global += T_EPOCA
        # estado final de cada individuo
        for v in vivos:
            q = v.raiz_q
            v.ind.pos = data.qpos[q:q + 3].copy()
            v.ind.quat = data.qpos[q + 3:q + 7].copy()
            v.ind.qpos_art = data.qpos[v.qpos_idx].copy()
        if grabar:
            grabaciones.append({"epoca": epoca, "t": t_global - T_EPOCA, "model": model, "vivos": vivos,
                                "cuadros": cuadros, "comida": cuadros_comida})
        # muertes
        sobrevivientes = []
        for ind in individuos:
            edad = t_global - ind.nacimiento
            if ind.energia <= 0 or edad > EDAD_MAXIMA or np.linalg.norm(ind.pos[:2]) > 3 * RADIO_COMIDA:
                muertes += 1
            else:
                sobrevivientes.append(ind)
        individuos = sobrevivientes
        # nacimientos
        crias = []
        for ind in sorted(individuos, key=lambda i: -i.energia):
            if ind.energia >= UMBRAL_REPRODUCCION and len(individuos) + len(crias) < POBLACION_MAXIMA:
                g = ind.genoma
                for _ in range(rng.randint(*MUTACIONES_CRIA)):
                    g = morph.mutar(g, rng)
                try:
                    des = dm.desarrollar(g, gravedad=False, paso=paso)
                    m2 = mujoco.MjModel.from_xml_string(des["xml"])
                    if dm.interpenetra(m2, mujoco.MjData(m2)):
                        raise ValueError("interpenetrada")
                except ValueError:
                    continue   # cría inviable: no nace, la madre no gasta
                ang = rng.uniform(0, 2 * math.pi)
                pos = ind.pos + np.array([1.2 * math.cos(ang), 1.2 * math.sin(ang), 0.0])
                cria = Individuo(siguiente_id, ind.especie, g, pos, ind.quat, ENERGIA_CRIA, ind.id, t_global)
                cria.des = des
                siguiente_id += 1
                ind.energia -= ENERGIA_CRIA
                ind.hijas += 1
                crias.append(cria)
                nacimientos += 1
        individuos += crias
        conteo = {esp: sum(1 for i in individuos if i.especie == esp) for esp in especies}
        energia_media = {esp: (sum(i.energia for i in individuos if i.especie == esp) / max(1, conteo[esp])) for esp in especies}
        piezas_media = {esp: (sum(len(i.des["piezas"]) for i in individuos if i.especie == esp) / max(1, conteo[esp])) for esp in especies}
        fila = {"epoca": epoca, "t": t_global, "poblacion": len(individuos), "conteo": conteo,
                "energia_media": energia_media, "piezas_media": piezas_media,
                "nacimientos": nacimientos, "muertes": muertes, "comidas": comidas,
                "segundos": time.time() - t_ep}
        historia.append(fila)
        print(f"época {epoca:3d} t={t_global:6.0f} s  población {len(individuos):2d} {conteo}  comidas {comidas:3d}  "
              f"nac {nacimientos:2d} muertes {muertes:2d}  {fila['segundos']:5.1f} s", flush=True)
        json.dump(historia, open(os.path.join(carpeta, "historia.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    # genomas finales
    json.dump([{"id": i.id, "especie": i.especie, "madre": i.madre, "nacimiento": i.nacimiento, "energia": i.energia,
                "comidas": i.comidas, "hijas": i.hijas, "genoma": i.genoma} for i in individuos],
              open(os.path.join(carpeta, "poblacion_final.json"), "w", encoding="utf-8"), separators=(",", ":"))
    exportar_acuario(nombre, grabaciones, especies, fps)
    print(f"listo: {len(historia)} épocas en {time.time() - t0:.0f} s", flush=True)


def exportar_acuario(nombre: str, grabaciones: list, especies: list[str], fps: int) -> None:
    carpeta = os.path.join(RAIZ, "runs", nombre)
    historia = json.load(open(os.path.join(carpeta, "historia.json"), encoding="utf-8"))
    grupos = []
    for k, gr in enumerate(grabaciones):
        model = gr["model"]
        pz_todas, bs_todas = piezas_y_bisagras(model)
        criaturas = []
        for v in gr["vivos"]:
            p = v.ind.prefijo
            piezas = [x for x in pz_todas if x["nombre"].startswith(p)]
            base = int(v.cuerpos[0]) - 1
            bisagras = [dict(b, cuerpo=b["cuerpo"] - base) for b in bs_todas if b["nombre"].startswith(p)]
            cu = gr["cuadros"][v.ind.id]
            criaturas.append({"etiqueta": f"{v.ind.especie} #{v.ind.id}", "indice": v.ind.id, "puesto": len(criaturas) + 1,
                              "aptitud": v.ind.energia, "distancia": float(v.ind.comidas), "motivo": "completa",
                              "n_neuronas": len(v.ind.des["cerebro"]["neuronas"]), "n_piezas": len(piezas), "n_dof": v.ind.des["n_dof"],
                              "especie": v.ind.especie, "tarea": "luz", "energia": v.ind.energia, "comidas": v.ind.comidas,
                              "descripcion": f"{v.ind.especie} #{v.ind.id}, nacida a los {v.ind.nacimiento:.0f} s"
                                             f"{', hija de #' + str(v.ind.madre) if v.ind.madre is not None else ' (fundadora)'}; "
                                             f"energía {v.ind.energia:.0f}, {v.ind.comidas} comidas.",
                              "cerebro": morph.describir(v.ind.genoma), "piezas": piezas, "bisagras": bisagras,
                              "cuadros": _redondear_cuadros(cu, 4)})
        luces = [{"cuadros": [[c[j][0], c[j][1], c[j][2]] for c in gr["comida"]]} for j in range(N_COMIDA)]
        grupos.append({"generacion": k + 1, "etiqueta": f"época {gr['epoca'] + 1} · t = {gr['t']:.0f} s", "tarea": "luz",
                       "escena_comun": True, "luces": luces, "poblacion": len(criaturas), "criaturas": criaturas})
    datos = {"meta": {"corrida": nombre, "semilla": 0, "generaciones": len(historia), "poblacion": 0, "duracion": T_EPOCA,
                      "fps": fps, "cuales": "acuario", "fuente": "acuario", "etapa": 6, "especies": especies},
             "historia": historia, "log": [], "generaciones": grupos}
    destino = os.path.join(carpeta, "acuario.json")
    json.dump(datos, open(destino, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    shutil.copyfile(destino, os.path.join(RAIZ, "viewer", "acuario.json"))
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB, {len(grupos)} épocas grabadas")


def main() -> None:
    ap = argparse.ArgumentParser(description="Ecosistema con comida y energía (Etapa 6).")
    ap.add_argument("--nombre", default="eco01")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--epocas", type=int, default=30)
    ap.add_argument("--especies", default="anguila,pez,remador")
    ap.add_argument("--por-especie", type=int, default=4)
    ap.add_argument("--grabar", default="0,9,19,29", help="épocas que se graban para el visor (desde 0)")
    ap.add_argument("--fps", type=int, default=10)
    a = ap.parse_args()
    correr(a.nombre, a.semilla, a.epocas, a.especies.split(","), a.por_especie,
           tuple(int(x) for x in a.grabar.split(",") if x), a.fps)


if __name__ == "__main__":
    main()
