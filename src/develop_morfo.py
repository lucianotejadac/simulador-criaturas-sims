"""Etapa 2: desarrollo del genoma morfológico (grafo dirigido) a MJCF.

Recorre el grafo desde la raíz instanciando piezas (respetando límites
recursivos, conexiones "solo terminal", escala y reflexión), escribe el XML
de MuJoCo con una, dos o tres bisagras por articulación según el tipo, y
aplana los cerebros anidados (uno por instancia de pieza, más las centrales)
en un único grafo con el formato de la Etapa 1, que `brain.Cerebro` ejecuta.

Reflexión (BITACORA 0008): una hija reflejada se coloca espejada respecto del
plano XZ de la madre (posición M·p, orientación M·R·M, ejes M·a) y el signo
del torque y del sensor de sus articulaciones se invierte, de modo que el
mismo cerebro produce el movimiento espejo. El estado de reflexión se
hereda por el subárbol.
"""
from __future__ import annotations

import math

import numpy as np

from develop import K_FUERZA
from genome import morph

SEPARACION = 0.02      # hueco entre la cara de la madre y la hija, donde va la articulación
DENSIDAD_PIEZAS = 300.0
PASO_FISICA = 1.0 / 480.0

# Cara 0..5 = +X, -X, +Y, -Y, +Z, -Z de la madre: normal y los dos ejes de la cara.
_CARAS = [
    (np.array([1, 0, 0.0]), 1, 2), (np.array([-1, 0, 0.0]), 1, 2),
    (np.array([0, 1, 0.0]), 2, 0), (np.array([0, -1, 0.0]), 2, 0),
    (np.array([0, 0, 1.0]), 0, 1), (np.array([0, 0, -1.0]), 0, 1),
]
_EJES = {"x": np.array([1.0, 0, 0]), "y": np.array([0, 1.0, 0]), "z": np.array([0, 0, 1.0])}
_M = np.diag([1.0, -1.0, 1.0])   # espejo respecto del plano XZ de la madre


def _rot_euler(gx: float, gy: float, gz: float) -> np.ndarray:
    """Rotación intrínseca X·Y·Z en grados, como matriz 3x3."""
    ax, ay, az = map(math.radians, (gx, gy, gz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def _quat(R: np.ndarray) -> np.ndarray:
    """Matriz de rotación -> cuaternión (w, x, y, z)."""
    tr = np.trace(R)
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


class Pieza:
    """Una instancia de un nodo en el cuerpo desarrollado."""

    def __init__(self, nombre, nodo_idx, dims, madre, pos, R, ejes, limite, espejo, escala):
        self.nombre = nombre
        self.nodo_idx = nodo_idx
        self.dims = dims            # dimensiones completas (m)
        self.madre = madre          # Pieza o None
        self.pos = pos              # posición del centro respecto de la madre
        self.R = R                  # orientación respecto de la madre
        self.ejes = ejes            # ejes (en el marco propio) de cada grado de libertad
        self.limite = limite
        self.espejo = espejo        # instancia reflejada: signo invertido en torque y sensor
        self.escala = escala
        self.hijas: list[Pieza] = []
        self.base_sensor = 0
        self.base_efector = 0
        self.ids_locales: dict[int, int] = {}   # id de neurona local -> índice global


def _instanciar(g: dict, nodo_idx: int, madre, conexion, contador: dict, piezas: list,
                espejo: bool, escala: float) -> None:
    nodo = g["nodos"][nodo_idx]
    if len(piezas) >= morph.MAX_PIEZAS:
        return
    dims = [max(morph.DIM_MIN * 0.5, d * escala) for d in nodo["dims"]]
    if madre is None:
        pos, R, ejes = np.zeros(3), np.eye(3), []
    else:
        n, i1, i2 = _CARAS[conexion["cara"]]
        md = np.array(madre.dims) / 2.0
        ancla = n * md[int(np.abs(n).argmax())]
        e1, e2 = np.zeros(3), np.zeros(3)
        e1[i1], e2[i2] = 1.0, 1.0
        ancla = ancla + e1 * conexion["u"] * md[i1] + e2 * conexion["v"] * md[i2]
        R_base = np.column_stack([n, e1, e2])        # X de la hija = normal de la cara
        if np.linalg.det(R_base) < 0:
            R_base[:, 2] *= -1
        R = R_base @ _rot_euler(*conexion["rot"])
        pos = ancla + R @ np.array([SEPARACION + dims[0] / 2.0, 0, 0])
        ejes = [_EJES[a].copy() for a in morph.ARTICULACIONES[nodo["art"]]]
        if espejo:
            pos = _M @ pos
            R = _M @ R @ _M
            ejes = [_M @ a for a in ejes]
    pieza = Pieza(f"p{len(piezas)}_n{nodo_idx}", nodo_idx, dims, madre, pos, R, ejes,
                  nodo["limite"], espejo, escala)
    piezas.append(pieza)
    if madre is not None:
        madre.hijas.append(pieza)
    contador = dict(contador)
    contador[nodo_idx] = contador.get(nodo_idx, 0) + 1
    ultima = contador[nodo_idx] >= nodo["rec"]
    for c in nodo["conexiones"]:
        if c["terminal"] and not ultima:
            continue
        if contador.get(c["a"], 0) >= g["nodos"][c["a"]]["rec"]:
            continue   # límite recursivo del nodo destino alcanzado en esta rama
        _instanciar(g, c["a"], pieza, c, contador, piezas,
                    espejo != bool(c["reflejo"]), escala * c["escala"])


def _mjcf(piezas: list, gravedad: bool) -> str:
    g = "0 0 -9.81" if gravedad else "0 0 0"
    out = ['<mujoco model="criatura">\n',
           '  <compiler angle="degree" autolimits="true"/>\n',
           f'  <option timestep="{PASO_FISICA:.6f}" gravity="{g}" integrator="implicitfast"/>\n',
           '  <default>\n',
           f'    <geom type="box" density="{DENSIDAD_PIEZAS}" rgba="0.85 0.89 0.92 1"/>\n',
           '    <joint type="hinge" damping="0.3"/>\n',
           '    <motor ctrlrange="-1 1"/>\n',
           '  </default>\n  <worldbody>\n']
    actuadores: list[str] = []

    def escribir(p, nivel: int) -> None:
        ind = "    " + "  " * nivel
        q = _quat(p.R)
        out.append(f'{ind}<body name="{p.nombre}" pos="{p.pos[0]:.5f} {p.pos[1]:.5f} {p.pos[2]:.5f}" '
                   f'quat="{q[0]:.6f} {q[1]:.6f} {q[2]:.6f} {q[3]:.6f}">\n')
        if p.madre is None:
            out.append(f'{ind}  <freejoint name="raiz"/>\n')
        else:
            anc = -(SEPARACION + p.dims[0] / 2.0)
            area = min(p.dims[1] * p.dims[2], p.madre.dims[1] * p.madre.dims[2])
            torque = K_FUERZA * area * (-1.0 if p.espejo else 1.0)
            for k, eje in enumerate(p.ejes):
                nombre = f"{p.nombre}_j{k}"
                out.append(f'{ind}  <joint name="{nombre}" axis="{eje[0]:.4f} {eje[1]:.4f} {eje[2]:.4f}" '
                           f'pos="{anc:.5f} 0 0" range="-{p.limite:.2f} {p.limite:.2f}"/>\n')
                actuadores.append(f'    <motor name="m_{nombre}" joint="{nombre}" gear="{torque:.4f}"/>\n')
        rgba = ' rgba="0.25 0.72 0.8 1"' if p.madre is None else ""
        out.append(f'{ind}  <geom name="g_{p.nombre}" size="{p.dims[0] / 2:.5f} {p.dims[1] / 2:.5f} '
                   f'{p.dims[2] / 2:.5f}"{rgba}/>\n')
        for h in p.hijas:
            escribir(h, nivel + 1)
        out.append(f'{ind}</body>\n')

    escribir(piezas[0], 0)
    out.append("  </worldbody>\n  <actuator>\n")
    out.extend(actuadores)
    out.append("  </actuator>\n</mujoco>\n")
    return "".join(out)


def _aplanar_cerebro(g: dict, piezas: list) -> dict:
    """Instancia el cerebro de cada pieza y las centrales en un solo grafo plano
    (formato de la Etapa 1: tipos s, n, c con índices globales)."""
    neuronas: list[tuple[dict, object]] = []
    centrales_idx: dict[int, int] = {}
    for neu in g["central"]:
        centrales_idx[neu["id"]] = len(neuronas)
        neuronas.append((neu, None))
    sensor = efector = 0
    for p in piezas:
        nodo = g["nodos"][p.nodo_idx]
        p.base_sensor, p.base_efector = sensor, efector
        for neu in nodo["neuronas"]:
            p.ids_locales[neu["id"]] = len(neuronas)
            neuronas.append((neu, p))
        sensor += len(p.ejes)
        efector += len(p.ejes)
    raiz = piezas[0]

    # Una referencia que no existe en esta instancia (por ejemplo "p" a una
    # neurona que la madre concreta no tiene) vale cero: entrada ausente.
    nada = ["c", 0, 0.0]

    def resolver(e: list, p) -> list:
        t, r, w = e
        if t == "c":
            return ["c", 0, w]
        if t == "g":
            return ["n", centrales_idx[r], w] if r in centrales_idx else nada
        if t == "r":
            return ["n", raiz.ids_locales[r], w] if r in raiz.ids_locales else nada
        if p is None:
            return nada
        if t == "s":
            return ["s", p.base_sensor + r, -w if p.espejo else w] if r < len(p.ejes) else nada
        if t == "n":
            return ["n", p.ids_locales[r], w] if r in p.ids_locales else nada
        if t == "p":
            if p.madre is not None and r in p.madre.ids_locales:
                return ["n", p.madre.ids_locales[r], w]
            return nada
        return nada

    plano = [{"f": neu["f"], "in": [resolver(e, p) for e in neu["in"]]} for neu, p in neuronas]
    efectores = []
    for p in piezas:
        nodo = g["nodos"][p.nodo_idx]
        for k in range(len(p.ejes)):
            efectores.append(resolver(nodo["efectores"][k], p))
    return {"n_sensores": sensor, "neuronas": plano, "efectores": efectores}


def desarrollar(g: dict, gravedad: bool = False) -> dict:
    """Genoma morfológico -> {"xml", "cerebro" (plano), "piezas", "n_dof"}.

    Lanza ValueError si el cuerpo alcanza MAX_PIEZAS o no tiene grados de
    libertad. La interpenetración se verifica aparte con `interpenetra`.
    """
    piezas: list = []
    _instanciar(g, g["raiz"], None, None, {}, piezas, False, 1.0)
    if len(piezas) >= morph.MAX_PIEZAS:
        raise ValueError(f"demasiadas piezas (>= {morph.MAX_PIEZAS})")
    n_dof = sum(len(p.ejes) for p in piezas)
    if n_dof == 0:
        raise ValueError("cuerpo sin grados de libertad")
    xml = _mjcf(piezas, gravedad)
    cerebro = _aplanar_cerebro(g, piezas)
    info = [{"nombre": p.nombre, "nodo": p.nodo_idx, "dims": p.dims, "espejo": p.espejo,
             "madre": p.madre.nombre if p.madre else None, "dof": len(p.ejes)} for p in piezas]
    return {"xml": xml, "cerebro": cerebro, "piezas": info, "n_dof": n_dof}


def interpenetra(model, data) -> bool:
    """True si hay contacto en reposo entre piezas no adyacentes (madre-hija se filtra)."""
    import mujoco
    mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)
    return data.ncon > 0


def compilar(g: dict, gravedad: bool = False):
    """Desarrolla y compila en MuJoCo. Devuelve (model, data, resultado) o lanza ValueError."""
    import mujoco
    r = desarrollar(g, gravedad)
    model = mujoco.MjModel.from_xml_string(r["xml"])
    data = mujoco.MjData(model)
    if interpenetra(model, data):
        raise ValueError("piezas interpenetradas")
    return model, data, r
