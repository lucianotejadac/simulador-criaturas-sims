"""Genoma morfológico: grafo dirigido de nodos (piezas) con cerebros anidados.

Sigue a Sims (1994). Cada nodo describe una caja y la articulación que la une a
su madre, un límite recursivo, un grafo neuronal local y una lista de
conexiones a nodos hijos. Cada conexión dice en qué cara de la madre se ancla
la hija, dónde, con qué orientación y escala, si va reflejada y si es "solo
terminal" (se aplica únicamente en la última instancia recursiva).

Representación (listas y diccionarios, para JSON y multiprocessing):

genoma = {"siguiente_id": int, "raiz": idx, "nodos": [nodo...], "central": [neurona...]}
nodo   = {"dims": [x, y, z] (m), "art": tipo de articulación, "limite": grados, "rec": int,
          "neuronas": [neurona...], "efectores": [entrada * n_dof(art)], "conexiones": [conexion...]}
neurona  = {"id": int, "f": función de Sims, "in": [entrada...]}
entrada  = [tipo, ref, peso]
    "s"  sensor local: ángulo del grado de libertad `ref` de la propia articulación
    "n"  neurona local con id `ref`
    "p"  neurona con id `ref` del nodo madre (en la instancia concreta)
    "g"  neurona central con id `ref`
    "r"  (solo en centrales) neurona con id `ref` del nodo raíz
    "c"  constante (el valor es el peso)
conexion = {"a": idx nodo hija, "cara": 0..5, "u": -1..1, "v": -1..1, "rot": [gx, gy, gz] grados,
            "escala": factor, "reflejo": bool, "terminal": bool}

Las referencias entre neuronas usan identificadores estables (no posiciones):
borrar una neurona nunca cambia a quién apunta otra. Una referencia a un id
que no existe se vuelve constante al compilar (`develop.desarrollar`).
Ver BITACORA 0008.
"""
from __future__ import annotations

import copy
import random

from genome.neural import FUNCIONES, NOMBRES_FUNCIONES, PESO_MAX, PESO_SIGMA

ARTICULACIONES: dict[str, list[str]] = {
    "rigida": [], "bisagra": ["z"], "torsion": ["x"], "universal": ["y", "z"],
    "flex-tors": ["z", "x"], "tors-flex": ["x", "z"], "esferica": ["x", "y", "z"],
}
NOMBRES_ART = sorted(ARTICULACIONES)
MAX_NODOS = 8
MAX_CONEXIONES = 4
MAX_PIEZAS = 16
MAX_NEURONAS_NODO = 12
MAX_CENTRALES = 8
DIM_MIN, DIM_MAX = 0.04, 0.8
REC_MAX = 4
TIPOS_LOCALES = ("s", "n", "p", "g", "c")
TIPOS_CENTRALES = ("g", "r", "c")


def n_dof(art: str) -> int:
    return len(ARTICULACIONES[art])


# ----------------------------------------------------------------------------
# Construcción aleatoria
# ----------------------------------------------------------------------------
def _nuevo_id(g: dict) -> int:
    g["siguiente_id"] += 1
    return g["siguiente_id"] - 1


def _ids(neuronas: list[dict]) -> list[int]:
    return [n["id"] for n in neuronas]


def entrada_aleatoria(rng: random.Random, g: dict, nodo: dict | None, central: bool = False) -> list:
    """Entrada nueva. Para nodos: s, n, p, g, c. Para centrales: g, r, c."""
    w = rng.uniform(-PESO_MAX, PESO_MAX)
    if central:
        opciones = []
        if g["central"]:
            opciones.append(("g", _ids(g["central"])))
        raiz = g["nodos"][g["raiz"]] if g["nodos"] else None
        if raiz and raiz["neuronas"]:
            opciones.append(("r", _ids(raiz["neuronas"])))
        if not opciones or rng.random() < 0.25:
            return ["c", 0, rng.uniform(-2.0, 2.0)]
        t, ids = rng.choice(opciones)
        return [t, rng.choice(ids), w]
    opciones = []
    nd = n_dof(nodo["art"])
    if nd:
        opciones += [("s", list(range(nd)))] * 2
    if nodo["neuronas"]:
        opciones += [("n", _ids(nodo["neuronas"]))] * 2
    # Madre: cualquier nodo que conecte a este; si no se sabe, cualquier neurona del genoma.
    ids_p = [n["id"] for x in g["nodos"] for n in x["neuronas"]]
    if ids_p:
        opciones.append(("p", ids_p))
    if g["central"]:
        opciones.append(("g", _ids(g["central"])))
    if not opciones or rng.random() < 0.2:
        return ["c", 0, rng.uniform(-2.0, 2.0)]
    t, ids = rng.choice(opciones)
    return [t, rng.choice(ids), w]


def neurona_aleatoria(rng: random.Random, g: dict, nodo: dict | None, central: bool = False) -> dict:
    f = rng.choice(NOMBRES_FUNCIONES)
    return {"id": _nuevo_id(g), "f": f,
            "in": [entrada_aleatoria(rng, g, nodo, central) for _ in range(FUNCIONES[f])]}


def conexion_aleatoria(rng: random.Random, n_nodos: int) -> dict:
    return {"a": rng.randrange(n_nodos), "cara": rng.randrange(6),
            "u": rng.uniform(-0.8, 0.8), "v": rng.uniform(-0.8, 0.8),
            "rot": [rng.uniform(-90, 90), rng.uniform(-60, 60), rng.uniform(-60, 60)],
            "escala": rng.uniform(0.6, 1.3), "reflejo": rng.random() < 0.3,
            "terminal": rng.random() < 0.2}


def nodo_aleatorio(rng: random.Random, g: dict) -> dict:
    art = rng.choice(NOMBRES_ART)
    nodo = {"dims": [rng.uniform(0.08, 0.5) for _ in range(3)], "art": art,
            "limite": rng.uniform(20, 80), "rec": rng.randint(1, REC_MAX),
            "neuronas": [], "efectores": [], "conexiones": []}
    for _ in range(rng.randint(0, 3)):
        nodo["neuronas"].append(neurona_aleatoria(rng, g, nodo))
    nodo["efectores"] = [entrada_aleatoria(rng, g, nodo) for _ in range(n_dof(art))]
    return nodo


def genoma_aleatorio(rng: random.Random, n_nodos: int | None = None) -> dict:
    g = {"siguiente_id": 0, "raiz": 0, "nodos": [], "central": []}
    n = n_nodos if n_nodos is not None else rng.randint(1, 3)
    for _ in range(n):
        g["nodos"].append(nodo_aleatorio(rng, g))
    for _ in range(rng.randint(0, 2)):
        g["central"].append(neurona_aleatoria(rng, g, None, central=True))
    for nodo in g["nodos"]:
        for _ in range(rng.randint(0, 2)):
            nodo["conexiones"].append(conexion_aleatoria(rng, n))
    return recolectar(g)


# ----------------------------------------------------------------------------
# Validación y recolección
# ----------------------------------------------------------------------------
def es_valido(g: dict) -> bool:
    nodos = g["nodos"]
    if not nodos or len(nodos) > MAX_NODOS or not (0 <= g["raiz"] < len(nodos)):
        return False
    if len(g["central"]) > MAX_CENTRALES:
        return False
    ids_vistos: set[int] = set()
    for lista in [g["central"]] + [x["neuronas"] for x in nodos]:
        for neu in lista:
            if neu["id"] in ids_vistos or neu["id"] >= g["siguiente_id"]:
                return False
            ids_vistos.add(neu["id"])
            if neu["f"] not in FUNCIONES or len(neu["in"]) != FUNCIONES[neu["f"]]:
                return False
    for neu in g["central"]:
        if any(e[0] not in TIPOS_CENTRALES for e in neu["in"]):
            return False
    for x in nodos:
        if x["art"] not in ARTICULACIONES or len(x["efectores"]) != n_dof(x["art"]):
            return False
        if len(x["neuronas"]) > MAX_NEURONAS_NODO or len(x["conexiones"]) > MAX_CONEXIONES:
            return False
        if not all(DIM_MIN <= d <= DIM_MAX for d in x["dims"]) or not (1 <= x["rec"] <= REC_MAX):
            return False
        for e in [e for neu in x["neuronas"] for e in neu["in"]] + x["efectores"]:
            if e[0] not in TIPOS_LOCALES:
                return False
            if e[0] == "s" and not (0 <= e[1] < max(1, n_dof(x["art"]))):
                return False
        for c in x["conexiones"]:
            if not (0 <= c["a"] < len(nodos)) or not (0 <= c["cara"] < 6):
                return False
    return True


def _nodos_alcanzables(g: dict) -> list[int]:
    vistos: list[int] = []
    pila = [g["raiz"]]
    while pila:
        i = pila.pop()
        if i in vistos:
            continue
        vistos.append(i)
        pila.extend(c["a"] for c in g["nodos"][i]["conexiones"])
    return sorted(vistos)


def recolectar(g: dict) -> dict:
    """Elimina nodos no alcanzables desde la raíz y neuronas que nadie usa.

    Una neurona local vive si una cadena de entradas locales la une a un
    efector de su nodo, o si alguna entrada "p" de cualquier nodo o "r" de
    las centrales apunta a su id. Una central vive si alguien apunta a su id
    (desde nodos o desde otras centrales vivas).
    """
    g = copy.deepcopy(g)
    alcanzables = _nodos_alcanzables(g)
    nuevo_idx = {viejo: k for k, viejo in enumerate(alcanzables)}
    nodos = [g["nodos"][i] for i in alcanzables]
    for x in nodos:
        for c in x["conexiones"]:
            c["a"] = nuevo_idx[c["a"]]
    g["nodos"] = nodos
    g["raiz"] = nuevo_idx[g["raiz"]]

    # Referencias externas (ids) que mantienen vivas neuronas de otros nodos.
    ref_p: set[int] = set()
    ref_g: set[int] = set()
    ref_r: set[int] = set()
    for x in nodos:
        for e in [e for neu in x["neuronas"] for e in neu["in"]] + x["efectores"]:
            if e[0] == "p":
                ref_p.add(e[1])
            elif e[0] == "g":
                ref_g.add(e[1])
    for x in nodos:
        por_id = {n["id"]: n for n in x["neuronas"]}
        vivas: set[int] = set()
        pila = [e[1] for e in x["efectores"] if e[0] == "n"] + [i for i in por_id if i in ref_p]
        while pila:
            i = pila.pop()
            if i in vivas or i not in por_id:
                continue
            vivas.add(i)
            pila.extend(e[1] for e in por_id[i]["in"] if e[0] == "n")
        x["neuronas"] = [n for n in x["neuronas"] if n["id"] in vivas]
    # Centrales: vivas las referidas por nodos, y sus antecesoras centrales.
    por_id_c = {n["id"]: n for n in g["central"]}
    vivas_c: set[int] = set()
    pila = [i for i in por_id_c if i in ref_g]
    while pila:
        i = pila.pop()
        if i in vivas_c or i not in por_id_c:
            continue
        vivas_c.add(i)
        pila.extend(e[1] for e in por_id_c[i]["in"] if e[0] == "g")
    g["central"] = [n for n in g["central"] if n["id"] in vivas_c]
    # Las referencias "r" solo importan si la central que las usa sigue viva:
    # ya se resolvió arriba (una "r" a un id inexistente se vuelve constante al compilar).
    return g


# ----------------------------------------------------------------------------
# Mutación por pasos (Sims), frecuencia escalada al tamaño
# ----------------------------------------------------------------------------
def _perturbar(rng: random.Random, v: float, sigma: float, lo: float, hi: float) -> float:
    if rng.random() < 0.15:
        return rng.uniform(lo, hi)
    return max(lo, min(hi, v + rng.gauss(0.0, sigma)))


def _mutar_entrada(rng: random.Random, g: dict, nodo: dict | None, e: list, central: bool) -> list:
    if rng.random() < 0.5:
        e = list(e)
        e[2] = _perturbar(rng, e[2], PESO_SIGMA, -PESO_MAX, PESO_MAX)
        return e
    return entrada_aleatoria(rng, g, nodo, central)


def _mutar_neurona(rng: random.Random, g: dict, nodo: dict | None, neu: dict, central: bool) -> None:
    if rng.random() < 0.3:
        f = rng.choice(NOMBRES_FUNCIONES)
        ar = FUNCIONES[f]
        ins = neu["in"][:ar]
        while len(ins) < ar:
            ins.append(entrada_aleatoria(rng, g, nodo, central))
        neu["f"], neu["in"] = f, ins
    else:
        k = rng.randrange(len(neu["in"]))
        neu["in"][k] = _mutar_entrada(rng, g, nodo, neu["in"][k], central)


def _contar_elementos(g: dict) -> int:
    n = len(g["central"]) + sum(len(x["in"]) for x in g["central"])
    for x in g["nodos"]:
        n += 4 + len(x["neuronas"]) + sum(len(neu["in"]) for neu in x["neuronas"])
        n += len(x["efectores"]) + 7 * len(x["conexiones"])
    return max(1, n)


def mutar(g: dict, rng: random.Random) -> dict:
    g = copy.deepcopy(g)
    p = 1.0 / _contar_elementos(g)   # al menos una mutación esperada por genoma
    nodos = g["nodos"]

    # 1. Parámetros de cada nodo y de su cerebro local.
    for x in nodos:
        if rng.random() < p:
            k = rng.randrange(3)
            x["dims"][k] = _perturbar(rng, x["dims"][k], 0.05, DIM_MIN, DIM_MAX)
        if rng.random() < p:
            x["art"] = rng.choice(NOMBRES_ART)
            nd = n_dof(x["art"])
            x["efectores"] = x["efectores"][:nd]
            while len(x["efectores"]) < nd:
                x["efectores"].append(entrada_aleatoria(rng, g, x))
            for e in [e for neu in x["neuronas"] for e in neu["in"]] + x["efectores"]:
                if e[0] == "s" and e[1] >= max(1, nd):
                    e[1] = rng.randrange(max(1, nd))
        if rng.random() < p:
            x["limite"] = _perturbar(rng, x["limite"], 10.0, 10.0, 90.0)
        if rng.random() < p:
            x["rec"] = max(1, min(REC_MAX, x["rec"] + rng.choice([-1, 1])))
        for neu in x["neuronas"]:
            if rng.random() < p:
                _mutar_neurona(rng, g, x, neu, False)
        if len(x["neuronas"]) < MAX_NEURONAS_NODO and rng.random() < 3 * p:
            nueva = neurona_aleatoria(rng, g, x)
            x["neuronas"].append(nueva)
            if rng.random() < 0.6:
                destinos = [e for neu in x["neuronas"][:-1] for e in neu["in"]] + x["efectores"]
                if destinos:
                    e = rng.choice(destinos)
                    e[0], e[1] = "n", nueva["id"]
        for k, e in enumerate(x["efectores"]):
            if rng.random() < p:
                x["efectores"][k] = _mutar_entrada(rng, g, x, e, False)
    # Centrales.
    for neu in g["central"]:
        if rng.random() < p:
            _mutar_neurona(rng, g, None, neu, True)
    if len(g["central"]) < MAX_CENTRALES and rng.random() < 2 * p:
        nueva = neurona_aleatoria(rng, g, None, central=True)
        g["central"].append(nueva)
        # Que alguien la use: una entrada aleatoria de algún nodo apunta a ella.
        destinos = [e for x in nodos for neu in x["neuronas"] for e in neu["in"]] + \
                   [e for x in nodos for e in x["efectores"]]
        if destinos:
            e = rng.choice(destinos)
            e[0], e[1] = "g", nueva["id"]

    # 2. Nodo nuevo (queda desconectado hasta que el paso 3 o 4 lo enganche).
    if len(nodos) < MAX_NODOS and rng.random() < 4 * p:
        nodos.append(nodo_aleatorio(rng, g))
        if rng.random() < 0.7:
            madre = rng.choice(nodos[:-1])
            if len(madre["conexiones"]) < MAX_CONEXIONES:
                c = conexion_aleatoria(rng, len(nodos))
                c["a"] = len(nodos) - 1
                madre["conexiones"].append(c)

    # 3. Parámetros y punteros de las conexiones.
    for x in nodos:
        for c in x["conexiones"]:
            if rng.random() < p:
                c["a"] = rng.randrange(len(nodos))
            if rng.random() < p:
                c["cara"] = rng.randrange(6)
            if rng.random() < p:
                c["u"] = _perturbar(rng, c["u"], 0.2, -0.9, 0.9)
            if rng.random() < p:
                c["v"] = _perturbar(rng, c["v"], 0.2, -0.9, 0.9)
            if rng.random() < p:
                k = rng.randrange(3)
                c["rot"][k] = _perturbar(rng, c["rot"][k], 20.0, -180.0 if k == 0 else -90.0, 180.0 if k == 0 else 90.0)
            if rng.random() < p:
                c["escala"] = _perturbar(rng, c["escala"], 0.1, 0.5, 1.5)
            if rng.random() < p:
                c["reflejo"] = not c["reflejo"]
            if rng.random() < p:
                c["terminal"] = not c["terminal"]

    # 4. Agregar o quitar conexiones.
    for x in nodos:
        if len(x["conexiones"]) < MAX_CONEXIONES and rng.random() < 2 * p:
            x["conexiones"].append(conexion_aleatoria(rng, len(nodos)))
        if x["conexiones"] and rng.random() < 2 * p:
            x["conexiones"].pop(rng.randrange(len(x["conexiones"])))

    # 5. Recolección.
    return recolectar(g)


# ----------------------------------------------------------------------------
# Cruce e injerto
# ----------------------------------------------------------------------------
def _renumerar_ids(g: dict, desde: int) -> dict:
    """Desplaza todos los ids de un genoma para que no choquen con otro."""
    g = copy.deepcopy(g)
    mapa = {}
    for lista in [g["central"]] + [x["neuronas"] for x in g["nodos"]]:
        for neu in lista:
            mapa[neu["id"]] = desde
            neu["id"] = desde
            desde += 1
    for lista in [g["central"]] + [x["neuronas"] for x in g["nodos"]]:
        for neu in lista:
            for e in neu["in"]:
                if e[0] in ("n", "p", "g", "r"):
                    e[1] = mapa.get(e[1], e[1])
    for x in g["nodos"]:
        for e in x["efectores"]:
            if e[0] in ("n", "p", "g"):
                e[1] = mapa.get(e[1], e[1])
    g["siguiente_id"] = desde
    return g


def cruzar(a: dict, b: dict, rng: random.Random) -> dict:
    """Las listas de nodos se alinean y se copian por tramos alternando de madre."""
    b = _renumerar_ids(b, a["siguiente_id"])
    na, nb = a["nodos"], b["nodos"]
    largo = max(len(na), len(nb))
    n_cortes = rng.choice([1, 2])
    cortes = sorted(rng.randrange(1, largo + 1) for _ in range(n_cortes))
    hijo: list[dict] = []
    fuente = a
    corte_i = 0
    for i in range(largo):
        while corte_i < len(cortes) and i >= cortes[corte_i]:
            fuente = b if fuente is a else a
            corte_i += 1
        lista = fuente["nodos"]
        if i < len(lista):
            hijo.append(copy.deepcopy(lista[i]))
    hijo = hijo[:MAX_NODOS] or [copy.deepcopy(na[a["raiz"]])]
    g = {"siguiente_id": b["siguiente_id"], "raiz": min(a["raiz"], len(hijo) - 1),
         "nodos": hijo, "central": copy.deepcopy(rng.choice([a, b])["central"])}
    for x in g["nodos"]:
        for c in x["conexiones"]:
            if not (0 <= c["a"] < len(hijo)):
                c["a"] = rng.randrange(len(hijo))
    return recolectar(g)


def injertar(receptor: dict, donante: dict, rng: random.Random) -> dict:
    """Copia un nodo del donante con su subgrafo y lo engancha en el receptor."""
    donante = _renumerar_ids(donante, receptor["siguiente_id"])
    g = copy.deepcopy(receptor)
    g["siguiente_id"] = donante["siguiente_id"]
    cupo = MAX_NODOS - len(g["nodos"])
    if cupo <= 0 or not donante["nodos"]:
        return g
    raiz_d = rng.randrange(len(donante["nodos"]))
    sub: list[int] = []
    pila = [raiz_d]
    while pila and len(sub) < cupo:
        i = pila.pop()
        if i in sub:
            continue
        sub.append(i)
        pila.extend(c["a"] for c in donante["nodos"][i]["conexiones"])
    base = len(g["nodos"])
    mapa = {viejo: base + k for k, viejo in enumerate(sub)}
    for viejo in sub:
        x = copy.deepcopy(donante["nodos"][viejo])
        x["conexiones"] = [c for c in x["conexiones"] if c["a"] in mapa]
        for c in x["conexiones"]:
            c["a"] = mapa[c["a"]]
        g["nodos"].append(x)
    # Enganchar: una conexión existente del receptor o una nueva apunta al injerto.
    candidatos = [c for x in g["nodos"][:base] for c in x["conexiones"]]
    if candidatos and rng.random() < 0.5:
        rng.choice(candidatos)["a"] = mapa[raiz_d]
    else:
        madre = rng.choice(g["nodos"][:base])
        c = conexion_aleatoria(rng, len(g["nodos"]))
        c["a"] = mapa[raiz_d]
        if len(madre["conexiones"]) >= MAX_CONEXIONES:
            madre["conexiones"].pop(rng.randrange(len(madre["conexiones"])))
        madre["conexiones"].append(c)
    for neu in donante["central"]:
        if len(g["central"]) < MAX_CENTRALES:
            g["central"].append(copy.deepcopy(neu))
    return recolectar(g)


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def describir(g: dict) -> str:
    def ent(e):
        t, r, w = e
        return f"{t}{'' if t == 'c' else r}×{w:+.2f}"
    lineas = []
    for i, x in enumerate(g["nodos"]):
        marca = " (raíz)" if i == g["raiz"] else ""
        lineas.append(f"nodo {i}{marca}: caja {x['dims'][0]:.2f}×{x['dims'][1]:.2f}×{x['dims'][2]:.2f} m, "
                      f"{x['art']} ±{x['limite']:.0f}°, rec {x['rec']}")
        for neu in x["neuronas"]:
            lineas.append(f"  n{neu['id']} = {neu['f']}({', '.join(ent(e) for e in neu['in'])})")
        for k, e in enumerate(x["efectores"]):
            lineas.append(f"  e{k} = {ent(e)}")
        for c in x["conexiones"]:
            lineas.append(f"  -> nodo {c['a']} cara {c['cara']} ({c['u']:+.2f},{c['v']:+.2f}) "
                          f"rot {c['rot'][0]:.0f}/{c['rot'][1]:.0f}/{c['rot'][2]:.0f} esc {c['escala']:.2f}"
                          f"{' reflejo' if c['reflejo'] else ''}{' terminal' if c['terminal'] else ''}")
    for neu in g["central"]:
        lineas.append(f"central g{neu['id']} = {neu['f']}({', '.join(ent(e) for e in neu['in'])})")
    return "\n".join(lineas)
