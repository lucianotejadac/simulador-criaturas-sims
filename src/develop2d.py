"""Desarrollo del genoma morfológico al mundo 2D (`mundo2d.Lote`).

Proyección del genoma de Sims al plano: todas las articulaciones son
bisagras (los demás tipos se tratan como bisagra); las caras ±Z se tratan
como ±Y; de la rotación de la conexión solo cuenta el giro en Z; la
reflexión es respecto del eje X de la madre (y → −y, desvío → −desvío) con
el signo del torque y del sensor invertidos, como en 3D. Escala y
conexiones terminales como en 3D; el tope de tamaño también.

El cerebro se aplana como en 3D (`develop_morfo._aplanar_cerebro`), con
sensores: ángulo de cada articulación (1 por segmento salvo la raíz) y
después dos componentes de luz por segmento (entradas "l" 0 y 1; la 2 no
existe en 2D y vale cero).
"""
from __future__ import annotations

import math

import numpy as np

from develop import K_FUERZA
from genome import morph
from mundo2d import ESPESOR, Lote

SEPARACION = 0.02
MAX_SEGMENTOS = morph.MAX_PIEZAS


class Segmento:
    def __init__(self, nodo_idx, madre, anclaje, desvio, largo, ancho, torque_max, limite, espejo):
        self.nodo_idx, self.madre, self.anclaje, self.desvio = nodo_idx, madre, anclaje, desvio
        self.largo, self.ancho, self.torque_max, self.limite, self.espejo = largo, ancho, torque_max, limite, espejo
        self.ids_locales: dict[int, int] = {}
        self.base_sensor = 0
        self.base_luz = 0
        self.indice = 0


def _instanciar(g, nodo_idx, madre, conexion, contador, segs, espejo, escala):
    if len(segs) >= MAX_SEGMENTOS:
        return
    nodo = g["nodos"][nodo_idx]
    largo = min(morph.DIM_MAX, max(morph.DIM_MIN, nodo["dims"][0] * escala))
    ancho = min(morph.DIM_MAX, max(morph.DIM_MIN, nodo["dims"][1] * escala))
    if madre is None:
        seg = Segmento(nodo_idx, -1, (0.0, 0.0), 0.0, largo, ancho, 0.0, math.radians(nodo["limite"]), False)
    else:
        cara = conexion["cara"]
        if cara >= 4:          # ±Z -> ±Y
            cara = 2 + (cara - 4)
        u = conexion["u"]
        hl, hw = madre.largo / 2.0, madre.ancho / 2.0
        if cara == 0:
            anclaje, base = (hl, u * hw), 0.0
        elif cara == 1:
            anclaje, base = (-hl, -u * hw), math.pi
        elif cara == 2:
            anclaje, base = (-u * hl, hw), math.pi / 2
        else:
            anclaje, base = (u * hl, -hw), -math.pi / 2
        desvio = base + math.radians(conexion["rot"][2])
        if espejo:
            anclaje = (anclaje[0], -anclaje[1])
            desvio = -desvio
        # el segmento nace SEPARACION más allá del anclaje a lo largo de su eje
        area = min(ancho, madre.ancho) * ESPESOR
        seg = Segmento(nodo_idx, madre.indice, anclaje, desvio, largo, ancho,
                       K_FUERZA * area * (-1.0 if espejo else 1.0), math.radians(nodo["limite"]), espejo)
    seg.indice = len(segs)
    segs.append(seg)
    contador = dict(contador)
    contador[nodo_idx] = contador.get(nodo_idx, 0) + 1
    ultima = contador[nodo_idx] >= nodo["rec"]
    for c in nodo["conexiones"]:
        if c["terminal"] and not ultima:
            continue
        if contador.get(c["a"], 0) >= g["nodos"][c["a"]]["rec"]:
            continue
        _instanciar(g, c["a"], seg, c, contador, segs, espejo != bool(c["reflejo"]), escala * c["escala"])


def _aplanar(g, segs):
    neuronas = []
    centrales_idx = {}
    for neu in g["central"]:
        centrales_idx[neu["id"]] = len(neuronas)
        neuronas.append((neu, None))
    sensor = 0
    for s in segs:
        nodo = g["nodos"][s.nodo_idx]
        s.base_sensor = sensor
        for neu in nodo["neuronas"]:
            s.ids_locales[neu["id"]] = len(neuronas)
            neuronas.append((neu, s))
        if s.madre >= 0:
            sensor += 1
    n_dof = sensor
    for k, s in enumerate(segs):
        s.base_luz = n_dof + 2 * k
    n_sensores = n_dof + 2 * len(segs)
    raiz = segs[0]
    nada = ["c", 0, 0.0]

    def resolver(e, s):
        t, r, w = e
        if t == "c":
            return ["c", 0, w]
        if t == "g":
            return ["n", centrales_idx[r], w] if r in centrales_idx else nada
        if t == "r":
            return ["n", raiz.ids_locales[r], w] if r in raiz.ids_locales else nada
        if s is None:
            return nada
        if t == "s":
            return ["s", s.base_sensor, -w if s.espejo else w] if (r == 0 and s.madre >= 0) else nada
        if t == "l":
            if r == 0:
                return ["s", s.base_luz, w]
            if r == 1:
                return ["s", s.base_luz + 1, -w if s.espejo else w]
            return nada
        if t == "n":
            return ["n", s.ids_locales[r], w] if r in s.ids_locales else nada
        if t == "p":
            if s.madre >= 0 and r in segs[s.madre].ids_locales:
                return ["n", segs[s.madre].ids_locales[r], w]
            return nada
        return nada

    plano = [{"f": neu["f"], "in": [resolver(e, s) for e in neu["in"]]} for neu, s in neuronas]
    efectores = []
    for s in segs:
        if s.madre >= 0:
            nodo = g["nodos"][s.nodo_idx]
            efectores.append(resolver(nodo["efectores"][0], s) if nodo["efectores"] else nada)
    return {"n_sensores": n_sensores, "n_dof": n_dof, "neuronas": plano, "efectores": efectores}


def desarrollar2d(g: dict) -> dict:
    """Genoma -> segmentos 2D y cerebro plano. ValueError si no hay articulaciones o hay demasiadas piezas."""
    segs: list[Segmento] = []
    _instanciar(g, g["raiz"], None, None, {}, segs, False, 1.0)
    if len(segs) >= MAX_SEGMENTOS:
        raise ValueError("demasiadas piezas")
    if len(segs) < 2:
        raise ValueError("cuerpo sin grados de libertad")
    return {"segmentos": segs, "cerebro": _aplanar(g, segs), "n": len(segs)}


def lote_desde(desarrollos: list[dict], N: int | None = None) -> Lote:
    """Arma un Lote con las criaturas desarrolladas (relleno al máximo de segmentos)."""
    B = len(desarrollos)
    N = N or max(d["n"] for d in desarrollos)
    madre = np.full((B, N), -1)
    anclaje = np.zeros((B, N, 2))
    desvio = np.zeros((B, N))
    largo = np.zeros((B, N))
    ancho = np.zeros((B, N))
    tq = np.zeros((B, N))
    lim = np.full((B, N), 60.0)
    masc = np.zeros((B, N), dtype=bool)
    for b, d in enumerate(desarrollos):
        for s in d["segmentos"]:
            i = s.indice
            madre[b, i] = s.madre
            anclaje[b, i] = s.anclaje
            desvio[b, i] = s.desvio
            largo[b, i] = s.largo
            ancho[b, i] = s.ancho
            tq[b, i] = abs(s.torque_max)
            lim[b, i] = math.degrees(s.limite)
            masc[b, i] = True
    return Lote(madre, anclaje, desvio, largo, ancho, tq, masc, limite_grados=lim)


def signos_torque(desarrollos: list[dict], N: int) -> np.ndarray:
    """(B, N) con -1 en segmentos reflejados: el mismo cerebro produce el movimiento espejo."""
    B = len(desarrollos)
    sg = np.ones((B, N))
    for b, d in enumerate(desarrollos):
        for s in d["segmentos"]:
            if s.espejo:
                sg[b, s.indice] = -1.0
    return sg
