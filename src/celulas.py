"""Etapa 8: de la unicelularidad a la multicelularidad, en el mundo 2D viscoso.

Cada célula es un segmento chico con un genoma mínimo:
    adhesion   probabilidad de que la hija nazca unida a la madre (0 = siempre suelta)
    cilio      0/1: la célula aplica torque oscilante en su unión con la madre
    amplitud   fuerza relativa del cilio (0..1)
    frecuencia Hz
    retardo    desfase del cilio respecto del de la madre (rad): heredado, hace ondas viajeras
    sesgo      cuánto curva hacia la comida (fototaxis), 0 al principio
    largo      m

Un grupo es un árbol de células unidas: un cuerpo articulado del mundo 2D.
Una célula sola no puede nadar (teorema de la vieira, BITACORA 0022); con
tres o más y desfase, sí. La comida chica la come la célula que la toca
(con --reparto se reparte por igual en el grupo: bien público, y una célula
con adhesión pero sin cilio viaja gratis); la grande siempre se reparte.

Fuerzas a favor del grupo, cada una activable: comida grande que exige masa,
un depredador que come todo lo que mida menos que cierto tamaño, y la propia
locomoción. En contra: existir y mover cuestan energía por célula.

Entre épocas (20 s) se aplican divisiones y muertes y se rearman los cuerpos:
una célula muerta corta el árbol en subárboles, que siguen como grupos.

Uso:
    python src/celulas.py --nombre cel-A --semilla 1 --epocas 90 --celulas 150
    python src/celulas.py --nombre cel-C --semilla 1 --epocas 90 --celulas 150 --depredador
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

import develop2d  # noqa: E402
from mundo2d import ESPESOR  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUNDO = 30.0
DT = 1.0 / 60.0
T_EPOCA = 20.0
N_CHICA, N_GRANDE = 240, 0           # comida presente como máximo (0.27 por m²)
TASA_CHICA, TASA_GRANDE = 6.0, 0.3   # comidas nuevas por segundo (la comida comida no reaparece al instante)
E_CHICA, E_GRANDE = 50.0, 200.0
MASA_GRANDE = 0.6          # kg: masa mínima del grupo para comer comida grande (dos células medianas)
RADIO_COMER = 0.4
E0, E_DIV, E_HIJA = 60.0, 100.0, 50.0   # una comida chica alcanza para una división
COSTO_MASA, COSTO_TORQUE = 0.4, 0.004   # basal: ~2.8 por época para una célula media
EDAD_MAXIMA = 2000.0
MAX_CELULAS = 600
MAX_GRUPO = 16
TORQUE_CELULA = 1000.0 * 0.08 * ESPESOR   # K_FUERZA · área de contacto (ancho 0.08 × espesor)
DEPREDADOR = {"activo": False, "radio": 1.2, "masa_escape": 0.5, "velocidad": 1.2}
F_FLAGELO = 0.3          # N: empuje axial de una célula con cilio y amplitud 1 (flagelo propio): 1.2 m por época sola
COSTO_EMPUJE = 0.3       # energía por N·s de empuje: un cilio a amplitud 1 cuesta 1.8 por época
REPARTO = False    # True: la comida chica se reparte por igual en el grupo (bien público); False: la come la célula que la toca
AGITACION = 0.05   # m/sqrt(s): deriva browniana de una célula sola (~0.3 m por época; nadar importa)
SESGO_MAX = 4.0


FRAC_ADHESIVAS = 0.0     # fracción de fundadoras que nacen con adhesión 1 (prueba de invasión)
ANCESTRO = "flagelado"   # "flagelado": todas con cilio y desfase útil (0.5–1.5 rad); "azar": cilio al 50 % y desfase ±1


def genoma_inicial(rng: random.Random) -> dict:
    if ANCESTRO == "flagelado":
        cilio, retardo, sesgo = 1, rng.uniform(0.5, 1.5), rng.uniform(0.0, 1.0)
    else:
        cilio, retardo, sesgo = (1 if rng.random() < 0.5 else 0), rng.uniform(-1.0, 1.0), 0.0
    return {"adhesion": 1.0 if rng.random() < FRAC_ADHESIVAS else 0.0, "cilio": cilio, "amplitud": rng.uniform(0.3, 1.0),
            "frecuencia": rng.uniform(0.5, 2.0), "retardo": retardo, "sesgo": sesgo,
            "largo": rng.uniform(0.12, 0.25)}


def mutar(g: dict, rng: random.Random) -> dict:
    g = dict(g)
    k = rng.randrange(7)
    if k == 0:
        g["adhesion"] = min(1.0, max(0.0, g["adhesion"] + rng.gauss(0.0, 0.3)))
    elif k == 1:
        g["cilio"] = 1 - g["cilio"]
    elif k == 2:
        g["amplitud"] = min(1.0, max(0.0, g["amplitud"] + rng.gauss(0.0, 0.2)))
    elif k == 3:
        g["frecuencia"] = min(3.0, max(0.2, g["frecuencia"] + rng.gauss(0.0, 0.3)))
    elif k == 4:
        g["retardo"] = g["retardo"] + rng.gauss(0.0, 0.5)
    elif k == 5:
        g["sesgo"] = min(SESGO_MAX, max(-SESGO_MAX, g["sesgo"] + rng.gauss(0.0, 0.8)))
    else:
        g["largo"] = min(0.4, max(0.08, g["largo"] + rng.gauss(0.0, 0.03)))
    return g


class Celula:
    __slots__ = ("id", "g", "energia", "nacimiento", "madre", "hijas", "cara", "u", "comidas", "fase")

    def __init__(self, ident, g, energia, nacimiento, madre=None, cara=None, u=0.0):
        self.id, self.g, self.energia, self.nacimiento = ident, g, energia, nacimiento
        self.madre = madre            # Celula a la que está unida (None si es raíz de su grupo)
        self.hijas = []               # células unidas que cuelgan de esta
        self.cara, self.u = cara, u   # dónde está unida a la madre
        self.comidas = 0
        self.fase = 0.0

    @property
    def masa(self) -> float:
        return self.g["largo"] * 0.08 * ESPESOR * 300.0


def grupos_de(celulas: list[Celula]) -> list[list[Celula]]:
    """Componentes conexas por adhesión, cada una ordenada desde su raíz (recorrido en profundidad)."""
    vistas = set()
    grupos = []
    for c in celulas:
        if c.id in vistas:
            continue
        r = c
        while r.madre is not None:
            r = r.madre
        orden = []
        pila = [r]
        while pila:
            x = pila.pop()
            if x.id in vistas:
                continue
            vistas.add(x.id)
            orden.append(x)
            pila.extend(reversed(x.hijas))
        grupos.append(orden)
    return grupos


class Epoca:
    """Cuerpos del mundo 2D para los grupos actuales, con torques de cilio calculados por célula."""

    def __init__(self, grupos: list[list[Celula]], poses: dict, thetas: dict):
        self.grupos = grupos
        des = []
        self.indice = {}        # id de célula -> (b, i)
        for b, gr in enumerate(grupos):
            segs = []
            pos = {gr[0].id: 0}
            for i, c in enumerate(gr):
                pos[c.id] = i
                if c.madre is None:
                    seg = develop2d.Segmento(0, -1, (0.0, 0.0), 0.0, c.g["largo"], 0.08, 0.0, math.radians(60), False)
                else:
                    m = c.madre
                    hl, hw = m.g["largo"] / 2.0, 0.04
                    if c.cara == 0:
                        anclaje, base = (hl, c.u * hw), 0.0
                    elif c.cara == 2:
                        anclaje, base = (-c.u * hl, hw), math.pi / 2
                    else:
                        anclaje, base = (c.u * hl, -hw), -math.pi / 2
                    seg = develop2d.Segmento(0, pos[m.id], anclaje, base, c.g["largo"], 0.08,
                                             TORQUE_CELULA if c.g["cilio"] else 0.0, math.radians(60), False)
                seg.indice = i
                segs.append(seg)
                self.indice[c.id] = (b, i)
            des.append({"segmentos": segs, "n": len(segs)})
        self.lote = develop2d.lote_desde(des)
        self.B, self.N = self.lote.B, self.lote.N
        # pose inicial: la raíz conserva su pose; los ángulos, si existen
        for b, gr in enumerate(grupos):
            r = gr[0]
            if r.id in poses:
                self.lote.pose[b] = poses[r.id]
            for i, c in enumerate(gr):
                if c.id in thetas and i > 0:
                    self.lote.theta[b, i] = thetas[c.id]
        # parámetros vectorizados de los cilios
        self.amp = np.zeros((self.B, self.N))
        self.frec = np.zeros((self.B, self.N))
        self.fase = np.zeros((self.B, self.N))
        self.sesgo = np.zeros((self.B, self.N))
        self.emp = np.zeros((self.B, self.N))
        self.masa_grupo = np.zeros(self.B)
        for b, gr in enumerate(grupos):
            for i, c in enumerate(gr):
                self.masa_grupo[b] += c.masa
                self.emp[b, i] = F_FLAGELO * c.g["amplitud"] * c.g["cilio"]
                if i == 0:
                    c.fase = 0.0
                    continue
                c.fase = c.madre.fase + c.g["retardo"]
                self.amp[b, i] = c.g["amplitud"] if c.g["cilio"] else 0.0
                self.frec[b, i] = gr[0].g["frecuencia"]   # un solo reloj por cuerpo: el de la raíz (sin eso no hay onda viajera)
                self.fase[b, i] = c.fase
                self.sesgo[b, i] = c.g["sesgo"]
        self.pose_inicial = self.lote.pose.copy()
        self.comidas = np.zeros(self.B, dtype=int)
        self.energia_comida = np.zeros((self.B, self.N))   # por célula: quien toca la comida chica, la come
        self.torque_acum = np.zeros((self.B, self.N))
        self.t = 0.0
        self.come_grande = self.masa_grupo >= MASA_GRANDE
        self.deriva = AGITACION / np.sqrt(np.array([len(g) for g in grupos], dtype=float))

    def paso(self, comida: np.ndarray, rng: np.random.Generator, depredador: dict | None) -> None:
        lote = self.lote
        centro, phi, com = lote.cinematica()
        # comida comestible más cercana al centro de masa del grupo
        d = _envolver(comida[None, :, :2] - com[:, None, :])
        dist = np.hypot(d[..., 0], d[..., 1])
        chica = comida[:, 2] == 0
        permitido = (chica[None, :] | self.come_grande[:, None]) & (comida[:, 3] > 0)[None, :]
        dist_ok = np.where(permitido, dist, np.inf)
        j = dist_ok.argmin(1)
        dmin = dist_ok[np.arange(self.B), j]
        # ¿alguna célula del grupo toca la comida? (distancia mínima de los segmentos)
        for b in np.flatnonzero(dmin < RADIO_COMER + 1.0):
            f = j[b]
            if comida[f, 3] <= 0:
                continue
            n = lote.nseg[b]
            dd = _envolver(comida[f, :2][None, :] - centro[b, :n])
            dcel = np.hypot(dd[:, 0], dd[:, 1])
            if dcel.min() < RADIO_COMER:
                if comida[f, 2] == 0 and not REPARTO:
                    self.energia_comida[b, dcel.argmin()] += E_CHICA
                else:
                    self.energia_comida[b, :n] += (E_CHICA if comida[f, 2] == 0 else E_GRANDE) / n
                self.comidas[b] += 1
                comida[f, 3] = 0
        # reposición a tasa fija: la comida comida no reaparece al instante
        for tipo, tasa in ((0, TASA_CHICA), (1, TASA_GRANDE)):
            if rng.random() < tasa * DT:
                libres = np.flatnonzero((comida[:, 2] == tipo) & (comida[:, 3] <= 0))
                if len(libres):
                    f = libres[rng.integers(len(libres))]
                    comida[f, :2] = rng.uniform(-MUNDO / 2, MUNDO / 2, size=2)
                    comida[f, 3] = 1
        objetivo = comida[j, :2]
        hay = np.isfinite(dmin)[:, None]
        # torques: cilio oscilante + sesgo hacia la comida (componente lateral en el marco del segmento)
        dx = _envolver(objetivo[:, None, 0] - centro[:, :, 0])
        dy = _envolver(objetivo[:, None, 1] - centro[:, :, 1])
        r = np.maximum(1e-9, np.hypot(dx, dy))
        ly = (-np.sin(phi) * dx + np.cos(phi) * dy) / r
        torque = self.amp * np.sin(2 * np.pi * self.frec * self.t + self.fase) + 0.25 * self.sesgo * ly * (self.amp > 0) * hay
        torque = np.clip(torque, -1.0, 1.0)
        self.torque_acum += np.abs(torque) * lote.torque_max
        lote.paso(torque, DT, self.emp)
        if AGITACION > 0.0:
            lote.pose[:, :2] += rng.normal(0.0, 1.0, size=(self.B, 2)) * (self.deriva * math.sqrt(DT))[:, None]
            lote.pose[:, 2] += rng.normal(0.0, 1.0, size=self.B) * (0.5 * self.deriva * math.sqrt(DT))
        lote.pose[:, :2] = _envolver(lote.pose[:, :2])
        self.t += DT
        if depredador is not None:
            depredador["pos"] = _envolver(depredador["pos"] + depredador["dir"] * depredador["velocidad"] * DT)
            if rng.random() < 0.02:
                a = rng.uniform(0, 2 * np.pi)
                depredador["dir"] = np.array([np.cos(a), np.sin(a)])
            dd = _envolver(com - depredador["pos"][None, :])
            cerca = np.hypot(dd[:, 0], dd[:, 1]) < depredador["radio"]
            for b in np.flatnonzero(cerca & (self.masa_grupo < depredador["masa_escape"])):
                self.comidos_por_depredador.add(b)


def _envolver(x):
    return (x + MUNDO / 2.0) % MUNDO - MUNDO / 2.0


def correr(nombre: str, semilla: int, epocas: int, n_celulas: int, depredador: bool, comida_grande: int,
           grabar_cada: int, fps: float) -> None:
    rng = random.Random(semilla)
    nrng = np.random.default_rng(semilla)
    carpeta = os.path.join(RAIZ, "runs", nombre)
    os.makedirs(carpeta, exist_ok=True)
    celulas: list[Celula] = []
    sig = 0
    poses, thetas = {}, {}
    for _ in range(n_celulas):
        c = Celula(sig, genoma_inicial(rng), E0, 0.0)
        poses[c.id] = np.array([nrng.uniform(-MUNDO / 2, MUNDO / 2), nrng.uniform(-MUNDO / 2, MUNDO / 2), nrng.uniform(-math.pi, math.pi)])
        celulas.append(c)
        sig += 1
    n_grande = comida_grande
    comida = np.zeros((N_CHICA + n_grande, 4))
    comida[:, :2] = nrng.uniform(-MUNDO / 2, MUNDO / 2, size=(len(comida), 2))
    comida[N_CHICA:, 2] = 1
    comida[:, 3] = 1
    dep = {"pos": np.zeros(2), "dir": np.array([1.0, 0.0]), "velocidad": DEPREDADOR["velocidad"],
           "radio": DEPREDADOR["radio"], "masa_escape": DEPREDADOR["masa_escape"]} if depredador else None
    config = {"nombre": nombre, "etapa": 8, "semilla": semilla, "epocas": epocas, "celulas": n_celulas, "mundo": MUNDO,
              "t_epoca": T_EPOCA, "depredador": dep is not None and dict(DEPREDADOR), "comida_grande": n_grande,
              "reglas": {"n_chica": N_CHICA, "tasa_chica": TASA_CHICA, "tasa_grande": TASA_GRANDE, "e_chica": E_CHICA, "e_grande": E_GRANDE, "masa_grande": MASA_GRANDE,
                         "radio_comer": RADIO_COMER, "e0": E0, "e_div": E_DIV, "e_hija": E_HIJA, "costo_masa": COSTO_MASA,
                         "costo_torque": COSTO_TORQUE, "f_flagelo": F_FLAGELO, "costo_empuje": COSTO_EMPUJE, "edad_maxima": EDAD_MAXIMA, "max_celulas": MAX_CELULAS,
                         "max_grupo": MAX_GRUPO, "agitacion": AGITACION, "reparto": REPARTO, "ancestro": ANCESTRO, "adhesivas": FRAC_ADHESIVAS, "radio_depredador": DEPREDADOR["radio"], "masa_escape": DEPREDADOR["masa_escape"]}}
    json.dump(config, open(os.path.join(carpeta, "config.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    historia, grabaciones = [], []
    t_global = 0.0
    t0 = time.time()
    pasos = int(round(T_EPOCA / DT))
    cada = max(1, int(round(1.0 / (fps * DT))))
    transicion = None
    for epoca in range(epocas):
        if not celulas:
            print(f"época {epoca}: extinción total", flush=True)
            break
        t_ep = time.time()
        grupos = grupos_de(celulas)
        E = Epoca(grupos, poses, thetas)
        E.comidos_por_depredador = set()
        grabar = (epoca % grabar_cada == 0) or epoca == epocas - 1
        cuadros, cuadros_comida, cuadros_dep = [], [], []
        for k in range(pasos):
            E.paso(comida, nrng, dep)
            if grabar and k % cada == 0:
                centro, phi, _ = E.lote.cinematica()
                arr = np.concatenate([centro, phi[..., None]], axis=2)
                cuadros.append([arr[b, :E.lote.nseg[b]].reshape(-1).round(2).tolist() for b in range(E.B)])
                cuadros_comida.append(comida[comida[:, 3] > 0, :3].round(2).tolist())
                if dep is not None:
                    cuadros_dep.append(dep["pos"].round(2).tolist())
        t_global += T_EPOCA
        # energía: costo por célula, reparto del alimento del grupo por igual (bien público)
        desplaz = np.hypot(*_envolver(E.lote.pose[:, :2] - E.pose_inicial[:, :2]).T)
        muertas_dep = 0
        for b, gr in enumerate(grupos):
            n = len(gr)
            for i, c in enumerate(gr):
                c.energia += E.energia_comida[b, i] - (COSTO_MASA * c.masa * T_EPOCA + COSTO_TORQUE * E.torque_acum[b, i] * DT
                                                        + COSTO_EMPUJE * E.emp[b, i] * T_EPOCA)
                c.comidas += int(E.comidas[b]) if i == 0 else 0
                if b in E.comidos_por_depredador:
                    c.energia = -1.0
                    muertas_dep += 1
        # estado para la próxima época
        poses, thetas = {}, {}
        for b, gr in enumerate(grupos):
            poses[gr[0].id] = E.lote.pose[b].copy()
            for i, c in enumerate(gr):
                thetas[c.id] = float(E.lote.theta[b, i])
        if grabar:
            grabaciones.append({"epoca": epoca, "t": t_global - T_EPOCA, "fps": 1.0 / (cada * DT),
                                "criaturas": [{"id": gr[0].id, "especie": "celulas", "madre": None, "energia": round(sum(c.energia for c in gr), 1),
                                               "comidas": int(E.comidas[b]), "n": len(gr),
                                               "segmentos": [[round(c.g["largo"], 3), 0.08] for c in gr],
                                               "cilios": sum(c.g["cilio"] for c in gr), "adhesion": round(sum(c.g["adhesion"] for c in gr) / len(gr), 2)}
                                              for b, gr in enumerate(grupos)],
                                "cuadros": cuadros, "comida": cuadros_comida, "depredador": cuadros_dep, "N": E.N})
        # muertes: cortar árboles
        vivas = []
        muertes = 0
        for c in celulas:
            if c.energia <= 0 or (t_global - c.nacimiento) > EDAD_MAXIMA:
                muertes += 1
                for h in c.hijas:
                    h.madre = None
                    h.cara = None
                    # la hija huérfana hereda la pose aproximada de la madre como raíz nueva
                    if c.id in poses or (c.madre is None and c.id in poses):
                        pass
                if c.madre is not None:
                    c.madre.hijas = [h for h in c.madre.hijas if h is not c]
                # pose para las nuevas raíces: la del grupo (aprox.)
                b, i = E.indice[c.id]
                centro, phi, _ = E.lote.cinematica()
                for h in c.hijas:
                    bi = E.indice[h.id]
                    poses[h.id] = np.array([centro[bi[0], bi[1], 0], centro[bi[0], bi[1], 1], phi[bi[0], bi[1]]])
            else:
                vivas.append(c)
        celulas = vivas
        # divisiones
        nuevas, nac, nac_unidas = [], 0, 0
        for c in sorted(celulas, key=lambda x: -x.energia):
            if c.energia < E_DIV or len(celulas) + len(nuevas) >= MAX_CELULAS:
                continue
            g = mutar(c.g, rng)   # una mutación por nacimiento
            h = Celula(sig, g, E_HIJA, t_global)
            sig += 1
            c.energia -= E_HIJA
            # ¿unida? según la adhesión de la madre, si hay lugar en el grupo
            raiz = c
            while raiz.madre is not None:
                raiz = raiz.madre
            tam = 0
            pila = [raiz]
            while pila:
                x = pila.pop()
                tam += 1
                pila.extend(x.hijas)
            libres = [k for k in (0, 2, 3) if k not in [x.cara for x in c.hijas]]
            if libres and tam < MAX_GRUPO and rng.random() < c.g["adhesion"]:
                h.madre = c
                h.cara = 0 if (0 in libres and rng.random() < 0.6) else rng.choice(libres)
                h.u = rng.uniform(-0.5, 0.5)
                c.hijas.append(h)
                nac_unidas += 1
            else:
                b, i = E.indice[c.id]
                centro, phi, _ = E.lote.cinematica()
                ang = rng.uniform(0, 2 * math.pi)
                poses[h.id] = np.array([_envolver(centro[b, i, 0] + 0.6 * math.cos(ang)), _envolver(centro[b, i, 1] + 0.6 * math.sin(ang)), rng.uniform(-math.pi, math.pi)])
            nuevas.append(h)
            nac += 1
        celulas += nuevas
        # métricas
        grupos_n = [len(g) for g in grupos_de(celulas)]
        tam = {}
        for n in grupos_n:
            tam[n] = tam.get(n, 0) + 1
        en_grupo = sum(n for n in grupos_n if n >= 3) / max(1, len(celulas))
        adh = sum(c.g["adhesion"] for c in celulas) / max(1, len(celulas))
        cil = sum(c.g["cilio"] for c in celulas) / max(1, len(celulas))
        ses = sum(abs(c.g["sesgo"]) for c in celulas) / max(1, len(celulas))
        desp_por_tam = {}
        for b, gr in enumerate(grupos):
            desp_por_tam.setdefault(len(gr), []).append(float(desplaz[b]))
        desp_por_tam = {n: round(float(np.mean(v)), 2) for n, v in desp_por_tam.items()}
        if transicion is None and en_grupo > 0.5:
            transicion = t_global
            print(f"  *** transición: más de la mitad de las células vive en grupos de 3 o más, t = {t_global:.0f} s", flush=True)
        fila = {"epoca": epoca, "t": t_global, "celulas": len(celulas), "grupos": len(grupos_n), "tamanos": tam,
                "fraccion_en_grupo": round(en_grupo, 3), "adhesion_media": round(adh, 3), "cilio_frac": round(cil, 3),
                "sesgo_medio": round(ses, 3), "nacimientos": nac, "nacidas_unidas": nac_unidas, "muertes": muertes,
                "muertas_por_depredador": muertas_dep, "comidas": int(E.comidas.sum()), "desplazamiento_por_tamano": desp_por_tam,
                "segundos": round(time.time() - t_ep, 1)}
        historia.append(fila)
        print(f"época {epoca:3d} t={t_global:5.0f} s  células {len(celulas):3d} grupos {len(grupos_n):3d} tamaños {dict(sorted(tam.items()))}  "
              f"en grupo {en_grupo:.2f} adh {adh:.2f} cilio {cil:.2f} sesgo {ses:.2f}  nac {nac:3d} ({nac_unidas} unidas) muertes {muertes:3d}"
              f"{' dep ' + str(muertas_dep) if dep else ''}  comidas {int(E.comidas.sum()):3d}  {fila['segundos']:5.1f} s", flush=True)
        json.dump(historia, open(os.path.join(carpeta, "historia.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump([{"id": c.id, "g": c.g, "energia": c.energia, "nacimiento": c.nacimiento, "madre": c.madre.id if c.madre else None}
               for c in celulas], open(os.path.join(carpeta, "celulas_final.json"), "w", encoding="utf-8"), separators=(",", ":"))
    datos = {"meta": {"corrida": nombre, "etapa": 8, "mundo": MUNDO, "t_epoca": T_EPOCA, "especies": ["celulas"],
                      "epocas": len(historia), "reglas": config["reglas"], "transicion": transicion, "depredador": dep is not None},
             "historia": historia, "epocas": grabaciones}
    destino = os.path.join(carpeta, "acuario2d.json")
    json.dump(datos, open(destino, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB, {len(grabaciones)} épocas grabadas; "
          f"listo en {time.time() - t0:.0f} s; transición {transicion}", flush=True)


def main() -> None:
    global AGITACION, N_CHICA, MAX_GRUPO, REPARTO, ANCESTRO, FRAC_ADHESIVAS
    ap = argparse.ArgumentParser(description="Unicelularidad -> multicelularidad (Etapa 8).")
    ap.add_argument("--nombre", default="cel01")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--epocas", type=int, default=90)
    ap.add_argument("--celulas", type=int, default=150)
    ap.add_argument("--depredador", action="store_true")
    ap.add_argument("--comida-grande", type=int, default=0)
    ap.add_argument("--grabar-cada", type=int, default=1)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--agitacion", type=float, default=AGITACION)
    ap.add_argument("--n-chica", type=int, default=N_CHICA)
    ap.add_argument("--max-grupo", type=int, default=MAX_GRUPO)
    ap.add_argument("--ancestro", choices=["flagelado", "azar"], default=ANCESTRO)
    ap.add_argument("--adhesivas", type=float, default=0.0, help="fracción de fundadoras con adhesión 1")
    ap.add_argument("--reparto", action="store_true", help="la comida chica se reparte por igual en el grupo (bien público)")
    a = ap.parse_args()
    AGITACION, N_CHICA, MAX_GRUPO, REPARTO, ANCESTRO = a.agitacion, a.n_chica, a.max_grupo, a.reparto, a.ancestro
    FRAC_ADHESIVAS = a.adhesivas
    correr(a.nombre, a.semilla, a.epocas, a.celulas, a.depredador, a.comida_grande, a.grabar_cada, a.fps)


if __name__ == "__main__":
    main()
