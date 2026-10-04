"""Ejecución del grafo neuronal (cerebro) de una criatura.

Actualización síncrona: en cada paso todas las neuronas leen los valores del
paso anterior, lo que permite recurrencias sin orden de evaluación. Las
funciones con estado (integrate, differentiate, smooth, memory, oscillate-*)
guardan su estado en la instancia.

Los valores se acotan a [-VAL_MAX, VAL_MAX] para que sum/product/expt no
desborden; es una decisión nuestra, Sims no lo especifica (BITACORA 0001).
"""
from __future__ import annotations

import math

VAL_MAX = 10.0
EPS = 1e-6


def _clip(v: float) -> float:
    if v != v:  # NaN
        return 0.0
    return VAL_MAX if v > VAL_MAX else (-VAL_MAX if v < -VAL_MAX else v)


class Cerebro:
    """Compila un genoma neuronal y lo ejecuta paso a paso."""

    def __init__(self, genoma: dict, dt: float):
        self.dt = dt
        self.t = 0.0
        self.n_sens = genoma["n_sensores"]
        self.neuronas = genoma["neuronas"]
        self.efectores = genoma["efectores"]
        n = len(self.neuronas)
        self.val = [0.0] * n
        self.estado = [0.0] * n   # integrador, valor previo, memoria, etc.
        self.estado2 = [0.0] * n  # segunda celda de estado (diferenciador)
        # Precompilar entradas como tuplas (tipo_codigo, idx, peso): 0 sensor, 1 neurona, 2 const
        cod = {"s": 0, "n": 1, "c": 2}
        self.ins = [[(cod[t], i, w) for t, i, w in neu["in"]] for neu in self.neuronas]
        self.fun = [neu["f"] for neu in self.neuronas]
        self.efs = [(cod[t], i, w) for t, i, w in self.efectores]

    def reiniciar(self) -> None:
        self.t = 0.0
        n = len(self.neuronas)
        self.val = [0.0] * n
        self.estado = [0.0] * n
        self.estado2 = [0.0] * n

    def _leer(self, e: tuple, sens, val) -> float:
        t, i, w = e
        if t == 0:
            return w * sens[i]
        if t == 1:
            return w * val[i]
        return w

    def paso(self, sensores) -> list[float]:
        """Un paso de cerebro. Devuelve la salida de cada efector en [-1, 1]."""
        val = self.val
        est = self.estado
        est2 = self.estado2
        dt = self.dt
        t = self.t
        nuevo = [0.0] * len(val)
        for k, f in enumerate(self.fun):
            ins = self.ins[k]
            a = self._leer(ins[0], sensores, val)
            b = self._leer(ins[1], sensores, val) if len(ins) > 1 else 0.0
            c = self._leer(ins[2], sensores, val) if len(ins) > 2 else 0.0
            if f == "sum":
                r = a + b + c
            elif f == "product":
                r = a * b * c
            elif f == "divide":
                r = a / b if abs(b) > EPS else (a / EPS if b >= 0 else -a / EPS)
            elif f == "sum-threshold":
                r = 1.0 if (a + b) > c else 0.0
            elif f == "greater-than":
                r = 1.0 if a > b else 0.0
            elif f == "sign-of":
                r = 1.0 if a > 0 else (-1.0 if a < 0 else 0.0)
            elif f == "min":
                r = min(a, b, c)
            elif f == "max":
                r = max(a, b, c)
            elif f == "abs":
                r = abs(a)
            elif f == "if":
                r = b if a > 0 else c
            elif f == "interpolate":
                u = 0.0 if c < 0 else (1.0 if c > 1 else c)
                r = a + (b - a) * u
            elif f == "sin":
                r = math.sin(a)
            elif f == "cos":
                r = math.cos(a)
            elif f == "atan":
                r = math.atan(a)
            elif f == "log":
                r = math.log(abs(a) + EPS)
            elif f == "expt":
                r = math.exp(a if a < 2.3 else 2.3)  # e^2.3 ≈ 10 = VAL_MAX
            elif f == "sigmoid":
                r = 1.0 / (1.0 + math.exp(-a)) if a > -30 else 0.0
            elif f == "integrate":
                est[k] = _clip(est[k] + a * dt)
                r = est[k]
            elif f == "differentiate":
                r = (a - est[k]) / dt
                est[k] = a
            elif f == "smooth":
                tasa = 0.0 if b < 0 else (1.0 if b > 1 else b)
                est[k] = est[k] + (a - est[k]) * tasa
                r = est[k]
            elif f == "memory":
                if b > 0:
                    est[k] = a
                r = est[k]
            elif f == "oscillate-wave":
                r = a * math.sin(2.0 * math.pi * b * t + c)
            elif f == "oscillate-saw":
                fase = (b * t + c) % 1.0
                r = a * (2.0 * fase - 1.0)
            else:
                r = 0.0
            nuevo[k] = _clip(r)
        self.val = nuevo
        self.t = t + dt
        salida = []
        for e in self.efs:
            v = self._leer(e, sensores, nuevo)
            salida.append(1.0 if v > 1.0 else (-1.0 if v < -1.0 else v))
        return salida
