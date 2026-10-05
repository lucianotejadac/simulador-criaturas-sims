"""Etapa 5: competencia por un cubo entre dos criaturas (Sims, Artificial Life IV, 1994).

Dos criaturas en el mismo mundo, un cubo en el centro, cada una a DISTANCIA
del cubo mirando hacia él (la cabeza, cara −X, apunta al cubo). Gravedad,
suelo con fricción, asentamiento sin torques, y después DURACION segundos
de enfrentamiento. Las dos chocan de verdad: están en la misma simulación.

    aptitud_A = (d_B − d_A) / (d_A + d_B) + BONO_CONTACTO · [A tocó el cubo]

con d la distancia del centro de masa de cada una al centro del cubo al
final. Va de −1 a +1 (más el bono): dos quietas empatan en 0.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np

import develop_morfo as dm
import brain
from fitness import PASOS_CEREBRO_POR_FISICA
from tareas import ALTURA_INICIAL, K_FUERZA_CAMINATA, T_ASENTAMIENTO_MAX, TAU_ACTIVACION, UMBRAL_ASENTADA

DISTANCIA = 1.5          # m del centro del cubo a la cabeza de cada criatura
LADO_CUBO = 0.25         # m
MASA_CUBO = 1.0          # kg
DURACION = 10.0          # s
BONO_CONTACTO = 0.5
PASOS = (1.0 / 480, 1.0 / 720)   # aptitud robusta: mínimo entre dos pasos
COLORES = ("0.25 0.72 0.8 1", "0.95 0.55 0.25 1")


def mjcf_arena(genomas: list[dict], paso: float = PASOS[0]) -> tuple[str, list[dict]]:
    """XML con el suelo, el cubo y las criaturas (A en +X mirando a −X, B en −X mirando a +X)."""
    desarrollos = [dm.desarrollar(g, gravedad=True, paso=paso, k_fuerza=K_FUERZA_CAMINATA) for g in genomas]
    g = "0 0 -9.81"
    out = ['<mujoco model="arena">\n',
           '  <compiler angle="degree" autolimits="true"/>\n',
           f'  <option timestep="{paso:.6f}" gravity="{g}" integrator="implicitfast"/>\n',
           '  <default>\n',
           f'    <geom type="box" density="{dm.DENSIDAD_PIEZAS}" rgba="0.85 0.89 0.92 1"/>\n',
           '    <joint type="hinge"/>\n',
           '    <motor ctrlrange="-1 1"/>\n',
           '  </default>\n  <worldbody>\n',
           '    <geom name="suelo" type="plane" size="0 0 1" friction="1 0.005 0.0001" rgba="0.3 0.35 0.3 1"/>\n',
           f'    <body name="cubo" pos="0 0 {LADO_CUBO / 2:.4f}">\n      <freejoint name="cubo_raiz"/>\n'
           f'      <geom name="g_cubo" size="{LADO_CUBO / 2:.4f} {LADO_CUBO / 2:.4f} {LADO_CUBO / 2:.4f}" '
           f'mass="{MASA_CUBO}" rgba="0.95 0.85 0.3 1"/>\n    </body>\n']
    actuadores: list[str] = []
    for i, (des, prefijo) in enumerate(zip(desarrollos, ("A_", "B_"))):
        piezas = des["_piezas"]
        # La cabeza (cara −X) mira al cubo: A se coloca en +X sin rotar; B en −X girada 180° en Z.
        signo = 1.0 if i == 0 else -1.0
        pos_raiz = (signo * (DISTANCIA + piezas[0].dims[0] / 2.0), 0.0, 0.5)
        quat = (1.0, 0.0, 0.0, 0.0) if i == 0 else (0.0, 0.0, 0.0, 1.0)
        dm.escribir_cuerpo(out, actuadores, piezas[0], 0, prefijo, K_FUERZA_CAMINATA, pos_raiz, quat, COLORES[i])
    out.append("  </worldbody>\n  <actuator>\n")
    out.extend(actuadores)
    out.append("  </actuator>\n</mujoco>\n")
    return "".join(out), desarrollos


class Competidor:
    """Índices de una criatura dentro del modelo compartido."""

    def __init__(self, model: mujoco.MjModel, prefijo: str, cerebro_plano: dict):
        self.prefijo = prefijo
        self.cuerpos = [b for b in range(model.nbody)
                        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) or "").startswith(prefijo)]
        self.geoms = set(int(g) for g in range(model.ngeom) if int(model.geom_bodyid[g]) in self.cuerpos)
        self.bisagras = [j for j in range(model.njnt) if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE
                         and (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j) or "").startswith(prefijo)]
        self.qpos_idx = np.array([int(model.jnt_qposadr[j]) for j in self.bisagras], dtype=int)
        self.limites = np.array([max(abs(float(model.jnt_range[j][1])), 1e-3) for j in self.bisagras])
        self.ctrl_idx = np.array([a for a in range(model.nu)
                                  if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a) or "").startswith("m_" + prefijo)], dtype=int)
        self.cerebro_plano = cerebro_plano
        self.relleno = [0.0] * max(0, cerebro_plano["n_sensores"] - len(self.bisagras))
        self.masas = model.body_mass[self.cuerpos]
        self.toco = False

    def com(self, data: mujoco.MjData) -> np.ndarray:
        return (self.masas[:, None] * data.xpos[self.cuerpos]).sum(0) / self.masas.sum()

    def sensores(self, data: mujoco.MjData) -> list[float]:
        q = data.qpos[self.qpos_idx] / self.limites
        return [float(v) for v in np.clip(q, -1.0, 1.0)] + self.relleno

    def punto_mas_bajo(self, model: mujoco.MjModel, data: mujoco.MjData) -> float:
        esquinas = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=float)
        zmin = math.inf
        for g in self.geoms:
            R = data.geom_xmat[g].reshape(3, 3)
            pts = data.geom_xpos[g] + (esquinas * model.geom_size[g]) @ R.T
            zmin = min(zmin, float(pts[:, 2].min()))
        return zmin


def enfrentar(genomas: list[dict], paso: float = PASOS[0], grabar_cada: int = 0,
              duracion: float = DURACION) -> dict:
    """Un enfrentamiento. Devuelve aptitudes, distancias, contactos y cuadros (si se piden)."""
    xml, desarrollos = mjcf_arena(genomas, paso)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    comps = [Competidor(model, pref, des["cerebro"]) for pref, des in zip(("A_", "B_"), desarrollos)]
    cubo_b = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "cubo")
    cubo_g = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "g_cubo")
    cubo_q = int(model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cubo_raiz")])
    # Interpenetración en reposo (entre piezas de una misma criatura o entre criaturas).
    mujoco.mj_forward(model, data)
    for c in comps:
        raiz_q = int(model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, c.prefijo + "raiz")])
        data.qpos[raiz_q + 2] += ALTURA_INICIAL - c.punto_mas_bajo(model, data)
        mujoco.mj_forward(model, data)
    suelo = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "suelo")
    for i in range(data.ncon):
        c = data.contact[i]
        if suelo not in (c.geom1, c.geom2):
            return {"aptitudes": [0.0, 0.0], "motivo": "interpenetradas", "cuadros": []}
    dt = model.opt.timestep
    # Asentamiento sin torques.
    data.ctrl[:] = 0.0
    prev = [c.com(data).copy() for c in comps]
    chequeo = max(1, int(round(0.05 / dt)))
    asentadas = False
    for k in range(int(round(T_ASENTAMIENTO_MAX / dt))):
        mujoco.mj_step(model, data)
        if k % chequeo == 0 and k > 0 and data.time > 0.3:
            coms = [c.com(data) for c in comps]
            v = max(float(np.linalg.norm(a - b)) / (chequeo * dt) for a, b in zip(coms, prev))
            prev = [c.copy() for c in coms]
            if v < UMBRAL_ASENTADA:
                asentadas = True
                break
    if data.warning.number.sum() > 0:
        return {"aptitudes": [0.0, 0.0], "motivo": "inestable", "cuadros": []}
    # Si alguna no se asentó en 2 s, se arranca igual: con dos cuerpos grandes el
    # criterio de quietud conjunta es demasiado exigente y castigaría al rival.
    asentamiento = "completo" if asentadas else "incompleto"
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    t0 = float(data.time)
    cerebros = [brain.crear(c.cerebro_plano, dt / PASOS_CEREBRO_POR_FISICA) for c in comps]
    sens = [c.sensores(data) for c in comps]
    cuadros = []
    n_pasos = int(round(duracion / dt))
    for k in range(n_pasos):
        for c, cer, s in zip(comps, cerebros, sens):
            salida = cer.pasos(PASOS_CEREBRO_POR_FISICA, s)
            data.ctrl[c.ctrl_idx] += (np.asarray(salida) - data.ctrl[c.ctrl_idx]) * min(1.0, dt / TAU_ACTIVACION)
        mujoco.mj_step(model, data)
        sens = [c.sensores(data) for c in comps]
        for i in range(data.ncon):
            con = data.contact[i]
            if cubo_g in (con.geom1, con.geom2):
                otro = con.geom2 if con.geom1 == cubo_g else con.geom1
                for c in comps:
                    if otro in c.geoms:
                        c.toco = True
        if grabar_cada and k % grabar_cada == 0:
            cuadros.append({
                "t": round(float(data.time - t0), 5),
                "pos": [[round(float(v), 5) for v in data.xpos[b]] for c in comps for b in c.cuerpos],
                "quat": [[round(float(v), 5) for v in data.xquat[b]] for c in comps for b in c.cuerpos],
                "cubo": [round(float(v), 5) for v in data.xpos[cubo_b]] + [round(float(v), 5) for v in data.xquat[cubo_b]],
                "com": [[round(float(v), 5) for v in c.com(data)] for c in comps],
            })
        if (k & 63) == 0 and (data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos))):
            return {"aptitudes": [0.0, 0.0], "motivo": "inestable", "cuadros": cuadros}
    if data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos)):
        return {"aptitudes": [0.0, 0.0], "motivo": "inestable", "cuadros": cuadros}
    cubo = data.xpos[cubo_b]
    d = [float(np.linalg.norm(c.com(data)[:2] - cubo[:2])) for c in comps]
    base = (d[1] - d[0]) / max(1e-6, d[0] + d[1])
    aptitudes = [base + (BONO_CONTACTO if comps[0].toco else 0.0),
                 -base + (BONO_CONTACTO if comps[1].toco else 0.0)]
    return {"aptitudes": aptitudes, "distancias": d, "contactos": [comps[0].toco, comps[1].toco],
            "motivo": "completa", "asentamiento": asentamiento,
            "cubo_final": [float(v) for v in cubo], "cuadros": cuadros,
            "n_cuerpos": [len(c.cuerpos) for c in comps], "desarrollos": desarrollos, "model": model}


def enfrentar_robusto(genomas: list[dict]) -> dict:
    """Mínimo de la aptitud de cada criatura entre dos pasos de integración."""
    res = [enfrentar(genomas, paso) for paso in PASOS]
    apt = [min(r["aptitudes"][i] for r in res) for i in range(2)]
    base = res[0]
    base["aptitudes"] = apt
    base["aptitudes_pasos"] = [r["aptitudes"] for r in res]
    base["motivo"] = base["motivo"] if all(r["motivo"] == "completa" for r in res) else \
        next(r["motivo"] for r in res if r["motivo"] != "completa")
    base.pop("model", None)
    base.pop("desarrollos", None)
    return base
