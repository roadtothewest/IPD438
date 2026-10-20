# Guion — presentación de avance IPD438

Meta: **13 min**. Una idea por diapositiva y siempre de vuelta al objetivo. Las siglas están en las notas al pie; dilas una vez en voz alta.

| # | Diapositiva | Tiempo |
|---|---|---|
| 1 | Portada | 0:15 |
| 2 | Objetivo | 1:15 |
| 3 | Topología | 1:30 |
| 4 | Codificación H.264: I, P e IDR | 1:15 |
| 5 | De la imagen a la red | 1:30 |
| 6 | Estado del arte: AGiLE | 1:30 |
| 7 | Estado del arte: keyframe injection | 1:30 |
| 8 | Problema | 1:30 |
| 9 | Cómo lo medimos | 1:15 |
| 10 | Resultados a producir | 1:00 |
| 11 | Referencias | 0:10 |
| 12 | Gracias | — |

---

**1. Portada.** "Voy a mostrar cómo recuperar el video después de una pérdida de paquetes, sin pedirle nada al codificador."

**2. Objetivo.** Lee el primer punto. El ejemplo lo hace concreto: con un GoP de 90 a 30 fps, una pérdida daña hasta 3 segundos; si hay un I-header cada 5 P, el daño dura unos 0,2 s. Todo eso sin lazo al codificador y sin gastar más en la última milla que el GoP largo.

**3. Topología.** Recorre el dibujo de izquierda a derecha. El video entra al codificador (STM32N6), que manda los P normales y, cada 5 P, un I-header escondido en una SEI. El edge guarda el último I-header. Al espectador sin pérdida le llegan solo los P; al que perdió paquetes, el I-header. La última milla va por SRT: retransmite mientras alcanza y, si no, descarta; por eso el edge sabe a quién le faltó.

**4. Codificación.** El I es una foto completa; el P es "lo que cambió" respecto del anterior. Si se pierde un P, todos los siguientes se arman sobre una imagen mala hasta el próximo intra. Con GoP 90, hasta 3 segundos.

**5. De la imagen a la red.** Recorre la cadena: la imagen se divide en macrobloques de 16×16, que forman slices; cada slice va en **una** NAL (no hay una NAL por macrobloque). El PES le pone la hora a cada frame y se corta en paquetes TS de 188 bytes, que viajan por SRT sobre UDP. SPS/PPS y SEI también son NAL: en una SEI viaja el I-header.

**6. AGiLE.** Paper de ByteDance, MMSys 2024. Resuelve otro problema: que un espectador nuevo no espere el próximo intra. Para eso pone I-headers dentro de una SEI, y el edge se los da solo a los nuevos. Sus números: −3,5 % de bits a igual calidad, +2,8 % de datos de subida, −1,1 VMAF al entrar por un I-header. "No buscamos mejorar esos números: reutilizamos sus I-headers para otra cosa."

**7. Keyframe injection.** "Hannes Mareen y Glenn Van Wallendael, de la Universidad de Gante, resolvieron algo parecido": un flujo aparte solo de keyframes, que pide quien entra o pierde paquetes. La calidad cae menos de 1 punto de VMAF. "Nos respaldan, porque ya probaron que un keyframe extra repara la pérdida. La diferencia: no usamos un flujo aparte, porque el I-header va dentro del stream, y el reproductor no pide nada, porque decide el edge."

**8. Problema.** Hoy hay dos caminos: pedir un intra al codificador (lazo) o mandar intra siempre (se paga con la red sana). FrameTrace mostró que refrescar seguido salva calidad (72,6 contra 55,7 VMAF), pero cuesta. La anomalía: AGiLE ya deja I-headers en el edge y los descarta justo para quien perdió paquetes. Lee la idea fuerte, despacio.

**9. Cómo lo medimos.** La referencia es el mismo stream decodificado sin pérdidas: la integridad original. Dos comparaciones por frame. **Temporal:** las diferencias entre frames consecutivos del video recibido deben parecerse a las de la referencia; un congelamiento o un salto se notan de inmediato. Es la misma base que la información temporal (TI) de ITU-T P.910 y que la parte temporal de ST-RRED. **De imagen:** PSNR de cada frame contra la referencia, porque un error que se queda quieto no cambia las diferencias, pero sí la imagen. Además: cuántos frames dura, cuánto se congela (FRR) y cuántos bits extra cuesta.

**10. Resultados.** Reproducir la degradación al entrar por un I-header (Fig. 12 de AGiLE), ahora en H.264. Producir: con la misma pérdida, comparar GoP 90 solo, GoP corto, y GoP 90 con I-header cada 5 P. Lee el impacto esperado.

**11. Referencias.** "Las principales son AGiLE y keyframe injection."

**12. Gracias.** Repite el objetivo en una frase y abre a preguntas.

---

## Preguntas probables

- **¿En qué se diferencia de keyframe injection?** Ellos usan un flujo aparte y el reproductor pide el keyframe. Aquí va dentro del stream y decide el edge.
- **¿No le das más trabajo al codificador?** No más que AGiLE, porque reutilizamos sus I-headers. Ojo: con un I-header cada 5 P, la subida al edge lleva bastante más bits; es el costo que vamos a medir.
- **¿Cómo sabe el edge quién perdió?** SRT: el emisor sabe qué paquetes descartó para cada espectador.
- **¿Qué es VMAF?** Una métrica de Netflix que compara contra el original y predice la nota que daría una persona (0–100). La usan AGiLE, FrameTrace y keyframe injection; nosotros medimos integridad contra la decodificación sin pérdidas.
- **¿Por qué no solo diferencias entre frames?** Porque un error que se queda quieto deja las diferencias iguales a las de la referencia, aunque la imagen esté mal. Por eso va también el PSNR.

## Uso de la tecnología

Presenta el PDF en pantalla completa; en Zoom comparte solo esa ventana. Ensaya dos veces con cronómetro.
