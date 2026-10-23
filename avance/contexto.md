# Contexto para continuar: IPD438, presentación de avance

Para adjuntar al empezar un chat nuevo. Estado al 23 de octubre de 2026.

## 1. Quién y qué

- Vicente Andrade Ercilla, Universidad Técnica Federico Santa María. Ramo IPD438, Seminario de Redes de Computadores. Trabaja en Sentrica (detección de artefactos de video).
- Entregable actual: presentación de avance de 15 min, más 5 de preguntas.
- Pauta: contenido 70 pts (contenidos previos 15, estado del arte 20, problema y motivación 15, objetivo 10, resultado a reproducir 5, al menos 2 referencias 5); forma 30 pts (tiempo, organización del material 10, uso de tecnología 5, lenguaje 5, promesa o idea fuerte 5).
- Repositorio: github.com/roadtothewest/IPD438, rama `main`.
  - `avance/presentacion/avance_ipd438.tex` y `.pdf`: la presentación (Beamer, estilo Sentrica). Se compila con pdflatex dos veces.
  - `avance/guion.md`: guion con tiempos y preguntas probables.
  - `avance/estudio/`: material de estudio (guía, H.264 en simple, revisión del estado del arte, transcripción del cuaderno).
  - `avance/experimentos/`: experimento de pérdida con x264 y FFmpeg.

## 2. El proyecto

**Título:** Recuperación de video bajo pérdida (sin lazo al codificador).

**En una frase:** reutilizar los I-headers de AGiLE (la misma imagen codificada además como intra, dentro de una SEI) para que el edge se los entregue solo a los espectadores que perdieron paquetes.

**Objetivo:** que un espectador que pierde paquetes recupere la imagen en el próximo I-header, y no en el próximo intra. Ejemplo: con GoP 90 a 30 fps el daño dura hasta 3 s; con un I-header cada 5 P, unos 0,2 s. El codificador no recibe un pedido por cada pérdida (decide el edge). Con la red sana, el espectador recibe lo mismo que con GoP 90.

**Idea fuerte:** el mecanismo para recuperarse de la pérdida ya está en la red, ya está pagado, y hoy se descarta.

**Impacto esperado:** quien pierde paquetes se recupera como con un GoP corto, y solo él recibe bits extra; quien no pierde recibe lo mismo que con GoP 90.

## 3. La presentación actual (16 diapos, guion de unos 13:40)

| # | Diapo | Contenido |
|---|---|---|
| 1 | Portada | |
| 2 | Codificación H.264: I, P e IDR | Bullets y secuencias de GoP 30 y GoP 90 |
| 3 | De la imagen a la red | Cadena imagen → macrobloques → slice → NAL → PES → TS → SRT → UDP |
| 4 | Cómo se empaqueta un frame | Figura: frame en 4 slices → una NAL por slice → PES con marca de tiempo → TS de 188 B → 7 TS por paquete SRT en UDP |
| 5 | Cómo se reconstruye el video | Un P copia bloques del frame anterior según el vector de movimiento y les suma una corrección. Se pierde un paquete SRT. Con un slice por fila se ubica el daño |
| 6 | Las NAL que usamos [7] | Tabla (SPS/PPS 7/8, IDR 5, no-IDR 1, SEI 6). Figura: el I-header (tipo 1) viaja dentro de una SEI (tipo 6) hasta el edge; al espectador sano le llega solo el P; al que perdió, una SEI recovery point y el I-header en lugar del P |
| 7 | Problema y motivación | Problema; motivación: "sin propagación del error no hay anomalía; el decodificador solo la disimula"; "¿GoP corto?". Figura de GoP 30 y 90 con la misma pérdida |
| 8 | Estado del arte: AGiLE [1] | Qué resuelve, idea, edge, indicadores, si esperamos mejorarlos, idea fuerte |
| 9 | Estado del arte: keyframe injection [2, 3] | Qué hacen, indicadores, P de reparación de 2023 [4], postura, diferencia |
| 10 | Punto de quiebre | Figura de 4 filas: GoP 30 y 90, con y sin un I-header cada 5 P |
| 11 | Objetivo | |
| 12 | Topología | Video → STM32N6 → edge → espectadores. Modo A y modo B (flecha punteada). SRT [6] |
| 13 | Cómo lo medimos | Referencia sin pérdida, integridad temporal, PSNR, duración y congelamiento (FRR [5]), costo (BD-rate) |
| 14 | Resultados a producir | Reproducir la degradación al entrar por un I-header (AGiLE), ahora en H.264. Comparar GoP 90 / GoP 30 / GoP 90 + I-header cada 5 P. Barrer cada cuántos P va el I-header |
| 15 | Referencias | Las 7 de `referencias.md` |
| 16 | Gracias | |

## 4. Preferencias del usuario

- **Estilo:** minimalista, como sus presentaciones de Sentrica. Bullets cortos con los conceptos clave, siglas explicadas en notas al pie, pocas figuras y que sirvan. Alto nivel: nadie del público es experto en video.
- **En el chat:** respuestas cortas y simples, sin irse en detalles. Si algo no se sabe, decirlo. Nunca inventar datos ni referencias.
- **En las diapos, no:** mencionar HEVC; usar VMAF como métrica propia (sí citar la de los papers); mencionar la Fig. 12 de AGiLE; poner el AUD; decir "hora" para el PTS (se dice "marca de tiempo"; el detalle de los ticks de 90 kHz lo dice él).
- **Referencias:** solo las que vienen al caso y que él puede explicar. Se sacaron Wiegand et al. (2003), Wang y Zhu (1998), ST-RRED e ITU-T P.910.
- **Repo:** después de cada cambio, compilar, hacer commit y push a `main`.

## 5. Conceptos clave

- **I, P e IDR:** el I es una imagen completa. El P copia bloques del frame anterior según vectores de movimiento y les suma una corrección, así que depende del anterior. El IDR es un intra que además reinicia el decodificador. No hay B: el STM32N6 no los hace.
- **GoP:** cada cuántos frames va un intra. Lo decide el codificador; no está escrito en el SPS.
- **I-header:** la misma imagen codificada además como intra sin reinicio (NAL tipo 1). Viaja dentro de una SEI (NAL tipo 6, mensaje 5, datos de usuario). El mensaje SEI 6 (recovery point) permite retomar desde un intra que no es IDR. Los números de mensaje SEI no son tipos de NAL.
- **Por qué el I-header deja una deriva leve:** los P siguientes se calcularon sobre el P, no sobre el I-header. Por la compresión, son dos versiones algo distintas de la misma imagen, y el error se hereda hasta el próximo intra. AGiLE mide −1,1 VMAF.
- **Peso:** un I-header pesa lo mismo que un IDR; lo que cambia es quién lo paga.
- **Cadena:** imagen → macrobloques de 16×16 → slice (una NAL por slice) → PES (un frame y su PTS) → TS (188 B) → SRT (7 TS = 1316 B, con número de secuencia) → UDP.
- **Qué se pierde:** un paquete SRT. El slice se daña desde ese punto hasta su final. Con un slice por fila de macrobloques se sabe el frame y la fila. El macrobloque exacto lo sabe el decodificador, y en los frames siguientes el daño se mueve con el movimiento.
- **SRT:** protocolo abierto sobre UDP. Retransmite lo que falta (el receptor avisa con NAK) dentro de una latencia fija, de 120 ms por defecto, y descarta lo que llega tarde. El emisor, que es el edge, sabe qué no llegó; por eso decide sin que el reproductor pida nada.
- **Modo A:** un I-header siempre, cada 5 P; el edge se lo entrega solo a quien perdió. **Modo B:** el edge detecta la pérdida y le pide al codificador que active los I-headers; ahorra subida, pero agrega ese aviso.
- **PLI:** mensaje "perdí imagen" del receptor al emisor, al que el codificador responde con un intra para todos. Es el lazo que evitamos.
- **Métricas:** la referencia es el mismo stream decodificado sin pérdida.
  - Integridad temporal: las diferencias entre frames deben parecerse a las de la referencia.
  - PSNR por frame: 10·log10(255²/MSE), en dB.
  - Duración y congelamiento: frames hasta recuperar la integridad; FRR = frames mostrados / frames enviados.
  - Costo: bits extra. El BD-rate es la diferencia promedio de bits a igual calidad, con PSNR o VMAF como métrica de calidad.

## 6. Datos propios medidos

- Big Buck Bunny 640×360, x264 Baseline a 1 Mbps, una referencia, GoP 30: perder un P daña 15 frames; perder un I no-IDR, 30; perder el IDR, 30, de los cuales 13 quedan congelados en FFmpeg.
- Al mismo QP, el mismo frame pesa 49 657 B como IDR y 49 621 B como intra no-IDR (0,07 % de diferencia).
- En ese clip (QP 26, poco movimiento), un intra pesa unas 15 veces un P. Un I-header cada 5 P en un GoP 90 multiplica la subida por unos 3 (+224 %).
- x264 no pone AUD por defecto; el muxer MPEG-TS de FFmpeg agrega uno por frame.

## 7. Estado del arte

- **AGiLE** (ByteDance, MMSys 2024): GoP de 10 s con un I-header cada 2 s dentro de una SEI; el edge lo entrega solo a quien entra. BD-rate −3,5 % frente a un GoP fijo de 2 s (−3,54 % fijo, −3,71 % adaptativo). Datos totales +2,8 %. −1,1 VMAF al entrar por el primer I-header (97,83 → 96,73); peor caso, 2,64. Evaluado con x265 a 720p y 30 fps.
- **Keyframe injection** (Mareen, Van Wallendael et al., Universidad de Gante): un flujo aparte solo de keyframes, del que pide uno quien entra o pierde paquetes.
  - Caída de VMAF menor que 0,94 (Electronics 2021).
  - Estudio en H.264, HEVC y VVC (MTAP 2024).
  - En 2023 reparan con un P que se apoya en un frame anterior a la pérdida (unas 2 veces un P normal), para evitar el peak de bitrate del keyframe.
  - Nos respalda. La diferencia: sin flujo aparte y sin pedido del reproductor.
- **FrameTrace** (EMS '25, SIGCOMM 2025): telemetría por frame en Media over QUIC, con FDR y FRR. Con 1 % de pérdida, GoP 0,5 s da VMAF 72,6 y GoP 2 s, 55,7. Su controlador acorta el GoP cuando hay pérdida, lo que necesita lazo al codificador. No está verificado si usaron decodificador por software o por hardware.

## 8. Hardware y fuente de video

- **STM32N6570-DK:** codificador H.264 por hardware, de VeriSilicon. 32 MB de PSRAM, 128 MB de flash y microSD. Según el datasheet, 1080p15 y 720p30.
- **Su API** (STM32CubeN6, `h264encapi.h`):
  - Tipo de cada frame: IDR, P o intra no-IDR.
  - `refFrameAmount` de 1 a 2 y referencias de largo plazo.
  - Slices por filas de macrobloques y refresco intra.
  - SEI de usuario de hasta 2048 B. El I-header no cabe, así que la SEI hay que armarla por software.
- **Pendiente:** el I-header debe llevar el `frame_num` del P que reemplaza; hay que reescribir ese campo.
- **Video fuente:** `speed_bag_1080p.y4m` (1920×1080, 29,97 fps, 4:2:2, 570 frames, 2,36 GB). Plan:
  1. Convertir a 4:2:0 crudo en el PC (1,77 GB).
  2. Leerlo desde la SD con un búfer de 1 o 2 frames en PSRAM.
  3. Codificar fuera de tiempo real y guardar el bitstream.
  4. Reproducirlo por SRT con pérdida.

## 9. Pendientes

- Confirmar en el PDF de FrameTrace qué decodificador usaron.
- Opcional: reescribir los indicadores de keyframe injection como "la calidad baja menos de 1 punto VMAF (de 100); cada keyframe inyectado es un golpe de bits, porque pesa como varios P".
- El usuario dijo una vez que se interpretaron mal las imágenes de su cuaderno; quedó sin aclarar.
- STM32N6: reescritura de `frame_num`, rendimiento en tiempo real y lectura del y4m desde la SD.

## 10. Referencias

Las 7 de la presentación están en `referencias.md`, con enlaces.
