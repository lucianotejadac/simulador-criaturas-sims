"""Tareas de la Etapa 3: nado (la de la Etapa 1) y caminata.

Caminata (Sims 1994): gravedad y suelo con fricción; la aptitud es el
desplazamiento horizontal del centro de masa. Antes de medir, la criatura se
asienta: se suelta a ALTURA_INICIAL sobre el suelo, sin torques, hasta que
su centro de masa casi no se mueve. Recién entonces arranca el cerebro y el
cronómetro, y la distancia se mide desde ahí, para que no gane nada por
caerse desde la posición inicial. Sims quitaba además la fricción durante el
asentamiento; aquí no, porque sin fricción la criatura que cae torcida
resbala sin fin y nunca se asienta (BITACORA 0010).

    aptitud = d_xy(T) + PESO_FINAL · (d_xy(T) − d_xy(0.8 T))

Si al final el centro de masa quedó por debajo de la mitad de su altura
asentada (se cayó), no se suma el premio de la fase final.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np

import fitness
from brain import Cerebro
from fitness import PASOS_CEREBRO_POR_FISICA, PESO_FINAL, T_SIN_MOVIMIENTO, UMBRAL_SIN_MOVIMIENTO
from fitness import centro_de_masa, limites_articulares, sensores_angulo

ALTURA_INICIAL = 0.10        # m entre el punto más bajo de la criatura y el suelo
T_ASENTAMIENTO_MAX = 2.0     # s
UMBRAL_ASENTADA = 0.01       # m/s del centro de masa


def punto_mas_bajo(model: mujoco.MjModel, data: mujoco.MjData) -> float:
    """Z mínima entre las esquinas de todas las cajas (en la pose actual)."""
    zmin = math.inf
    esquinas = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], dtype=float)
    for g in range(model.ngeom):
        if model.geom_type[g] != mujoco.mjtGeom.mjGEOM_BOX:
            continue
        R = data.geom_xmat[g].reshape(3, 3)
        c = data.geom_xpos[g]
        pts = c + (esquinas * model.geom_size[g]) @ R.T
        zmin = min(zmin, float(pts[:, 2].min()))
    return zmin


def elevar_al_suelo(model: mujoco.MjModel, data: mujoco.MjData, altura: float = ALTURA_INICIAL) -> None:
    """Deja el punto más bajo de la criatura a `altura` sobre el plano z = 0."""
    mujoco.mj_forward(model, data)
    data.qpos[2] += altura - punto_mas_bajo(model, data)
    mujoco.mj_forward(model, data)


def evaluar_caminata(model: mujoco.MjModel, data: mujoco.MjData, genoma: dict,
                     duracion: float = 10.0, grabar_cada: int = 0,
                     cortar_temprano: bool = True, tau_activacion: float = 0.0) -> dict:
    mujoco.mj_resetData(model, data)
    elevar_al_suelo(model, data)
    dt = model.opt.timestep
    # --- asentamiento: sin torques ---
    data.ctrl[:] = 0.0
    asentada = False
    com_prev = centro_de_masa(model, data).copy()
    pasos_chequeo = max(1, int(round(0.05 / dt)))
    for k in range(int(round(T_ASENTAMIENTO_MAX / dt))):
        mujoco.mj_step(model, data)
        if k % pasos_chequeo == 0 and k > 0:
            com = centro_de_masa(model, data)
            v = float(np.linalg.norm(com - com_prev)) / (pasos_chequeo * dt)
            com_prev = com.copy()
            if v < UMBRAL_ASENTADA and data.time > 0.3:
                asentada = True
                break
    if not asentada or data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos)):
        return {"aptitud": 0.0, "distancia": 0.0, "motivo": "no_asentada", "cuadros": [],
                "t_asentamiento": float(data.time), "asentada": asentada,
                "warnings": [int(v) for v in data.warning.number]}
    t_asent = float(data.time)
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)
    # --- medición ---
    lim = limites_articulares(model)
    cerebro = Cerebro(genoma, dt / PASOS_CEREBRO_POR_FISICA)
    com0 = centro_de_masa(model, data).copy()
    z0 = float(com0[2])
    n_pasos = int(round(duracion / dt))
    paso_corte = int(round(T_SIN_MOVIMIENTO / dt))
    paso_final = int(round(0.8 * duracion / dt))
    d_08 = 0.0
    cuadros = []
    sens = sensores_angulo(model, data, lim)
    motivo = "completa"

    def d_xy() -> float:
        c = centro_de_masa(model, data)
        return float(math.hypot(c[0] - com0[0], c[1] - com0[1]))

    for k in range(n_pasos):
        salida = None
        for _ in range(PASOS_CEREBRO_POR_FISICA):
            salida = cerebro.paso(sens)
        if tau_activacion > 0:
            data.ctrl[:] += (np.asarray(salida) - data.ctrl) * min(1.0, dt / tau_activacion)
        else:
            data.ctrl[:] = salida
        mujoco.mj_step(model, data)
        sens = sensores_angulo(model, data, lim)
        if grabar_cada and k % grabar_cada == 0:
            com = centro_de_masa(model, data)
            cuadros.append({
                "t": round(float(data.time - t_asent), 5),
                "pos": [[round(float(v), 5) for v in data.xpos[b]] for b in range(1, model.nbody)],
                "quat": [[round(float(v), 5) for v in data.xquat[b]] for b in range(1, model.nbody)],
                "q": [round(float(v), 4) for v in data.qpos[7:]],
                "ctrl": [round(float(v), 3) for v in data.ctrl],
                "com": [round(float(v), 5) for v in com],
            })
        if k == paso_final:
            d_08 = d_xy()
        if cortar_temprano and k == paso_corte and d_xy() < UMBRAL_SIN_MOVIMIENTO:
            motivo = "sin_movimiento"
            break
        if (k & 63) == 0 and (data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos))):
            return {"aptitud": 0.0, "distancia": 0.0, "motivo": "inestable", "cuadros": cuadros}
    if data.warning.number.sum() > 0 or not np.all(np.isfinite(data.qpos)):
        return {"aptitud": 0.0, "distancia": 0.0, "motivo": "inestable", "cuadros": cuadros}
    d_fin = d_xy()
    z_fin = float(centro_de_masa(model, data)[2])
    caida = z_fin < 0.5 * z0
    if motivo == "sin_movimiento" or caida:
        aptitud = d_fin
    else:
        aptitud = d_fin + PESO_FINAL * (d_fin - d_08)
    if not math.isfinite(aptitud):
        aptitud = 0.0
    return {"aptitud": aptitud, "distancia": d_fin, "d_08": d_08, "motivo": motivo, "caida": caida,
            "z0": z0, "z_fin": z_fin, "t_asentamiento": t_asent, "t_final": float(data.time - t_asent),
            "com0": [float(v) for v in com0], "cuadros": cuadros}


TAU_ACTIVACION = 0.05   # s; Etapa 3: activación muscular de primer orden (BITACORA 0010)
K_FUERZA_CAMINATA = 300.0   # en tierra la escala es el peso: torque/peso ~3, no ~10 (BITACORA 0010)
PASOS_CAMINATA = (1.0 / 480, 1.0 / 720, 1.0 / 960)   # aptitud = mínimo entre tres pasos de integración


def compilar_tarea(genoma: dict, tarea: str, paso: float | None = None):
    import develop_morfo as dm
    if tarea == "caminata":
        return dm.compilar(genoma, gravedad=True, paso=paso or PASOS_CAMINATA[0], k_fuerza=K_FUERZA_CAMINATA)
    return dm.compilar(genoma, gravedad=False, paso=paso or dm.PASO_FISICA)


def evaluar(model: mujoco.MjModel, data: mujoco.MjData, genoma: dict, tarea: str,
            duracion: float = 10.0, grabar_cada: int = 0, cortar_temprano: bool = True,
            tau_activacion: float = TAU_ACTIVACION) -> dict:
    if tarea == "nado":
        return fitness.evaluar_nado(model, data, genoma, duracion, grabar_cada, cortar_temprano,
                                    tau_activacion=tau_activacion)
    if tarea == "caminata":
        return evaluar_caminata(model, data, genoma, duracion, grabar_cada, cortar_temprano, tau_activacion)
    raise ValueError("tarea desconocida: " + tarea)
