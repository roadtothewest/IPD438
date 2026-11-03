# Guía para el trabajo final (IPD438)

Esto no va en el informe: es el mapa de lo que sigue. La pauta pide no incluir el plan de trabajo en el informe.

## 1. En una frase

**Objetivo.** Que un espectador que pierde paquetes recupere la imagen en el próximo I-header, y no en el próximo intra, sin pedirle nada al codificador por cada pérdida. El espectador sin pérdidas recibe exactamente lo mismo que con GoP largo.

**Promesa.** El mecanismo para recuperarse ya está en la red, ya está pagado y hoy se descarta.

## 2. Qué responde el avance sobre SRT

- **¿Hay macroblocking con SRT?** Sí, cuando el corte dura más que la latencia, aproximadamente cuando D + RTT + d > L. En ese caso TLPKTDROP descarta el paquete, el slice se trunca y el error se propaga hasta el próximo intra.
- **¿Cómo lo usamos?** SRT recupera los cortes cortos y el I-header cubre los largos. No compiten, se suman.
- **¿El edge sabe qué perdió el espectador?** El NAK solo dice qué falta, no si al final llegó. El borrador dice que el descarte queda desconocido para el emisor. Lo inferimos con la marca de tiempo del ACK (regla (2) del informe), sin cambiar SRT, y da lo mismo que un aviso explícito.
- **Ojo con la diapo 12.** Dice que SRT "ya avisa qué paquetes faltan". Es cierto, pero hay que precisar que el resultado final se infiere por el ACK.

## 3. Lo que está hecho

| Pieza | Dónde |
|---|---|
| Núcleo portable (parser, SEI, reescritura IDR → intra con `frame_num`/QP, TS) | `Proyecto/ihdr/core/` |
| Modelo de SRT live y simulador | `Proyecto/ihdr/host/` |
| Codificación, evaluación y figuras | `Proyecto/ihdr/tools/` |
| Resultados (CSV y curvas por frame) | `Proyecto/ihdr/results/` (`crf23/` es la primera versión, con I-headers de calidad fija) |
| Informe | `Proyecto/informe/informe_avance.tex` |

## 4. Hallazgos que cambian el diseño

1. **El I-header debe tener el QP del P que reemplaza.** Con un I-header de calidad fija (CRF 23) la deriva fue grande donde el codificador estaba ahogado.
2. **Aun con el QP ajustado, la deriva depende del régimen.** Con QP de unos 29 queda en 39 dB o más contra la referencia. Con QP de unos 43 cae a 28–31 dB, que es tan malo como el artefacto. En ese régimen conviene no enviar el I-header y esperar el IDR.
3. **Subir la latencia de SRT** elimina el daño si L > D + RTT, pero retrasa a todos. El I-header no agrega latencia.

## 5. Siguientes pasos para el final, por prioridad

1. **VMAF.** El FFmpeg del PC no trae libvmaf, y compilarlo desde GitHub quedó bloqueado en esta sesión. Opciones:
   - autorizar ese build;
   - usar un FFmpeg estático que traiga libvmaf;
   - calcularlo en otro equipo con los `.ts` que deja el emulador.
2. **Política del edge**, que es el "mejorar SRT":
   - (a) no enviar el I-header si el QP es alto o el IDR está cerca (deriva esperada > daño esperado);
   - (b) detección temprana: cuando el edge suprime una retransmisión porque ya no llegaría a tiempo, el descarte es seguro, así que puede decidir sin esperar el ACK.
3. **Barrido de n** (cada cuántos P va un I-header), midiendo el costo de subida contra la duración del daño. Después, el modo B.
4. **Validar el modelo de SRT** contra libsrt real con `tc netem`, que necesita sudo.
5. **STM32N6.**
   - Portar `core/` con un adaptador HAL: codificador (`h264encapi.h`), lectura del y4m desde la SD y salida UDP.
   - Fijar el `frame_num` y el QP del I-header desde la API.
   - Medir el tiempo real.
6. **Escenarios.** Varios espectadores y pérdida en el tramo codificador → edge.

## 6. Coherencia con la presentación

| Diapo | Qué cambiar |
|---|---|
| 13 (métricas) | Agregar el umbral de 35 dB y decir que la referencia es el stream decodificado sin pérdida |
| 14 (resultados) | Reemplazar "a producir" por la tabla del informe; la matriz UDP/SRT × con/sin I-header ya está |
| Nueva o en la 12 | La condición D + RTT + d ≤ L: responde "¿SRT no lo resuelve?" |
