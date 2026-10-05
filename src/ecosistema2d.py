"""Etapa 7: ecosistema 2D a escala. Cientos de criaturas, comida de dos tamaños, energía,
reproducción con mutación y muerte, en el mundo viscoso sin inercia (`mundo2d`).

Reglas (todas decisiones nuestras, BITACORA 0023):
- Mundo cuadrado de lado MUNDO, toroidal (lo que sale por un borde entra por el otro).
- Comida chica (vale E_CHICA) solo para cuerpos cortos (largo total ≤ LARGO_CHICO);
  comida grande (vale E_GRANDE) solo para cuerpos pesados (masa ≥ MASA_GRANDE).
  Cada criatura percibe la comida comestible más cercana. Al comer, la comida reaparece.
- Energía: inicial E0; cuesta existir (por kg y s) y moverse (por N·m aplicado y s).
  Con energía ≥ E_REPRO se reproduce (hija con 1-2 mutaciones, a su lado); a 0 o a la
  edad máxima, muere. Tope de población.
- Épocas de T_EPOCA s: entre épocas se aplican nacimientos y muertes y se rearma el lote.
  Pose, ángulos y energía se conservan; el cerebro se reinicia.

Uso:
    python src/ecosistema2d.py --nombre eco2d01 --semilla 1 --epocas 90 --por-especie 40
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
from brain_lote import CerebrosLote  # noqa: E402
from genome import bestiario, morph  # noqa: E402
from tareas import TAU_ACTIVACION  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MUNDO = 50.0
DT = 1.0 / 60.0
DT_CEREBRO = 1.0 / 960.0
T_EPOCA = 20.0
N_CHICA, N_GRANDE = 90, 30
E_CHICA, E_GRANDE = 40.0, 150.0
LARGO_CHICO = 1.3          # m: largo total máximo para comer comida chica
MASA_GRANDE = 2.0          # kg: masa mínima para comer comida grande
RADIO_COMER = 0.45
E0, E_REPRO, E_CRIA = 100.0, 160.0, 60.0
COSTO_MASA, COSTO_TORQUE = 0.03, 0.004
EDAD_MAXIMA = 400.0
POBLACION_MAXIMA = 500
MUTACIONES = (1, 2)


class Individuo:
    __slots__ = ("id", "especie", "genoma", "des", "pose", "theta", "energia", "madre", "nacimiento",
                 "comidas", "hijas", "largo_total", "masa")

    def __init__(self, ident, especie, genoma, des, pose, energia, madre, nacimiento):
        self.id, self.especie, self.genoma, self.des = ident, especie, genoma, des
        self.pose = np.array(pose, dtype=float)
        self.theta = None
        self.energia, self.madre, self.nacimiento = energia, madre, nacimiento
        self.comidas, self.hijas = 0, 0
        segs = des["segmentos"]
        self.largo_total = sum(s.largo for s in segs)
        self.masa = sum(s.largo * s.ancho * 0.08 * 300.0 for s in segs)


def _envolver(x: np.ndarray) -> np.ndarray:
    return (x + MUNDO / 2.0) % MUNDO - MUNDO / 2.0


class Epoca:
    """Estructuras vectorizadas de una época (se rearman cuando cambia la población)."""

    def __init__(self, individuos: list[Individuo]):
        self.ind = individuos
        des = [i.des for i in individuos]
        self.lote = develop2d.lote_desde(des)
        B, N = self.lote.B, self.lote.N
        self.B, self.N = B, N
        self.signos = develop2d.signos_torque(des, N)
        self.cer = CerebrosLote([d["cerebro"] for d in des], DT_CEREBRO)
        for b, i in enumerate(individuos):
            self.lote.pose[b] = i.pose
            if i.theta is not None and len(i.theta) == N:
                self.lote.theta[b] = i.theta
            elif i.theta is not None:
                self.lote.theta[b, :len(i.theta)] = i.theta[:N]
        # índices planos de sensores: ángulos (segmentos con madre) y luz (2 por segmento)
        ia_b, ia_s, ia_k = [], [], []
        il_b, il_s, il_k = [], [], []
        ef_b, ef_s = [], []
        for b, d in enumerate(des):
            so = self.cer.off_s[b]
            nd = d["cerebro"]["n_dof"]
            j = 0
            for s in d["segmentos"]:
                if s.madre >= 0:
                    ia_b.append(b); ia_s.append(s.indice); ia_k.append(so + j); j += 1
                    ef_b.append(b); ef_s.append(s.indice)
                il_b.append(b); il_s.append(s.indice); il_k.append(so + nd + 2 * s.indice)
        self.ia_b, self.ia_s, self.ia_k = np.array(ia_b), np.array(ia_s), np.array(ia_k)
        self.il_b, self.il_s, self.il_k = np.array(il_b), np.array(il_s), np.array(il_k)
        self.ef_b, self.ef_s = np.array(ef_b), np.array(ef_s)
        self.ctrl = np.zeros((B, N))
        self.k_cerebro = max(1, int(round(DT / DT_CEREBRO)))
        self.masa = np.array([i.masa for i in individuos])
        self.come_chica = np.array([i.largo_total <= LARGO_CHICO for i in individuos])
        self.come_grande = np.array([i.masa >= MASA_GRANDE for i in individuos])
        self.energia = np.array([i.energia for i in individuos])
        self.comidas = np.zeros(B, dtype=int)

    def paso(self, comida: np.ndarray, rng: np.random.Generator) -> dict:
        lote, cer = self.lote, self.cer
        centro, phi, com = lote.cinematica()
        # comida comestible más cercana por criatura (con envoltura toroidal)
        d = _envolver(comida[None, :, :2] - com[:, None, :])           # (B, F, 2)
        dist = np.hypot(d[..., 0], d[..., 1])
        chica = comida[:, 2] == 0
        permitido = np.where(chica[None, :], self.come_chica[:, None], self.come_grande[:, None])
        dist_ok = np.where(permitido, dist, np.inf)
        j = dist_ok.argmin(1)
        dmin = dist_ok[np.arange(self.B), j]
        # comer
        comen = dmin < RADIO_COMER
        n_chica = n_grande = 0
        if comen.any():
            for b in np.flatnonzero(comen):
                f = j[b]
                if comida[f, 3] <= 0:        # ya comida en este paso por otra
                    continue
                valor = E_CHICA if comida[f, 2] == 0 else E_GRANDE
                self.energia[b] += valor
                self.comidas[b] += 1
                if comida[f, 2] == 0:
                    n_chica += 1
                else:
                    n_grande += 1
                comida[f, 3] = 0
            # reaparecer
            muertas = comida[:, 3] <= 0
            comida[muertas, :2] = rng.uniform(-MUNDO / 2, MUNDO / 2, size=(int(muertas.sum()), 2))
            comida[muertas, 3] = 1
            d = _envolver(comida[None, :, :2] - com[:, None, :])
            dist = np.hypot(d[..., 0], d[..., 1])
            dist_ok = np.where(permitido, dist, np.inf)
            j = dist_ok.argmin(1)
        objetivo = comida[j, :2]                                           # (B, 2)
        # sensores: ángulos
        th = lote.theta[self.ia_b, self.ia_s] / np.maximum(1e-3, lote.limite[self.ia_b, self.ia_s])
        cer.sens[self.ia_k] = np.clip(th, -1.0, 1.0)
        # luz: dirección a la comida objetivo en el marco de cada segmento
        dx = _envolver(objetivo[self.il_b, 0] - centro[self.il_b, self.il_s, 0])
        dy = _envolver(objetivo[self.il_b, 1] - centro[self.il_b, self.il_s, 1])
        r = np.maximum(1e-9, np.hypot(dx, dy))
        c, s = np.cos(phi[self.il_b, self.il_s]), np.sin(phi[self.il_b, self.il_s])
        cer.sens[self.il_k] = (c * dx + s * dy) / r
        cer.sens[self.il_k + 1] = (-s * dx + c * dy) / r
        sal = cer.pasos(self.k_cerebro)
        obj = np.zeros((self.B, self.N))
        obj[self.ef_b, self.ef_s] = sal
        self.ctrl += (obj - self.ctrl) * min(1.0, DT / TAU_ACTIVACION)
        lote.paso(self.ctrl * self.signos, DT)
        lote.pose[:, :2] = _envolver(lote.pose[:, :2])
        torque = np.abs(self.ctrl * lote.torque_max).sum(1)
        self.energia -= (COSTO_MASA * self.masa + COSTO_TORQUE * torque) * DT
        return {"chica": n_chica, "grande": n_grande}


def correr(nombre: str, semilla: int, epocas: int, especies: list[str], por_especie: int,
           grabar_cada: int, fps_grab: float) -> None:
    rng = random.Random(semilla)
    nrng = np.random.default_rng(semilla)
    carpeta = os.path.join(RAIZ, "runs", nombre)
    os.makedirs(carpeta, exist_ok=True)
    individuos: list[Individuo] = []
    sig = 0
    for esp in especies:
        g = bestiario.especie(esp)
        des = develop2d.desarrollar2d(g)
        for _ in range(por_especie):
            pose = (nrng.uniform(-MUNDO / 2, MUNDO / 2), nrng.uniform(-MUNDO / 2, MUNDO / 2), nrng.uniform(-math.pi, math.pi))
            individuos.append(Individuo(sig, esp, g, des, pose, E0, None, 0.0))
            sig += 1
    comida = np.zeros((N_CHICA + N_GRANDE, 4))
    comida[:, :2] = nrng.uniform(-MUNDO / 2, MUNDO / 2, size=(len(comida), 2))
    comida[N_CHICA:, 2] = 1
    comida[:, 3] = 1
    config = {"nombre": nombre, "etapa": 7, "semilla": semilla, "epocas": epocas, "t_epoca": T_EPOCA, "mundo": MUNDO,
              "especies": especies, "por_especie": por_especie, "reglas": {
                  "n_chica": N_CHICA, "n_grande": N_GRANDE, "e_chica": E_CHICA, "e_grande": E_GRANDE,
                  "largo_chico": LARGO_CHICO, "masa_grande": MASA_GRANDE, "radio_comer": RADIO_COMER,
                  "e0": E0, "e_repro": E_REPRO, "e_cria": E_CRIA, "costo_masa": COSTO_MASA, "costo_torque": COSTO_TORQUE,
                  "edad_maxima": EDAD_MAXIMA, "poblacion_maxima": POBLACION_MAXIMA, "dt": DT, "dt_cerebro": DT_CEREBRO}}
    json.dump(config, open(os.path.join(carpeta, "config.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    historia, grabaciones = [], []
    t_global = 0.0
    t0 = time.time()
    pasos = int(round(T_EPOCA / DT))
    cada = max(1, int(round(1.0 / (fps_grab * DT))))
    for epoca in range(epocas):
        if not individuos:
            print(f"época {epoca}: extinción total", flush=True)
            break
        t_ep = time.time()
        E = Epoca(individuos)
        grabar = (epoca % grabar_cada == 0) or epoca == epocas - 1
        cuadros, cuadros_comida = [], []
        com_tot = {"chica": 0, "grande": 0}
        for k in range(pasos):
            r = E.paso(comida, nrng)
            com_tot["chica"] += r["chica"]
            com_tot["grande"] += r["grande"]
            if grabar and k % cada == 0:
                centro, phi, _ = E.lote.cinematica()
                cuadros.append(np.concatenate([centro, phi[..., None]], axis=2).round(3).tolist())
                cuadros_comida.append(comida[:, :3].round(2).tolist())
        t_global += T_EPOCA
        for b, ind in enumerate(individuos):
            ind.pose = E.lote.pose[b].copy()
            ind.theta = E.lote.theta[b].copy()
            ind.energia = float(E.energia[b])
            ind.comidas += int(E.comidas[b])
        if grabar:
            grabaciones.append({"epoca": epoca, "t": t_global - T_EPOCA, "fps": 1.0 / (cada * DT),
                                "criaturas": [{"id": i.id, "especie": i.especie, "madre": i.madre, "energia": round(i.energia, 1),
                                               "comidas": i.comidas, "n": i.des["n"],
                                               "segmentos": [[round(s.largo, 3), round(s.ancho, 3)] for s in i.des["segmentos"]]}
                                              for i in individuos],
                                "cuadros": cuadros, "comida": cuadros_comida, "N": E.N})
        vivos, muertes = [], 0
        for ind in individuos:
            if ind.energia <= 0 or (t_global - ind.nacimiento) > EDAD_MAXIMA:
                muertes += 1
            else:
                vivos.append(ind)
        individuos = vivos
        crias, nac = [], 0
        for ind in sorted(individuos, key=lambda i: -i.energia):
            if ind.energia < E_REPRO or len(individuos) + len(crias) >= POBLACION_MAXIMA:
                continue
            g = ind.genoma
            for _ in range(rng.randint(*MUTACIONES)):
                g = morph.mutar(g, rng)
            try:
                des = develop2d.desarrollar2d(g)
            except ValueError:
                continue
            ang = rng.uniform(0, 2 * math.pi)
            pose = (ind.pose[0] + 1.5 * math.cos(ang), ind.pose[1] + 1.5 * math.sin(ang), rng.uniform(-math.pi, math.pi))
            cria = Individuo(sig, ind.especie, g, des, pose, E_CRIA, ind.id, t_global)
            cria.pose[:2] = _envolver(cria.pose[:2])
            sig += 1
            ind.energia -= E_CRIA
            ind.hijas += 1
            crias.append(cria)
            nac += 1
        individuos += crias
        conteo = {e: sum(1 for i in individuos if i.especie == e) for e in especies}
        fila = {"epoca": epoca, "t": t_global, "poblacion": len(individuos), "conteo": conteo,
                "energia_media": {e: round(float(np.mean([i.energia for i in individuos if i.especie == e])), 1) if conteo[e] else 0.0 for e in especies},
                "segmentos_media": {e: round(float(np.mean([i.des["n"] for i in individuos if i.especie == e])), 2) if conteo[e] else 0.0 for e in especies},
                "nacimientos": nac, "muertes": muertes, "comidas": com_tot, "segundos": round(time.time() - t_ep, 1)}
        historia.append(fila)
        print(f"época {epoca:3d} t={t_global:6.0f} s  población {len(individuos):3d} {conteo}  comidas {com_tot}  "
              f"nac {nac:3d} muertes {muertes:3d}  {fila['segundos']:5.1f} s", flush=True)
        json.dump(historia, open(os.path.join(carpeta, "historia.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump([{"id": i.id, "especie": i.especie, "madre": i.madre, "nacimiento": i.nacimiento, "energia": i.energia,
                "comidas": i.comidas, "hijas": i.hijas, "n": i.des["n"], "genoma": i.genoma} for i in individuos],
              open(os.path.join(carpeta, "poblacion_final.json"), "w", encoding="utf-8"), separators=(",", ":"))
    datos = {"meta": {"corrida": nombre, "etapa": 7, "mundo": MUNDO, "t_epoca": T_EPOCA, "especies": especies,
                      "epocas": len(historia), "reglas": config["reglas"]},
             "historia": historia, "epocas": grabaciones}
    destino = os.path.join(carpeta, "acuario2d.json")
    json.dump(datos, open(destino, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    shutil.copyfile(destino, os.path.join(RAIZ, "viewer", "acuario2d.json"))
    print(f"exportado {destino}: {os.path.getsize(destino) / 1e6:.1f} MB, {len(grabaciones)} épocas grabadas; "
          f"listo en {time.time() - t0:.0f} s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Ecosistema 2D a escala (Etapa 7).")
    ap.add_argument("--nombre", default="eco2d01")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--epocas", type=int, default=90)
    ap.add_argument("--especies", default="anguila,pez,renacuajo,raya,ciempies_acuatico,remador")
    ap.add_argument("--por-especie", type=int, default=40)
    ap.add_argument("--grabar-cada", type=int, default=15)
    ap.add_argument("--fps", type=float, default=2.0)
    a = ap.parse_args()
    correr(a.nombre, a.semilla, a.epocas, a.especies.split(","), a.por_especie, a.grabar_cada, a.fps)


if __name__ == "__main__":
    main()
