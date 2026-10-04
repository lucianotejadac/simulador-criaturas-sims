import os
import random
import sys

import mujoco
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import develop  # noqa: E402
import fitness  # noqa: E402
from genome import neural  # noqa: E402


def test_cuerpo_fijo_compila():
    c = develop.CuerpoFijo()
    m = mujoco.MjModel.from_xml_string(develop.mjcf_cuerpo_fijo(c))
    assert m.nbody == 5          # mundo + 4 piezas
    assert m.nu == 3             # 3 motores
    bisagras = [j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE]
    assert len(bisagras) == 3
    ejes = [tuple(m.jnt_axis[j]) for j in bisagras]
    assert ejes == [(0, 0, 1), (0, 0, 1), (0, 0, 1)]
    # Torque máximo proporcional al área de sección (ley cuadrado-cubo).
    assert np.isclose(m.actuator_gear[0][0], develop.K_FUERZA * c.ancho ** 2)
    assert m.opt.gravity[2] == 0.0 and m.opt.density == 0  # el agua la pone fluido.py
    assert np.isclose(m.body_mass[1], c.largo * c.ancho ** 2 * c.densidad_piezas)


def test_evaluacion_nado_devuelve_aptitud_finita():
    m = mujoco.MjModel.from_xml_string(develop.mjcf_cuerpo_fijo())
    d = mujoco.MjData(m)
    rng = random.Random(5)
    g = neural.genoma_aleatorio(rng, 3, 3)
    r = fitness.evaluar_nado(m, d, g, duracion=2.0, grabar_cada=4)
    assert np.isfinite(r["aptitud"]) and r["aptitud"] >= 0
    assert len(r["cuadros"]) > 0 and len(r["cuadros"][0]["pos"]) == 4


def test_cerebro_vacio_no_se_mueve_y_se_corta():
    m = mujoco.MjModel.from_xml_string(develop.mjcf_cuerpo_fijo())
    d = mujoco.MjData(m)
    g = {"n_sensores": 3, "neuronas": [], "efectores": [["c", 0, 0.0]] * 3}
    r = fitness.evaluar_nado(m, d, g, duracion=10.0)
    assert r["motivo"] == "sin_movimiento"
    assert r["t_final"] < 4.0
