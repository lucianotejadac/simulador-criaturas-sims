"""Arrastre viscoso por cara, como en Sims (1994).

Sims simula el agua con un modelo simple: en cada cara de cada caja, la
componente de la velocidad normal a la cara, multiplicada por el área de la
cara, produce una fuerza de arrastre opuesta. Esa anisotropía (una caja resiste
más de lado que de punta) convierte la ondulación en empuje.

Integrando ese arrastre lineal sobre toda la superficie de cada cara (no solo
en su centro, ver BITACORA 0004) se obtiene, en el marco local de la caja de
semiejes (a, b, c):

    F_local = -k · diag(2bc·4, 2ac·4, 2ab·4) · v_local        (área de cada par de caras)
    T_local = -k · diag(D_x, D_y, D_z) · w_local
    con D_x = (8/3)·(a·b·c³ + a·c·b³), etc.  (momentos de área de las caras)

El término de fuerza no genera torque porque las dos caras opuestas lo
cancelan; el torque viene del segundo momento de área de cada cara.

Se reemplazó el modelo de fluido nativo de MuJoCo (density/viscosity) porque
el empuje que producía dependía del paso de integración (BITACORA 0004).
"""
from __future__ import annotations

import mujoco
import numpy as np

K_ARRASTRE = 400.0  # N·s/m³  (fuerza por unidad de área y de velocidad normal)

try:
    from numba import njit
except Exception:   # sin Numba: versión NumPy
    njit = None


def _nucleo_py(cvel, xpos, com, xmat, dlin, drot, F, T):
    n = cvel.shape[0]
    for k in range(n):
        wx, wy, wz = cvel[k, 0], cvel[k, 1], cvel[k, 2]
        rx, ry, rz = xpos[k, 0] - com[k, 0], xpos[k, 1] - com[k, 1], xpos[k, 2] - com[k, 2]
        vx = cvel[k, 3] + (wy * rz - wz * ry)
        vy = cvel[k, 4] + (wz * rx - wx * rz)
        vz = cvel[k, 5] + (wx * ry - wy * rx)
        # columnas de R = ejes locales; v_loc = Rᵀ v ; w_loc = Rᵀ w
        for i in range(3):
            r0, r1, r2 = xmat[k, i], xmat[k, 3 + i], xmat[k, 6 + i]
            vl = r0 * vx + r1 * vy + r2 * vz
            wl = r0 * wx + r1 * wy + r2 * wz
            fl = -dlin[k, i] * vl
            tl = -drot[k, i] * wl
            F[k, 0] += r0 * fl
            F[k, 1] += r1 * fl
            F[k, 2] += r2 * fl
            T[k, 0] += r0 * tl
            T[k, 1] += r1 * tl
            T[k, 2] += r2 * tl


_nucleo = njit(cache=True)(_nucleo_py) if njit else _nucleo_py


class ArrastrePorCara:
    """Precalcula los coeficientes de cada caja y aplica el arrastre en cada paso."""

    def __init__(self, model: mujoco.MjModel, k: float = K_ARRASTRE):
        self.k = k
        ids, dlin, drot = [], [], []
        for b in range(1, model.nbody):
            g = model.body_geomadr[b]
            if g < 0 or model.geom_type[g] != mujoco.mjtGeom.mjGEOM_BOX:
                continue
            s = model.geom_size[g].copy()  # semiejes a, b, c
            # Área total de las dos caras normales a cada eje: 2 · (2 s_j)(2 s_k).
            lin = np.array([8 * s[1] * s[2], 8 * s[0] * s[2], 8 * s[0] * s[1]])
            rot = np.zeros(3)
            for i in range(3):
                j, m = (i + 1) % 3, (i + 2) % 3
                # Cara normal a i (dos caras): rotación alrededor de j resiste con (4/3)·s_j·s_m³,
                # alrededor de m con (4/3)·s_j³·s_m; por dos caras, ×2.
                rot[j] += 2 * (4.0 / 3.0) * s[j] * s[m] ** 3
                rot[m] += 2 * (4.0 / 3.0) * s[j] ** 3 * s[m]
            ids.append(b)
            dlin.append(k * lin)
            drot.append(k * rot)
        self.ids = np.array(ids)
        self.raices = model.body_rootid[self.ids]
        # Índices contiguos (una criatura sola): rebanadas, sin copias.
        contiguos = len(ids) > 0 and ids == list(range(ids[0], ids[0] + len(ids)))
        self.sel = slice(ids[0], ids[0] + len(ids)) if contiguos else self.ids
        r0 = int(self.raices[0]) if len(ids) else 0
        self.sel_r = slice(r0, r0 + 1) if contiguos and np.all(self.raices == r0) else self.raices
        self._com = np.zeros((len(ids), 3))
        self.dlin = np.array(dlin)
        self.drot = np.array(drot)
        self._F = np.zeros((len(ids), 3))
        self._T = np.zeros((len(ids), 3))

    def aplicar(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        # Velocidad de cada cuerpo en su origen, a partir de cvel (expresada en el
        # centro de masa del subárbol raíz): v = v_c + w × (x − c). Igual que
        # mj_objectVelocity, pero para todos los cuerpos de una vez (BITACORA 0019).
        F, T = self._F, self._T
        F[:] = 0.0
        T[:] = 0.0
        com = self._com
        com[:] = data.subtree_com[self.sel_r]
        _nucleo(data.cvel[self.sel], data.xpos[self.sel], com, data.xmat[self.sel], self.dlin, self.drot, F, T)
        data.xfrc_applied[self.sel, :3] = F
        data.xfrc_applied[self.sel, 3:] = T
