"""Bestiario: criaturas acuáticas escritas a mano, con cerebro verificado y
fototaxis cableada, para poblar el ecosistema de la Etapa 6.

Restricción física que decide qué animales son posibles: el agua es de
arrastre lineal (régimen de Stokes) y rige el teorema de la vieira: un
movimiento igual de ida que de vuelta no desplaza nada. Avanza lo que rompe
la simetría temporal: ondas viajeras (anguila, pez, renacuajo), remos con
desfase (ciempiés, raya) y aletas que giran mientras baten (remador). Una
medusa o un calamar de cajas no funcionarían (BITACORA 0020).

Fototaxis cableada: en cada nodo con cadena de retardo, la suma que recibe
la oscilación de la madre suma además la componente lateral de la dirección
a la luz (entrada "l" 1) con un peso `sesgo`: el cuerpo se curva hacia la
luz mientras ondula. El signo se eligió probando (BITACORA 0020).
"""
from __future__ import annotations

import copy

from genome.ejemplos import LAG, LAG_IN, OSC, OSC_Q, _con, _neu, _nodo, _segmento_con_lag, bilateral, ciempies, pez

SESGO_LUZ = 2.0
# Signo y peso del sesgo por especie (probado en BITACORA 0020; el remador tiene la cola en la cara -X).
SESGOS = {"anguila": (2.0, 0.0), "pez": (4.0, 0.0), "renacuajo": (4.0, 0.0), "raya": (4.0, 0.0),
          "ciempies_acuatico": (0.0, -1.5), "remador": (-2.0, 0.0)}   # (sesgo del cuerpo, diferencial de remos)
DESCRIPCIONES = {
    "anguila": "Cabeza chica y seis segmentos delgados con onda viajera. La más rápida y la que mejor gira.",
    "pez": "El ancestro de la Etapa 4: cola que se afina, aleta caudal y pectorales en cuadratura.",
    "renacuajo": "Cabeza grande y cola fina: mucha masa, poco empuje.",
    "raya": "Cuerpo corto y ancho con placas laterales que baten. Las placas no empujan ni giran: solo la onda del cuerpo.",
    "ciempies_acuatico": "Patas con articulación universal que reman y giran en cuadratura (plumeo). Gira apenas.",
    "remador": "El bilateral de la Etapa 2: aletas universales que baten y barren en cuadratura, y una cola corta.",
}





MODA, PMOD = 6, 7   # modulación diferencial: amplitud = 1 + sesgo·luz_lateral (las reflejadas, al revés)


def con_fototaxis(g: dict, sesgo: float = SESGO_LUZ, diferencial: float = 0.0) -> dict:
    """Agrega la componente lateral de la luz a toda neurona LAG_IN (el cuerpo se curva) y,
    si `diferencial` no es cero, modula la amplitud de los efectores que leen p:LAG en los
    nodos sin cadena de retardo (placas, patas): el lado de la luz rema distinto."""
    g = copy.deepcopy(g)
    for nodo in g["nodos"]:
        for neu in nodo["neuronas"]:
            if neu["id"] == LAG_IN and neu["f"] == "sum":
                neu["in"][2] = ["l", 1, sesgo]
        if diferencial and not any(n["id"] == LAG for n in nodo["neuronas"]):
            efs = [e for e in nodo["efectores"] if e[0] == "p" and e[1] == LAG]
            if efs:
                nodo["neuronas"].append(_neu(MODA, "sum", ["c", 0, 1.0], ["l", 1, diferencial], ["c", 0, 0.0]))
                nodo["neuronas"].append(_neu(PMOD, "product", ["p", LAG, 1.0], ["n", MODA, 1.0], ["c", 0, 1.0]))
                for e in efs:
                    e[0], e[1] = "n", PMOD
    return g


def anguila() -> dict:
    cabeza = _nodo((0.15, 0.09, 0.09), "rigida", 60, 1,
                   [_neu(OSC, "oscillate-wave", ["c", 0, 1.0], ["c", 0, 1.4], ["c", 0, 0.0])],
                   [], [_con(1, 0)])
    cuerpo = _segmento_con_lag((0.25, 0.08, 0.08), "bisagra", 60, 6, [_con(1, 0, escala=0.97)], ganancia=2.2)
    return {"siguiente_id": 10, "raiz": 0, "nodos": [cabeza, cuerpo], "central": []}


def renacuajo() -> dict:
    cabeza = _nodo((0.30, 0.26, 0.20), "rigida", 60, 1,
                   [_neu(OSC, "oscillate-wave", ["c", 0, 1.0], ["c", 0, 2.0], ["c", 0, 0.0])],
                   [], [_con(1, 0)])
    cola = _segmento_con_lag((0.22, 0.06, 0.12), "bisagra", 60, 4,
                             [_con(1, 0, escala=0.8), _con(2, 0, terminal=True)], ganancia=2.2)
    caudal = _nodo((0.14, 0.04, 0.26), "bisagra", 35, 1, [], [["p", LAG, 1.3]], [])
    return {"siguiente_id": 10, "raiz": 0, "nodos": [cabeza, cola, caudal], "central": []}


def raya() -> dict:
    """Cuerpo corto y ancho; en cada segmento un par de placas laterales reflejadas que baten
    arriba y abajo con el desfase del segmento (onda que viaja de adelante hacia atrás)."""
    cabeza = _nodo((0.20, 0.30, 0.08), "rigida", 60, 1,
                   [_neu(OSC, "oscillate-wave", ["c", 0, 1.0], ["c", 0, 1.4], ["c", 0, 0.0])],
                   [], [_con(1, 0)])
    cuerpo = _segmento_con_lag((0.18, 0.28, 0.07), "bisagra", 40, 4,
                               [_con(1, 0, escala=0.9), _con(2, 2, u=0.0, v=0.0), _con(2, 2, u=0.0, v=0.0, reflejo=True)],
                               ganancia=1.6)
    placa = _nodo((0.30, 0.16, 0.04), "universal", 45, 1, [], [["p", LAG, 2.0], ["c", 0, 0.0]], [])
    return {"siguiente_id": 10, "raiz": 0, "nodos": [cabeza, cuerpo, placa], "central": []}


DLAG = 5   # derivada del retardo: la cuadratura de la onda, para el plumeo de las patas


def ciempies_acuatico() -> dict:
    """Patas con articulación universal: barren (z) con la onda del segmento y giran (y)
    con su derivada, en cuadratura, como un remo que se pone de canto al volver.
    Una pata que solo va y viene no empuja en arrastre lineal (teorema de la vieira)."""
    g = ciempies()
    cuerpo = g["nodos"][1]
    cuerpo["limite"] = 20.0          # cuerpo casi rígido: reman las patas
    cuerpo["neuronas"].append(_neu(DLAG, "differentiate", ["n", LAG, 0.16]))
    pata = g["nodos"][2]
    pata["dims"] = [0.32, 0.05, 0.12]
    pata["art"] = "universal"
    pata["limite"] = 50.0
    pata["efectores"] = [["p", DLAG, 1.0], ["p", LAG, 1.5]]
    return g


BESTIARIO = {
    "anguila": anguila, "pez": pez, "renacuajo": renacuajo, "raya": raya,
    "ciempies_acuatico": ciempies_acuatico, "remador": bilateral,
}


def especie(nombre: str) -> dict:
    """Genoma de la especie con su fototaxis cableada."""
    sesgo, dif = SESGOS[nombre]
    return con_fototaxis(BESTIARIO[nombre](), sesgo, dif)
