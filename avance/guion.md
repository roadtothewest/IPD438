# Guion — presentación de avance IPD438

Meta: **13 min**. Mismo orden que tu apunte: contenidos previos, estado del arte, problema y punto de quiebre, objetivo, resultados y referencias. Las siglas están en notas al pie: dilas una vez en voz alta.

| # | Diapositiva | Tiempo |
|---|---|---|
| 1 | Portada | 0:15 |
| 2 | Codificación H.264: I, P e IDR | 1:15 |
| 3 | De la imagen a la red | 1:15 |
| 4 | Cómo se reconstruye el video | 1:00 |
| 5 | Las NAL que usamos | 1:00 |
| 6 | Estado del arte: AGiLE | 1:15 |
| 7 | Estado del arte: keyframe injection | 1:15 |
| 8 | Problema, motivación y punto de quiebre | 1:30 |
| 9 | Objetivo | 0:45 |
| 10 | Topología | 1:15 |
| 11 | Cómo lo medimos | 1:00 |
| 12 | Resultados a producir | 0:45 |
| 13 | Referencias | 0:10 |
| 14 | Gracias | — |

---

**1. Portada.** "Voy a mostrar cómo recuperar el video después de una pérdida de paquetes, sin pedirle nada al codificador."

**2. Codificación.** El I es una foto completa; el P es "lo que cambió" respecto del anterior; el IDR es un I que además reinicia el decodificador. Señala la figura: con GoP 30 hay un intra por segundo; con GoP 90, uno cada 3 segundos. Un GoP largo gasta menos, pero deja pocos puntos de partida.

**3. De la imagen a la red.** Recorre la cadena. La imagen se divide en macrobloques de 16×16, que forman slices; cada slice va en **una** NAL. El PES junta todas las NAL de un frame y les pone una marca de tiempo. El TS lo corta en paquetes de 188 bytes, y SRT lleva 7 de esos paquetes dentro de cada datagrama UDP, con número de secuencia y marca de tiempo.

**4. Cómo se reconstruye.** El decodificador lee la configuración y decodifica el intra solo. Para cada P, por cada macrobloque, copia un bloque del frame anterior desde donde indica el vector de movimiento y le suma una pequeña corrección. Si el frame anterior está dañado, la copia también lo está. Lo que se pierde es un paquete SRT: el slice se daña desde ese punto hasta su final. Si cada slice es una fila de macrobloques, sabemos exactamente en qué frame y en qué fila quedó el daño.

**5. Las NAL que usamos.** Cuatro tipos: configuración (SPS/PPS), IDR, slice normal y SEI, que son datos extra que el decodificador puede ignorar. Señala la figura. El I-header es la misma imagen, codificada además como intra: un slice normal (tipo 1). Hacia el edge, el servidor más cercano al espectador, viaja escondido dentro de una SEI, junto al P. Al espectador sano, el edge le quita la SEI. Al que perdió paquetes le entrega el I-header en lugar del P, junto con otra SEI, el recovery point, que le dice al decodificador que puede retomar desde ahí.

**6. AGiLE.** Paper de ByteDance, MMSys 2024. Usa I-headers en SEI para otra cosa: que un espectador nuevo no espere el próximo intra. El edge se los da solo a los nuevos y al conectado se los descarta. Sus números: −3,5 % de bits a igual calidad, +2,8 % de subida, −1,1 VMAF al entrar por un I-header. Lee la idea fuerte, despacio.

**7. Keyframe injection.** "Hannes Mareen y Glenn Van Wallendael, de la Universidad de Gante, resolvieron algo parecido": un flujo aparte solo de keyframes, que pide quien entra o pierde paquetes. "Nos respaldan: ya probaron que un keyframe extra repara la pérdida. La diferencia: no usamos un flujo aparte y el reproductor no pide nada."

**8. Problema, motivación y punto de quiebre.** Ya vimos que los I-headers existen y que un keyframe extra repara la pérdida. El problema: una pérdida se arrastra hasta el próximo intra. La motivación: sin propagación del error no hay anomalía; el decodificador solo la disimula, congelando o copiando el frame anterior. Señala la figura, con la misma pérdida en las cuatro filas: con GoP 30 el daño dura unos 0,7 s y con GoP 90, casi 2 s. Con un I-header cada 5 P, en ambos casos dura dos frames y después queda solo una deriva leve. "Ese es el punto de quiebre: recuperarse temprano sin pedirle nada al codificador."

**9. Objetivo.** Lee el objetivo y el ejemplo: de hasta 3 s a unos 0,2 s. Sin lazo al codificador y, con la red sana, el ancho de banda de un GoP largo hacia el espectador.

**10. Topología.** El codificador (STM32N6) manda los P y los I-headers en SEI al edge, que guarda el último. Dos modos a evaluar: A, el I-header viaja siempre y el edge lo reenvía solo a quien perdió; B, el edge detecta la pérdida y recién ahí activa el flujo de I-headers. SRT nos dice qué paquete se perdió y con qué marca de tiempo, o sea, en qué frame y en qué slice.

**11. Cómo lo medimos.** La referencia es el mismo stream decodificado sin pérdidas. Medimos si las diferencias entre frames se parecen a las de la referencia (integridad temporal), el PSNR de cada frame (integridad de imagen), cuántos frames dura el daño, cuánto se congela y cuántos bits cuesta.

**12. Resultados.** Reproducir la degradación al entrar por un I-header (Fig. 12 de AGiLE) en H.264. Producir: GoP 90, GoP 30 y GoP 90 con I-header, con la misma pérdida, barriendo cada cuántos P va el I-header. Lee el impacto esperado.

**13. Referencias.** "Las principales: AGiLE y keyframe injection."

**14. Gracias.** Repite el objetivo en una frase y abre a preguntas.

---

## Preguntas probables

- **¿Qué es un PLI?** *Picture Loss Indication*: un mensaje del receptor al emisor que dice "perdí imagen". El codificador responde mandando un intra. Es el lazo cerrado que queremos evitar.
- **¿En qué se diferencia de keyframe injection?** Ellos usan un flujo aparte y el reproductor pide el keyframe. Aquí va dentro del stream y decide el edge.
- **¿El modo B no es un lazo?** Sí, pero es un aviso del edge para activar un modo, no un pedido por cada pérdida y por cada espectador. El modo A no tiene lazo.
- **¿Por qué el I-header es tipo 1 y no IDR?** Porque un IDR reinicia el decodificador, y los P que vienen después ya no calzarían.
- **¿Un I-header pesa menos que un IDR?** No, pesan lo mismo: lo pesado es ser intra, no ser IDR. Medido con x264 a igual calidad (Big Buck Bunny 640×360), el mismo frame pesa 49 657 B como IDR y 49 621 B como intra no-IDR. Cambia quién lo paga: el IDR va a todos; el I-header, solo en la subida y a quien perdió paquetes. En ese clip un intra pesó ~15 P, así que un I-header cada 5 P multiplica la subida por ~3. Por eso el modo B y el barrido.
- **¿Por qué el I-header deja una deriva leve, si es un intra?** Porque el codificador calculó los P siguientes sobre el P original, no sobre el I-header. La compresión no es exacta: el P y el I-header son dos versiones de la misma imagen que difieren un poco, y esa diferencia se arrastra hasta el próximo intra. AGiLE la midió: −1,1 VMAF. Para eliminarla, el codificador tendría que usar el I-header como referencia, y entonces sería un intra normal que pagan todos.
- **¿Por qué no solo diferencias entre frames?** Porque un error que se queda quieto deja las diferencias iguales a las de la referencia, aunque la imagen esté mal. Por eso va también el PSNR.

## Uso de la tecnología

Presenta el PDF en pantalla completa; en Zoom comparte solo esa ventana. Ensaya dos veces con cronómetro.
