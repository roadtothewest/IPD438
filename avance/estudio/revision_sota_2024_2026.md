# Revisión del estado del arte (2024–2026): SEI e intras extra para recuperarse de pérdidas

Búsqueda hecha el 19-10-2026. Cada referencia tiene enlace; lo no confirmado está marcado **[por verificar]**.

## Respuesta corta

1. **Sí existe, y es casi tu propuesta.** El grupo IDLab de la Universidad de Gante (imec), con THEO Technologies (los autores de HESP), publicó entre 2021 y 2024 la técnica ***keyframe injection*** (o *keyframe insertion*). El stream normal usa GoP largo y va acompañado de un **flujo compañero hecho solo de keyframes**. Esos keyframes se entregan **solo a quien se conecta o pierde paquetes**. La técnica está estudiada en H.264, HEVC y VVC, y desplegada en HESP. En 2023 publicaron una variante que inyecta frames P en vez de I.
2. **No usa SEI.** El keyframe viaja en un flujo aparte: el cliente lo pide y después sigue con el stream normal. Lo único reciente que mete un keyframe **dentro de una SEI** es AGiLE (2024), y solo para espectadores nuevos.
3. **El uso de SEI para ocultar errores es antiguo.** H.264 (2003) ya trae SEIs para eso: *spare picture*, *scene information* y *recovery point*. Las 15 SEI nuevas de H.274 v4 (enero 2026) no incluyen ninguna de resiliencia, según lo que encontré.
4. **Consecuencia:** en la tabla de la diapositiva 8, la fila "¿?" (sin lazo al codificador y sin costo con la red sana) **ya está ocupada** por keyframe injection. La novedad hay que reformularla (sección 5).

---

## 1. Lo más cercano: keyframe injection (Gante / imec + THEO)

| Año | Trabajo | Qué aporta |
|---|---|---|
| 2021 | G. Van Wallendael, H. Mareen, J. Vounckx, P. Lambert. *Keyframe Insertion: Enabling Low-Latency Random Access and Packet Loss Repair*. **Electronics** 10(6), 748. [doi:10.3390/electronics10060748](https://www.mdpi.com/2079-9292/10/6/748) | La técnica, en HEVC. Caída promedio de VMAF menor que 0,94. |
| 2022 | H. Mareen, M. Courteaux, J. Vounckx, P. Lambert, G. Van Wallendael. *Keyframe Insertion for Random Access and Packet-Loss Repair in H.264/AVC, H.265/HEVC, and H.266/VVC*. **DCC 2022** (póster), p. 472. [doi:10.1109/DCC52660.2022.00083](https://ieeexplore.ieee.org/document/9810787/) | Requisitos para cada códec: TMVP desactivado, manejo de los parameter sets. |
| 2022 | G. Van Wallendael, P. Lambert, P.-J. Speelmans, H. Mareen. *Mixed-Resolution HESP for More Efficient Fast Channel Switching and Packet-Loss Repair*. **PCS 2022**, pp. 319–323. [doi:10.1109/PCS56426.2022.10018074](https://imec-publications.be/handle/20.500.12860/41156) | El flujo compañero a menor resolución, para bajar su costo. |
| 2023 | H. Mareen, P. Lambert, G. Van Wallendael. *P-Frame Injection for Efficient Packet-Loss Repair in Ultra-Low-Latency Video Streaming*. **IEEE VCIP 2023**. [IEEE Xplore](https://ieeexplore.ieee.org/document/10402720/) | Inyecta P en vez de I: evita el peak de bitrate durante la reparación. Código abierto (HEVC y VVC). |
| 2024 | H. Mareen, M. Courteaux, P.-J. Speelmans, P. Lambert, G. Van Wallendael. *A study on keyframe injection in three generations of video coding standards for fast channel switching and packet-loss repair*. **Multimedia Tools and Applications** 83, 44485–44501 (en línea: 18-10-2023). [doi:10.1007/s11042-023-17163-2](https://link.springer.com/article/10.1007/s11042-023-17163-2) | Versión de revista del trabajo de DCC: H.264, HEVC y VVC. |

**Cómo funciona.** Quien se conecta o pierde paquetes **recupera un keyframe del flujo compañero** y sigue decodificando el stream normal. Es decir, el cliente lo pide al servidor: hay lazo, pero al servidor, no al codificador. Es la misma celda de la tabla que tu propuesta.

**Hallazgos que te afectan directamente:**
- La calidad perdida en general es baja, pero en casos raros la **deriva crece hasta hacerse visible**.
- En **H.264**, el peor caso venía de la **interpolación de medio píxel**. Se evita modificando o desactivando la estimación de movimiento subpíxel. Esto toca tu reproducción en H.264.
- Requisitos por códec: TMVP desactivado; parameter sets iguales o reenviados; en HEVC, misma resolución dentro del GoP.

**Patentes de la misma idea.** *Fast recovery of video quality using companion streams* ([US 12720109](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12720109)) y *Systems and methods for fast resolution recovery in mixed-resolution HESP streams* ([US 12647608](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12647608)); titular **[por verificar]**. Antes, en IPTV: *Video data loss recovery using low bit rate stream in an IPTV system* ([US 2010/0046634](https://patents.justia.com/patent/20100046634)).

## 2. SEI para ocultamiento y recuperación

- **Clásicas de H.264 (Anexo D, 2003):**
  - *Spare picture SEI*: indica qué zonas de una imagen ya decodificada pueden reemplazar a una referencia perdida ([descrita en esta patente](https://patents.justia.com/patent/8520733)).
  - *Scene information SEI*: usada para elegir el método de ocultamiento, espacial si hubo cambio de escena ([patente](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8107539)).
  - *Recovery point SEI*: marca desde dónde se puede arrancar sin IDR.
  - El estándar define la sintaxis, pero no cómo debe usarlas el decodificador. Cada implementación decide.
- **H.274 v4 (enero 2026):** agrega 15 SEI nuevas, entre ellas optimización del codificador, tiempos de la imagen fuente, contenido firmado digitalmente, video facial generativo y restricciones de uso de IA. **Ninguna de resiliencia a errores** según lo que encontré ([ITU-T](https://www.itu.int/epublications/ru/publication/itu-t-h-274-v4-2026-01-versatile-supplemental-enhancement-information-messages-for-coded-video-bitstreams/en), [MPEG 154](https://www.mpeg.org/meetings/mpeg-154/)). **[por verificar]** con la lista completa del estándar.
- **AGiLE (MMSys 2024):** el único trabajo reciente que lleva un keyframe completo dentro de una SEI, y solo para que entren espectadores nuevos ([ACM](https://dl.acm.org/doi/10.1145/3625468.3647609)).
- **Riesgo práctico:** Chrome m128 introdujo un error en el depaquetizador H.264 que afecta las SEI cuando hay pérdida ([nota de Dolby](https://support.dolby.io/hc/en-au/articles/11057317291663-Playback-Issues-with-SEI-Messages-in-H-264-Streaming)). Meter datos grandes en SEI no es inocuo.

## 3. Recuperación de pérdidas 2024–2026 (contexto)

| Trabajo | Idea | Relación con la propuesta |
|---|---|---|
| B. Wu et al., **ACM MM 2024**, *Toward Timeliness-Enhanced Loss Recovery for Large-Scale Live Streaming* ([doi](https://doi.org/10.1145/3664647.3681423)); versión de revista **AutoRec** en IEEE ToN 2025 ([arXiv](https://arxiv.org/pdf/2511.22046)); borrador IETF de noviembre 2025 ([draft-wu-moq-recovery](https://www.ietf.org/archive/id/draft-wu-moq-recovery-for-video-streaming-00.html)) | Retransmisión más rápida sobre QUIC, medida en hasta 50 millones de streams | Actúa a nivel de paquete. Confirma que la pérdida en live a gran escala es un problema real. |
| Z. Meng et al., **NSDI 2024**, *Hairpin* ([USENIX](https://www.usenix.org/conference/nsdi24/presentation/meng)) | Retransmisión y FEC desde el edge para video interactivo | Recuperación en el edge, pero de paquetes, no del decodificador. |
| Y. Cheng et al., **NSDI 2024**, *GRACE* ([arXiv](https://arxiv.org/pdf/2305.12333)) | Códec neuronal entrenado para tolerar pérdida | Otro enfoque: cambiar el códec. |
| X. Jin, L. Zhang, H. Wang, L. Cui, **NOSSDAV 2026**, *Fast Loss Recovery for Real-Time Video Streaming* ([doi](https://dl.acm.org/doi/pdf/10.1145/3798065.3798066)) | Refresco intra selectivo de macrobloques para cortar la propagación | Resincronización parcial, del lado del codificador. |
| A. Ansari et al., **IEEE ISM 2025**, *A First Look at Open-GoP Streaming with AV1 S-Frames* ([IEEE](https://ieeexplore.ieee.org/document/11366700/)) | S-frames de AV1 como puntos de entrada | Para cambios de calidad y stalls, no para pérdida. |
| IETF MoQ, reunión de abril 2026 ([minuta](https://datatracker.ietf.org/doc/minutes-interim-2026-moq-13-202604131630/)) | Entrar a mitad de un grupo es indecodificable con video predictivo; no se adoptó REWIND | Es el mismo problema de los puntos de entrada, sin resolver en MoQ. |

**Práctica en SFU de WebRTC.** Se cachea el último keyframe para quien recién entra, pero los PLI se reenvían al emisor ([ejemplo](https://github.com/moadabdou/Kith/issues/81), [webrtc-rs](https://github.com/webrtc-rs/sfu)). Un keyframe cacheado está viejo: los P actuales no dependen de él. Con I-headers cada 2 s, el edge sí tendría un punto de entrada reciente.

## 4. Antecedentes clásicos (para no venderlos como nuevos)

- **SP/SI frames** (H.264 Extended, 2003): representación alternativa de un frame para conmutar sin deriva. M. Karczewicz, R. Kurceren, IEEE TCSVT 2003.
- **J. Boyce, A. Tourapis**, *Fast efficient channel change*, **ICCE 2005** ([RG](https://www.researchgate.net/publication/4143431_Fast_efficient_channel_change_set-top_box_applications)): I extra de baja tasa para entrar al canal sin I frecuentes. Es el origen de la idea.
- **RFC 6285** (2011), RAMS ([RFC](https://www.rfc-editor.org/rfc/rfc6285)), y **Cisco VQE**: un servidor en el edge que retransmite pérdidas y, al cambiar de canal, envía una ráfaga desde su caché ([guía](https://www.cisco.com/c/en/us/td/docs/video/cds/cda/vqe/3_5/user/guide/vqe_guide3_5.pdf)).
- **HESP** (draft-theo-hesp, 2021–2024): flujo de inicialización (keyframes) más flujo de continuación ([draft-06](https://www.ietf.org/archive/id/draft-theo-hesp-06.html)). Es la versión fuera de banda del I-header de AGiLE.

## 5. Qué queda para el proyecto

Ya no se puede decir "nadie entrega un intra extra a quien perdió paquetes". Lo que queda, de más a menos defendible:

1. **Dentro del stream y no en un flujo aparte.** AGiLE ya fabrica y transporta los I-headers dentro de SEI hasta el edge; keyframe injection necesita un segundo flujo y un pedido del cliente. La propuesta conecta dos líneas que parecen no citarse: no encontré evidencia de que AGiLE cite keyframe injection. **[por verificar]** en la bibliografía del PDF de AGiLE; si no la cita, es un buen argumento de "anomalía".
2. **Quién decide.** En keyframe injection pide el cliente. Con SRT, el edge sabe qué paquetes descartó y puede entregar el I-header sin que nadie lo pida.
3. **Codificador embebido.** Doble codificación en un STM32 con H.264 por hardware. Gante trabajó con codificadores de software **[por verificar]**.
4. **Transporte.** SRT (contribución en vivo, UDP) en vez de HESP (HTTP).

**Para la reproducción.** El resultado H.264 de Mareen et al. (calidad al entrar por un keyframe inyectado y la deriva por medio píxel) mide lo mismo que la Fig. 12 de AGiLE, pero directamente para reparar pérdidas. Conviene reproducir ese, o los dos.

## 6. Cambios sugeridos a la presentación

- **Diapositiva 8 (tabla):** agregar *Keyframe injection (Mareen et al., 2021–2024)*: lazo al codificador "No" (pide el cliente al servidor); costo con red sana "No" (solo a quien lo pide, más el flujo compañero en el servidor). La fila "¿?" pasa a ser "Propuesta: lo mismo, dentro del stream (SEI) y decidido por el edge".
- **Diapositiva 10 (anomalía):** "Keyframe injection ya demostró que un intra extra repara la pérdida sin lazo al codificador. AGiLE ya fabrica esos intras dentro del stream… y los descarta para quien perdió paquetes." La idea fuerte se mantiene.
- **Diapositiva 12:** reproducir el resultado H.264 de Mareen et al. (o ambos).
- **Referencias:** agregar Mareen et al., MTAP 2024 (y Van Wallendael et al., Electronics 2021).
