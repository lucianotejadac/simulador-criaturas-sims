"""Pruebas mínimas de la Etapa 8 (células -> cuerpos)."""
import random
import sys
import os

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import celulas as C  # noqa: E402


def _cadena(n, retardo=1.0, cilio=1):
    cells = []
    for i in range(n):
        g = {"adhesion": 1.0, "cilio": cilio, "amplitud": 1.0, "frecuencia": 1.0, "retardo": retardo, "sesgo": 0.0, "largo": 0.2}
        c = C.Celula(i, g, 60.0, 0.0)
        if i > 0:
            c.madre = cells[-1]
            c.cara = 0
            cells[-1].hijas.append(c)
        cells.append(c)
    return cells


def _desplazamiento(cells, segundos=20.0):
    C.AGITACION = 0.0
    grupos = C.grupos_de(cells)
    E = C.Epoca(grupos, {grupos[0][0].id: np.array([0.0, 0.0, 0.0])}, {})
    E.comidos_por_depredador = set()
    comida = np.array([[100.0, 100.0, 0.0, 1.0]])
    rng = np.random.default_rng(0)
    for _ in range(int(segundos / C.DT)):
        E.paso(comida, rng, None)
    return float(np.hypot(*(E.lote.pose[0, :2] - E.pose_inicial[0, :2])))


def test_una_celula_nada_con_flagelo_y_no_sin_el():
    assert 0.8 < _desplazamiento(_cadena(1)) < 1.6
    assert _desplazamiento(_cadena(1, cilio=0)) < 0.01


def test_el_par_es_el_valle_y_la_onda_paga_desde_tres():
    sola, par, tres, tres_sin, cuatro = (_desplazamiento(_cadena(1)), _desplazamiento(_cadena(2)),
                                          _desplazamiento(_cadena(3, retardo=1.0)), _desplazamiento(_cadena(3, retardo=0.0)),
                                          _desplazamiento(_cadena(4, retardo=1.0)))
    assert par < sola                 # dos células: mismo empuje por célula y más arrastre, sin onda
    assert tres > 1.4 * sola          # tres con desfase: empuje + onda viajera
    assert tres_sin < sola            # sin desfase el movimiento articular es recíproco
    assert cuatro > 2.0 * sola


def test_grupos_de_corta_arboles():
    cells = _cadena(4)
    assert [len(g) for g in C.grupos_de(cells)] == [4]
    # muere la segunda: la tercera y la cuarta siguen juntas
    muerta = cells[1]
    for h in muerta.hijas:
        h.madre = None
    muerta.madre.hijas.remove(muerta)
    vivas = [c for c in cells if c is not muerta]
    assert sorted(len(g) for g in C.grupos_de(vivas)) == [1, 2]


def test_mutacion_mantiene_rangos():
    rng = random.Random(3)
    g = C.genoma_inicial(rng)
    for _ in range(500):
        g = C.mutar(g, rng)
        assert 0.0 <= g["adhesion"] <= 1.0 and g["cilio"] in (0, 1)
        assert 0.08 <= g["largo"] <= 0.4 and 0.2 <= g["frecuencia"] <= 3.0
