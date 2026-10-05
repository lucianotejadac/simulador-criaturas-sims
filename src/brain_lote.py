"""Cerebros de muchas criaturas en un solo núcleo Numba (para el mundo 2D).

Los grafos planos de B criaturas se concatenan en arreglos con desplazamientos
por criatura; un solo llamado avanza k pasos de todos los cerebros. Misma
semántica que `brain.Cerebro` y `brain_rapido` (BITACORA 0019).
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit

from brain import EPS, VAL_MAX
from brain_rapido import CODIGOS, TIPO


@njit(cache=True)
def _clip(v):
    if v != v:
        return 0.0
    if v > VAL_MAX:
        return VAL_MAX
    if v < -VAL_MAX:
        return -VAL_MAX
    return v


@njit(cache=True)
def _leer(t, i, w, sens, so, val, vo):
    if t == 0:
        return w * sens[so + i]
    if t == 1:
        return w * val[vo + i]
    return w


@njit(cache=True)
def pasos_lote(k, B, off_n, off_e, off_s, fcode, ar, it, ii, iw, et, ei, ew, val, nuevo, est, sens, dt, t, salida):
    """k pasos de cada cerebro; `t` es (B,) y se actualiza. Devuelve nada; escribe `salida` (plana por efector)."""
    for b in range(B):
        n0, n1 = off_n[b], off_n[b + 1]
        so = off_s[b]
        tb = t[b]
        for _ in range(k):
            for j in range(n0, n1):
                f = fcode[j]
                a = _leer(it[j, 0], ii[j, 0], iw[j, 0], sens, so, val, n0)
                bb = _leer(it[j, 1], ii[j, 1], iw[j, 1], sens, so, val, n0) if ar[j] > 1 else 0.0
                c = _leer(it[j, 2], ii[j, 2], iw[j, 2], sens, so, val, n0) if ar[j] > 2 else 0.0
                if f == 0:
                    r = a + bb + c
                elif f == 1:
                    r = a * bb * c
                elif f == 2:
                    if abs(bb) > EPS:
                        r = a / bb
                    elif bb >= 0:
                        r = a / EPS
                    else:
                        r = -a / EPS
                elif f == 3:
                    r = 1.0 if (a + bb) > c else 0.0
                elif f == 4:
                    r = 1.0 if a > bb else 0.0
                elif f == 5:
                    r = 1.0 if a > 0 else (-1.0 if a < 0 else 0.0)
                elif f == 6:
                    r = min(a, min(bb, c))
                elif f == 7:
                    r = max(a, max(bb, c))
                elif f == 8:
                    r = abs(a)
                elif f == 9:
                    r = bb if a > 0 else c
                elif f == 10:
                    u = 0.0 if c < 0 else (1.0 if c > 1 else c)
                    r = a + (bb - a) * u
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
                    tasa = 0.0 if bb < 0 else (1.0 if bb > 1 else bb)
                    est[j] = est[j] + (a - est[j]) * tasa
                    r = est[j]
                elif f == 20:
                    if bb > 0:
                        est[j] = a
                    r = est[j]
                elif f == 21:
                    r = a * math.sin(2.0 * math.pi * bb * tb + c)
                elif f == 22:
                    fase = (bb * tb + c) % 1.0
                    r = a * (2.0 * fase - 1.0)
                else:
                    r = 0.0
                nuevo[j] = _clip(r)
            for j in range(n0, n1):
                val[j] = nuevo[j]
            tb = tb + dt
        t[b] = tb
        for e in range(off_e[b], off_e[b + 1]):
            v = _leer(et[e], ei[e], ew[e], sens, so, val, n0)
            salida[e] = 1.0 if v > 1.0 else (-1.0 if v < -1.0 else v)


class CerebrosLote:
    """Cerebros planos de B criaturas; `pasos(k, sens)` con `sens` plano (concatenado por criatura)."""

    def __init__(self, genomas: list[dict], dt: float):
        self.B = len(genomas)
        self.dt = dt
        off_n = [0]
        off_e = [0]
        off_s = [0]
        fcode, ar, it, ii, iw, et, ei, ew = [], [], [], [], [], [], [], []
        for g in genomas:
            for x in g["neuronas"]:
                fcode.append(CODIGOS[x["f"]])
                ar.append(len(x["in"]))
                row_t, row_i, row_w = [2, 2, 2], [0, 0, 0], [0.0, 0.0, 0.0]
                for k, (t, i, w) in enumerate(x["in"]):
                    row_t[k], row_i[k], row_w[k] = TIPO[t], i, w
                it.append(row_t)
                ii.append(row_i)
                iw.append(row_w)
            for (t, i, w) in g["efectores"]:
                et.append(TIPO[t])
                ei.append(i)
                ew.append(w)
            off_n.append(len(fcode))
            off_e.append(len(et))
            off_s.append(off_s[-1] + max(1, g.get("n_sensores", 0)))
        self.off_n = np.array(off_n, dtype=np.int64)
        self.off_e = np.array(off_e, dtype=np.int64)
        self.off_s = np.array(off_s, dtype=np.int64)
        n = len(fcode)
        self.fcode = np.array(fcode, dtype=np.int64).reshape(n)
        self.ar = np.array(ar, dtype=np.int64).reshape(n)
        self.it = np.array(it, dtype=np.int64).reshape(n, 3)
        self.ii = np.array(ii, dtype=np.int64).reshape(n, 3)
        self.iw = np.array(iw, dtype=np.float64).reshape(n, 3)
        self.et = np.array(et, dtype=np.int64)
        self.ei = np.array(ei, dtype=np.int64)
        self.ew = np.array(ew, dtype=np.float64)
        self.val = np.zeros(n)
        self.nuevo = np.zeros(n)
        self.est = np.zeros(n)
        self.t = np.zeros(self.B)
        self.salida = np.zeros(len(et))
        self.sens = np.zeros(self.off_s[-1])
        self.n_efectores = [off_e[b + 1] - off_e[b] for b in range(self.B)]

    def pasos(self, k: int) -> np.ndarray:
        """Avanza k pasos leyendo `self.sens` (llenado por el llamador). Devuelve las salidas planas."""
        pasos_lote(k, self.B, self.off_n, self.off_e, self.off_s, self.fcode, self.ar, self.it, self.ii, self.iw,
                   self.et, self.ei, self.ew, self.val, self.nuevo, self.est, self.sens, self.dt, self.t, self.salida)
        return self.salida
