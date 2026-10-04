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
