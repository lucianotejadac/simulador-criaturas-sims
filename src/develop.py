"""Desarrollo genoma -> cuerpo (MJCF).

Etapa 1: el cuerpo es FIJO. Esta función construye siempre la misma cadena de
cuatro cajas unidas por tres bisagras coplanares (eje Z: ondulación lateral). En la Etapa 2 se
reemplaza por el desarrollo real desde el genoma morfológico de grafo dirigido.

Convenciones (MuJoCo): Z hacia arriba, unidades SI. La cadena se extiende a lo
largo de +X; la pieza 0 es la "cabeza".
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Constante de fuerza muscular: torque máximo = K_FUERZA * área de sección (m²).
# Sims: la fuerza máxima es proporcional al área transversal de las piezas unidas.
# Calibrado con una onda impuesta de 45° a 1 Hz, que exige ~10 N·m (BITACORA 0002 y 0004).
K_FUERZA = 1000.0


@dataclass
class CuerpoFijo:
    """Parámetros del cuerpo fijo de la Etapa 1."""

    n_piezas: int = 4
    largo: float = 0.40          # m, a lo largo de X
    ancho: float = 0.12          # m, sección cuadrada ancho x ancho
    separacion: float = 0.03     # m, hueco entre cajas donde va la bisagra
    limite_grados: float = 60.0  # límite articular +/- en grados
    ejes: tuple[str, ...] = ("z", "z", "z")  # bisagras coplanares: la cadena ondula de lado (BITACORA 0005)
    densidad_piezas: float = 300.0  # kg/m³; con 1000 la inercia domina al arrastre (BITACORA 0004)
    amortiguacion: float = 0.3   # N·m·s/rad en cada bisagra
    densidad_agua: float = 0.0   # el agua la pone fluido.py (arrastre por cara), no MuJoCo
    viscosidad_agua: float = 0.0
    paso: float = 1.0 / 480.0    # s, paso de física (convergencia verificada, BITACORA 0004)
    nombres: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.nombres:
            self.nombres = [f"pieza{i}" for i in range(self.n_piezas)]
        assert len(self.ejes) == self.n_piezas - 1

    @property
    def area_seccion(self) -> float:
        return self.ancho * self.ancho

    @property
    def torque_max(self) -> float:
        return K_FUERZA * self.area_seccion

    @property
    def n_dof(self) -> int:
        return self.n_piezas - 1


EJE_VEC = {"x": "1 0 0", "y": "0 1 0", "z": "0 0 1"}


def mjcf_cuerpo_fijo(c: CuerpoFijo | None = None, gravedad: bool = False) -> str:
    """Devuelve el XML MJCF de la cadena. `gravedad=False` es el mundo acuático."""
    c = c or CuerpoFijo()
    medio = c.largo / 2.0
    semi = c.ancho / 2.0
    lim = c.limite_grados
    g = "0 0 -9.81" if gravedad else "0 0 0"

    partes: list[str] = []
    partes.append(
        f'<mujoco model="cadena4">\n'
        f'  <compiler angle="degree" autolimits="true"/>\n'
        f'  <option timestep="{c.paso:.6f}" gravity="{g}" integrator="implicitfast"\n'
        f'          density="{c.densidad_agua}" viscosity="{c.viscosidad_agua}"/>\n'
        f'  <default>\n'
        f'    <geom type="box" size="{medio} {semi} {semi}" density="{c.densidad_piezas}" rgba="0.85 0.89 0.92 1"/>\n'
        f'    <joint type="hinge" range="-{lim} {lim}" damping="{c.amortiguacion}"/>\n'
        f'    <motor ctrlrange="-1 1" gear="{c.torque_max:.4f}"/>\n'
        f'  </default>\n'
        f'  <worldbody>\n'
    )
    # Pieza raíz con articulación libre, centrada en el origen.
    indent = "    "
    partes.append(f'{indent}<body name="{c.nombres[0]}" pos="0 0 0">\n')
    partes.append(f'{indent}  <freejoint name="raiz"/>\n')
    partes.append(f'{indent}  <geom name="g_{c.nombres[0]}" rgba="0.25 0.72 0.8 1"/>\n')
    # Cada hija nace en el extremo +X de su madre; la bisagra queda en el hueco.
    for i in range(1, c.n_piezas):
        eje = c.ejes[i - 1]
        indent += "  "
        # La bisagra está a (largo + separacion) del centro de la madre.
        partes.append(
            f'{indent}<body name="{c.nombres[i]}" pos="{c.largo + c.separacion:.4f} 0 0">\n'
            f'{indent}  <joint name="bisagra{i}" axis="{EJE_VEC[eje]}" pos="-{medio + c.separacion / 2:.4f} 0 0"/>\n'
            f'{indent}  <geom name="g_{c.nombres[i]}"/>\n'
        )
    # Cerrar cuerpos anidados (n_piezas niveles).
    cierre = []
    for i in range(c.n_piezas, 0, -1):
        cierre.append("    " + "  " * (i - 1) + "</body>\n")
    partes.extend(cierre)
    partes.append("  </worldbody>\n  <actuator>\n")
    for i in range(1, c.n_piezas):
        partes.append(f'    <motor name="m{i}" joint="bisagra{i}"/>\n')
    partes.append("  </actuator>\n</mujoco>\n")
    return "".join(partes)


if __name__ == "__main__":
    print(mjcf_cuerpo_fijo())
