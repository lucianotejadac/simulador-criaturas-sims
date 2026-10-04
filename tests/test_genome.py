import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from brain import Cerebro  # noqa: E402
from genome import neural  # noqa: E402

NS, NE = 3, 3


def test_genoma_aleatorio_valido():
    rng = random.Random(0)
    for _ in range(200):
        g = neural.genoma_aleatorio(rng, NS, NE)
        assert neural.es_valido(g)
        assert len(g["efectores"]) == NE


def test_mutaciones_mantienen_validez():
    rng = random.Random(1)
    g = neural.genoma_aleatorio(rng, NS, NE)
    for _ in range(2000):
        g = neural.mutar(g, rng)
        assert neural.es_valido(g), neural.describir(g)
        assert len(g["neuronas"]) <= neural.MAX_NEURONAS


def test_cruce_e_injerto_validos():
    rng = random.Random(2)
    pob = [neural.genoma_aleatorio(rng, NS, NE) for _ in range(20)]
    for _ in range(500):
        a, b = rng.sample(pob, 2)
        h = neural.cruzar(a, b, rng)
        assert neural.es_valido(h)
        h2 = neural.injertar(a, b, rng)
        assert neural.es_valido(h2)
        pob[rng.randrange(20)] = neural.mutar(rng.choice([h, h2]), rng)


def test_recolectar_elimina_desconectadas():
    g = {"n_sensores": NS,
         "neuronas": [{"f": "sin", "in": [["s", 0, 1.0]]},
                      {"f": "cos", "in": [["s", 1, 1.0]]},   # nadie la usa
                      {"f": "sum", "in": [["n", 0, 1.0], ["c", 0, 0.5], ["n", 2, 0.1]]}],
         "efectores": [["n", 2, 1.0], ["s", 0, 1.0], ["c", 0, 0.0]]}
    r = neural.recolectar(g)
    assert len(r["neuronas"]) == 2
    assert r["neuronas"][1]["f"] == "sum"
    assert r["neuronas"][1]["in"][2] == ["n", 1, 0.1]  # recurrencia reindexada
    assert r["efectores"][0] == ["n", 1, 1.0]
    assert neural.es_valido(r)


def test_cerebro_todas_las_funciones_sin_nan():
    rng = random.Random(3)
    for f in neural.NOMBRES_FUNCIONES:
        ar = neural.FUNCIONES[f]
        g = {"n_sensores": NS,
             "neuronas": [{"f": f, "in": [["s", i % NS, 3.0] for i in range(ar)]},
                          {"f": "sum", "in": [["n", 0, 2.0], ["n", 1, 1.0], ["c", 0, 0.0]]}],
             "efectores": [["n", 0, 1.0], ["n", 1, 1.0], ["c", 0, 0.3]]}
        c = Cerebro(g, 0.004)
        for k in range(500):
            s = [math.sin(k * 0.1), 0.0, -0.9]
            out = c.paso(s)
            assert all(math.isfinite(v) and -1 <= v <= 1 for v in out), f
        assert all(math.isfinite(v) for v in c.val)


def test_oscilador_oscila():
    g = {"n_sensores": NS,
         "neuronas": [{"f": "oscillate-wave", "in": [["c", 0, 1.0], ["c", 0, 1.0], ["c", 0, 0.0]]}],
         "efectores": [["n", 0, 1.0], ["c", 0, 0.0], ["c", 0, 0.0]]}
    c = Cerebro(g, 0.05)
    vals = [c.paso([0, 0, 0])[0] for _ in range(20)]
    assert max(vals) > 0.9 and min(vals) < -0.9


def test_operadores_con_genomas_vacios():
    rng = random.Random(4)
    vacio = {"n_sensores": NS, "neuronas": [], "efectores": [["c", 0, 0.0]] * NE}
    lleno = neural.genoma_aleatorio(rng, NS, NE, n_neuronas=3)
    for a, b in [(vacio, vacio), (vacio, lleno), (lleno, vacio)]:
        for _ in range(50):
            assert neural.es_valido(neural.cruzar(a, b, rng))
            assert neural.es_valido(neural.injertar(a, b, rng))
            assert neural.es_valido(neural.mutar(a, rng))
