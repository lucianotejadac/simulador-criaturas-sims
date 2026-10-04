import os
import random
import sys

import mujoco
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import develop_morfo as dm  # noqa: E402
import fitness  # noqa: E402
from genome import ejemplos, morph  # noqa: E402


def test_genomas_aleatorios_validos():
    rng = random.Random(0)
    for _ in range(200):
        assert morph.es_valido(morph.genoma_aleatorio(rng))


def test_mutaciones_mantienen_validez():
    rng = random.Random(1)
    g = morph.genoma_aleatorio(rng)
    for _ in range(1500):
        g = morph.mutar(g, rng)
        assert morph.es_valido(g), morph.describir(g)


def test_cruce_e_injerto_validos():
    rng = random.Random(2)
    pob = [morph.genoma_aleatorio(rng, 3) for _ in range(12)]
    for _ in range(300):
        a, b = rng.sample(pob, 2)
        h, h2 = morph.cruzar(a, b, rng), morph.injertar(a, b, rng)
        assert morph.es_valido(h) and morph.es_valido(h2)
        pob[rng.randrange(len(pob))] = morph.mutar(rng.choice([h, h2]), rng)


def test_recolectar_nodos_y_neuronas():
    g = ejemplos.cadena4()
    # Nodo suelto, no alcanzable desde la raíz, y neurona de la cabeza que nadie usa.
    g["nodos"].append(ejemplos._nodo((0.1, 0.1, 0.1), "bisagra", 30, 1, [], [["c", 0, 0.0]], []))
    g["nodos"][0]["neuronas"].append(ejemplos._neu(9, "sin", ["c", 0, 1.0]))
    r = morph.recolectar(g)
    assert len(r["nodos"]) == 2
    ids_cabeza = [n["id"] for n in r["nodos"][0]["neuronas"]]
    assert ids_cabeza == [ejemplos.OSC]            # OSC vive porque el segmento la lee con "p"; la 9 no
    assert morph.es_valido(r)


def test_cadena4_reproduce_la_etapa_1():
    r = dm.desarrollar(ejemplos.cadena4())
    assert len(r["piezas"]) == 4 and r["n_dof"] == 3
    m = mujoco.MjModel.from_xml_string(r["xml"])
    assert m.nu == 3 and m.nbody == 5
    # La onda viajera: cada segmento lee a su madre. El primer segmento lee la
    # oscilación de la cabeza; los siguientes, el retardo del segmento anterior.
    cer = r["cerebro"]
    assert cer["n_sensores"] == 3 and len(cer["efectores"]) == 3
    assert all(e[0] == "n" for e in cer["efectores"])
    d = mujoco.MjData(m)
    assert not dm.interpenetra(m, d)
    res = fitness.evaluar_nado(m, d, cer, duracion=4.0, cortar_temprano=False)
    assert res["motivo"] == "completa" and res["distancia"] > 0.2


def test_limite_recursivo_y_terminal():
    g = ejemplos.cadena4()
    g["nodos"][1]["rec"] = 2
    assert len(dm.desarrollar(g)["piezas"]) == 3
    # Conexión "solo terminal": una pieza extra solo en la última instancia.
    g["nodos"].append(ejemplos._nodo((0.1, 0.1, 0.1), "bisagra", 30, 1, [], [["c", 0, 0.0]], []))
    g["nodos"][1]["conexiones"].append(ejemplos._con(2, 4, terminal=True))
    piezas = dm.desarrollar(g)["piezas"]
    assert len(piezas) == 4 and sum(p["nodo"] == 2 for p in piezas) == 1


def test_reflexion_espeja_posicion_y_signo():
    r = dm.desarrollar(ejemplos.ciempies())
    m = mujoco.MjModel.from_xml_string(r["xml"])
    patas = [p for p in r["piezas"] if p["nodo"] == 2]
    assert len(patas) == 8 and sum(p["espejo"] for p in patas) == 4
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    ys = {}
    for p in patas:
        b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, p["nombre"])
        ys.setdefault(p["madre"], []).append((p["espejo"], float(d.xpos[b][1])))
    for madre, lista in ys.items():
        (e1, y1), (e2, y2) = lista
        assert e1 != e2 and np.isclose(y1, -y2, atol=1e-6) and abs(y1) > 0.05
    # El torque de las patas reflejadas tiene signo invertido.
    for p in patas:
        a = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, f"m_{p['nombre']}_j0")
        assert (m.actuator_gear[a][0] < 0) == p["espejo"]
    assert not dm.interpenetra(m, d)


def test_interpenetracion_detectada():
    g = ejemplos.cadena4()
    # Segundo segmento doblado 180° sobre la madre: se superponen.
    g["nodos"][1]["conexiones"][0]["rot"] = [0.0, 0.0, 180.0]
    r = dm.desarrollar(g)
    m = mujoco.MjModel.from_xml_string(r["xml"])
    assert dm.interpenetra(m, mujoco.MjData(m))


def test_ejemplos_compilan_y_nadan():
    for nombre, fabrica in ejemplos.EJEMPLOS.items():
        g = fabrica()
        assert morph.es_valido(g), nombre
        m, d, r = dm.compilar(g)
        res = fitness.evaluar_nado(m, d, r["cerebro"], duracion=3.0, cortar_temprano=False)
        assert res["motivo"] == "completa", nombre
        assert res["distancia"] > 0.02, (nombre, res["distancia"])


def test_demasiadas_piezas():
    g = ejemplos.ciempies()
    g["nodos"][1]["rec"] = 4
    g["nodos"][2]["conexiones"].append(ejemplos._con(2, 0))   # patas que crecen patas
    g["nodos"][2]["rec"] = 4
    try:
        dm.desarrollar(g)
        assert False, "debió rechazar"
    except ValueError as e:
        assert "piezas" in str(e)
