# Guía de estudio — avance IPD438

Sigue la numeración de tu apunte (I a VII). En cada punto:

- **En la presentación** = lo que dices (alto nivel, sin abusar de conceptos).
- **Si preguntan** = el detalle que tienes que dominar aunque no esté en las diapositivas.
- **Autoevaluación** = respóndelas en voz alta, sin mirar.

Marcas: **[paper]** verificado en el PDF; **[medido]** de nuestro experimento; **[doc]** documentación oficial; **[por verificar]** no citar sin revisar.

Prioridad para mañana: I.i, I.ii, I.iii, I.iv, II (AGiLE), SRT, III. El resto, si alcanza.

---

## I. Contenidos previos

### i) Códec predictivo y propagación del error — diapositivas 3 y 5

**En la presentación**
- Video = 30 imágenes por segundo. Se comprime porque frames vecinos se parecen.
- **I** (intra): imagen completa. **P** (predicho): solo lo que cambió respecto del anterior. **IDR**: I que reinicia el decodificador. **GoP**: de un I al siguiente.
- Si falta un P, los siguientes se aplican sobre una imagen equivocada: el error se arrastra hasta el próximo I.

**Si preguntan**
- Un P lleva vectores de movimiento y un residuo; el decodificador lo reconstruye **sumando** sobre su referencia. Referencia mala → P malo aunque haya llegado entero → siguiente P también.
- Perder un P a mitad de GoP daña hasta el fin del GoP; perder el I daña el GoP entero. Con GoP 30 a 30 fps, 1 s. **[medido]** P perdido en el frame 45: 15 frames dañados; I perdido: 30.
- El I es el frame más grande, así que es el más expuesto. **[medido]** en un clip a 1 Mbps, un IDR ocupó 47 paquetes y un P típico 2. Con 1 % de pérdida independiente, la probabilidad de dañarlo es 1 − 0,99ⁿ: 38 % para el IDR, 2 % para un P.
- Referencia: Wang & Zhu, 1998 (control y ocultamiento de errores).

**Autoevaluación**
1. Explica la propagación del error con la analogía de "instrucciones de cambio".
2. Si pierdo el P número 5 de un GoP de 30, ¿cuántos frames se dañan?
3. ¿Por qué el I es a la vez el frame más caro de perder y el más probable de perder?

### ii) VCL / NAL en H.264 — diapositiva 4

**En la presentación**
- Jerarquía: **segmento** (lo que el servidor guarda y reparte) → **GoP** → **frame** → **slice** (trozo de frame que se decodifica solo) → **NAL** (la caja que H.264 entrega a la red).
- El primer byte de la NAL dice qué lleva: 1 slice, 5 slice IDR, 6 SEI, 7/8 parámetros.

**Si preguntan**
- **VCL** (*Video Coding Layer*): lo que codifica la imagen (los slices). **NAL** (*Network Abstraction Layer*): cómo se empaqueta para la red.
- Cabecera NAL (1 byte): `forbidden_zero_bit` (1 bit, siempre 0), `nal_ref_idc` (2 bits: importancia como referencia), `nal_unit_type` (5 bits).
- Tipos: **1** slice no-IDR · **5** slice IDR · **6** SEI · **7** SPS · **8** PPS · **9** delimitador de access unit.
- **SPS/PPS** (*Sequence / Picture Parameter Set*): resolución, perfil, cómo se numeran los frames. Sin ellos no se decodifica nada. Normalmente se repiten antes de cada IDR.
- **Annex B**: formato en que las NAL van una tras otra separadas por *start codes* (`00 00 01` o `00 00 00 01`). Para que un start code no aparezca por accidente dentro de los datos se insertan **bytes de prevención de emulación** (`00 00 03`).
- **Access unit** (tu "¿access unit?"): todas las NAL de **un** frame: sus slices más las NAL que lo acompañan (SPS, PPS, SEI). Si hay un slice por frame, access unit ≈ frame.
- **Segmento**: unidad de HLS/DASH/MoQ, de algunos segundos, alineada para empezar en un IDR. Con SRT no hay segmentos: el flujo es continuo.
- Referencia: Wiegand et al., 2003.

**Autoevaluación**
1. Dibuja la jerarquía segmento → NAL sin mirar.
2. Di el tipo de NAL de un IDR, un P y una SEI.
3. ¿Qué es un access unit y en qué se diferencia de una NAL?

### iii) Slice header y gestión de referencias (!!!) — diapositivas 5 y 12

**En la presentación**
- Perder un IDR es el peor caso: además se pierde la orden de "empezar de cero" y la imagen puede congelarse.
- En H.264, el I-header debe ser un I **no-IDR** y cada P debe usar una sola referencia.

**Si preguntan**
- **`frame_num`**: contador en la cabecera de cada slice. Sube 1 por frame de referencia y vuelve a 0 en cada IDR. Sirve para detectar huecos.
- **POC** (*Picture Order Count*): orden de presentación. Sin B-frames, x264 usa el tipo 2, que se deriva de `frame_num`.
- **DPB** (*Decoded Picture Buffer*): las referencias guardadas. El IDR lo vacía.
- **Por qué el I-header no puede ser IDR:** un IDR vacía el DPB y reinicia `frame_num`; los P siguientes fueron codificados contra el P original, con su numeración, y no calzarían. Tiene que ser un slice I no-IDR que ocupe el lugar (y el `frame_num`) del P que reemplaza.
- **Por qué multi-referencia rompe la recuperación:** si un P posterior puede apuntar a un frame anterior al I-header, apunta a algo dañado. AGiLE usa una sola referencia: cada P mira solo al anterior.
- **[medido] Por qué el IDR congela en FFmpeg:** sin el IDR, el decodificador ve `frame_num` 13 → 1, rellena el hueco y no detecta el reinicio; calcula POC menores que los ya mostrados y descarta esos frames por desordenados ("no picture ooo" en el log): 12 frames congelados, después artefactos hasta el próximo IDR. Es comportamiento de FFmpeg 6.1; otro decodificador puede mostrar basura en vez de congelar.

**Autoevaluación**
1. ¿Qué hace un IDR que no hace un I?
2. ¿Por qué el I-header no puede ser IDR?
3. ¿Por qué con varias referencias no sirve?

### iv) SEI (Anexo D de H.264) (!!!) — diapositivas 4 y 6

**En la presentación**
- SEI = datos extra que el decodificador puede ignorar. AGiLE esconde el I-header ahí.

**Si preguntan**
- **payloadType 5**, `user_data_unregistered`: datos arbitrarios identificados por un UUID. Es donde **nosotros** pondríamos el I-header. AGiLE solo dice "SEI"; el tipo es decisión nuestra.
- **payloadType 6**, `recovery_point`: le dice al decodificador que desde ese frame puede arrancar y obtener imagen correcta, **aunque no sea IDR**. Es el que "engaña" al decodificador (tu apunte). Algunos decodificadores no arrancan desde un I no-IDR sin él.

**Autoevaluación:** ¿qué tipo de SEI lleva el I-header y cuál permite arrancar desde él?

### v) Encapsulación y transporte — diapositiva 9

**En la presentación**
- Uso **SRT**: retransmite dentro de una latencia fija y descarta lo que no llega a tiempo. Lleva MPEG-TS. El emisor sabe qué descartó.

**Si preguntan — SRT** **[doc]** (documentación oficial de libsrt, Haivision)
- *Secure Reliable Transport*: protocolo abierto sobre UDP para video en vivo de baja latencia. Especificación: borrador IETF draft-sharabayko-srt-01 (2021).
- **ARQ** (*Automatic Repeat reQuest*) es su mecanismo principal: cuando el receptor detecta un paquete faltante, envía un aviso de pérdida (**NAK**) y el emisor lo retransmite. FEC es opcional.
- **Latencia fija** (`SRTO_LATENCY`, por defecto **120 ms**): el receptor entrega cada paquete en su momento; dentro de ese margen caben las retransmisiones.
- **Too-late packet drop** (`SRTO_TLPKTDROP`): el receptor salta los paquetes que no llegaron a tiempo; el emisor descarta los que ya no tienen posibilidad de llegar. **La pérdida residual llega al decodificador.**
- El emisor lleva la cuenta: `pktSndLossTotal` (pérdidas reportadas por el receptor) y `pktSndDropTotal` (paquetes que descartó por tarde). **Por eso el edge, como emisor SRT, sabe qué espectador quedó dañado sin preguntarle al codificador.**
- Cifrado AES de 128, 192 o 256 bits.
- Es agnóstico al contenido, pero lo típico es **MPEG-TS**: 7 paquetes TS de 188 B = 1316 B por paquete SRT.

**Si preguntan — MPEG-TS** (tu apunte)
- Video elemental (ES) → PES (agrega PTS/DTS, los tiempos de presentación y decodificación) → paquetes TS de **188 B**.
- Cada paquete TS lleva un `continuity_counter` de 4 bits por flujo: si salta, se perdió algo. Detección de pérdida en el receptor.

**Si preguntan — RTP (RFC 6184)**, la alternativa
- NAL simple (una por paquete), **STAP-A** (varias NAL chicas en un paquete) y **FU-A** (una NAL grande en fragmentos). Más liviano de parsear para el edge.
- Perder un fragmento FU-A rompe la NAL desde ese punto.

**Autoevaluación**
1. ¿Qué hace SRT con un paquete perdido y qué hace si no alcanza a recuperarlo?
2. ¿Por qué SRT le resuelve al edge la pregunta "¿a quién le entrego el I-header?"?
3. ¿Cómo se detecta una pérdida en MPEG-TS?

### vi) Ocultamiento de errores — diapositiva 5

- El decodificador puede congelar, copiar el frame anterior o compensar movimiento. **Disimula** el daño (baja la severidad); **no lo elimina** (no acorta la duración). Nosotros buscamos eliminarlo.
- Por eso medimos también congelamiento: ocultar ≠ recuperar.

### vii) STM32 — no va en la presentación

- Los codificadores por hardware embebidos suelen ser **Constrained Baseline**: sin B-frames.
- **TMVP** (*Temporal Motion Vector Prediction*) es de H.265; AGiLE lo desactiva. En H.264 sin B-frames probablemente no aplica. **[por verificar]** con el codificador concreto.
- Riesgo principal: que el codificador no permita codificar dos veces la misma imagen (P e I-header) ni forzar un I no-IDR. Confirmar el modelo es lo primero.

---

## II. Estado del arte — diapositivas 6, 7 y 8

### AGiLE [2] — el fuerte **[paper]**

C. Chen, W. Yin, Z. Huang, S. Shi (ByteDance y SJTU). MMSys '24, pp. 34–44. Paper completo.

**En la presentación**
- Resuelve: GoP largo ahorra bits, pero quien se conecta espera el próximo I.
- Idea: GoP de codificación de 10 s, **pseudo-GOP** de transmisión de 2 s.
- **I-header**: la misma imagen de la frontera, codificada además como I, dentro de una SEI del P.
- El **edge** (servidor de la CDN más cercano al espectador) guarda el I-header y se lo da solo al espectador nuevo; al conectado se lo descarta.
- ~3,5 % menos bits a igual calidad; +2,8 % de datos hacia el CDN; deriva de ~1 punto de VMAF.

**Si preguntan**
- Motivación medida: top 20 streams de Douyin; pasar de GoP 2 s a 10 s beneficia a 11 de 20 (los de poco movimiento).
- El I-header **no cambia las referencias**: el P siguiente sigue apuntando al P, no al I-header.
- Doble codificador (uno primario, otro solo para I-headers); TMVP desactivado (~0,23 % de costo).
- **Deriva**: el I-header no reconstruye idéntico al P (cuantizaciones distintas); quien entra por él arrastra un error leve hasta el próximo I real.
- BD-bitrate: −3,54 % (fijo) / −3,71 % (adaptativo) frente a GoP fijo de 2 s. Datos totales +2,8 %.
- **Fig. 12**: la caída de VMAF baja mientras más tarde se entra en el GoP; por el 1.º I-header, ~1,1 (97,83 → 96,73); peor caso 2,64.
- Evaluación offline: x265, 720p 30 fps; separar frames con `hevc_mp4toannexb`, reemplazar P por I-header, concatenar, VMAF.

**Autoevaluación**
1. Explica pseudo-GOP e I-header en 30 segundos, para alguien que no sabe de video.
2. ¿Qué hace el edge con el I-header y a quién se lo descarta?
3. ¿Por qué hay deriva si la imagen es la misma?

### FrameTrace [1] **[paper]**

B. Denizer, L. Winkel, O. Landsiedel. EMS '25, ACM SIGCOMM **2025**, pp. 31–36 (en tu apunte dice 2026).

**En la presentación**
- Con 1 % de pérdida: GoP 0,5 s → VMAF 72,6; GoP 2 s → 55,7. Refrescar seguido salva calidad.
- Su controlador acorta el GoP con pérdida, pero necesita lazo al codificador.

**Si preguntan**
- Mide 4 marcas de tiempo por frame (captura, segmento, llegada, render) en Media over QUIC (MoQ).
- **FDR** = frames recibidos / enviados (mide la red). **FRR** = frames mostrados / enviados (mide la experiencia).
- Controlador: GoP medio 2,02 / 1,56 / 0,88 s con 0 / 10 / 20 % de pérdida.
- No habla de H.264 ni de NAL: es agnóstico al códec.
- Cita a AGiLE como técnica de video bajo demanda; AGiLE es de **video en vivo**. Las dos líneas se citan sin conectarse.

### Otros mecanismos (la tabla)

| Mecanismo | Qué hace | ¿Lazo al codificador? | ¿Costo con red sana? |
|---|---|---|---|
| **PLI** (*Picture Loss Indication*) | El receptor pide un intra | Sí | No; con pérdida, un IDR para todos |
| **RPSI** + **LTR** (*Reference Picture Selection Indication*, *Long-Term Reference*) | El codificador predice desde una referencia que el receptor confirmó | Sí | Estado por receptor |
| GoP corto / refresco intra periódico | Intras frecuentes, o una franja intra por frame | No | Siempre |
| **Recovery Point SEI** | Marca desde dónde se puede arrancar | No | Siempre (acompaña al refresco) |
| Redundant Coded Pictures (H.264) | Segunda copia codificada de la imagen, siempre enviada | No | Siempre |
| GoP adaptativo (FrameTrace) | Acorta el GoP al ver pérdida | Sí | Sí |
| **Propuesta** | El edge entrega el I-header a quien perdió | **No** | **No** en la última milla |

- PLI, FIR y RPSI están en RFC 8834 (RTP en WebRTC). LTR es una herramienta del códec.
- Tu apunte: Redundant Coded Pictures "**podría estar hecho**". Es lo más parecido (una segunda representación), pero se manda siempre a todos. **[por verificar]** antes de afirmar novedad.

---

## III. Motivación y problema — diapositiva 10

**En la presentación**
1. Sin propagación del error no habría problema.
2. Hoy: pedir un intra (lazo) o mandar intras siempre (costo con red sana).
3. **Quiebre**: AGiLE alarga el GoP a 10 s → una pérdida dura hasta 10 s.
4. **Anomalía**: cada 2 s el edge tiene un I-header que lo arreglaría… y lo descarta.
5. **Idea fuerte**: "El mecanismo para recuperarse de la pérdida ya está en la red, ya está pagado, y hoy se descarta."

**Si preguntan**
- "Pagado" = pagado hasta el edge (ingest y CDN). En la última milla se paga solo cuando se entrega, y solo a quien lo necesita.
- Frase útil: *"No elimino el intra. Elimino el intra que se envía a quien no lo necesita."*

## IV. Objetivo — diapositiva 11

- Demostrar que entregar el I-header a quien perdió paquetes corta el daño en la próxima frontera (≤ 2 s) y no en el próximo I (≤ 10 s), sin lazo al codificador.
- Meta (tu apunte): reducir la duración de los artefactos al mismo ancho de banda en el último salto que un GoP largo, cerca de un GoP corto sin su costo permanente.
- Métricas:
  - **Duración**: frames desde la pérdida hasta la imagen limpia.
  - **Severidad**: VMAF (o PSNR) por frame contra la referencia. **VMAF**: calidad percibida, 0–100 (Netflix). **PSNR**: relación señal a ruido, en dB.
  - **Congelamiento**: FRR o duración de stalls. Ocultar ≠ íntegro.
- **Promesa**: "Recuperarse de la pérdida sin pedirle nada al codificador, usando un punto de recuperación que ya está en la red."

## V. Resultados a producir — diapositiva 12

- Fig. 12 de AGiLE en H.264: caída de VMAF según el índice del I-header por el que se entra.
- Pasos (tu apunte): codificar → separar Annex B (FFmpeg) → reemplazar P por I-H → concatenar → medir VMAF.
- Ya probado: x264 puede forzar un I no-IDR en una posición dada (con un `qpfile`, tipo `i`); separar el Annex B y quitar frames funciona (`avance/experimentos/perdida_gop.py`).
- Benchmark en la plataforma: GoP largo, GoP corto, PLI y propuesta con la misma pérdida.

## VI. Referencias — diapositiva 14

FrameTrace, AGiLE, Wiegand 2003, Wang & Zhu 1998, Sjöberg 2012, ITU-T H.264 (Anexos B y D), RFC 6184, RFC 8834 y, nuevo, el borrador de **SRT** (Sharabayko et al., 2021).

## VII. Costos — diapositiva 13

- **Exactitud**: deriva hasta el próximo I; se reduce la duración del artefacto pero queda uno leve.
- **Ráfaga en el peor momento**: tamaño del I ≫ tamaño del P; se envía cuando el enlace pierde y puede empeorar la congestión. Por eso LTR evita los intras.
- **Doble codificación** en cada frontera: cómputo, memoria y energía en el STM32.
- **Sobrecarga de ingest**: +2,8 % en AGiLE (H.265); en H.264, por medir.
- **Estado en el edge**: no hay lazo al codificador, pero hay que llevar el estado de cada receptor.
- **Granularidad**: solo se recupera en fronteras de pseudo-GOP.
- **Depende del contenido**: con mucho movimiento, el GoP largo empeora (la mejora no es universal).
- **Compatibilidad**: decodificadores sin soporte de Recovery Point SEI pueden negarse a arrancar desde un I no-IDR.

---

## Experimento (no va en la presentación; sirve para el informe)

`avance/experimentos/perdida_gop.py` codifica Big Buck Bunny a 30 fps con GoP 30 (x264 Baseline, una referencia), quita un frame del Annex B (un P, un I no-IDR o el IDR), decodifica con FFmpeg y mide por frame. `avance/experimentos/figuras.py` genera la figura `figuras/propagacion.pdf`.

```bash
pip install av numpy matplotlib     # además: ffmpeg, x264 y LaTeX
python3 avance/experimentos/perdida_gop.py big_buck_bunny.mp4 avance/experimentos/datos/perdida_gop.csv
python3 avance/experimentos/figuras.py
```

Resultado: P perdido → 15 frames dañados; I no-IDR perdido → 30; IDR perdido → 30, de los cuales 13 congelados.

## Cómo seguimos

Un bloque por sesión: te hago las preguntas de autoevaluación, corregimos lo que falle y pasamos al siguiente. Antes de presentar: I.i a I.v, II y III, y un ensayo cronometrado con el guion.
