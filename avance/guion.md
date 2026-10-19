# Guion — presentación de avance IPD438

Objetivo de tiempo: **14 min** (deja 1 min de holgura sobre 15). Las diapositivas son apoyo visual: lo que está aquí lo dices tú, no se lee de la pantalla.

| # | Diapositiva | Pauta | Tiempo | Acumulado |
|---|---|---|---|---|
| 1 | Portada | Promesa | 0:20 | 0:20 |
| 2 | Una pérdida dura hasta el próximo intra | Contenidos previos | 2:00 | 2:20 |
| 3 | El IDR es el frame más grande, y el más expuesto | Contenidos previos | 1:45 | 4:05 |
| 4 | Hoy, recuperarse exige lazo o pagar siempre | Estado del arte | 2:00 | 6:05 |
| 5 | FrameTrace [1] | Estado del arte, referencia | 1:30 | 7:35 |
| 6 | AGiLE [2] | Estado del arte, referencia | 1:45 | 9:20 |
| 7 | Anomalía | Problema y motivación | 1:45 | 11:05 |
| 8 | Objetivo | Objetivo | 1:30 | 12:35 |
| 9 | Reproducir Fig. 12 de AGiLE | Resultado a reproducir | 1:15 | 13:50 |
| 10 | Qué recordar | Promesa | 0:20 | 14:10 |

Si vas atrasado, recorta en la 4 (no expliques cada mecanismo, solo los ejes) y en la 6 (salta los números de BD-bitrate). Nunca recortes la 7.

---

## 1. Portada (0:20)

> "Mi tema es cómo recuperar el video después de una pérdida de paquetes **sin pedirle nada al codificador**. Les voy a mostrar que el mecanismo para hacerlo ya existe en la red, y que hoy se descarta."

Eso es la promesa: dila aquí y repítela al final.

## 2. Una pérdida dura hasta el próximo intra (2:00)

- Explica cómo leer la figura: arriba, el flujo a 30 fps con GoP 30, o sea, un intra por segundo; todo lo demás son P, que se codifican como diferencia con el frame anterior.
- Fila 1: se pierde un P a mitad de la GoP. Todo lo que viene depende de él, así que el daño dura **15 frames, medio segundo**, hasta el próximo intra.
- Fila 2: se pierde el I. Se pierde la GoP completa, **1 segundo**.
- Fila 3: se pierde el IDR. También 1 segundo, pero además **13 frames congelados**: el IDR reinicia la numeración de frames y, sin él, el decodificador se desordena (si preguntan: respaldo 2).
- "Esto no es un dibujo: lo medí." Codifiqué con x264 en perfil Baseline, una referencia, boté el frame del bitstream y decodifiqué con FFmpeg. El color es la caída de PSNR frame a frame.
- Transición: *"¿Y qué tan probable es perder justo el IDR?"*

## 3. El IDR es el frame más grande, y el más expuesto (1:45)

- H.264 entrega el video en **NAL units**. Cada una tiene un byte de cabecera que dice qué es: 1 = P, 5 = IDR, 6 = SEI, 7 y 8 = parámetros (SPS, PPS).
- En Annex B van una tras otra, separadas por start codes. Para mandarlas por RTP (RFC 6184), una NAL más grande que el MTU se parte en fragmentos FU-A.
- En este clip, el IDR pesa 55 kB, o sea **47 paquetes**; un P típico pesa 2. Basta perder uno de los 47 para que el IDR quede roto.
- Con 1 % de pérdida independiente: **38 %** de probabilidad de dañar el IDR contra **2 %** para un P. Uno de cada tres paquetes del clip es de un IDR. "La pérdida más cara es también la más probable."
- Señala el SEI: "es información dentro del stream que el decodificador puede ignorar. Guárdenlo, porque es donde AGiLE esconde lo que me interesa."
- Transición: *"Entonces, ¿cómo se recupera uno hoy?"*

## 4. Hoy, recuperarse exige lazo o pagar siempre (2:00)

- Primera línea de defensa, a nivel de paquete: **NACK** (pedir retransmisión) y **FEC** (mandar redundancia). Si el plazo de latencia vence o la pérdida viene en ráfaga, el daño llega igual al decodificador y hay que resincronizarlo. Este mapa es para eso.
- Dos ejes: ¿hay que pedirle algo al codificador? ¿Se paga aunque la red esté sana?
- Abajo a la izquierda: **PLI/FIR**, el receptor pide un IDR; **LTR con RPSI**, el codificador predice desde una referencia que el receptor confirmó. No cuestan nada con la red sana, pero son lazo: hay que esperar un RTT, y en 1-a-muchos el IDR que pide uno lo pagan todos.
- Arriba a la derecha: **GoP corto**, **intra refresh** con Recovery Point SEI, **redundant pictures** de H.264. Sin lazo, pero se paga siempre, haya o no pérdida.
- Arriba a la izquierda: **FrameTrace**, de 2025: adaptativo, con lazo y con costo.
- Abajo a la derecha está vacío: sin lazo y sin costo con la red sana. "Ahí apunta mi trabajo."

## 5. FrameTrace [1] (1:30)

- Workshop EMS de **SIGCOMM 2025**. Mide la latencia frame por frame en Media over QUIC.
- Gráfico izquierdo: con 1 % de pérdida, GoP de 0,5 s da **VMAF 72,6** contra **55,7** con GoP de 2 s. Refrescar seguido salva la calidad. (VMAF: métrica perceptual de Netflix, de 0 a 100.)
- Gráfico derecho: su controlador mide en el cliente la tasa de entrega de frames y le pide al codificador acortar el GoP: de **2,02 s a 0,88 s** cuando la pérdida sube a 20 %. Funciona, pero es lazo al codificador y más intras para todos.
- Lo que me llevo: la métrica **FRR**, frames mostrados sobre frames enviados. Mide congelamiento: ocultar el daño congelando la imagen no cuenta como ganar.

## 6. AGiLE [2] (1:45)

- **MMSys 2024**, ByteDance. Resuelve otro problema: el GoP largo ahorra bits, pero un espectador que llega tiene que esperar el próximo I.
- Separa la unidad de codificación (GoP de **10 s**) de la unidad de transmisión (**pseudo-GOP de 2 s**).
- En cada frontera, la misma imagen se codifica además como I: el **I-header**. Viaja dentro de un SEI del P (el SEI de la diapositiva 3).
- El edge lo guarda. Al espectador nuevo le entrega I-header más los P siguientes; al conectado, se lo **descarta**.
- Números: **−3,5 % de BD-bitrate**, es decir, el mismo VMAF con 3,5 % menos de bits; **+2,8 % de datos** en ingest por los I-headers; **1,1 VMAF de deriva**, porque el I-header no es idéntico al P que reemplaza.
- Transición: *"Fíjense en el espectador conectado."*

## 7. Anomalía (1:45)

- Un espectador conectado pierde algo a los 2,5 s. Con GoP de 10 s queda dañado hasta el próximo I real: **7,5 segundos**.
- A los 4 s pasa por el edge un I-header que lo arreglaría, y se descarta, porque la regla del edge es "¿eres nuevo?".
- Si se le entregara: **1,5 s** de daño y después una deriva leve.
- Inestabilidad: AGiLE alarga el GoP para ahorrar bits y, con un transporte que descarta lo que llega tarde, eso alarga cada artefacto. Además FrameTrace cita a AGiLE como técnica de video on demand, cuando es de live: las dos líneas se citan sin conectarse.
- Lee el bloque, despacio: **"El mecanismo para recuperarse de la pérdida ya está en la red, ya está pagado, y hoy se descarta."**
- Precisión que conviene decir antes de que te la pregunten: está pagado **hasta el edge** (ingest y CDN). En la última milla se paga solo cuando se entrega, y solo a quien lo necesita.

## 8. Objetivo (1:30)

- Lee el objetivo: demostrar en una plataforma real que entregar el I-header a los receptores con pérdida acorta el daño, sin lazo al codificador.
- Plataforma: el STM32 codifica H.264 y genera el I-header en SEI; el edge lee el SEI y decide a quién entregarlo; la pérdida va **después** del edge, en la última milla (tc-netem); el receptor mide por frame.
- Tabla: las cuatro configuraciones bajo el mismo perfil de pérdida; tres métricas. Duración: frames hasta la reconstrucción limpia. Severidad: VMAF. Congelamiento: FRR. "Los signos de interrogación son lo que traigo a la final."
- Hipótesis: duración cercana a la del GoP corto, costo con red sana igual al del GoP largo.

## 9. Reproducir la Fig. 12 de AGiLE en H.264 (1:15)

- Antes del benchmark reproduzco el resultado de calidad de AGiLE, en H.264: cuánto VMAF se pierde según el I-header por el que se entra.
- AGiLE: **1,1** entrando por el primero, menos en los siguientes; peor caso, **2,64**.
- Lo que ya funciona: codificar con x264, forzar un I no-IDR en la frontera (eso es un I-header en H.264), quitar frames del Annex B y medir por frame. Es lo que produjo la figura de la diapositiva 2.
- Detalle que muestra que entiendes: en H.264 el I-header **no puede ser IDR**, porque reinicia la numeración y vacía las referencias (lo que vimos en la fila 3). Tiene que ser un I no-IDR con el `frame_num` del P que reemplaza.

## 10. Qué recordar (0:20)

- Lee la frase grande. Señala los tres números: un segundo por IDR perdido; hoy, lazo o costo; con AGiLE, de 10 s a 2 s.
- "Gracias. ¿Preguntas?" **Deja esta diapositiva puesta durante las preguntas.**

---

## Respaldo (solo si preguntan)

- **R1 Referencias:** lista completa.
- **R2 Por qué perder el IDR es peor que perder un I:** el mecanismo de `frame_num` y POC (ver guía de estudio, bloque 2).
- **R3 ¿Cómo sabe el edge a quién entregarlo?** Tres alternativas. Respuesta preparada: *"Es la pregunta central del trabajo; la plataforma es lo que me permite comparar (a) y (b)."*
- **R4 Costos.**

## Uso de la tecnología (5 pts de la pauta)

- Presenta el **PDF** en pantalla completa. En Zoom, comparte **solo la ventana** del visor de PDF, no la pantalla entera.
- Ten este guion abierto en otra pantalla o impreso. Opción: `pdfpc avance_ipd438.pdf` muestra la diapositiva siguiente y un cronómetro en tu pantalla mientras Zoom comparte la otra.
- Antes de la clase: prueba compartir pantalla, que la figura de la diapositiva 2 se vea nítida y que el audio funcione. Cronométrate dos veces en voz alta.
