"""Evaluación y funciones de aptitud por tarea.

Etapa 1: nado. Sin gravedad, con arrastre viscoso por cara (fluido.py).
Aptitud = distancia final del centro de masa a su posición inicial (no al
origen: la cadena en reposo ya tiene su CoM a 0.645 m del origen, ver
BITACORA 0003), más un término que
premia la velocidad de la fase final (Sims: "más peso a la velocidad del
tramo final", para no premiar un impulso inicial seguido de deriva).

    aptitud = d(T) + PESO_FINAL * (d(T) - d(0.8 T))

Cortes tempranos:
  * sin movimiento: si a los T_SIN_MOVIMIENTO s el CoM se desplazó menos de
    UMBRAL_SIN_MOVIMIENTO m, se corta y la aptitud es la distancia actual.
  * inestabilidad numérica (NaN o advertencias de MuJoCo): aptitud 0.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np

import brain
from fluido import ArrastrePorCara

PASOS_CEREBRO_POR_FISICA = 2   # Sims: dos pasos de cerebro por paso de física
PESO_FINAL = 2.0
T_SIN_MOVIMIENTO = 3.0
UMBRAL_SIN_MOVIMIENTO = 0.02


def centro_de_masa(model: mujoco.MjModel, data: mujoco.MjData) -> np.ndarray:
    m = model.body_mass[1:]
    return (m[:, None] * data.xpos[1:]).sum(0) / m.sum()


def sensores_angulo(model: mujoco.MjModel, data: mujoco.MjData, limites: np.ndarray) -> list[float]:
    """Ángulo de cada bisagra normalizado por su límite a [-1, 1]."""
    n = len(limites)
    q = data.qpos[7:7 + n] / limites  # saltar la articulación libre (7 coordenadas)
    np.minimum(q, 1.0, out=q)
    np.maximum(q, -1.0, out=q)
    return q.tolist()


def limites_articulares(model: mujoco.MjModel) -> np.ndarray:
    lim = []
    for j in range(model.njnt):
        if model.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE:
            lim.append(max(abs(model.jnt_range[j][1]), 1e-3))
    return np.array(lim)


def evaluar_nado(model: mujoco.MjModel, data: mujoco.MjData, genoma: dict,
                 duracion: float = 10.0, grabar_cada: int = 0,
                 cortar_temprano: bool = True, arrastre: ArrastrePorCara | None = None,
                 tau_activacion: float = 0.0) -> dict:
    """Simula una criatura y devuelve aptitud y diagnósticos.

    `grabar_cada` > 0 guarda un cuadro cada tantos pasos de física (para exportar).
    """
    mujoco.mj_resetData(model, data)
    dt = model.opt.timestep
    dt_cerebro = dt / PASOS_CEREBRO_POR_FISICA
    lim = limites_articulares(model)
    cerebro = brain.crear(genoma, dt_cerebro)
    arrastre = arrastre or ArrastrePorCara(model)
    mujoco.mj_forward(model, data)
    com0 = centro_de_masa(model, data).copy()
    n_pasos = int(round(duracion / dt))
    paso_corte = int(round(T_SIN_MOVIMIENTO / dt))
    paso_final = int(round(0.8 * duracion / dt))
    d_08 = 0.0
    cuadros = []
    relleno = [0.0] * max(0, genoma.get("n_sensores", len(lim)) - len(lim))   # fotosensores apagados
    sens = sensores_angulo(model, data, lim) + relleno
    motivo = "completa"
    for k in range(n_pasos):
        salida = cerebro.pasos(PASOS_CEREBRO_POR_FISICA, sens)
        if tau_activacion > 0:
            # Activación muscular de primer orden: el torque no cambia de golpe.
            data.ctrl[:] += (np.asarray(salida) - data.ctrl) * min(1.0, dt / tau_activacion)
        else:
            data.ctrl[:] = salida
        arrastre.aplicar(model, data)
        mujoco.mj_step(model, data)
        sens = sensores_angulo(model, data, lim) + relleno
        if grabar_cada and k % grabar_cada == 0:
            com = centro_de_masa(model, data)
            cuadros.append({
                "t": round(float(data.time), 5),
                "pos": [[round(float(v), 5) for v in data.xpos[b]] for b in range(1, model.nbody)],
                "quat": [[round(float(v), 5) for v in data.xquat[b]] for b in range(1, model.nbody)],
                "q": [round(float(v), 4) for v in data.qpos[7:]],
                "ctrl": [round(float(v), 3) for v in data.ctrl],
                "com": [round(float(v), 5) for v in com],
            })
        if k == paso_final:
            d_08 = float(np.linalg.norm(centro_de_masa(model, data) - com0))
        if cortar_temprano and k == paso_corte:
            d = float(np.linalg.norm(centro_de_masa(model, data) - com0))
            if d < UMBRAL_SIN_MOVIMIENTO:
                motivo = "sin_movimiento"
                break
        if (k & 63) == 0 and (data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos))):
            return {"aptitud": 0.0, "distancia": 0.0, "motivo": "inestable", "cuadros": cuadros}
    if data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos)):
        return {"aptitud": 0.0, "distancia": 0.0, "motivo": "inestable", "cuadros": cuadros}
    d_fin = float(np.linalg.norm(centro_de_masa(model, data) - com0))
    if motivo == "sin_movimiento":
        aptitud = d_fin
    else:
        aptitud = d_fin + PESO_FINAL * (d_fin - d_08)
    if not math.isfinite(aptitud):
        aptitud = 0.0
    return {"aptitud": aptitud, "distancia": d_fin, "d_08": d_08, "motivo": motivo,
            "t_final": float(data.time), "com0": [float(v) for v in com0], "cuadros": cuadros}
