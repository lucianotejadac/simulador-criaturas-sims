# Bitácora de decisiones

Registro al estilo ADR (contexto, decisión, alternativas descartadas, consecuencias).
Las trampas que encuentran las criaturas se documentan aquí **antes** de corregirlas:
son parte del objetivo del proyecto, no ruido.

---

## 0001 · 2026-10-04 · Arranque de la Etapa 1 y decisiones de base

**Contexto.** Reconstrucción de Sims (1994) por etapas. La Etapa 1 fija el cuerpo
(cadena de cuatro cajas) y evoluciona solo el cerebro, para validar física, aptitud
de nado, algoritmo genético y paralelismo antes de tocar la morfología.

**Decisiones.**
- Repositorio local desde el primer día; el repo público en GitHub y Pages se crean
  cuando el visor muestre al primer campeón nadando.
- MuJoCo 3.3.2 fijado en `requirements.txt`. Las versiones 3.4 en adelante están
  bloqueadas en esta máquina por *Smart App Control* de Windows (la DLL no tiene
  reputación en Microsoft); 3.3.2 y anteriores pasan.
- Cerebro: repertorio completo de 23 funciones de Sims con aridad fija por función
  (1 a 3 entradas), actualización síncrona (todas leen el paso anterior) y dos pasos
  de cerebro por paso de física. Los valores se acotan a ±10 para que `sum`,
  `product` y `expt` no desborden: Sims no lo especifica, es nuestro supuesto.
- Sensores de la Etapa 1: solo ángulo articular normalizado al límite. Sin contacto
  (no hay suelo) ni fotosensores (Etapa 4).
- Algoritmo genético con los números de Sims: población 300, sobrevive 1/5,
  descendencia proporcional a la aptitud, 40 % asexual / 30 % cruce / 30 % injerto.
  Toda cría pasa además por mutación. Probabilidad de mutación por elemento
  = 1 / (número de elementos mutables), así se espera al menos una por genoma.
- Semilla explícita por corrida, guardada en `runs/<nombre>/config.json`.

**Alternativas descartadas.** MJX/Brax en GPU: cada criatura tendrá un cuerpo
distinto en la Etapa 3 y rompe el *batching*. Gradientes: no hay; lo que aprende es
la población.

---

## 0002 · 2026-10-04 · Fuerza muscular proporcional al área de sección

**Contexto.** Sims: la fuerza máxima de cada articulación es proporcional al área
transversal de las piezas unidas (ley cuadrado-cubo).

**Decisión.** `torque_max = K_FUERZA · ancho²`. Con el cuerpo final (cajas de
0.40 × 0.12 × 0.12 m, densidad 300 kg/m³, arrastre K = 400) una onda impuesta de
45° a 1 Hz exige unos 10 N·m, así que `K_FUERZA = 1000` (14.4 N·m) deja margen sin
sobrar. Una primera calibración con el fluido nativo de MuJoCo había dado
`K_FUERZA = 2000`, pero ese fluido resultó inválido (0004).

---

## 0003 · 2026-10-04 · Trampa: aptitud gratis por medir distancia al origen

**Qué pasó.** El test del cerebro vacío (efectores en cero) no se cortaba por "sin
movimiento": la criatura quieta ya tenía 0.645 m de aptitud. La cadena se construye
desde la raíz hacia +X, así que su centro de masa en reposo no está en el origen.

**Por qué funcionó.** La aptitud de Sims es "distancia del centro de masa al
origen", y se implementó literal.

**Cambio.** La aptitud mide el desplazamiento del centro de masa respecto de su
posición inicial: `d(t) = |CoM(t) − CoM(0)|`. La exportación guarda `com0`.

---

## 0004 · 2026-10-04 · Trampa: el empuje dependía del paso de integración

**Qué pasó.** En una corrida de humo (64 criaturas, 3 generaciones) apareció un
campeón con una sola neurona y 12.7 de aptitud (7.9 m en 10 s). Reevaluado con
pasos más finos, su distancia caía: 7.9 m a 1/120 s, 3.8 m a 1/480 s, 1.2 m a
1/1200 s, 0.15 m con RK4. El controlador era *bang-bang* (torque máximo alternado
por realimentación del ángulo) y golpeaba los límites articulares.

**Por qué funcionó.** Lo mismo le pasaba a un controlador sinusoidal escrito a
mano: su distancia se reducía a la mitad cada vez que el paso se reducía a la
mitad. El empuje no venía de nadar sino del error de integración del modelo de
fluido nativo de MuJoCo (`density`/`viscosity`, modelo *inertia-box*) combinado
con impactos contra los límites. En el límite de paso fino la criatura casi no
avanzaba.

**Cambio.** Se reemplazó el fluido nativo por el modelo de Sims: arrastre viscoso
lineal por cara, en `src/fluido.py`. Primer intento (fuerza puntual en el centro
de cada cara): las dos caras opuestas se cancelan y la caja no tiene arrastre
rotacional; también fallaba. Versión final: el arrastre lineal se integra sobre
la superficie de cada cara, lo que da en el marco de la caja una matriz diagonal
de arrastre de traslación (área de cada par de caras) y otra de rotación (segundo
momento de área de cada cara). Se verificó:

| prueba | resultado |
|---|---|
| caja aislada, 1 m/s a lo largo | se detiene en 0.146 m (teoría m/D = 0.150 s) |
| caja aislada, 1 m/s de lado | se detiene en 0.041 m (teoría 0.045 s) |
| cadena plana, onda impuesta 45° a 1 Hz | 2.01 m a 1/240 s, 2.07 m a 1/960 s |
| campeón evolucionado (bang-bang) | 4.85 m a 1/240, 4.47 a 1/480, 4.29 a 1/960, 4.20 a 1/1920 |

Además, con cajas de densidad 1000 kg/m³ (5.76 kg) la inercia dominaba al
arrastre y el régimen no se parecía al "agua viscosa" de Sims; se bajó la densidad
de las piezas a 300 kg/m³ y se fijó `K_ARRASTRE = 400 N·s/m³`. Paso de física:
1/480 s (el campeón queda a 6 % del valor convergido). Costo: una generación de
300 criaturas tarda unos segundos con 14 procesos.

**Consecuencia para el proyecto.** Toda corrida nueva debería terminar con una
reevaluación del campeón a la mitad del paso; si la aptitud cambia más de un 15 %,
hay una trampa numérica.

---

## 0005 · 2026-10-04 · Bisagras coplanares en vez de ejes alternados

**Contexto.** La decisión inicial fue alternar los ejes de las bisagras (vertical,
horizontal, vertical) para que la cadena pudiera ondular en 3D.

**Qué se vio.** Con la onda impuesta de 45° a 1 Hz la cadena de ejes alternados
avanzaba 0.03 a 0.6 m según la fase entre articulaciones; la cadena con las tres
bisagras en Z avanzaba 1.1 a 2.1 m. Con ejes alternados la onda queda repartida en
dos planos y el empuje se cancela en gran parte.

**Decisión.** Las tres bisagras en Z (ondulación lateral, como una anguila).
`CuerpoFijo(ejes=...)` conserva la opción de alternarlos. Los movimientos 3D
quedan para la Etapa 2, donde el genoma elige el tipo de articulación.

---

## 0006 · 2026-10-04 · Cierre de la Etapa 1: corrida `nado01`

**Corrida.** 300 criaturas, 50 generaciones, semilla 1, 14 procesos, paso 1/480 s:
302 s en total (6 s por generación). Registro en `runs/nado01/log.csv`.

| generación | mejor | media | mediana |
|---|---|---|---|
| 1 | 1.24 | 0.02 | 0.01 |
| 10 | 5.25 | 2.49 | 3.36 |
| 25 | 6.01 | 3.45 | 4.97 |
| 50 | 6.45 | 4.25 | 6.44 |

**Campeón.** Aptitud 6.45, desplazamiento 4.58 m en 10 s (0.46 m/s, 2.7 largos de
cuerpo). Tres neuronas: un `oscillate-wave` cuya amplitud y frecuencia salen de un
`if` realimentado, que mueve las bisagras 1 y 3 en contrafase (pesos +0.76 y
−2.72); la bisagra 2 lee directamente el ángulo de la bisagra 3 con peso 4.0, es
decir, un acoplamiento reflejo saturado. No es una onda viajera limpia como la del
controlador a mano (que daba 2.0 m), pero la supera porque usa el torque máximo.

**Verificación numérica.** Reevaluado a 1/240, 1/960 y 1/1920 s: 4.93, 4.40 y
4.32 m. Converge (diferencias que se reducen a la mitad) y el valor a 1/480 queda
a 6 % del límite. No hay trampa numérica detectable en este campeón.

**Observaciones.**
- "Quietas" (cortadas a los 3 s por no moverse): entre 19 y 38 por generación
  hasta el final. Son crías cuya mutación desconectó los efectores; el corte
  temprano las hace baratas.
- Ninguna simulación inestable en las 15 000 evaluaciones.
- En la generación 1, 215 de las 300 criaturas aleatorias no se movieron y la
  mediana fue 0.006; el mejor avanzó 0.87 m con un reflejo saturado del ángulo.
  A la generación 10 la mediana ya era 3.6: el mecanismo (oscilación por
  realimentación a torque máximo) se descubre temprano y después se afina.
- A la generación 50 la mediana (6.44) casi iguala al mejor (6.45): la población
  convergió a variantes del mismo cerebro. Sigue habiendo un 10 % de crías rotas
  por mutación (las "quietas"), que es el precio de seguir explorando.

**Pendiente para la Etapa 2.** Genoma morfológico de grafo dirigido con recursión
y desarrollo a MJCF; `fluido.py` ya acepta cualquier conjunto de cajas.

---

## 0007 · 2026-10-04 · Ver a las que no ganaron: población guardada y galería

**Contexto.** El visor solo mostraba al campeón; la evolución descartaba las
trayectorias y los genomas de las otras 299 criaturas de cada generación. Para
entender qué hace una criatura mediana, una "quieta" o la peor, hacía falta
poder volver a verlas.

**Decisión.** `evolve.py` guarda la población completa de cada generación
(genoma y aptitud, `runs/<nombre>/poblacion/gen_NNN.json`, unos 300 KB por
generación; no se versionan). Como la física es determinista, `galeria.py`
vuelve a simular criaturas elegidas (mejor, mediana, peor y algunas al azar) de
las generaciones pedidas y escribe `galeria.json` para el visor, que suma dos
vistas: una criatura a la vez, con su ficha y su cerebro, y **carrera**: todas
las elegidas de una generación en carriles paralelos, con una tabla de
colores, puesto, aptitud y distancia.

**Alternativas descartadas.** Guardar las trayectorias de todas las criaturas
durante la evolución: 300 × 50 × 80 KB = 1.2 GB por corrida, cuando el genoma
pesa 1 KB y se puede volver a simular en 0.1 s. Grabar solo algunas al azar
durante la evolución: no permite elegir después.

**Verificación.** La corrida `nado01` se repitió con la misma semilla para
generar las poblaciones y dio exactamente el mismo campeón (6.4527 en la
generación 50). Las aptitudes de la galería coinciden con las del registro,
salvo las criaturas cortadas a los 3 s por quietas, que en la galería se
simulan completas (siguen quietas).

**Consecuencias.** `galeria.json` pesa 2.3 MB (28 criaturas a 30 cuadros por
segundo) y se versiona en `viewer/` para Pages. Las trampas futuras se podrán
ver en la criatura que las explota, no solo en la curva.

---

## 0008 · 2026-10-04 · Etapa 2: genoma morfológico y desarrollo a MJCF

**Contexto.** Con la Etapa 1 cerrada, el cuerpo pasa a salir de un genoma de
grafo dirigido como el de Sims: nodos (cajas con articulación, límites, límite
recursivo y cerebro local) y conexiones (cara de anclaje, posición, rotación,
escala, reflexión y "solo terminal"). Esta etapa cierra sin evolución: se
verifica con genomas escritos a mano.

**Decisiones.**
- Siete tipos de articulación desde el inicio: rígida, bisagra, torsión,
  universal, flexión-torsión, torsión-flexión y esférica. En MuJoCo son una,
  dos o tres bisagras en serie en la hija, con ejes X, Y o Z de su marco.
- Límites: 8 nodos, 4 conexiones por nodo, 16 piezas, 12 neuronas por nodo y
  8 centrales. Un cuerpo que alcanza 16 piezas, que no tiene grados de libertad
  o cuyas piezas no adyacentes se tocan en reposo se rechaza (MuJoCo filtra el
  contacto madre–hija; cualquier otro contacto en reposo es interpenetración).
- **Referencias por identificador, no por posición.** Las neuronas tienen un id
  único por genoma y las entradas "n" (local), "p" (madre), "g" (central) y "r"
  (raíz, desde las centrales) apuntan a ids. Con índices, borrar una neurona
  corría las demás y cambiaba a quién apuntaban los nodos vecinos; con ids,
  la recolección de basura nunca reconecta nada. Una referencia que no existe
  en la instancia concreta vale cero (entrada ausente), lo que permite escribir
  `sum(p:cabeza.osc, p:segmento.lag)` en un nodo recursivo: la primera
  instancia lee a la cabeza y las siguientes al segmento anterior.
- **Reflexión** (bilateralidad): la hija reflejada se espeja respecto del plano
  XZ de la madre (posición M·p, orientación M·R·M, ejes de las bisagras M·a) y
  se invierte el signo del torque y del sensor de sus articulaciones, de modo
  que el mismo cerebro produce el movimiento espejo. El estado se hereda por
  el subárbol (reflejo de reflejo = normal).
- Fuerza muscular: `K_FUERZA` por el área menor entre la sección de la hija y
  la de la madre.
- El cerebro anidado se "aplana" al desarrollar: una copia por instancia de
  pieza más las centrales, en el formato de la Etapa 1, así `brain.Cerebro`,
  `fitness` y `fluido` no cambian.

**Alternativas descartadas.** Resolver las referencias "p" por módulo del
número de neuronas de la madre (frágil ante cualquier borrado). Un solo plano
de reflexión global en vez de relativo a la madre (no reproduce extremidades
reflejadas en subárboles rotados).

**Verificación.** Tres genomas a mano (`src/genome/ejemplos.py`): `cadena4`
reproduce la Etapa 1 con un nodo recursivo (4 piezas, 3 dof) y nada 1.9 m con
una onda viajera que nace de la recursión (cada segmento retarda la oscilación
de su madre); `ciempies` (13 piezas, 12 dof, 8 patas de las que 4 son reflejadas)
y `bilateral` (aletas universales en cuadratura y cola que se achica por la
escala). De 300 genomas aleatorios mutados cinco veces, un tercio compila; el
resto se rechaza por interpenetración, por no tener grados de libertad o por
exceso de piezas. Diez tests nuevos cubren validez tras mutación, cruce e
injerto, recolección, límite recursivo, conexiones terminales, reflexión
(posición espejada y torque con signo invertido), interpenetración y exceso
de piezas.

**Pendiente (Etapa 3).** Evolucionar: generación de la población inicial con
rechazo de genomas inválidos, evaluación con el modelo compilado por criatura
(cada esclavo compila su MJCF), y la aptitud de caminata con asentamiento.

---

## 0009 · 2026-10-04 · Cinco semillas: ¿convergen al mismo cerebro?

**Contexto.** Pendiente de la Etapa 1: repetir `nado01` con semillas 2 a 5
(300 × 50, mismos parámetros) para ver si todas las corridas llegan al mismo
tipo de cerebro o aparecen otras formas de nadar.

| corrida | aptitud | distancia | a mitad de paso | neuronas | mejor gen 10 | mediana final |
|---|---|---|---|---|---|---|
| nado01 | 6.45 | 4.58 m | 4.40 m | 3 | 5.25 | 6.44 |
| nado02 | 5.75 | 4.08 m | 4.16 m | 7 | 5.49 | 5.74 |
| nado03 | 5.46 | 3.86 m | 3.97 m | 14 | 5.16 | 5.45 |
| nado04 | 6.42 | 4.56 m | 4.35 m | 18 | 3.32 | 6.39 |
| nado05 | 6.47 | 4.60 m | 4.41 m | 24 | 6.16 | 6.46 |

**Qué se vio.**
- Las cinco corridas terminan entre 3.9 y 4.6 m en 10 s, y en todas la mediana
  final casi iguala al mejor: cada población converge a su campeón. Las tres
  mejores (semillas 1, 4 y 5) quedan a menos de 1 % entre sí, lo que sugiere un
  techo del cuerpo (torque de 14.4 N·m contra el arrastre) más que del cerebro.
- El mecanismo es el mismo en las cinco: **un efector lee directamente un
  sensor de ángulo con peso grande** (`e1 = s2×4.00`, `e1 = s0×4.00`,
  `e1 = s0×2.93`, `e0 = s1×1.41`, `e0 = s1×1.64`), un reflejo saturado que
  convierte la bisagra en un oscilador de relevo a torque máximo. Las otras dos
  bisagras siguen a esa con neuronas evolucionadas (oscilador, retardo, `if`).
  No apareció una onda viajera "limpia" como la del controlador a mano: el
  relevo saturado es más rápido de encontrar y más fuerte.
- Los cerebros grandes están llenos de neuronas inertes: en `nado05`, nueve de
  las 24 son `if` con condición constante negativa, que siempre devuelven su
  tercera entrada. La recolección de basura no las quita porque siguen
  conectadas a un efector. Es deriva neutral, no funcionalidad. Sims no
  penalizaba el tamaño; nosotros tampoco, por ahora.
- `nado04` arrancó lento (3.3 en la generación 10, la peor) y terminó segundo:
  la curva de las primeras generaciones no predice el resultado.
- Verificación numérica: las cinco a la mitad del paso cambian menos de 5 %.

**Decisión.** Sin cambios en el modelo. Queda anotado para la Etapa 3 que la
aptitud de nado con este cuerpo tiene un techo cerca de 4.6 m, y que un
reflejo saturado sobre un sensor es la primera solución que encuentra la
evolución en cualquier semilla. Los cinco campeones se pueden ver en carrera en
el visor («Cinco semillas»).
