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
        self.dlin = np.array(dlin)
        self.drot = np.array(drot)
        self._vel = np.zeros(6)
        self._v = np.zeros((len(ids), 3))
        self._w = np.zeros((len(ids), 3))

    def aplicar(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        vel, v, w = self._vel, self._v, self._w
        for n, b in enumerate(self.ids):
            mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, int(b), vel, 0)
            w[n] = vel[:3]
            v[n] = vel[3:]
        R = data.xmat[self.ids].reshape(-1, 3, 3)          # columnas = ejes locales
        v_loc = np.einsum("nji,nj->ni", R, v)              # Rᵀ v
        w_loc = np.einsum("nji,nj->ni", R, w)
        F = np.einsum("nij,nj->ni", R, -self.dlin * v_loc)
        T = np.einsum("nij,nj->ni", R, -self.drot * w_loc)
        data.xfrc_applied[self.ids, :3] = F
        data.xfrc_applied[self.ids, 3:] = T
