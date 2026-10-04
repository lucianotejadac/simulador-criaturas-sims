"""Genoma neuronal: grafo dirigido (posiblemente recurrente) de neuronas.

Sigue el repertorio de Sims (1994): cada neurona tiene una función y hasta
tres entradas ponderadas. Cada entrada apunta a un sensor, a otra neurona o es
una constante. Los efectores tienen una sola entrada ponderada.

Representación en datos simples (listas y diccionarios) para que viaje sin
problemas por `multiprocessing` y se guarde como JSON.

Entrada = [tipo, indice, peso]
  tipo "s": sensor `indice`           (ángulo articular normalizado a [-1, 1])
  tipo "n": neurona `indice`          (valor del paso anterior: actualización síncrona)
  tipo "c": constante                 (`indice` se ignora, el valor es `peso`)

Neurona = {"f": nombre_funcion, "in": [Entrada, ...]}   (len(in) == aridad)
Genoma  = {"n_sensores": int, "neuronas": [Neurona...], "efectores": [Entrada...]}
"""
from __future__ import annotations

import copy
import random

# Aridad fija por función (Sims: "hasta tres entradas").
FUNCIONES: dict[str, int] = {
    "sum": 3, "product": 3, "divide": 2, "sum-threshold": 3, "greater-than": 2,
    "sign-of": 1, "min": 3, "max": 3, "abs": 1, "if": 3, "interpolate": 3,
    "sin": 1, "cos": 1, "atan": 1, "log": 1, "expt": 1, "sigmoid": 1,
    "integrate": 1, "differentiate": 1, "smooth": 2, "memory": 2,
    "oscillate-wave": 3, "oscillate-saw": 3,
}
NOMBRES_FUNCIONES = sorted(FUNCIONES)

MAX_NEURONAS = 24
PESO_SIGMA = 0.5          # desviación de la perturbación gaussiana de pesos
PESO_MAX = 4.0
PROB_NUEVA_NEURONA = 0.25  # probabilidad fija de agregar una neurona por mutación
PROB_TIPO = {"s": 0.35, "n": 0.45, "c": 0.20}  # cómo se elige el tipo de una entrada nueva


# ----------------------------------------------------------------------------
# Construcción aleatoria
# ----------------------------------------------------------------------------
def entrada_aleatoria(rng: random.Random, n_sensores: int, n_neuronas: int) -> list:
    r = rng.random()
    if r < PROB_TIPO["s"] or (n_neuronas == 0 and r < PROB_TIPO["s"] + PROB_TIPO["n"]):
        return ["s", rng.randrange(n_sensores), rng.uniform(-PESO_MAX, PESO_MAX)]
    if r < PROB_TIPO["s"] + PROB_TIPO["n"]:
        return ["n", rng.randrange(n_neuronas), rng.uniform(-PESO_MAX, PESO_MAX)]
    return ["c", 0, rng.uniform(-2.0, 2.0)]


def neurona_aleatoria(rng: random.Random, n_sensores: int, n_neuronas: int) -> dict:
    f = rng.choice(NOMBRES_FUNCIONES)
    return {"f": f, "in": [entrada_aleatoria(rng, n_sensores, n_neuronas) for _ in range(FUNCIONES[f])]}


def genoma_aleatorio(rng: random.Random, n_sensores: int, n_efectores: int,
                     n_neuronas: int | None = None) -> dict:
    n = n_neuronas if n_neuronas is not None else rng.randint(1, 4)
    neuronas = []
    for i in range(n):
        # Las primeras neuronas solo pueden apuntar a las ya creadas o a sensores;
        # las recurrencias aparecen con las mutaciones de punteros.
        neuronas.append(neurona_aleatoria(rng, n_sensores, i))
    g = {"n_sensores": n_sensores, "neuronas": neuronas,
         "efectores": [entrada_aleatoria(rng, n_sensores, n) for _ in range(n_efectores)]}
    return recolectar(g)


# ----------------------------------------------------------------------------
# Validación y limpieza
# ----------------------------------------------------------------------------
def es_valido(g: dict) -> bool:
    n = len(g["neuronas"])
    ns = g["n_sensores"]

    def ok(e: list) -> bool:
        t, i, w = e
        if t == "s":
            return 0 <= i < ns
        if t == "n":
            return 0 <= i < n
        return t == "c"

    if n > MAX_NEURONAS:
        return False
    for neu in g["neuronas"]:
        if neu["f"] not in FUNCIONES or len(neu["in"]) != FUNCIONES[neu["f"]]:
            return False
        if not all(ok(e) for e in neu["in"]):
            return False
    return len(g["efectores"]) > 0 and all(ok(e) for e in g["efectores"])


def recolectar(g: dict) -> dict:
    """Recolección de basura: elimina neuronas que no influyen en ningún efector."""
    n = len(g["neuronas"])
    vivas = set()
    pila = [e[1] for e in g["efectores"] if e[0] == "n"]
    while pila:
        i = pila.pop()
        if i in vivas or not (0 <= i < n):
            continue
        vivas.add(i)
        pila.extend(e[1] for e in g["neuronas"][i]["in"] if e[0] == "n")
    orden = sorted(vivas)
    nuevo_idx = {viejo: k for k, viejo in enumerate(orden)}

    def remap(e: list) -> list:
        if e[0] == "n":
            return ["n", nuevo_idx[e[1]], e[2]]
        return list(e)

    neuronas = [{"f": g["neuronas"][i]["f"], "in": [remap(e) for e in g["neuronas"][i]["in"]]}
                for i in orden]
    return {"n_sensores": g["n_sensores"], "neuronas": neuronas,
            "efectores": [remap(e) for e in g["efectores"]]}


# ----------------------------------------------------------------------------
# Mutación (por pasos, como Sims; frecuencia escalada al tamaño del grafo)
# ----------------------------------------------------------------------------
def _perturbar_peso(rng: random.Random, w: float) -> float:
    if rng.random() < 0.2:
        return rng.uniform(-PESO_MAX, PESO_MAX)
    w += rng.gauss(0.0, PESO_SIGMA)
    return max(-PESO_MAX, min(PESO_MAX, w))


def mutar(g: dict, rng: random.Random) -> dict:
    g = copy.deepcopy(g)
    ns = g["n_sensores"]
    neuronas = g["neuronas"]
    n = len(neuronas)
    n_punteros = sum(len(x["in"]) for x in neuronas) + len(g["efectores"])
    # Al menos una mutación esperada por genoma: p = 1 / (número de elementos mutables).
    p = 1.0 / max(1, n + n_punteros)

    # 1. Parámetros internos de cada neurona (función y pesos).
    for neu in neuronas:
        if rng.random() < p:
            if rng.random() < 0.3:
                f = rng.choice(NOMBRES_FUNCIONES)
                ar = FUNCIONES[f]
                ins = neu["in"][:ar]
                while len(ins) < ar:
                    ins.append(entrada_aleatoria(rng, ns, n))
                neu["f"], neu["in"] = f, ins
            else:
                e = rng.choice(neu["in"])
                e[2] = _perturbar_peso(rng, e[2])

    # 2. Neurona nueva (no conectada aún; el paso 3 o la conexión forzada la enganchan).
    if n < MAX_NEURONAS and rng.random() < PROB_NUEVA_NEURONA:
        neuronas.append(neurona_aleatoria(rng, ns, n + 1))
        n += 1
        if rng.random() < 0.5:
            # Conectar algo a la neurona nueva para que no se recolecte de inmediato.
            destinos = [e for x in neuronas[:-1] for e in x["in"]] + g["efectores"]
            if destinos:
                e = rng.choice(destinos)
                e[0], e[1] = "n", n - 1

    # 3. Punteros de entrada: cambiar destino, tipo o peso (incluye agregar y
    #    quitar conexiones: pasar de puntero a constante y viceversa).
    for x in neuronas:
        for k, e in enumerate(x["in"]):
            if rng.random() < p:
                x["in"][k] = entrada_aleatoria(rng, ns, n)
    for k, e in enumerate(g["efectores"]):
        if rng.random() < p:
            if rng.random() < 0.5:
                e[2] = _perturbar_peso(rng, e[2])
            else:
                g["efectores"][k] = entrada_aleatoria(rng, ns, n)

    # 4. Recolección de elementos desconectados.
    return recolectar(g)


# ----------------------------------------------------------------------------
# Cruce y injerto
# ----------------------------------------------------------------------------
def cruzar(a: dict, b: dict, rng: random.Random) -> dict:
    """Cruce al estilo Sims: se alinean las listas de nodos y se copian por
    tramos alternando de padre, con uno o dos puntos de cruce."""
    na, nb = a["neuronas"], b["neuronas"]
    largo = max(len(na), len(nb))
    if largo == 0:
        g = {"n_sensores": a["n_sensores"], "neuronas": [],
             "efectores": copy.deepcopy(rng.choice([a, b])["efectores"])}
        return recolectar(g)
    n_cortes = rng.choice([1, 2])
    cortes = sorted(rng.randrange(1, largo + 1) for _ in range(n_cortes))
    hijo: list[dict] = []
    fuente = a
    corte_i = 0
    for i in range(largo):
        while corte_i < len(cortes) and i >= cortes[corte_i]:
            fuente = b if fuente is a else a
            corte_i += 1
        lista = fuente["neuronas"]
        if i < len(lista):
            hijo.append(copy.deepcopy(lista[i]))
    hijo = hijo[:MAX_NEURONAS]
    n = len(hijo)
    efectores = copy.deepcopy(rng.choice([a, b])["efectores"])
    g = {"n_sensores": a["n_sensores"], "neuronas": hijo, "efectores": efectores}
    _arreglar_punteros(g, rng)
    return recolectar(g)


def injertar(receptor: dict, donante: dict, rng: random.Random) -> dict:
    """Injerto: se copia una neurona del donante junto con sus antecesoras y se
    engancha a un puntero aleatorio del receptor."""
    g = copy.deepcopy(receptor)
    nd = donante["neuronas"]
    if not nd:
        return g
    raiz = rng.randrange(len(nd))
    # Cierre de antecesoras (acotado para no desbordar MAX_NEURONAS).
    cupo = MAX_NEURONAS - len(g["neuronas"])
    if cupo <= 0:
        return g
    sub: list[int] = []
    pila = [raiz]
    while pila and len(sub) < cupo:
        i = pila.pop()
        if i in sub:
            continue
        sub.append(i)
        pila.extend(e[1] for e in nd[i]["in"] if e[0] == "n")
    base = len(g["neuronas"])
    mapa = {viejo: base + k for k, viejo in enumerate(sub)}
    for viejo in sub:
        neu = copy.deepcopy(nd[viejo])
        for e in neu["in"]:
            if e[0] == "n":
                if e[1] in mapa:
                    e[1] = mapa[e[1]]
                else:
                    # Antecesora que no cupo: se vuelve constante.
                    e[0], e[1] = "c", 0
        g["neuronas"].append(neu)
    destinos = [e for x in g["neuronas"][:base] for e in x["in"]] + g["efectores"]
    e = rng.choice(destinos)
    e[0], e[1] = "n", mapa[raiz]
    _arreglar_punteros(g, rng)
    return recolectar(g)


def _arreglar_punteros(g: dict, rng: random.Random) -> None:
    n, ns = len(g["neuronas"]), g["n_sensores"]
    for x in g["neuronas"]:
        for e in x["in"]:
            if e[0] == "n" and not (0 <= e[1] < n):
                e[1] = rng.randrange(n) if n else 0
                if n == 0:
                    e[0] = "s"
                    e[1] = rng.randrange(ns)
            elif e[0] == "s" and not (0 <= e[1] < ns):
                e[1] = rng.randrange(ns)
    for e in g["efectores"]:
        if e[0] == "n" and not (0 <= e[1] < n):
            if n:
                e[1] = rng.randrange(n)
            else:
                e[0], e[1] = "s", rng.randrange(ns)
        elif e[0] == "s" and not (0 <= e[1] < ns):
            e[1] = rng.randrange(ns)


def describir(g: dict) -> str:
    """Descripción legible del grafo, para el registro y el visor."""
    lineas = []
    for i, neu in enumerate(g["neuronas"]):
        ins = ", ".join(f"{t}{idx if t != 'c' else ''}×{w:+.2f}" for t, idx, w in neu["in"])
        lineas.append(f"n{i} = {neu['f']}({ins})")
    for k, (t, idx, w) in enumerate(g["efectores"]):
        lineas.append(f"e{k} = {t}{idx if t != 'c' else ''}×{w:+.2f}")
    return "\n".join(lineas)
