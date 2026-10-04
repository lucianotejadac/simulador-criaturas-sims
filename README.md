# Simulador de criaturas al estilo Karl Sims (1994)

Reconstrucción didáctica de *Evolving Virtual Creatures* (SIGGRAPH 1994) y
*Evolving 3D Morphology and Behavior by Competition* (Artificial Life IV, 1994).
Se coevolucionan cuerpo y cerebro de criaturas articuladas en un mundo físico 3D
con un algoritmo genético. No hay descenso de gradiente: lo que aprende es la
población.

**Visor en vivo:** <https://lucianotejadac.github.io/simulador-criaturas-sims/viewer/>

## Estado: Etapa 3

**Etapa 1 (cerrada):** cuerpo fijo (cadena de cuatro cajas unidas por tres
bisagras) en agua sin gravedad. Solo evoluciona el cerebro: un grafo de neuronas
con el repertorio de 23 funciones de Sims, sensores de ángulo articular y un
efector de torque por bisagra. La aptitud es el desplazamiento del centro de masa
en 10 s, con más peso a la velocidad del tramo final.

**Etapa 2 (cerrada, sin evolución):** genoma morfológico de grafo dirigido con
recursión, reflexión, escala y conexiones terminales, y desarrollo a MJCF con los
siete tipos de articulación de Sims. Los cerebros anidados (uno por nodo, más
centrales) se aplanan al desarrollar. Verificado con tres genomas escritos a
mano que se ven en el visor (`Etapa 2 · los tres cuerpos juntos`).

**Etapa 3 (cerrada):** coevolución de cuerpo y cerebro para nado y caminata
(`src/evolve_morfo.py`). En caminata la criatura se asienta antes de medir y la
aptitud es el mínimo entre tres pasos de integración, porque los saltadores son
caóticos (BITACORA 0010). Cinco semillas por tarea: nadadores de 2.3 a 7.2 m y
caminantes de 3.1 a 4.7 m en 10 s, todos verificados al afinar el paso; campeones
en el visor (`Etapa 3 · campeones con cuerpo evolucionado`). Tres trampas
documentadas en el camino (BITACORA 0011 a 0013).

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

# galería: volver a simular criaturas que no ganaron (mejor, mediana, peor y 4 al azar
# de las generaciones 1, 10, 25 y la última) para verlas una a una o en carrera
python src/galeria.py --nombre nado01 --generaciones 1,10,25,50 --cuales mejor,mediana,peor,azar:4

# Etapa 2: desarrollar y simular los genomas escritos a mano (viewer/ejemplos.json)
python src/ejemplos.py

# Etapa 3: coevolución cuerpo + cerebro (nado o caminata) y reunión de campeones para el visor
python src/evolve_morfo.py --nombre morfo-cam01 --tarea caminata --semilla 1 --generaciones 60 --poblacion 200
python src/etapa3.py --nado morfo-nado01,morfo-nado02 --caminata morfo-cam01

# tests
python -m pytest -q tests

# ver el resultado (el visor lee viewer/campeon.json)
cd viewer && python -m http.server 8000
```

Cada corrida deja en `runs/<nombre>/`: `config.json` (parámetros y semilla),
`cuerpo.xml` (MJCF), `log.csv` (mejor, media, peor y mediana por generación),
`poblacion/gen_NNN.json` (genoma y aptitud de las 300 criaturas de cada
generación), `campeon.json` (genoma), `campeon_trayectoria.json` y
`galeria.json` (posición y cuaternión de cada pieza por cuadro, para el visor).
Como la física es determinista, cualquier criatura de cualquier generación se
puede volver a simular desde su genoma guardado.

## Estructura

```
src/
  genome/neural.py   genoma neuronal: construcción, mutación, cruce, injerto, recolección
  genome/morph.py    genoma morfológico: nodos, conexiones, cerebros anidados, operadores
  genome/ejemplos.py genomas escritos a mano (cadena4, ciempies, bilateral)
  develop.py         cuerpo fijo de la Etapa 1 -> MJCF
  develop_morfo.py   genoma morfológico -> MJCF + cerebro aplanado (Etapa 2)
  ejemplos.py        simula los genomas a mano -> viewer/ejemplos.json
  tareas.py          caminata (asentamiento, suelo) y despacho por tarea (Etapa 3)
  evolve_morfo.py    coevolución cuerpo + cerebro con multiprocessing (Etapa 3)
  etapa3.py          campeones de varias corridas -> viewer/etapa3.json
  semillas.py        campeones de nado01..05 -> viewer/semillas.json
  brain.py           ejecución del grafo neuronal
  fluido.py          arrastre viscoso por cara (modelo de agua de Sims)
  fitness.py         evaluación y aptitud de nado
  evolve.py          bucle evolutivo + multiprocessing
  export.py          trayectoria del campeón -> JSON
  galeria.py         criaturas no campeonas de varias generaciones -> JSON
viewer/index.html    visor Three.js (GitHub Pages): campeón, criatura a criatura o carrera
tests/               genomas válidos, cuerpo que compila, aptitud finita
runs/                resultados por corrida (los pesados no se versionan)
BITACORA.md          decisiones de diseño y trampas detectadas
```

## Hoja de ruta

1. **Etapa 1**: cuerpo fijo, cerebro evolucionado, nado. *(cerrada)*
2. **Etapa 2**: genoma morfológico de grafo dirigido con recursión y desarrollo a MJCF. *(cerrada)*
3. **Etapa 3**: coevolución cuerpo + cerebro para nado y caminata. *(cerrada)*
4. Etapa 4: seguimiento de luz con fotosensores.
5. Etapa 5: competencia por un cubo y mundo compartido.

## Referencias

- Sims, K. (1994). *Evolving Virtual Creatures.* SIGGRAPH 94. <https://www.karlsims.com/papers/siggraph94.pdf>
- Sims, K. (1994). *Evolving 3D Morphology and Behavior by Competition.* Artificial Life IV. <https://www.karlsims.com/papers/alife94.pdf>

## Licencia

MIT. Ver [LICENSE](LICENSE).
