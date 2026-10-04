"""Genomas morfológicos diseñados a mano para verificar el desarrollo (Etapa 2).

Tres criaturas con cerebro escrito a mano:
  * cadena4: la cadena de la Etapa 1 escrita como genoma recursivo (cabeza + un
    nodo segmento con límite recursivo 3). La onda viajera sale de la recursión:
    cada segmento lee la neurona retardada de su madre y la retarda otra vez.
  * ciempies: cabeza, cuerpo recursivo y en cada segmento dos patas, una de
    ellas por reflexión. Las patas reman en fase con la onda de su segmento.
  * bilateral: cabeza con dos aletas (una reflejada) con articulación universal
    y una cola recursiva. Las aletas baten en cuadratura (batido y barrido).

Las referencias "p" apuntan por id a una neurona de la madre; cuando la madre
es otro nodo (sin ese id) la entrada vale cero, lo que permite escribir
`sum(p:cabeza.osc, p:segmento.lag)` y que cada instancia lea lo que corresponde.
"""
from __future__ import annotations

# Ids fijos para poder referirlos desde otros nodos.
OSC, OSC_Q, LAG_IN, LAG, OSC2 = 0, 1, 2, 3, 4


def _neu(id_: int, f: str, *ins: list) -> dict:
    return {"id": id_, "f": f, "in": [list(e) for e in ins]}


def _nodo(dims, art, limite, rec, neuronas, efectores, conexiones) -> dict:
    return {"dims": list(dims), "art": art, "limite": float(limite), "rec": rec,
            "neuronas": neuronas, "efectores": [list(e) for e in efectores],
            "conexiones": conexiones}


def _con(a, cara, u=0.0, v=0.0, rot=(0.0, 0.0, 0.0), escala=1.0, reflejo=False, terminal=False) -> dict:
    return {"a": a, "cara": cara, "u": u, "v": v, "rot": list(rot), "escala": escala,
            "reflejo": reflejo, "terminal": terminal}


# Retardo de primer orden: tasa por paso de cerebro (1/960 s) para ~45° de desfase a 1 Hz.
TASA_LAG = 0.0065


def _segmento_con_lag(dims, art, limite, rec, conexiones, ganancia=1.4) -> dict:
    """Nodo cuya neurona LAG retarda la oscilación que le llega de su madre
    (la cabeza, por OSC, o el segmento anterior, por su propio LAG)."""
    return _nodo(dims, art, limite, rec,
                 [_neu(LAG_IN, "sum", ["p", OSC, ganancia], ["p", LAG, ganancia], ["c", 0, 0.0]),
                  _neu(LAG, "smooth", ["n", LAG_IN, 1.0], ["c", 0, TASA_LAG])],
                 [["n", LAG, 1.0]] * (0 if art == "rigida" else {"bisagra": 1, "torsion": 1, "universal": 2,
                                                                 "flex-tors": 2, "tors-flex": 2, "esferica": 3}[art]),
                 conexiones)


def cadena4() -> dict:
    cabeza = _nodo((0.40, 0.12, 0.12), "rigida", 60, 1,
                   [_neu(OSC, "oscillate-wave", ["c", 0, 1.0], ["c", 0, 1.0], ["c", 0, 0.0])],
                   [], [_con(1, 0)])
    segmento = _segmento_con_lag((0.40, 0.12, 0.12), "bisagra", 60, 3, [_con(1, 0)])
    return {"siguiente_id": 10, "raiz": 0, "nodos": [cabeza, segmento], "central": []}


def ciempies() -> dict:
    cabeza = _nodo((0.30, 0.20, 0.12), "rigida", 60, 1,
                   [_neu(OSC, "oscillate-wave", ["c", 0, 1.0], ["c", 0, 1.0], ["c", 0, 0.0])],
                   [], [_con(1, 0)])
    cuerpo = _segmento_con_lag((0.25, 0.18, 0.10), "bisagra", 30, 4,
                               [_con(1, 0), _con(2, 2, u=0.0, v=0.0), _con(2, 2, u=0.0, v=0.0, reflejo=True)])
    pata = _nodo((0.30, 0.05, 0.05), "bisagra", 45, 1, [],
                 [["p", LAG, 1.5]], [])
    return {"siguiente_id": 10, "raiz": 0, "nodos": [cabeza, cuerpo, pata], "central": []}


def bilateral() -> dict:
    cabeza = _nodo((0.35, 0.25, 0.12), "rigida", 60, 1,
                   [_neu(OSC, "oscillate-wave", ["c", 0, 1.0], ["c", 0, 1.2], ["c", 0, 0.0]),
                    _neu(OSC_Q, "oscillate-wave", ["c", 0, 1.0], ["c", 0, 1.2], ["c", 0, 1.5708])],
                   [], [_con(1, 2, u=0.2, v=0.0, rot=(0, 0, -20)), _con(1, 2, u=0.2, v=0.0, rot=(0, 0, -20), reflejo=True),
                        _con(2, 1)])
    aleta = _nodo((0.30, 0.20, 0.04), "universal", 45, 1, [],
                  [["p", OSC, 1.0], ["p", OSC_Q, 1.0]], [])
    cola = _segmento_con_lag((0.30, 0.08, 0.08), "bisagra", 50, 2, [_con(2, 0, escala=0.8)])
    return {"siguiente_id": 10, "raiz": 0, "nodos": [cabeza, aleta, cola], "central": []}


EJEMPLOS = {"cadena4": cadena4, "ciempies": ciempies, "bilateral": bilateral}
