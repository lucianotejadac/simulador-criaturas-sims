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

---

## 0010 · 2026-10-04 · Etapa 3: coevolución, caminata y la física de los contactos

**Contexto.** Con el genoma morfológico verificado, se coevolucionan cuerpo y
cerebro en dos tareas: nado (el agua de la Etapa 1) y caminata (gravedad y
suelo con fricción). El usuario dejó las decisiones a mi criterio y preguntó
por la GPU.

**Decisiones de base.**
- **CPU, no GPU.** MJX simula en GPU miles de copias del *mismo* modelo; aquí
  cada criatura tiene un árbol de piezas distinto y no se puede agrupar en un
  lote. El costo tampoco está en la física sino en el cerebro (grafo
  heterogéneo en Python) y en el arrastre por cara. Y JAX con CUDA no corre en
  Windows nativo. Patrón maestro–esclavo con un proceso por criatura, como
  Sims en la CM-5. Medido: una evaluación de nado tarda 0.14 s (mediana) con
  cuerpos de hasta 13 piezas; no hace falta Numba.
- **Crías inválidas se descartan y se regeneran** (demasiadas piezas, sin
  grados de libertad, interpenetradas), hasta 40 intentos por cupo. En la
  población inicial se rechazan unos dos genomas aleatorios por cada uno
  aceptado.
- **Tamaño del cerebro sin penalizar**, como Sims; los topes de la Etapa 2
  acotan la deriva neutral.
- **Asentamiento con fricción.** Sims soltaba la criatura sin fricción ni
  torques hasta que se quedara quieta, para que no ganara distancia cayendo.
  Sin fricción, una criatura que cae torcida resbala para siempre y nunca se
  asienta (el `bilateral` de ejemplo no se asentó en 2 s). Se asienta *con*
  fricción y sin torques, y la distancia se mide desde ahí: el efecto que Sims
  quería evitar se evita igual, porque el origen se fija después de la caída.
  Si al final el centro de masa queda por debajo de la mitad de su altura
  asentada, no se suma el premio de la fase final.

**Trampa: el caminante que avanza por el error de integración.** En la primera
corrida de humo (40 criaturas, 3 generaciones), una criatura de 2 piezas con
articulación universal obtuvo 5.4 de aptitud en la generación 0 y el campeón
de 6 piezas llegó a 4.0 m. Reevaluado a paso más fino: 1.2 m a 1/960 s y
1.6 m a 1/1920 s, con el centro de masa saltando hasta 0.79 m de altura con
un cuerpo de 12 cm. Torque máximo alternado (bang-bang) contra el suelo y los
límites articulares, con contactos blandos integrados a 1/480 s.

Lo que se probó, en orden:
1. **Filtro de activación muscular** de primer orden (50 ms): el torque no
   puede cambiar de signo en un paso. Fisiológicamente razonable, y queda. No
   bastó: el nuevo campeón pasaba de 5.3 m a 1.4 m al afinar el paso.
2. **Opciones del solver de contactos** (cono elíptico, `impratio` 10,
   `noslip`, límites y contactos más rígidos): ninguna hizo converger la
   distancia; cambiaban los números, no la dispersión.
3. **Menos fuerza en tierra.** En el agua la escala del torque es el arrastre;
   en tierra es el peso. Con `K_FUERZA = 1000` el torque era diez veces el
   necesario para levantar el propio cuerpo; en caminata se usa
   `K_FUERZA_CAMINATA = 300` (unas tres veces). Los saltos bajan de 0.8 m a
   0.3 m, pero la dispersión sigue.
4. **Diagnóstico final:** se evaluó el campeón de humo en diez pasos entre
   1/480 y 1/1000 s y en diez entre 1/1900 y 1/4000 s. Distancias de 1.6 a
   5.2 m en el primer rango (media 3.4, desviación 1.2) y de 0.7 a 6.3 m en el
   segundo (media 2.6, desviación 1.6). **No es un error que se reduce con el
   paso: es caos.** Una criatura que salta y rebota es un sistema caótico; la
   distancia de un ensayo de 10 s es una variable aleatoria ancha, y el
   promedio sí es parecido entre rangos. Nada que ver con el nado, donde el
   fluido viscoso amortigua todo y el campeón convergía a 6 %.

**Decisión.** La aptitud de caminata es el **mínimo entre tres evaluaciones
con pasos distintos** (1/480, 1/720 y 1/960 s). No elimina el caos, pero
premia a las criaturas que avanzan de forma consistente y castiga a las que
dependen de un rebote afortunado. Costo: tres evaluaciones por criatura,
unos 7 s por generación de 200. El nado sigue con una evaluación, porque
converge. En la bitácora queda la lección de método: antes de llamar "trampa"
a una dependencia del paso, mirar si el promedio converge; si converge y la
dispersión no, es caos y la respuesta es estadística, no numérica.

**Lote lanzado.** Cinco semillas de nado y cinco de caminata (200 criaturas,
60 generaciones), en secuencia y desacopladas, `scratch/lote_etapa3.py`.
Resultados en la entrada siguiente.

---

## 0011 · 2026-10-04 · Trampa: el nadador de 227 metros y la fuerza–velocidad del músculo

**Qué pasó.** Primera corrida del lote de la Etapa 3 (`morfo-nado01`, 200 × 60).
Campeón con 15 piezas y aptitud 322: 227 m en 10 s, 23 m/s de media. Un
genoma con un nodo que se repite cuatro veces con escala 1.27 acumulada, de
modo que las piezas crecen hasta 1.56 m y 185 kg, todas con articulación
esférica (tres bisagras apiladas) y torques de hasta 318 N·m.

**Por qué funcionó.** Reevaluado a paso fino: 69 m a 1/960 s y 15 m a
1/1920 s. La distancia se divide por tres cada vez que el paso se divide por
dos: artefacto de integración puro. Aislando factores sobre el mismo genoma:
sin arrastre la simulación explota; con límites más rígidos baja a la mitad;
con el integrador `implicit` baja a un quinto; **con amortiguación articular
10 veces mayor (3 en vez de 0.3 N·m·s/rad) queda en 0.3 m a cualquier paso.**
La energía entraba por las bisagras: torques enormes sobre piezas enormes con
una amortiguación fija pensada para la cadena de 14 N·m de la Etapa 1, y tres
bisagras coincidentes peleando contra sus límites blandos.

**Cambio.** La amortiguación de cada bisagra es proporcional a su torque
máximo: `damping = 0.05 · torque_max` (N·m·s/rad). Es la relación
fuerza–velocidad del músculo: un músculo grande también frena más, y a 20 rad/s
la fricción iguala a la fuerza máxima. Con eso el campeón tramposo da 0.23,
0.20 y 0.20 m a 1/480, 1/960 y 1/1920 s, y la cadena de ejemplo pasa de 1.83
a 1.66 m. Además, en nado, toda criatura con aptitud mayor que 8 (por encima
del techo de la Etapa 1) se reevalúa a la mitad del paso: si cae a menos de la
mitad, su aptitud es 0 con motivo "inconsistente"; si no, se queda con la menor.

**Consecuencias.** El lote se detuvo en la segunda corrida y se relanzó con la
física corregida; los resultados de `morfo-nado01` se descartaron. Queda la
lección de la Etapa 1 confirmada: cada vez que el cuerpo cambia de escala, hay
que volver a verificar la convergencia con el paso. Y una segunda lección para
la morfología evolutiva: la escala acumulada por recursión (1.27⁴ ≈ 2.6) lleva
a las criaturas a los extremos del rango donde los parámetros numéricos dejan
de estar calibrados; la respuesta correcta no fue acotar la escala sino hacer
que la amortiguación acompañe a la fuerza.

---

## 0012 · 2026-10-04 · Trampa: gigantes por escala acumulada

**Qué pasó.** Segunda corrida del lote relanzado (`morfo-nado02`). En la
generación 29, toda la población nadaba entre 50 y 80 m: la mediana era 61.
El campeón tenía 15 piezas, la mayor de 8 × 14 × 9 m, y una masa total de
690 toneladas, con torques de 43 000 N·m. Cada generación tardaba 35 s en vez
de 5. Había pasado la verificación a medio paso (78 frente a 83) pero no a un
cuarto de paso (41).

**Por qué funcionó.** El genoma limita las dimensiones de cada nodo a
[0.04, 0.8] m, pero la escala de cada conexión (hasta 1.5) se multiplica a lo
largo de la recursión y el desarrollo no la acotaba: 1.46⁴ ≈ 4.5 por rama y
más al encadenar nodos. Como la aptitud se mide en metros absolutos, ser
grande paga por sí solo, y con tamaños fuera de todo lo calibrado la física
tampoco converge.

**Cambio.** Las dimensiones de cada pieza desarrollada se recortan al mismo
rango del genoma, [0.04, 0.8] m, sin importar la escala acumulada: la escala
sigue sirviendo para afinar y para hacer colas que se achican, pero no para
crecer sin límite. Con eso el gigante queda en 1.8 t y 1.5 m de pieza máxima
y nada 1.5 m. Además, la verificación de consistencia en nado pasa de medio
paso a un cuarto de paso (1/1920 s), porque el gigante era consistente a
medio paso y no a un cuarto.

**Consecuencias.** La aptitud en metros absolutos sigue favoreciendo a las
criaturas grandes dentro del rango, como en Sims. Si en el lote se ve que
todas convergen al tope de 0.8 m, la alternativa es medir en largos de
cuerpo; queda anotado, no decidido. El lote se relanzó por tercera vez,
conservando `morfo-nado01`, cuyo campeón (3 piezas, 7.2 m) converge con la
física corregida: 7.20, 6.96 y 6.82 m a 1/480, 1/960 y 1/1920 s.

---

## 0013 · 2026-10-04 · Cierre del lote de la Etapa 3 y la trampa del umbral

**Trampa: la población aprende dónde está el umbral.** La verificación de
consistencia en nado (0011) se aplicaba solo a criaturas con aptitud mayor
que 8. En el tercer lanzamiento del lote, `morfo-nado02` y `morfo-nado04`
terminaron con 8.00 y 7.98: justo debajo del umbral, y ninguna de las dos
convergía (5.7 → 2.2 → 0.9 m y 4.4 → 0.1 → 0.03 m al afinar el paso). Se bajó
el umbral a 1.0 y se repitieron: a la generación 7 la mejor valía 0.998 y la
mediana 0.97. La población no "sabe" nada, pero la selección encuentra
cualquier discontinuidad de la aptitud y se acomoda justo del lado barato.

**Cambio.** La verificación es incondicional: toda criatura de nado que se
mueva (aptitud > 0.05) se reevalúa a la mitad del paso; si cae a menos de la
mitad, su aptitud es 0 con motivo "inconsistente"; si no, vale la menor. Las
quietas, que se cortan a los 3 s, no pagan la segunda evaluación. Costo: dos
evaluaciones por nadador. Lección de método: **un chequeo condicionado a la
aptitud crea un umbral, y el umbral se convierte en objetivo**; las defensas
contra artefactos tienen que ser uniformes o la evolución las rodea.

Resultado final (distancias a 1/480, 1/960 y 1/1920 s):

| corrida | tarea | aptitud | 1/480 | 1/960 | 1/1920 | piezas | dof | neuronas | nodos | gen del mejor | mediana final |
|---|---|---|---|---|---|---|---|---|---|---|---|
| morfo-nado01 | nado | 10.11 | 7.20 m | 6.96 m | 6.82 m | 3 | 2 | 2 | 7 | 59 | 9.57 |
| morfo-nado02 | nado | 7.00 | 4.94 m | 4.93 m | 4.92 m | 5 | 9 | 5 | 8 | 59 | 6.67 |
| morfo-nado03 | nado | 3.21 | 2.28 m | 2.24 m | 2.19 m | 4 | 9 | 12 | 1 | 57 | 3.20 |
| morfo-nado04 | nado | 3.60 | 2.44 m | 2.39 m | 2.37 m | 4 | 6 | 2 | 8 | 59 | 3.48 |
| morfo-nado05 | nado | 5.74 | 3.95 m | 3.95 m | 3.94 m | 3 | 4 | 2 | 8 | 60 | 5.37 |
| morfo-cam01 | caminata | 4.77 | 3.17 m | 3.16 m | 1.49 m | 2 | 2 | 1 | 3 | 11 | 4.77 |
| morfo-cam02 | caminata | 6.70 | 4.71 m | 4.63 m | 4.76 m | 2 | 2 | 3 | 5 | 53 | 6.70 |
| morfo-cam03 | caminata | 5.49 | 3.98 m | 3.87 m | 4.06 m | 3 | 4 | 1 | 8 | 46 | 5.49 |
| morfo-cam04 | caminata | 6.10 | 4.21 m | 4.33 m | 4.28 m | 3 | 3 | 5 | 8 | 57 | 6.07 |
| morfo-cam05 | caminata | 4.60 | 3.13 m | 3.15 m | 3.03 m | 3 | 4 | 8 | 2 | 57 | 4.60 |


**Qué se vio.**
- **Nado.** Con la verificación incondicional, las cinco convergen a menos de
  3 % al afinar el paso. Los cuerpos son chicos: `morfo-nado01` son tres placas
  de 0.76 m con articulaciones flexión–torsión movidas por un oscilador central
  (7.2 m); `morfo-nado02` cinco piezas con 9 grados de libertad (4.9 m);
  `morfo-nado05` tres piezas (3.9 m). Solo dos superan a la cadena fija de la
  Etapa 1 (4.6 m), y lo hacen con menos piezas. En este régimen viscoso, más
  piezas no ayudan.
- **Caminata.** Las cinco corridas convergen (cuatro dentro del 5 % al afinar
  el paso) a cuerpos de 2 o 3 piezas y 2 a 4 grados de libertad: balancines y
  reptadores que avanzan entre 3.1 y 4.7 m en 10 s. En todas hay un efector
  que lee un sensor de ángulo con peso grande (reflejo saturado), el mismo
  mecanismo que en la Etapa 1. La aptitud robusta (mínimo de tres pasos)
  eliminó a los saltadores caóticos de las corridas de humo.
- **Tamaño.** Ningún campeón se acerca al tope de 0.8 m por pieza (la mayor
  mide 0.77 m), así que no hace falta medir en largos de cuerpo por ahora.
- **Generación del mejor.** En nado el mejor aparece al final (gen 54 a 60);
  en caminata, en `morfo-cam01` apareció en la generación 11 y no mejoró en
  49 generaciones: con aptitud robusta y cuerpos de dos piezas, el paisaje es
  plano.

**Decisión.** La Etapa 3 cierra con este lote. Quedan para la bitácora de la
Etapa 4 dos preguntas abiertas: si conviene premiar en largos de cuerpo, y si
la recursión está sirviendo (los campeones usan pocos nodos; los cuerpos
repetitivos aparecen en la población pero no ganan).

---

## 0014 · 2026-10-05 · Etapa 4: un ancestro reconocible, el pez fuera del agua y la luz

**Contexto.** El usuario pidió criaturas con una forma más conocida ("partir
con gusanos", después "algo que pueda evolucionar en pez") y propuso el
experimento de "un pez recién salido del agua". La Etapa 4 original era solo
seguimiento de luz; se reorganiza en dos experimentos con el mismo ancestro.

**Decisiones.**
- **Sembrar, no restringir.** La población inicial es el ancestro más 199
  mutantes suyos (1 a 3 mutaciones); la mutación morfológica sigue completa.
  Se descartó restringir la gramática a "solo gusanos" porque se perdería lo
  que queremos ver: qué hace la selección con las aletas. Si los cuerpos
  degeneran, la restricción queda como alternativa (`--ancestro` en
  `evolve_morfo.py`).
- **Ancestro pez** (`genome/ejemplos.py: pez`): cabeza rígida con dos
  osciladores en cuadratura (1.6 Hz); cola de 5 segmentos recursivos con
  escala 0.85 (se afina) y bisagras verticales ±60° con la cadena de retardo
  de la Etapa 2; aleta caudal vertical por conexión *solo terminal* (el
  mecanismo de Sims para "algo distinto en la última instancia"); par de
  aletas pectorales reflejadas con articulación universal que baten en
  cuadratura. 9 piezas, 10 grados de libertad. Nada 0.77 m en 10 s con el
  cerebro a mano, menos que la cadena de ejemplo (1.66 m): el cuerpo que se
  afina y la cabeza ancha tienen menos empuje y más arrastre. Para que quepan
  5 segmentos, `REC_MAX` pasa de 4 a 6.
- **Pez fuera del agua.** El mismo ancestro sembrado en la tarea de caminata
  de la Etapa 3, sin ningún cambio en la tarea: cinco semillas, 200 × 60. El
  ancestro avanza 0.69 m a los tumbos; la pregunta es qué hace la selección
  con las aletas pectorales y la cola.
- **Fotosensores.** Cada pieza tiene un sensor en su centro que da las tres
  componentes de la dirección unitaria a la luz en su propio marco (entradas
  "l" 0, 1, 2 en el genoma). En piezas reflejadas se invierte la componente Y,
  como el signo de los sensores articulares, para que el mismo cerebro dé la
  conducta espejo. Los sensores se aplanan después de los ángulos
  (`n_sensores = n_dof + 3·n_piezas`); en nado y caminata valen cero.
- **Aptitud de luz.** Tres ensayos de 6 s con la luz a 4 m en direcciones
  90°, 210° y 330°; aptitud = velocidad media de acercamiento (m/s)
  promediada. Cuatro ensayos de 8 s costaban 45 s por generación; con tres
  de 6 s, unos 25. Si la criatura no se mueve en el primer ensayo, no corre
  los demás. Verificación incondicional a medio paso como en nado.
- **Linaje en el visor.** La mejor criatura de las generaciones 1, 10, 20,
  30, 40, 50 y 60 de una corrida, en carriles, para ver cómo se deforma el
  ancestro. Sale de las poblaciones guardadas por generación (0007).
- **Piel.** Pendiente: ojo en la cabeza y aletas dibujadas como placas. Por
  ahora el visor dibuja las cajas tal cual.

**Alternativas descartadas.** Un sensor de luz solo en la raíz (más simple,
menos Sims). Aptitud de luz con premio por distancia final (redundante con la
velocidad media). Correr luz y caminata a la vez (duplica el tiempo de cada
uno en los 16 hilos; se encadenaron).

---

## 0015 · 2026-10-05 · Pez fuera del agua: resultados

**Corrida.** Ancestro pez sembrado en caminata, cinco semillas, 200 × 60.
Distancias a 1/480, 1/960 y 1/1920 s; "reflejadas" cuenta las piezas que
nacen de una conexión con reflexión (el par de aletas y lo que cuelga de él).

| corrida | aptitud | 1/480 | 1/960 | 1/1920 | piezas | dof | gen del mejor |
|---|---|---|---|---|---|---|---|
| pez-cam01 | 6.91 | 4.81 m | 5.18 m | 3.84 m | 5 (1 reflejada) | 8 | 55 |
| pez-cam02 | 9.58 | 6.81 m | 6.83 m | 6.58 m | 11 (5 reflejadas) | 20 | 60 |
| pez-cam03 | 7.78 | 5.44 m | 5.45 m | 3.08 m | 15 (7 reflejadas) | 18 | 57 |
| pez-cam04 | 5.69 | 3.99 m | 4.01 m | 4.07 m | 3 (0 reflejadas) | 2 | 38 |
| pez-cam05 | 6.42 | 4.42 m | 4.49 m | 2.32 m | 5 (1 reflejada) | 7 | 49 |

**Qué se vio.**
- **Las aletas se vuelven extremidades.** En `pez-cam02`, el mejor resultado
  de caminata de todo el proyecto (6.8 m, convergente), la cola desapareció y
  cada aleta pectoral es ahora una cadena de cinco segmentos articulados que
  se afinan hacia la punta, con articulaciones de dos grados de libertad, una
  espejo de la otra. Dos brazos remando en simetría bilateral: la recursión y
  la reflexión del genoma de Sims, que en la Etapa 3 no ganaban, aquí ganan.
  `pez-cam03` hizo lo mismo con 15 piezas (el tope) y 7 reflejadas.
- **La cola es lo primero que se pierde.** En las cinco corridas el linaje
  muestra lo mismo: entre la generación 5 y la 10 el campeón pasa de 9 piezas
  a 3 o 5, descartando segmentos de cola, antes de que crezca nada nuevo. En
  tierra la cola ondulante del pez no empuja; solo pesa.
- **Dos caminos.** Semillas 2 y 3: cuerpo grande con extremidades
  articuladas. Semillas 1, 4 y 5: cuerpo chico (3 a 5 piezas) que se balancea
  con una o ninguna aleta, como los caminantes de la Etapa 3. Partir del pez
  no garantiza extremidades, pero las hace alcanzables: en la Etapa 3, desde
  cuerpos al azar, nunca aparecieron.
- **Mejor que desde cero.** Los cinco campeones (4.0 a 6.8 m) igualan o
  superan a los cinco de la Etapa 3 partidos de cuerpos al azar (3.1 a 4.7 m).
  Un ancestro con simetría bilateral y partes repetidas es un mejor punto de
  partida que el azar, aunque sea un pez en el suelo.
- **Convergencia.** Semillas 2 y 4 convergen al afinar el paso; 1, 3 y 5
  bajan a 1/1920 s (3.8, 3.1 y 2.3 m): son caminantes con saltos, que la
  aptitud robusta (mínimo entre 1/480 y 1/960) acota pero no elimina (0010).
  Lo que se afirma es la jerarquía, no el segundo decimal.

**Consecuencias.** El linaje queda en el visor (`Etapa 4 · linaje`), con el
mejor de las generaciones 1, 10, 20, 30, 40, 50 y 60 de cada semilla en
carriles, y la carrera «pez en tierra» junto a los campeones de la Etapa 3.
Los archivos del visor crecieron (linaje 6.5 MB); si molesta en Pages, se
bajan a cinco generaciones por linaje.

---

## 0016 · 2026-10-05 · Cierre de la Etapa 4: el pez que sigue la luz

**Corrida.** Ancestro pez sembrado en la tarea de luz (tres ensayos de 6 s,
luz a 4 m en 90°, 210° y 330°), cinco semillas, 200 × 50. Aptitud en m/s de
acercamiento; "8 direcciones" es una prueba posterior con la luz cada 45°,
incluida una posición que no se usó en la evolución y otra justo detrás.

| corrida | aptitud (m/s) | a medio paso | 8 direcciones: mín · media · máx | piezas | dof | entradas de fotosensor |
|---|---|---|---|---|---|---|
| pez-luz01 | 0.206 | 0.207 | 0.12 · 0.18 · 0.24 | 10 | 14 | 3 |
| pez-luz02 | 0.204 | 0.218 | 0.02 · 0.15 · 0.30 | 8 | 12 | 2 |
| pez-luz03 | 0.127 | 0.127 | −0.01 · 0.10 · 0.14 | 10 | 18 | 7 |
| pez-luz04 | 0.110 | 0.110 | 0.01 · 0.10 · 0.17 | 8 | 8 | 1 |
| pez-luz05 | 0.123 | 0.138 | 0.04 · 0.11 · 0.17 | 9 | 16 | 4 |

**Qué se vio.**
- **Fototaxis real, no suerte.** Las cinco campeonas se acercan a la luz desde
  las ocho direcciones (solo `pez-luz03` queda en cero en una). El ancestro
  daba exactamente 0 (nadaba recto, sin saber dónde estaba la luz). Las dos
  mejores llegan a 0.2 m/s de media, 1.2 m de acercamiento en 6 s.
- **El mecanismo es modulación de amplitud, no un timón.** En `pez-luz01`
  el fotosensor entra en la amplitud del oscilador de la cabeza:
  `n0 = oscillate-wave(l0 × −1.31, 1.6 Hz, 0)`. La criatura coletea más o
  menos fuerte según de qué lado le llega la luz, y la trayectoria se curva
  hacia ella. Es la estrategia de los organismos sin sistema nervioso
  direccional (klinoquinesis), y es lo que la evolución encontró primero en
  las cinco semillas: entre 1 y 7 entradas de fotosensor, casi siempre en la
  amplitud o la fase de un oscilador.
- **Cuerpos.** De 8 a 10 piezas: menos cola que el ancestro (9), y en varias
  el par reflejado de aletas crece o se duplica. Ninguna llegó al tope de
  piezas; la tarea premia girar, no masa.
- **Convergencia.** Las cinco cambian menos de 12 % a medio paso.
- **Costo.** 35 a 58 s por generación de 200 (tres ensayos más la
  verificación a medio paso): 2 h 50 min las cinco semillas. Es la tarea más
  cara del proyecto; la verificación incondicional (0013) duplica el costo y
  no se negocia.

**Decisión.** La Etapa 4 cierra con dos experimentos desde el mismo ancestro
pez: en tierra (0015) y con luz. Queda para la Etapa 5 la competencia por un
cubo entre dos especies, que en Sims es el paso siguiente. Dos cosas quedan
anotadas: el seguimiento de luz en tierra (no corrido, por costo) y reducir
`linaje.json` si Pages tarda en cargarlo.

---

## 0017 · 2026-10-05 · Etapa 5: competencia por el cubo, decisiones

**Contexto.** Último paso de la hoja de ruta: la competencia de *Evolving 3D
Morphology and Behavior by Competition* (Sims, Artificial Life IV, 1994). Dos
especies coevolucionan; cada enfrentamiento pone a dos criaturas en el mismo
mundo, con un cubo entre ellas, y gana la que termina más cerca del cubo.

**Decisiones.**
- **Arena** (`src/arena.py`). Suelo con fricción, gravedad, cubo de 0.25 m y
  1 kg con articulación libre (se puede empujar) en el origen; la criatura A a
  1.5 m en +X y la B a 1.5 m en −X, girada 180°, de modo que la cara −X de la
  cabeza (la de los ojos) apunta al cubo. Las dos se asientan sin torques en
  la misma simulación; si en 2 s no están quietas se arranca igual, porque
  con dos cuerpos grandes el criterio de quietud conjunta castigaría al rival.
  Después, 10 s de enfrentamiento con contactos reales entre todo: criaturas,
  cubo y suelo.
- **Aptitud.** `(d_rival − d_propia) / (d_rival + d_propia)`, con las
  distancias horizontales del centro de masa de cada una al centro del cubo al
  final, más 0.5 si la criatura tocó el cubo en algún momento. Va de −1 a +1
  más el bono; dos quietas empatan en 0; una quieta contra una que se acerca
  queda en negativo. Robusta: el mínimo entre dos pasos de integración (1/480
  y 1/720 s), como en caminata (0010).
- **Emparejamiento "todos contra el mejor".** Cada individuo de A se enfrenta
  al campeón de B de la generación anterior, y cada individuo de B al campeón
  de A. Es el esquema que Sims eligió por costo; "todos contra todos" serían
  10 000 enfrentamientos por generación. Los campeones iniciales son el
  ancestro. Cada generación se registra además el duelo de cabeza, campeón
  contra campeón.
- **Punto de partida.** Las dos especies parten del ancestro pez (0014), con
  flujos aleatorios distintos (semilla·1000+1 y +2), para que diverjan por la
  competencia y no por el origen. Se descartó sembrarlas con los campeones del
  pez en tierra: ya caminan, pero en una dirección arbitraria (el campeón de
  `pez-cam02` se aleja del cubo a 8.4 m en 10 s), y la pregunta de la etapa es
  qué inventa la competencia, no qué heredan.
- **Presupuesto.** 100 por especie, 50 generaciones, cinco semillas; un
  enfrentamiento robusto tarda 1 s, unos 15 s por generación, 12 minutos por
  semilla. Se guardan las poblaciones de ambas especies por generación, y para
  el visor los duelos entre campeones de las generaciones 1, 10, 25 y 50.
- **Visor.** Vista "duelo por el cubo": las dos criaturas (A celeste, B naranja)
  y el cubo amarillo en la misma escena, animado con la trayectoria; curva de
  la especie del campeón mostrado. Las aptitudes de coevolución no son
  comparables entre generaciones (el rival cambia), y la bitácora de
  resultados tendrá que leer las curvas con esa cautela.

**Trampas esperadas, no corregibles.** Sims describió criaturas que bloquean
al rival, lo apartan del cubo o se apoyan en él. En esta tarea todo eso es
parte del juego y se documenta como estrategia; solo se corrigen artefactos
físicos, con la verificación a medio paso de siempre.

---

## 0018 · 2026-10-05 · Cierre de la Etapa 5: la carrera armamentista por el cubo

**Corrida.** Cinco semillas, dos especies de 100 desde el ancestro pez, 50
generaciones, "todos contra el mejor". La tabla muestra el duelo de cabeza
(campeón A contra campeón B) en generaciones elegidas, como aptitud A/B y
distancias finales al cubo; "tocan" es cuántos de los 100 de cada especie
tocaron el cubo en la última generación.

| corrida | gen 1 | gen 10 | gen 25 | gen 50 | tocan A/B | piezas A/B | cubo movido |
|---|---|---|---|---|---|---|---|
| duelo01 | −0.20/+0.20 (1.70/1.12 m) | +0.32/+0.68 (0.71/0.49) | +0.77/+0.23 (0.26/0.45) | +0.23/+0.27 (0.32/0.50) | 72/77 | 12/6 | 0.12 m |
| duelo02 | 0.00/0.00 (1.26/1.26) | +0.59/+0.41 (0.40/0.48) | +0.16/+0.84 (0.68/0.33) | +0.46/+0.54 (0.67/0.62) | 26/51 | 13/10 | 0.09 m |
| duelo03 | −0.17/+0.17 (1.37/0.98) | +0.47/+0.53 (0.45/0.42) | +0.46/+0.54 (0.42/0.39) | +0.53/+0.47 (0.38/0.40) | 61/70 | 4/7 | 0.12 m |
| duelo04 | +0.08/−0.08 (1.03/1.21) | −0.49/+0.99 (1.09/0.38) | +0.66/+0.34 (0.34/0.46) | −0.31/+0.81 (0.75/0.40) | 16/60 | 13/12 | 0.58 m |
| duelo05 | −0.24/+0.74 (0.86/0.53) | +0.62/+0.38 (0.39/0.50) | +0.68/+0.32 (0.40/0.58) | +0.60/+0.40 (0.38/0.47) | 61/69 | 6/10 | 0.06 m |

**Qué se vio.**
- **Llegar al cubo se aprende rápido.** En la generación 1 ninguna de las
  diez campeonas lo toca (la más cercana queda a 0.53 m); en la 10, en las
  cinco semillas ambas campeonas lo tocan y más de la mitad de cada población
  también. El pez, que en tierra avanzaba a los tumbos, en diez generaciones
  recorre 1.5 m en la dirección correcta, porque ahora la aptitud tiene
  dirección (el cubo) y rival.
- **Ventaja que va y viene.** En `duelo01` el duelo de cabeza pasa de
  −0.20 a +0.25, +0.68 y +0.23; en `duelo04`, de +0.08 a −0.49, +0.66 y −0.31.
  Es la dinámica de la Reina Roja que Sims describe: cada especie se adapta
  al campeón del rival y el rival responde. Por eso las curvas de aptitud de
  esta etapa no son comparables entre generaciones: un 0.5 en la generación
  40 es contra un rival mucho mejor que el de la 10.
- **Dos tamaños de respuesta.** En tres semillas una especie creció (12 o 13
  piezas) y la otra se quedó chica (6, 7, 4); en `duelo04` las dos crecieron.
  Las grandes cubren el cubo con el cuerpo; las chicas llegan antes. Ninguna
  estrategia gana siempre: en la generación 50 la especie chica gana en
  `duelo01` y `duelo02`, la grande en `duelo05`.
- **El cubo se empuja poco.** Salvo en `duelo04` (0.58 m), el cubo termina a
  menos de 0.12 m de donde estaba. Las campeonas no lo arrastran lejos del
  rival: se quedan sobre él. Las estrategias de bloqueo que Sims describió
  aparecen como "cuerpo grande sobre el cubo", no como empujones.
- **Costo.** 26 a 31 minutos por semilla (1538 a 1882 s); 2 h 20 min el lote.

**Decisión.** La Etapa 5 cierra la hoja de ruta de Sims. Quedan anotadas dos
extensiones no hechas: el mundo compartido con recursos (varias criaturas y
varios cubos a la vez) y "todos contra varios" (contra los tres mejores del
rival, que Sims recomienda para reducir el ruido de un solo campeón).

---

## 0019 · 2026-10-05 · Optimización en CPU: dónde estaba el tiempo

**Contexto.** Antes de armar un ecosistema con decenas de criaturas en un
mismo mundo, medir. El perfil de una evaluación de nado de 0.20 s (cuerpo de
5 piezas, 9 grados de libertad, 5 neuronas) dio: cerebro en Python puro
0.14 s, arrastre por cara 0.07 s (24 000 llamadas a `mj_objectVelocity`),
física de MuJoCo 0.02 s. **El motor era el 10 % del tiempo.**

**Cambios.**
- **Cerebro compilado** (`src/brain_rapido.py`): el grafo se convierte en
  arreglos y el paso se compila con Numba. Mismas funciones, mismo recorte,
  mismos casos límite: los cinco campeones de prueba dan la misma aptitud con
  seis decimales. `brain.crear` elige el compilado si Numba carga;
  `CRIATURAS_CEREBRO=lento` fuerza el intérprete para comparar.
- **Arrastre compilado**: la velocidad de todos los cuerpos sale de `cvel`
  con la fórmula v = v_c + w × (x − c) (verificada contra MuJoCo con error
  cero) y el núcleo es una función Numba. `np.cross` sobre arreglos chicos
  costaba más que la física entera.
- **Caché de aptitud** en `evolve_morfo.py`: los sobrevivientes (un quinto de
  cada generación) y las crías idénticas no se reevalúan; la física es
  determinista.
- Numba: 0.68 queda bloqueado por el control de aplicaciones de Windows, como
  MuJoCo 3.4; 0.61.2 pasa. Fijado en `requirements.txt`.

| evaluación | antes | después |
|---|---|---|
| nado, 5 piezas | 0.21 s | 0.07 s |
| nado, 3 placas | 0.21 s | 0.07 s |
| caminata, 11 piezas | 0.15 s | 0.12 s |
| luz, 3 ensayos | 0.70 s | 0.30 s |

**Qué queda.** En nado, el piso es el bucle de Python que llama a `mj_step`
4800 veces, unos 0.05 s; en caminata manda el solver de contactos, que no
depende de nosotros. Más allá de esto, solo la GPU con cuerpos fijos (0010).

**Lección.** Tres veces en el proyecto el tiempo estuvo donde no se miraba:
en el fluido (0004), en el cerebro interpretado y en una función de NumPy
pensada para arreglos grandes. Perfilar antes de optimizar, y verificar bit a
bit después, porque una optimización que cambia el resultado es otra trampa.

---

## 0020 · 2026-10-05 · Bestiario: seis especies a mano y el teorema de la vieira

**Contexto.** Para poblar un ecosistema sin esperar a la evolución, el
usuario pidió partir de criaturas conocidas. Se buscó un bestiario publicado:
Framsticks tiene genotipos compartidos (varillas y muelles, otro formato),
dm_control trae un pez y nadadores en MJCF sin cerebro, Evolution Gym tiene
robots de vóxeles en 2D. Nada en el formato de Sims. Se escribió el propio
(`src/genome/bestiario.py`), con cerebro verificado y fototaxis cableada.

**Fototaxis cableada.** Lo que la Etapa 4 enseñó se escribe a mano: en cada
nodo con cadena de retardo, la suma que recibe la oscilación de la madre suma
además la componente lateral de la dirección a la luz (entrada "l" 1) con un
peso `sesgo`. El cuerpo se curva hacia la luz mientras ondula. El signo
depende de cómo está orientado el nodo: el remador tiene la cola en la cara
−X y necesita el signo contrario. Para remos y placas se probó una
modulación diferencial de amplitud (el lado de la luz rema distinto).

| especie | piezas | nado 10 s | acercamiento a la luz (m/s) | mecanismo |
|---|---|---|---|---|
| anguila | 7 | 2.99 m | +0.097 | onda viajera, 6 segmentos |
| pez | 9 | 0.73 m | +0.017 | onda + caudal + pectorales |
| renacuajo | 6 | 0.44 m | +0.003 | onda, cabeza pesada |
| raya | 13 | 0.72 m | −0.003 | onda del cuerpo; las placas no empujan |
| ciempiés acuático | 13 | 0.15 m | +0.004 | patas universales con plumeo en cuadratura |
| remador | 5 | 0.20 m | +0.024 | aletas universales en cuadratura |

**El teorema de la vieira decide qué animales son posibles.** El agua del
proyecto es de arrastre lineal (régimen de Stokes, 0004). Ahí, un movimiento
que es igual de ida que de vuelta no desplaza nada, por rápido que sea el
golpe: es el teorema de la vieira de Purcell. Se vio tres veces en el
bestiario: el ciempiés con patas de una bisagra nadaba 0.04 m (reman igual
hacia adelante y hacia atrás); con articulación universal y plumeo en
cuadratura, que es romper la simetría temporal, sube a 0.15 m. Las placas de
la raya, de una bisagra, no empujan ni giran por más que se modulen: su
avance es todo de la onda del cuerpo. Una medusa o un calamar de cajas no
funcionarían aquí. Avanza lo que rompe la simetría en el tiempo: ondas
viajeras, remos con desfase y plumeo, aletas que giran mientras baten. Eso
explica, retrospectivamente, por qué la evolución encontró siempre ondas y
retardos y nunca remos.

**Consecuencias.** Dos especies entran al ecosistema sin saber girar hacia
la comida (raya) o apenas (ciempiés): son el control. La raya, además, es la
más pesada. Lo que les pase es resultado, no defecto. `REC_MAX` quedó en 6
(la anguila pedía 8; se acortó a 6 segmentos).

---

## 0021 · 2026-10-05 · Etapa 6: el acuario, reglas de vida y primer resultado

**Contexto.** El usuario propuso partir de varias criaturas conocidas
conviviendo y dejar que evolucione. Es un cambio de paradigma: no hay
generaciones ni una aptitud definida por nosotros. Hay energía, comida,
reproducción y muerte, y lo que "gana" emerge (`src/ecosistema.py`).

**Reglas de vida** (todas son decisiones nuestras sobre qué vida es posible):
- Acuario de agua sin gravedad con 8 luces-comida dentro de un radio de 5 m.
  Tocar una luz (centro de masa a menos de 0.35 m) da 60 de energía y la luz
  reaparece en otro lugar al azar. Cada criatura percibe la luz más cercana.
- Energía inicial 100. Costo por existir 0.03 por segundo y por kg, y por
  moverse 0.004 por segundo y por N·m de torque aplicado: ser grande y
  agitarse cuesta.
- Con energía ≥ 160 se reproduce: una hija con 1 o 2 mutaciones nace a 1.2 m,
  con 60 de energía que la madre cede. Si la cría no desarrolla un cuerpo
  válido, no nace y la madre no gasta. Tope de 36 individuos.
- Muerte a energía 0, a los 400 s de edad, o al alejarse más de 15 m.
- **Épocas.** MuJoCo no agrega ni quita cuerpos en medio de una simulación: el
  mundo se recompila cada 20 s. Nacimientos y muertes se aplican entre
  épocas; cada sobreviviente conserva posición, orientación, ángulos
  articulares y energía; el estado interno del cerebro se reinicia. Una
  limitación técnica convertida en regla del mundo.
- Costo de cómputo: 13 a 17 s por época de 20 s con 24 a 36 criaturas, o sea
  más rápido que el tiempo real. Sin el cerebro compilado (0019) habría sido
  diez veces más lento.

**Primer acuario (`eco01`)**: seis especies del bestiario, cuatro de cada
una, 30 épocas = 10 minutos de vida.

| época | t (s) | anguila | pez | renacuajo | raya | ciempiés | remador | total |
|---|---|---|---|---|---|---|---|---|
| 1 | 20 | 4 | 4 | 4 | 4 | 4 | 4 | 24 |
| 7 | 140 | 4 | 4 | 4 | 4 | 1 | 6 | 23 |
| 10 | 200 | 4 | 4 | 4 | 0 | 1 | 8 | 21 |
| 13 | 260 | 7 | 1 | 4 | 0 | 0 | 10 | 22 |
| 20 | 400 | 25 | 0 | 4 | 0 | 0 | 7 | 36 |
| 25 | 500 | 35 | 0 | 0 | 0 | 0 | 1 | 36 |
| 30 | 600 | 36 | 0 | 0 | 0 | 0 | 0 | 36 |

**Qué se vio.**
- **Primero mueren las que no saben girar.** El ciempiés (gira apenas) y la
  raya (no gira, y es la más pesada) se extinguen antes de los 200 s sin haber
  comido: gastan energía por masa y por torque y no encuentran comida. Las dos
  entraron como control, y el control se cumplió.
- **Después pierde la que no es rentable.** El pez cae a uno a los 260 s y a
  cero a los 400: nada cinco veces más lento que la anguila con una masa
  parecida. El renacuajo, de cabeza pesada, resiste sin reproducirse hasta
  los 500 s.
- **El remador tiene su momento.** Es el que más se reproduce al principio
  (10 individuos a los 260 s): liviano y barato, aunque lento. Cuando la
  anguila llena el acuario y la comida escasea, desaparece.
- **Monocultivo en 25 épocas.** La anguila, la más rápida y la que mejor
  gira, llega al tope de 36 individuos y es la única especie a los 500 s. Sus
  descendientes ya mutan: el promedio de piezas bajó de 7 a 5.8, y hay
  anguilas de 2 piezas que no comen y van a morir. La mutación no para porque
  las anguilas de 7 segmentos sigan ganando.
- **Un acuario con tope y comida constante no sostiene diversidad.** Es el
  resultado esperable de la exclusión competitiva: un solo recurso, un solo
  ganador. Para sostener varias especies harían falta nichos distintos
  (comida de varios tipos o tamaños, zonas) o depredación.

**Decisión.** La Etapa 6 queda abierta como laboratorio, no cerrada: las
reglas de vida son parámetros y cada ajuste cambia qué vida es posible. Lo
que sigue, si se sigue: un segundo acuario con comida de dos tipos (una que
solo pueden comer los cuerpos chicos, otra los grandes) para ver si aparece
coexistencia; y más tiempo, para ver si del monocultivo de anguilas sale
algo nuevo.

---

## 0022 · 2026-10-05 · Mundo 2D viscoso sin inercia: la física que escala

**Contexto.** Para un ecosistema de cientos de criaturas y horas de vida, la
física 3D con contactos de MuJoCo es el cuello de botella (0021: 1.3 veces el
tiempo real con 36 criaturas). El usuario pidió "escala más grande pero 2D".

**Modelo** (`src/mundo2d.py`). Árboles de segmentos rígidos en el plano,
unidos por bisagras, en agua de arrastre lineal **sin inercia**: en el régimen
de Stokes las fuerzas se equilibran en cada instante, R(q)·q̇ = τ, con R la
matriz de resistencia generalizada (suma de jacobianos por arrastre de cada
segmento) y τ los torques musculares menos la amortiguación. Es la teoría de
la fuerza resistiva de Gray y Hancock (1955) para cuerpos articulados, con el
mismo coeficiente de arrastre por área que el fluido 3D (0004). Numba,
criatura por criatura con su número real de segmentos, con un solver
gaussiano propio porque el de Numba exige SciPy.

**Tres artefactos cerrados antes de confiar en él.**
1. Recortar los ángulos al tope después de resolver rompía la reciprocidad:
   la cadena de dos eslabones, que no puede nadar (teorema de la vieira),
   avanzaba 2.1 m en 10 s. Ahora el tope es un resorte rígido implícito y,
   sobre todo, el músculo tiene relación fuerza-longitud: el torque hacia el
   tope se apaga con 1 − (θ/lím)², así la articulación no lo golpea.
2. Euler explícito en articulaciones rápidas daba error de primer orden: la
   distancia cambiaba 10 % por cada duplicación del paso. Integración de
   punto medio (dos resoluciones por paso): ahora cambia 2 % entre 1/60 y
   1/240 s. Con el paso de 1/60 s, ocho veces mayor que en 3D.
3. El cerebro tiene reloj propio: 1/960 s, como en 3D, 16 pasos por paso de
   física. Con el reloj del cerebro ligado al de la física, las neuronas de
   retardo (`smooth`) cambiaban de comportamiento y la anguila nadaba 0.05 m.

**Verificación contra la física 3D** (bestiario, 10 s, nado libre):

| especie | 3D (MuJoCo) | 2D | luz 3D | luz 2D |
|---|---|---|---|---|
| anguila | 2.99 m | 2.97 m | +0.097 | +0.067 |
| pez | 0.73 m | 0.86 m | +0.017 | +0.010 |
| renacuajo | 0.44 m | 1.14 m | +0.003 | +0.025 |
| raya | 0.72 m | 0.21 m | −0.003 | −0.001 |
| ciempiés | 0.15 m | 0.17 m | +0.004 | +0.001 |
| remador | 0.20 m | 0.25 m | +0.024 | 0.000 |

Las jerarquías coinciden; las placas de la raya pierden en 2D el empuje
vertical que tenían en 3D, y el remador pierde la cuadratura de sus aletas
(en 2D una aleta universal es una bisagra). Pruebas de principio: dos
eslabones 0.007 m, cinco en fase 0.027 m (ambos "cero" de Purcell), tres
eslabones en cuadratura 0.84 m (el nadador de Purcell nada).

**Costo.** 500 cadenas de 5 segmentos: 14 veces el tiempo real; de 16
segmentos: 2.6 veces. Las seis especies del bestiario, 10 s, en 0.2 s.

**Consecuencias.** Todo lo demás se reutiliza: genoma (proyectado al plano
por `develop2d.py`: bisagras, caras ±X ±Y, reflexión respecto del eje X),
cerebro (en lote, `brain_lote.py`), fototaxis, reglas de vida, bitácora. Lo
que se pierde: choques entre criaturas y toda la tercera dimensión.

---

## 0023 · 2026-10-05 · Etapa 7: el acuario 2D a escala, reglas y primera corrida

**Contexto.** Con la física 2D (0022), el ecosistema de la Etapa 6 se
reescribe a escala (`src/ecosistema2d.py`): cientos de criaturas, un mundo
de 50 × 50 m toroidal, y comida de dos tamaños, que es la hipótesis de
coexistencia que quedó abierta en 0021: si hay dos recursos que exigen
cuerpos distintos, ¿sobreviven dos tipos de cuerpo?

**Reglas** (cada una es una decisión sobre qué vida es posible; el visor las
muestra al pie):
- Comida chica (90 puntos, vale 40) solo para cuerpos de largo total ≤ 1.3 m;
  comida grande (30 puntos, vale 150) solo para cuerpos de masa ≥ 2 kg. Cada
  criatura percibe la comida comestible más cercana; al comer, la comida
  reaparece en otro lugar.
- Energía inicial 100; cuesta 0.03 por kg y segundo existir y 0.004 por N·m y
  segundo moverse. Reproducción con energía ≥ 160: una hija con 1 o 2
  mutaciones a 1.5 m, con 60 de energía que la madre cede. Muerte a energía 0
  o a los 400 s. Tope de 500 individuos.
- Épocas de 20 s (nacimientos y muertes entre épocas, pose y ángulos
  conservados, cerebro reiniciado). Paso de física 1/60 s; reloj del cerebro
  1/960 s.
- Sin choques: las criaturas se atraviesan. Lo que en 3D era bloqueo aquí no
  existe.

**Costo.** 6 a 8 s de cómputo por época de 20 s con 500 criaturas: 2.5 a 3
veces el tiempo real con la población al tope, y 50 veces con pocas.

**Primera corrida (`eco2d01`)**: seis especies, 40 de cada una, 90 épocas =
30 minutos de vida, 12.5 minutos de cómputo.

| época | t (s) | anguila | pez | renacuajo | raya | ciempiés | remador | total | comida chica | grande |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 20 | 50 | 41 | 42 | 40 | 42 | 41 | 256 | 0 | 17 |
| 5 | 100 | 134 | 46 | 49 | 25 | 49 | 44 | 347 | 3 | 26 |
| 10 | 200 | 303 | 45 | 53 | 1 | 45 | 46 | 493 | 1 | 34 |
| 20 | 400 | 430 | 9 | 55 | 0 | 1 | 5 | 500 | 4 | 40 |
| 30 | 600 | 498 | 0 | 2 | 0 | 0 | 0 | 500 | 5 | 36 |
| 60 | 1200 | 500 | 0 | 0 | 0 | 0 | 0 | 500 | 9 | 41 |
| 90 | 1800 | 500 | 0 | 0 | 0 | 0 | 0 | 500 | 19 | 35 |

**Qué se vio.**
- **El mismo monocultivo que en 3D, más rápido.** La anguila, la más rápida
  y la que mejor gira, llena el tope de 500 a los 200 s y es la única especie
  a los 600 s. Con 240 fundadoras y comida abundante, la exclusión competitiva
  tarda diez minutos.
- **La comida chica quedó casi sin comer durante media hora**: 0 a 9 por
  época. Ninguna fundadora cabía bien en ese nicho (la anguila mide 1.75 m;
  el renacuajo, que sí cabe, nada despacio y come también la grande).
- **Y después la anguila se diversifica.** Entre los 1200 y los 1800 s, el
  consumo de comida chica sube de 9 a 23 por época. Al final hay 50 anguilas
  de 2 segmentos y 18 de 3, cuerpos de menos de un metro que solo pueden
  comer la chica, junto a 301 de 7 segmentos, 63 de 13 y 4 de 14, que solo
  comen la grande. Dos nichos, dos cuerpos, un solo linaje: radiación
  adaptativa dentro de la especie que ganó. Es el resultado que la hipótesis
  de 0021 buscaba, pero no por coexistencia de especies fundadoras sino por
  divergencia posterior.
- **El tope de población es el regulador.** Desde la época 10 nacen y mueren
  unos 30 por época: la población está saturada y la selección opera por
  reemplazo, no por crecimiento.
- **Lo que no se puede decir todavía:** si los cuerpos cortos y largos de
  anguila son estables (dos poblaciones que se mantienen) o transitorios.
  Hace falta más tiempo y más semillas; cada media hora de vida cuesta 12
  minutos.

**Decisión.** El acuario 2D es el laboratorio de aquí en adelante: mismo
genoma, mismas reglas, cincuenta veces más barato. Siguiente paso: varias
semillas, dos horas de vida, y la sopa primitiva (partir de cajas sueltas,
sin bestiario), que ahora es viable. El archivo del visor se recorta a tres
épocas grabadas (6.8 MB); las 34 MB completas quedan en `runs/`.


---

## 0024 · 2026-10-05 · Sopa primitiva: de cajas sueltas a nadadores

**Contexto.** El usuario propuso partir de lo mínimo: no del bestiario ni de
cuerpos al azar, sino de cajas sueltas que no pueden moverse, y dejar que la
mutación invente articulaciones, cerebros y movimiento. En el mundo 2D es
viable; en 3D no lo era. La física tiene una predicción (0020, teorema de la
vieira): una caja no nada, dos eslabones tampoco, el primer nadador necesita
tres piezas y desfase, como el nadador de Purcell.

**Reglas de la sopa** (`ecosistema2d.py --sopa N`):
- 300 cajas de 0.12 a 0.30 m de largo, sin articulaciones ni neuronas,
  repartidas al azar en el mundo de 50 m. El desarrollo acepta cuerpos de una
  pieza (`permitir_uno`); las articulaciones rígidas del genoma ahora son
  rígidas de verdad en 2D (tope en 0 y sin músculo), que antes eran bisagras.
- **Agitación browniana** de 0.25 m/√s: cada caja deriva 1.4 m por época de
  20 s sin hacer nada. Sin agitación nadie comería nunca y no habría de qué
  seleccionar.
- Comida chica escasa (60 puntos, vale 40) que reaparece cerca de donde
  estaba (manchas, 80 %): premia quedarse donde hay y, después, llegar antes.
  Comida grande (vale 150) solo para masa ≥ 2 kg: un premio que exige cuerpo.
- Energía inicial 100, reproducción a 160 (hay que comer dos veces), hija
  con 60 y 1 o 2 mutaciones; edad máxima 900 s. Una caja de 0.2 × 0.1 m gasta
  0.014 por segundo en existir: muere de vieja, no de hambre.
- **Nadador confirmado:** una criatura que en una época se desplaza más que
  la media de las cajas sueltas más tres desviaciones, y que vuelta a simular
  sola, sin agitación, avanza más de 1 m en 20 s. Sin la segunda prueba, la
  deriva browniana disfrazaba de nadadores a cuerpos que no nadan.

**Corrida de humo (12 épocas, 300 cajas):** la población crece de 300 a 413
solo por comer a la deriva; a los 240 s hay 69 cuerpos de 2 o 3 segmentos
y uno de 13, nacidos de mutación, y ninguno se desplaza más que las cajas.
La primera candidata (3 segmentos, época 11) no pasó la prueba en solitario.

**Corrida larga (`sopa01`)**: 300 cajas, 300 épocas = 100 minutos de vida,
24 minutos de cómputo. Columnas: cuántos individuos hay con cada número de
segmentos, y cuánto se desplaza por época cada tamaño (la deriva de una caja
sola es 1.4 m).

| t (s) | población | 1 seg. | 2 | 3 | 4 | 5+ | desplaz. 1 seg. | desplaz. 2–3 | máx. |
|---|---|---|---|---|---|---|---|---|---|
| 20 | 302 | 300 | 0 | 1 | 0 | 1 | 1.42 | – | – |
| 500 | 500 | 363 | 71 | 51 | 11 | 4 | 1.45 | 1.3 | 1.9 (9 seg.) |
| 1000 | 474 | 98 | 176 | 136 | 35 | 29 | 1.48 | 1.4 | 2.1 (9 seg.) |
| 2000 | 500 | 37 | 182 | 181 | 48 | 52 | 1.34 | 1.5 | 1.7 |
| 4000 | 500 | 31 | 170 | 159 | 59 | 81 | 1.15 | 1.4 | 3.2 (12 seg.) |
| 6000 | 500 | 18 | 170 | 192 | 40 | 80 | 1.51 | 1.45 | 2.5 (9 seg.) |

**Qué se vio.**
- **Complejidad sin función.** En 100 minutos las cajas sueltas pasaron de
  300 a 18 y la sopa se llenó de cuerpos de 2 a 6 segmentos, con algunos de
  13 y 14. Pero ningún tamaño se desplaza más que la deriva: todos entre 1.1
  y 1.6 m por época, igual que una caja sola. Hubo candidatos (hasta 3.2 m)
  y ninguno pasó la prueba en solitario. **No apareció el nadador.**
- **Por qué crece la complejidad sin que sirva.** La mutación desde un genoma
  de un nodo tiene una probabilidad por elemento de 1/4: agrega nodos y
  conexiones con mucha frecuencia, y nada lo castiga, porque comer no
  depende de moverse. Es deriva mutacional hacia lo complejo, no selección.
  La vieja regla de este proyecto en su forma más cruda: la población
  responde a lo que la aptitud mide, y aquí la aptitud era quedarse quieto
  cerca de una mancha de comida. Las que comían, se reproducían; moverse
  costaba energía y no ganaba nada.
- **Pocas tiradas.** Unos 9 nacimientos por época: 2700 crías en toda la
  corrida, cada una con 1 o 2 mutaciones. Para que una cría tenga tres
  segmentos, un oscilador en el cerebro conectado a dos articulaciones y un
  desfase entre ellas, hacen falta varias mutaciones coordinadas; 2700
  intentos en los que además el movimiento no se premia son pocos.
- **Lo que sí emergió:** cuerpos pesados (≥ 2 kg) que comen la comida
  grande, de 1 a 23 por época desde los 1000 s. Ser grande sí pagaba.

**Decisión.** La sopa como está no produce locomoción, y eso es un
resultado: la deriva browniana alimenta lo suficiente como para que moverse
no valga la pena. La versión siguiente tiene que hacer que la deriva no
alcance: menos agitación o comida más lejana, de modo que solo coma quien
llega. Queda anotada, y queda anotado también que el experimento necesita
diez veces más nacimientos (población más grande o más tiempo) para que
aparezcan las tres mutaciones del nadador de Purcell. La partida "sopa" del
acuario en vivo (`vivo.html`) permite probar esas reglas a mano.


---

## 0025 · 2026-10-05 · Tres semillas, dos horas: la radiación es estable

**Corrida.** Tres semillas del acuario 2D (`eco2d02`, `03`, `04`), seis
especies × 40, 360 épocas = 2 horas de vida cada una, en paralelo, 50 a 53
minutos de cómputo por semilla. La pregunta de 0023: ¿los cuerpos cortos que
aparecieron dentro de la anguila son estables o transitorios?

| | eco2d02 | eco2d03 | eco2d04 |
|---|---|---|---|
| monocultivo de anguila desde | 900 s | 840 s | 620 s |
| comida chica por época a los 1200 s | 51 | 8 | 1 |
| a los 3000 s | 112 | 102 | 42 |
| a los 7200 s | 171 | 107 | 147 |
| comida grande por época (constante) | 57–79 | 47–86 | 41–66 |
| anguilas de 2–3 segmentos al final | 39 | 33 | 44 |
| de 7 segmentos | 312 | 430 | 356 |
| de 13–14 | 11 | 16 | 11 |

**Qué se vio.**
- **Monocultivo en las tres, antes del cuarto de hora.** Igual que en 3D
  (0021) y en la primera corrida 2D (0023). Con esta comida y estas reglas,
  la exclusión competitiva no depende de la semilla.
- **La radiación se repite y se sostiene.** En las tres semillas, entre los
  1200 y los 3000 s aparecen anguilas de 2 segmentos, de menos de un metro,
  y el consumo de comida chica pasa de casi nada a 100–170 por época, más
  que la grande. Y se queda ahí durante la última hora: al final hay 33 a 44
  cuerpos cortos conviviendo con 310 a 430 de 7 segmentos y 11 a 16 de 13.
  No es transitorio: es un polimorfismo mantenido por dos recursos.
- **Proporciones estables, y una pregunta.** Los cortos son el 7–9 % de la
  población en las tres semillas, aunque comen más de la mitad de toda la
  comida. Cada corto come mucho pero son pocos; probablemente porque un
  cuerpo de 2 segmentos nada peor (dos eslabones no nadan, 0022: viven de la
  deriva y de estar donde reaparece la comida) y porque sus crías mutan
  fácilmente de vuelta a 3 o más segmentos, con lo que salen del nicho. Es
  una hipótesis; medirla pediría seguir los linajes de los cortos.
- **El tope regula todo.** Las tres poblaciones viven saturadas en 500 desde
  los 200 s; la composición cambia por reemplazo.

**Decisión.** La hipótesis de 0021 queda respondida: dos recursos que exigen
cuerpos distintos sostienen dos cuerpos, pero no dos especies fundadoras,
sino dos formas de la que ganó. Para la bitácora del magíster, la lección es
que la diversidad que estas reglas producen es *dentro* de un linaje, y que
el visor, que colorea por especie fundadora, no la muestra: las 500 son
"anguila". Falta colorear por tamaño o por linaje. El visor 2D publicado
muestra ahora `eco2d02` (épocas 1, 181 y 360); los archivos completos
quedan en `runs/`.
