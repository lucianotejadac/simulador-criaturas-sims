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

| generación | mejor | media |
|---|---|---|
| 1 | 3.6 | 0.9 |
| 10 | 5.5 | 2.9 |
| 25 | 6.0 | 3.3 |
| 50 | 6.45 | 4.25 |

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
- El mejor de la generación 1 ya nadaba 3.6 m: con tres bisagras y realimentación
  del ángulo, un reflejo saturado basta para avanzar. La evolución después afinó
  frecuencia y fase, no inventó el mecanismo.

**Pendiente para la Etapa 2.** Genoma morfológico de grafo dirigido con recursión
y desarrollo a MJCF; `fluido.py` ya acepta cualquier conjunto de cajas.
