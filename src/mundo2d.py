"""Mundo 2D viscoso sin inercia (régimen de Stokes), para muchas criaturas a la vez.

Cada criatura es un árbol de segmentos rígidos (rectángulos) unidos por
bisagras. Sin inercia, en cada instante las fuerzas se equilibran: el
arrastre viscoso de todos los segmentos iguala a los torques de las
articulaciones. En coordenadas generalizadas q = (x, y, φ, θ_1..θ_n):

    R(q) · q̇ = τ          con   R = Σ_i J_iᵀ D_i J_i

donde J_i es el jacobiano del segmento i (su velocidad lineal y angular como
función de q̇), D_i su matriz de arrastre (anisotrópica: resiste más de
costado que de punta, y gira contra un arrastre rotacional) y τ los torques
generalizados: cero en (x, y, φ) —ninguna fuerza externa— y el torque
muscular menos la amortiguación articular en cada θ_j. Es la teoría de la
fuerza resistiva (Gray y Hancock, 1955) aplicada a cuerpos articulados.

Músculo con relación fuerza-longitud: el torque que empuja hacia el tope se
apaga al acercarse a él, 1 − (θ/lím)², y el que trae de vuelta no; así la
articulación no golpea el tope. Un resorte rígido implícito actúa solo si el
ángulo se pasa del límite. Integración de punto medio (segundo orden): dos
resoluciones por paso (BITACORA 0022).

El paso está compilado con Numba, criatura por criatura con su número real
de segmentos. El sistema lineal se resuelve con eliminación gaussiana propia
(sin LAPACK, que exigiría SciPy).

Convenciones: el segmento 0 es la raíz; su centro es (x, y) y su orientación
φ. Cada segmento i > 0 cuelga de `madre[i]` en el punto `anclaje[i]` (en el
marco de la madre, desde su centro) y su propio marco nace en el anclaje con
desvío `desvio[i]` más el ángulo articular θ_i; su centro está a `largo[i]/2`
a lo largo de su eje X.
"""
from __future__ import annotations

import numpy as np
from numba import njit

K_ARRASTRE_2D = 400.0   # N·s/m³, el mismo coeficiente por área que en 3D
ESPESOR = 0.08          # m: profundidad nominal de las cajas en 2D (para áreas de arrastre)
C_AMORTIGUACION = 0.05  # s/rad · torque máximo, como en 3D
K_LIMITE = 40.0         # rigidez del tope articular, en torques máximos por radián (implícita)
DENSIDAD = 300.0


@njit(cache=True)
def _resolver(A, b):
    """Eliminación gaussiana con pivoteo parcial (sistemas chicos, sin LAPACK)."""
    n = b.shape[0]
    M = A.copy()
    x = b.copy()
    for c in range(n):
        p = c
        mx = abs(M[c, c])
        for r in range(c + 1, n):
            if abs(M[r, c]) > mx:
                mx = abs(M[r, c])
                p = r
        if p != c:
            for q in range(n):
                tmp = M[c, q]
                M[c, q] = M[p, q]
                M[p, q] = tmp
            tmp = x[c]
            x[c] = x[p]
            x[p] = tmp
        piv = M[c, c]
        if piv == 0.0:
            piv = 1e-30
        for r in range(c + 1, n):
            f = M[r, c] / piv
            if f != 0.0:
                for q in range(c, n):
                    M[r, q] -= f * M[c, q]
                x[r] -= f * x[c]
    for c in range(n - 1, -1, -1):
        s = x[c]
        for q in range(c + 1, n):
            s -= M[c, q] * x[q]
        piv = M[c, c]
        if piv == 0.0:
            piv = 1e-30
        x[c] = s / piv
    return x


@njit(cache=True)
def _cinematica_una(n, madre, anclaje, desvio, largo, theta, pose, centro, phi, art):
    centro[0, 0] = pose[0]
    centro[0, 1] = pose[1]
    phi[0] = pose[2]
    art[0, 0] = pose[0]
    art[0, 1] = pose[1]
    for i in range(1, n):
        m = madre[i]
        pm = phi[m]
        cs = np.cos(pm)
        sn = np.sin(pm)
        ax = anclaje[i, 0]
        ay = anclaje[i, 1]
        pax = centro[m, 0] + cs * ax - sn * ay
        pay = centro[m, 1] + sn * ax + cs * ay
        ph = pm + desvio[i] + theta[i]
        art[i, 0] = pax
        art[i, 1] = pay
        phi[i] = ph
        centro[i, 0] = pax + np.cos(ph) * largo[i] * 0.5
        centro[i, 1] = pay + np.sin(ph) * largo[i] * 0.5


@njit(cache=True)
def _qdot_una(n, madre, anclaje, desvio, largo, d_along, d_norm, d_rot, torque_max, limite, torque, empuje,
              pose, theta, dt, c_amort, k_lim, centro, phi, art, anc, R, tau, Jx, Jy, Ja):
    """Velocidades generalizadas de una criatura en la configuración (pose, theta)."""
    _cinematica_una(n, madre, anclaje, desvio, largo, theta, pose, centro, phi, art)
    for i in range(n):
        for k in range(n):
            anc[i, k] = False
        j = i
        while j >= 1:
            anc[i, j] = True
            j = madre[j]
    nd = 3 + n
    for p in range(nd):
        tau[p] = 0.0
        for q in range(nd):
            R[p, q] = 0.0
    for i in range(n):
        cs = np.cos(phi[i])
        sn = np.sin(phi[i])
        for d in range(nd):
            Jx[d] = 0.0
            Jy[d] = 0.0
            Ja[d] = 0.0
        Jx[0] = cs
        Jy[0] = -sn
        Jx[1] = sn
        Jy[1] = cs
        px = -(centro[i, 1] - centro[0, 1])
        py = centro[i, 0] - centro[0, 0]
        Jx[2] = px * cs + py * sn
        Jy[2] = -px * sn + py * cs
        Ja[2] = 1.0
        for k in range(1, n):
            if anc[i, k]:
                qx = -(centro[i, 1] - art[k, 1])
                qy = centro[i, 0] - art[k, 0]
                Jx[3 + k] = qx * cs + qy * sn
                Jy[3 + k] = -qx * sn + qy * cs
                Ja[3 + k] = 1.0
        da = d_along[i]
        dn = d_norm[i]
        dr = d_rot[i]
        fe = empuje[i]          # empuje externo a lo largo del eje del segmento (flagelo): trabajo generalizado F·Jx
        for p in range(nd):
            jxp = Jx[p]
            jyp = Jy[p]
            jap = Ja[p]
            if jxp == 0.0 and jyp == 0.0 and jap == 0.0:
                continue
            tau[p] += fe * jxp
            for q in range(nd):
                R[p, q] += da * jxp * Jx[q] + dn * jyp * Jy[q] + dr * jap * Ja[q]
    for k in range(1, n):
        tq = torque[k]
        if tq > 1.0:
            tq = 1.0
        elif tq < -1.0:
            tq = -1.0
        th = theta[k]
        lim = limite[k]
        tm = torque_max[k]
        if lim > 0.0 and tq * th > 0.0:
            r = th / lim
            fac = 1.0 - r * r
            if fac < 0.0:
                fac = 0.0
            R[3 + k, 3 + k] += dt * abs(tq * tm) * 2.0 * abs(th) / (lim * lim)
            tq = tq * fac
        tau[3 + k] += tq * tm
        R[3 + k, 3 + k] += c_amort * tm + 1e-9
        K = k_lim * tm
        if th > lim:
            tau[3 + k] += -K * (th - lim)
            R[3 + k, 3 + k] += K * dt
        elif th < -lim:
            tau[3 + k] += -K * (th + lim)
            R[3 + k, 3 + k] += K * dt
    R[3, 3] += 1e9   # θ_0 no existe (la raíz no tiene articulación)
    return _resolver(R[:nd, :nd], tau[:nd])


@njit(cache=True)
def _paso_lote(B, nseg, madre, anclaje, desvio, largo, d_along, d_norm, d_rot, torque_max, limite,
               torque, empuje, pose, theta, dt, c_amort, k_lim):
    maxn = madre.shape[1]
    centro = np.zeros((maxn, 2))
    phi = np.zeros(maxn)
    art = np.zeros((maxn, 2))
    anc = np.zeros((maxn, maxn), dtype=np.bool_)
    R = np.zeros((3 + maxn, 3 + maxn))
    tau = np.zeros(3 + maxn)
    Jx = np.zeros(3 + maxn)
    Jy = np.zeros(3 + maxn)
    Ja = np.zeros(3 + maxn)
    pose_m = np.zeros(3)
    theta_m = np.zeros(maxn)
    for b in range(B):
        n = nseg[b]
        k1 = _qdot_una(n, madre[b], anclaje[b], desvio[b], largo[b], d_along[b], d_norm[b], d_rot[b],
                       torque_max[b], limite[b], torque[b], empuje[b], pose[b], theta[b], dt, c_amort, k_lim,
                       centro, phi, art, anc, R, tau, Jx, Jy, Ja)
        for p in range(3):
            pose_m[p] = pose[b, p] + 0.5 * dt * k1[p]
        for k in range(n):
            theta_m[k] = theta[b, k] + 0.5 * dt * k1[3 + k]
        theta_m[0] = 0.0
        k2 = _qdot_una(n, madre[b], anclaje[b], desvio[b], largo[b], d_along[b], d_norm[b], d_rot[b],
                       torque_max[b], limite[b], torque[b], empuje[b], pose_m, theta_m, dt, c_amort, k_lim,
                       centro, phi, art, anc, R, tau, Jx, Jy, Ja)
        for p in range(3):
            pose[b, p] += dt * k2[p]
        for k in range(1, n):
            theta[b, k] += dt * k2[3 + k]


@njit(cache=True)
def _centros_lote(B, nseg, madre, anclaje, desvio, largo, theta, pose, masa, salida_centro, salida_phi, salida_com):
    maxn = madre.shape[1]
    centro = np.zeros((maxn, 2))
    phi = np.zeros(maxn)
    art = np.zeros((maxn, 2))
    for b in range(B):
        n = nseg[b]
        _cinematica_una(n, madre[b], anclaje[b], desvio[b], largo[b], theta[b], pose[b], centro, phi, art)
        mt = 0.0
        cx = 0.0
        cy = 0.0
        for i in range(n):
            salida_centro[b, i, 0] = centro[i, 0]
            salida_centro[b, i, 1] = centro[i, 1]
            salida_phi[b, i] = phi[i]
            mt += masa[b, i]
            cx += masa[b, i] * centro[i, 0]
            cy += masa[b, i] * centro[i, 1]
        salida_com[b, 0] = cx / max(mt, 1e-9)
        salida_com[b, 1] = cy / max(mt, 1e-9)


class Lote:
    """Un lote de B criaturas con hasta N segmentos. Arreglos (B, N) salvo indicación."""

    def __init__(self, madre, anclaje, desvio, largo, ancho, torque_max, mascara, limite_grados=60.0):
        self.B, self.N = largo.shape
        self.madre = np.ascontiguousarray(madre.astype(np.int64))
        self.anclaje = np.ascontiguousarray(anclaje.astype(np.float64))
        self.desvio = np.ascontiguousarray(desvio.astype(np.float64))
        self.largo = np.ascontiguousarray(largo.astype(np.float64))
        self.ancho = np.ascontiguousarray(ancho.astype(np.float64))
        self.mascara = mascara.astype(bool)
        self.nseg = np.ascontiguousarray(self.mascara.sum(1).astype(np.int64))   # segmentos 0..n-1 contiguos
        self.torque_max = np.ascontiguousarray(torque_max.astype(np.float64))
        a, b = self.largo / 2.0, self.ancho / 2.0
        c = ESPESOR / 2.0
        self.d_along = np.ascontiguousarray(K_ARRASTRE_2D * 8 * b * c)
        self.d_norm = np.ascontiguousarray(K_ARRASTRE_2D * 8 * a * c)
        self.d_rot = np.ascontiguousarray(K_ARRASTRE_2D * ((8 / 3) * (a * c ** 3 + a ** 3 * c) + (8 / 3) * (b * c ** 3 + b ** 3 * c)))
        self.masa = np.ascontiguousarray((self.largo * self.ancho * ESPESOR * DENSIDAD) * self.mascara)
        self.pose = np.zeros((self.B, 3))
        self._sin_empuje = np.zeros((self.B, self.N))
        self.theta = np.zeros((self.B, self.N))
        lim = np.full((self.B, self.N), np.radians(limite_grados)) if np.isscalar(limite_grados) else np.radians(limite_grados)
        self.limite = np.ascontiguousarray(lim.astype(np.float64))
        self._centro = np.zeros((self.B, self.N, 2))
        self._phi = np.zeros((self.B, self.N))
        self._com = np.zeros((self.B, 2))

    def paso(self, torque: np.ndarray, dt: float, empuje: np.ndarray | None = None) -> None:
        """Avanza dt. `torque` (B, N) en [-1, 1] por articulación; `empuje` (B, N) en N a lo largo del eje de cada
        segmento (flagelo propio de la pieza), opcional."""
        if empuje is None:
            empuje = self._sin_empuje
        _paso_lote(self.B, self.nseg, self.madre, self.anclaje, self.desvio, self.largo, self.d_along, self.d_norm,
                   self.d_rot, self.torque_max, self.limite, np.ascontiguousarray(torque, dtype=np.float64),
                   np.ascontiguousarray(empuje, dtype=np.float64), self.pose, self.theta, dt, C_AMORTIGUACION, K_LIMITE)

    def cinematica(self):
        """Centros (B, N, 2), orientaciones (B, N) y centro de masa (B, 2)."""
        _centros_lote(self.B, self.nseg, self.madre, self.anclaje, self.desvio, self.largo, self.theta, self.pose,
                      self.masa, self._centro, self._phi, self._com)
        return self._centro, self._phi, self._com

    def centro_de_masa(self) -> np.ndarray:
        return self.cinematica()[2].copy()


def cadena(B: int, n: int, largo: float = 0.25, ancho: float = 0.08, torque: float = 10.0, N: int | None = None) -> Lote:
    """Lote de B cadenas iguales de n segmentos, rellenadas a N (para pruebas)."""
    N = N or n
    madre = np.full((B, N), -1)
    madre[:, 1:n] = np.arange(n - 1)[None, :]
    anclaje = np.zeros((B, N, 2))
    anclaje[:, 1:n, 0] = largo / 2.0
    desvio = np.zeros((B, N))
    L = np.zeros((B, N)); L[:, :n] = largo
    W = np.zeros((B, N)); W[:, :n] = ancho
    tq = np.zeros((B, N)); tq[:, 1:n] = torque
    masc = np.zeros((B, N), dtype=bool); masc[:, :n] = True
    return Lote(madre, anclaje, desvio, L, W, tq, masc)
