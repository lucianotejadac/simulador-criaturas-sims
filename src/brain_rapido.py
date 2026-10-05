"""Cerebro compilado con Numba: la misma semántica que `brain.Cerebro`, 20 a 50 veces más rápido.

El grafo se convierte en arreglos (código de función, tres entradas con tipo,
índice y peso por neurona; una entrada por efector) y el paso se compila a
código de máquina. Las funciones replican exactamente las de `brain.py`,
incluidos el recorte a ±VAL_MAX y los casos límite (división por cero,
logaritmo, exponencial), así que una criatura evaluada con uno u otro cerebro
da el mismo resultado (BITACORA 0019).
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit

from brain import EPS, VAL_MAX

# Códigos de función, en el mismo orden para ambos cerebros.
CODIGOS = {
    "sum": 0, "product": 1, "divide": 2, "sum-threshold": 3, "greater-than": 4, "sign-of": 5,
    "min": 6, "max": 7, "abs": 8, "if": 9, "interpolate": 10, "sin": 11, "cos": 12, "atan": 13,
    "log": 14, "expt": 15, "sigmoid": 16, "integrate": 17, "differentiate": 18, "smooth": 19,
    "memory": 20, "oscillate-wave": 21, "oscillate-saw": 22,
}
TIPO = {"s": 0, "n": 1, "c": 2}


@njit(cache=True, fastmath=False)
def _clip(v):
    if v != v:
        return 0.0
    if v > VAL_MAX:
        return VAL_MAX
    if v < -VAL_MAX:
        return -VAL_MAX
    return v


@njit(cache=True, fastmath=False)
def _leer(t, i, w, sens, val):
    if t == 0:
        return w * sens[i]
    if t == 1:
        return w * val[i]
    return w


@njit(cache=True, fastmath=False)
def pasos(k, fcode, ar, it, ii, iw, et, ei, ew, val, nuevo, est, sens, dt, t, salida):
    """k pasos síncronos del cerebro con los sensores fijos. Devuelve el tiempo."""
    n = fcode.shape[0]
    for _ in range(k):
        for j in range(n):
            f = fcode[j]
            a = _leer(it[j, 0], ii[j, 0], iw[j, 0], sens, val)
            b = _leer(it[j, 1], ii[j, 1], iw[j, 1], sens, val) if ar[j] > 1 else 0.0
            c = _leer(it[j, 2], ii[j, 2], iw[j, 2], sens, val) if ar[j] > 2 else 0.0
            if f == 0:
                r = a + b + c
            elif f == 1:
                r = a * b * c
            elif f == 2:
                if abs(b) > EPS:
                    r = a / b
                elif b >= 0:
                    r = a / EPS
                else:
                    r = -a / EPS
            elif f == 3:
                r = 1.0 if (a + b) > c else 0.0
            elif f == 4:
                r = 1.0 if a > b else 0.0
            elif f == 5:
                r = 1.0 if a > 0 else (-1.0 if a < 0 else 0.0)
            elif f == 6:
                r = min(a, min(b, c))
            elif f == 7:
                r = max(a, max(b, c))
            elif f == 8:
                r = abs(a)
            elif f == 9:
                r = b if a > 0 else c
            elif f == 10:
                u = 0.0 if c < 0 else (1.0 if c > 1 else c)
                r = a + (b - a) * u
            elif f == 11:
                r = math.sin(a)
            elif f == 12:
                r = math.cos(a)
            elif f == 13:
                r = math.atan(a)
            elif f == 14:
                r = math.log(abs(a) + EPS)
            elif f == 15:
                r = math.exp(a if a < 2.3 else 2.3)
            elif f == 16:
                r = 1.0 / (1.0 + math.exp(-a)) if a > -30 else 0.0
            elif f == 17:
                est[j] = _clip(est[j] + a * dt)
                r = est[j]
            elif f == 18:
                r = (a - est[j]) / dt
                est[j] = a
            elif f == 19:
                tasa = 0.0 if b < 0 else (1.0 if b > 1 else b)
                est[j] = est[j] + (a - est[j]) * tasa
                r = est[j]
            elif f == 20:
                if b > 0:
                    est[j] = a
                r = est[j]
            elif f == 21:
                r = a * math.sin(2.0 * math.pi * b * t + c)
            elif f == 22:
                fase = (b * t + c) % 1.0
                r = a * (2.0 * fase - 1.0)
            else:
                r = 0.0
            nuevo[j] = _clip(r)
        for j in range(n):
            val[j] = nuevo[j]
        t = t + dt
    for e in range(et.shape[0]):
        v = _leer(et[e], ei[e], ew[e], sens, val)
        salida[e] = 1.0 if v > 1.0 else (-1.0 if v < -1.0 else v)
    return t


class CerebroRapido:
    """Misma interfaz que `brain.Cerebro`: paso(sensores) y pasos(k, sensores)."""

    def __init__(self, genoma: dict, dt: float):
        self.dt = dt
        self.t = 0.0
        neuronas = genoma["neuronas"]
        n = len(neuronas)
        self.fcode = np.array([CODIGOS[x["f"]] for x in neuronas], dtype=np.int64)
        self.ar = np.array([len(x["in"]) for x in neuronas], dtype=np.int64)
        self.it = np.zeros((n, 3), dtype=np.int64)
        self.ii = np.zeros((n, 3), dtype=np.int64)
        self.iw = np.zeros((n, 3), dtype=np.float64)
        for j, x in enumerate(neuronas):
            for k, (t, i, w) in enumerate(x["in"]):
                self.it[j, k], self.ii[j, k], self.iw[j, k] = TIPO[t], i, w
        ef = genoma["efectores"]
        self.et = np.array([TIPO[e[0]] for e in ef], dtype=np.int64)
        self.ei = np.array([e[1] for e in ef], dtype=np.int64)
        self.ew = np.array([e[2] for e in ef], dtype=np.float64)
        self.val = np.zeros(n)
        self.nuevo = np.zeros(n)
        self.est = np.zeros(n)
        self.salida = np.zeros(len(ef))
        self._sens = np.zeros(max(1, genoma.get("n_sensores", 0)))

    def reiniciar(self) -> None:
        self.t = 0.0
        self.val[:] = 0.0
        self.nuevo[:] = 0.0
        self.est[:] = 0.0

    def pasos(self, k: int, sensores) -> np.ndarray:
        s = self._sens
        s[:len(sensores)] = sensores
        self.t = pasos(k, self.fcode, self.ar, self.it, self.ii, self.iw, self.et, self.ei, self.ew,
                       self.val, self.nuevo, self.est, s, self.dt, self.t, self.salida)
        return self.salida

    def paso(self, sensores) -> list[float]:
        return list(self.pasos(1, sensores))
