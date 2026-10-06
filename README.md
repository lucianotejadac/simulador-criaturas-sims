# Simulador de criaturas al estilo Karl Sims (1994)

Reconstrucción didáctica de *Evolving Virtual Creatures* (SIGGRAPH 1994) y
*Evolving 3D Morphology and Behavior by Competition* (Artificial Life IV, 1994).
Se coevolucionan cuerpo y cerebro de criaturas articuladas en un mundo físico 3D
con un algoritmo genético. No hay descenso de gradiente: lo que aprende es la
población.

**Visor en vivo:** <https://lucianotejadac.github.io/simulador-criaturas-sims/viewer/>

## Estado: hoja de ruta completa y un ecosistema abierto

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

**Etapa 8 (abierta):** de la célula al cuerpo (`src/celulas.py`, visor
`viewer/celulas.html`). Cada célula es un segmento con flagelo propio y siete
genes (adhesión, cilio, amplitud, frecuencia, desfase heredado, sesgo hacia la
comida, largo); al dividirse, la hija puede nacer unida a la madre con la
probabilidad que dice el gen de adhesión, y los árboles de células unidas son
cuerpos articulados del mundo 2D que nadan en onda viajera si tienen tres o
más células con cilio y desfase. Presiones activables: depredador que come lo
que pese menos que un umbral, comida grande que exige masa. Medido antes de
evolucionar nada: el par de células es un valle (come dos tercios de lo que
come una sola) y el cuerpo de cuatro gana un 55 % (BITACORA 0026-0028). Con
una prueba de invasión (la mitad de las fundadoras adhesivas) las colonias
persisten; partiendo de adhesión cero, en 300 épocas con depredador la adhesión sube a 0.10 y aparecen cuerpos de 3 a 13 células (7 % de las células), y luego retrocede porque las solas aprenden a nadar más rápido y escapan sin unirse; sin presiones nada cambia (el tope congela la evolución).

**Etapa 7 (abierta):** el mismo ecosistema a escala en un mundo 2D viscoso sin
inercia (`src/mundo2d.py`, `src/ecosistema2d.py`, visor `viewer/acuario2d.html`):
500 criaturas, mundo de 50 m, comida de dos tamaños que exigen cuerpos distintos.
Primera corrida: monocultivo de anguilas a los 10 min, y después, dentro de la
anguila, radiación hacia cuerpos cortos que ocupan el nicho de la comida chica
(BITACORA 0022-0023). El visor 2D publicado muestra `eco2d-fluido`: 40 criaturas en un mundo de
24 m, las 50 épocas grabadas enteras y reproducidas de corrido con interpolación
(`--mundo 24 --tope 40 --grabar-cada 1 --fps 2`). `viewer/vivo.html` es el mismo mundo portado a JavaScript:
corre en vivo en el navegador, con las reglas (comida, energía, agitación, tope)
editables, y una «sopa primitiva» de cajas sueltas como partida alternativa.

**Etapa 6 (abierta, laboratorio):** ecosistema. Un bestiario de seis especies
acuáticas escritas a mano con fototaxis cableada (`src/genome/bestiario.py`) convive
en un acuario con luces-comida, energía, reproducción y muerte, sin generaciones ni
aptitud (`src/ecosistema.py`). El mundo se recompila por épocas de 20 s. En el
primer acuario la anguila, la más rápida y la que mejor gira, forma un monocultivo
a los 500 s (BITACORA 0020-0021). Requiere Numba (cerebro y arrastre compilados,
BITACORA 0019).

**Etapa 5 (cerrada):** competencia por un cubo entre dos especies que
coevolucionan (`src/arena.py`, `src/evolve_duelo.py`): dos criaturas en el mismo
mundo, cada una a 1.5 m del cubo, aptitud por distancia relativa más bono por
tocarlo, emparejamiento "todos contra el mejor". En diez generaciones ambas
especies llegan al cubo; después la ventaja va y viene (Reina Roja). Duelos
entre campeones en el visor (`Etapa 5 · duelo por el cubo`).

**Etapa 4 (cerrada):** un ancestro pez escrito a mano (cola recursiva que se
afina, aleta caudal terminal, aletas pectorales reflejadas) sembrado en dos
experimentos: *pez fuera del agua* (caminata: en dos de cinco semillas las
aletas se vuelven extremidades articuladas) y *seguimiento de luz* con
fotosensores por pieza (las cinco campeonas giran hacia la luz modulando la
amplitud de su oscilador). Linajes por generación y carreras en el visor.

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

# Etapa 4: sembrar con el ancestro pez (caminata o luz) y ver el linaje
python src/evolve_morfo.py --nombre pez-cam01 --tarea caminata --ancestro pez --semilla 1
python src/evolve_morfo.py --nombre pez-luz01 --tarea luz --ancestro pez --semilla 1 --generaciones 50
python src/linaje.py --corridas pez-cam01 --generaciones 1,10,20,30,40,50,60

# Etapa 5: dos especies por el cubo
python src/evolve_duelo.py --nombre duelo01 --semilla 1 --ancestro pez --generaciones 50 --poblacion 100

# Etapa 6: bestiario y acuario (30 épocas de 20 s, seis especies, cuatro de cada una)
python src/bestiario_export.py
python src/ecosistema.py --nombre eco01 --semilla 1 --epocas 30 --especies anguila,pez,renacuajo,raya,ciempies_acuatico,remador --por-especie 4

# Etapa 7: acuario 2D a escala (240 fundadoras, 90 épocas de 20 s, tope 500)
python src/ecosistema2d.py --nombre eco2d01 --semilla 1 --epocas 90 --por-especie 40

# Etapa 8: células -> cuerpos (150 fundadoras, 300 épocas de 20 s, tope 600); --depredador, --comida-grande 8,
# --adhesivas 0.5 (prueba de invasión), --reparto (comida chica como bien público), --ancestro azar
python src/celulas.py --nombre cel-L1 --semilla 1 --epocas 300 --celulas 150 --depredador --grabar-cada 6

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
  luz.py             fotosensores y aptitud de seguimiento de luz (Etapa 4)
  linaje.py          el mejor de varias generaciones de una corrida -> viewer/linaje.json
  arena.py           dos criaturas y un cubo en el mismo mundo; aptitud del duelo (Etapa 5)
  evolve_duelo.py    coevolución de dos especies, todos contra el mejor -> viewer/duelos.json
  brain_rapido.py    cerebro compilado con Numba (misma semántica que brain.py)
  genome/bestiario.py seis especies a mano con fototaxis cableada
  bestiario_export.py bestiario -> viewer/bestiario.json
  ecosistema.py      acuario con energía, comida, reproducción y muerte -> viewer/acuario.json
  mundo2d.py         física 2D viscosa sin inercia (Stokes), Numba, punto medio
  develop2d.py       genoma morfológico proyectado al plano
  brain_lote.py      cerebros de muchas criaturas en un solo núcleo
  ecosistema2d.py    acuario a escala en 2D -> viewer/acuario2d.json (visor: viewer/acuario2d.html)
  celulas.py         células con flagelo que se dividen y se unen -> viewer/celulas-*.json (visor: viewer/celulas.html)
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
4. **Etapa 4**: ancestro pez, pez fuera del agua y seguimiento de luz. *(cerrada)*
5. **Etapa 5**: competencia por un cubo entre dos especies. *(cerrada)*
6. **Etapa 6**: bestiario y ecosistema con energía y comida. *(abierta como laboratorio)*
7. **Etapa 7**: mundo 2D viscoso sin inercia y ecosistema a escala. *(abierta)*
8. **Etapa 8**: de la célula al cuerpo: adhesión, cilios y depredador. *(abierta)*

## Referencias

- Sims, K. (1994). *Evolving Virtual Creatures.* SIGGRAPH 94. <https://www.karlsims.com/papers/siggraph94.pdf>
- Sims, K. (1994). *Evolving 3D Morphology and Behavior by Competition.* Artificial Life IV. <https://www.karlsims.com/papers/alife94.pdf>

## Licencia

MIT. Ver [LICENSE](LICENSE).
