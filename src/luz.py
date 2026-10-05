"""Etapa 4: seguimiento de luz con fotosensores (Sims 1994).

Cada pieza lleva un fotosensor en su centro que entrega las tres componentes
de la dirección unitaria hacia la luz, expresada en el marco de la pieza. En
una pieza reflejada se invierte la componente Y, igual que el signo de sus
sensores articulares, para que el mismo cerebro produzca la conducta espejo.

Aptitud: promedio, sobre varios ensayos con la luz en posiciones distintas,
de la velocidad media de acercamiento al punto de luz (m/s):

    v_i = (d_i(0) − d_i(T)) / T,   aptitud = media(v_i)

Agua sin gravedad con el arrastre por cara de la Etapa 1. Si en el primer
ensayo la criatura no se mueve a los 3 s, los demás ensayos no se corren.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np

import brain
from fitness import PASOS_CEREBRO_POR_FISICA, T_SIN_MOVIMIENTO, UMBRAL_SIN_MOVIMIENTO
from fitness import centro_de_masa, limites_articulares, sensores_angulo
from fluido import ArrastrePorCara

DISTANCIA_LUZ = 4.0
LUCES = [[DISTANCIA_LUZ * math.cos(math.radians(a)), DISTANCIA_LUZ * math.sin(math.radians(a)), 0.0]
         for a in (90.0, 210.0, 330.0)]   # tres ensayos: a un lado, atrás-izquierda, adelante-derecha
DURACION_ENSAYO = 6.0


def sensores_luz(model: mujoco.MjModel, data: mujoco.MjData, luz: np.ndarray, espejos: np.ndarray) -> np.ndarray:
    """Dirección unitaria a la luz en el marco de cada pieza, aplanada (3 por pieza)."""
    pos = data.xpos[1:]
    d = luz[None, :] - pos
    norma = np.linalg.norm(d, axis=1, keepdims=True)
    d = d / np.maximum(norma, 1e-9)
    R = data.xmat[1:].reshape(-1, 3, 3)
    local = np.einsum("nji,nj->ni", R, d)          # Rᵀ d
    local[:, 1] *= np.where(espejos, -1.0, 1.0)
    return local.reshape(-1)


def evaluar_luz(model: mujoco.MjModel, data: mujoco.MjData, genoma: dict, espejos: list[bool],
                luces: list | None = None, duracion: float = DURACION_ENSAYO, grabar_cada: int = 0,
                cortar_temprano: bool = True, tau_activacion: float = 0.05) -> dict:
    luces = luces or LUCES
    espejos_arr = np.array(espejos, dtype=bool)
    dt = model.opt.timestep
    lim = limites_articulares(model)
    arrastre = ArrastrePorCara(model)
    n_pasos = int(round(duracion / dt))
    paso_corte = int(round(T_SIN_MOVIMIENTO / dt))
    velocidades = []
    cuadros = []
    motivo = "completa"
    n_dof = len(lim)
    for ensayo, luz in enumerate(luces):
        luz = np.asarray(luz, dtype=float)
        mujoco.mj_resetData(model, data)
        mujoco.mj_forward(model, data)
        cerebro = brain.crear(genoma, dt / PASOS_CEREBRO_POR_FISICA)
        com0 = centro_de_masa(model, data).copy()
        d0 = float(np.linalg.norm(luz - com0))
        sens = list(sensores_angulo(model, data, lim)) + list(sensores_luz(model, data, luz, espejos_arr))
        cortada = False
        for k in range(n_pasos):
            salida = cerebro.pasos(PASOS_CEREBRO_POR_FISICA, sens)
            if tau_activacion > 0:
                data.ctrl[:] += (np.asarray(salida) - data.ctrl) * min(1.0, dt / tau_activacion)
            else:
                data.ctrl[:] = salida
            arrastre.aplicar(model, data)
            mujoco.mj_step(model, data)
            sens = list(sensores_angulo(model, data, lim)) + list(sensores_luz(model, data, luz, espejos_arr))
            if grabar_cada and ensayo == 0 and k % grabar_cada == 0:
                com = centro_de_masa(model, data)
                cuadros.append({
                    "t": round(float(data.time), 5),
                    "pos": [[round(float(v), 5) for v in data.xpos[b]] for b in range(1, model.nbody)],
                    "quat": [[round(float(v), 5) for v in data.xquat[b]] for b in range(1, model.nbody)],
                    "q": [round(float(v), 4) for v in data.qpos[7:7 + n_dof]],
                    "ctrl": [round(float(v), 3) for v in data.ctrl],
                    "com": [round(float(v), 5) for v in com],
                })
            if cortar_temprano and ensayo == 0 and k == paso_corte:
                if float(np.linalg.norm(centro_de_masa(model, data) - com0)) < UMBRAL_SIN_MOVIMIENTO:
                    cortada = True
                    motivo = "sin_movimiento"
                    break
            if (k & 63) == 0 and (data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos))):
                return {"aptitud": 0.0, "distancia": 0.0, "motivo": "inestable", "cuadros": cuadros,
                        "luz": list(luces[0])}
        if data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos)):
            return {"aptitud": 0.0, "distancia": 0.0, "motivo": "inestable", "cuadros": cuadros, "luz": list(luces[0])}
        d_fin = float(np.linalg.norm(luz - centro_de_masa(model, data)))
        velocidades.append((d0 - d_fin) / max(1e-9, float(data.time)))
        if cortada:
            break
    aptitud = float(np.mean(velocidades)) if velocidades else 0.0
    if not math.isfinite(aptitud):
        aptitud = 0.0
    return {"aptitud": aptitud, "distancia": aptitud * duracion, "motivo": motivo,
            "velocidades": velocidades, "luz": list(luces[0]), "luces": [list(l) for l in luces],
            "t_final": float(data.time), "cuadros": cuadros}
