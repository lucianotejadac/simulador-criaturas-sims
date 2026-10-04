# Simulador de criaturas al estilo Karl Sims (1994)

Reconstrucción didáctica de *Evolving Virtual Creatures* (SIGGRAPH 1994) y
*Evolving 3D Morphology and Behavior by Competition* (Artificial Life IV, 1994).
Se coevolucionan cuerpo y cerebro de criaturas articuladas en un mundo físico 3D
con un algoritmo genético. No hay descenso de gradiente: lo que aprende es la
población.

**Visor en vivo:** <https://lucianotejadac.github.io/simulador-criaturas-sims/viewer/>

## Estado: Etapa 1

Cuerpo fijo (cadena de cuatro cajas unidas por tres bisagras) en agua sin
gravedad. Solo evoluciona el cerebro: un grafo de neuronas con el repertorio de
23 funciones de Sims, sensores de ángulo articular y un efector de torque por
bisagra. La aptitud es el desplazamiento del centro de masa en 10 s, con más peso
a la velocidad del tramo final.

Las decisiones de diseño y las trampas que encontraron las criaturas están en
[BITACORA.md](BITACORA.md).

## Instalación

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

MuJoCo queda fijado en 3.3.2: en Windows con *Smart App Control* activo, las
versiones 3.4 en adelante se bloquean al importar.

## Uso

```
# evolución (300 criaturas, 50 generaciones, semilla 1) y exportación del campeón
python src/evolve.py --nombre nado01 --generaciones 50 --poblacion 300 --semilla 1

# solo exportar la trayectoria del campeón de una corrida ya hecha
python src/export.py --nombre nado01

# tests
python -m pytest -q tests

# ver el resultado (el visor lee viewer/campeon.json)
cd viewer && python -m http.server 8000
```

Cada corrida deja en `runs/<nombre>/`: `config.json` (parámetros y semilla),
`cuerpo.xml` (MJCF), `log.csv` (mejor, media, peor y mediana por generación),
`campeon.json` (genoma) y `campeon_trayectoria.json` (posición y cuaternión de
cada pieza por cuadro, para el visor).

## Estructura

```
src/
  genome/neural.py   genoma neuronal: construcción, mutación, cruce, injerto, recolección
  develop.py         genoma -> MJCF (Etapa 1: cuerpo fijo)
  brain.py           ejecución del grafo neuronal
  fluido.py          arrastre viscoso por cara (modelo de agua de Sims)
  fitness.py         evaluación y aptitud de nado
  evolve.py          bucle evolutivo + multiprocessing
  export.py          trayectoria del campeón -> JSON
viewer/index.html    visor Three.js (GitHub Pages)
tests/               genomas válidos, cuerpo que compila, aptitud finita
runs/                resultados por corrida (los pesados no se versionan)
BITACORA.md          decisiones de diseño y trampas detectadas
```

## Hoja de ruta

1. **Etapa 1**: cuerpo fijo, cerebro evolucionado, nado. *(en curso)*
2. Etapa 2: genoma morfológico de grafo dirigido con recursión y desarrollo a MJCF.
3. Etapa 3: coevolución cuerpo + cerebro para nado y caminata.
4. Etapa 4: seguimiento de luz con fotosensores.
5. Etapa 5: competencia por un cubo y mundo compartido.

## Referencias

- Sims, K. (1994). *Evolving Virtual Creatures.* SIGGRAPH 94. <https://www.karlsims.com/papers/siggraph94.pdf>
- Sims, K. (1994). *Evolving 3D Morphology and Behavior by Competition.* Artificial Life IV. <https://www.karlsims.com/papers/alife94.pdf>

## Licencia

MIT. Ver [LICENSE](LICENSE).
