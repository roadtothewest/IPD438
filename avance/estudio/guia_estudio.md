# Guía de estudio — avance IPD438

Ordenada de abajo hacia arriba: cada bloque usa el anterior. Para cada uno: qué tienes que poder explicar, lo esencial y preguntas para autoevaluarte (respóndelas en voz alta, sin mirar). La columna "Diapo" dice dónde lo usas.

Marcas: **[medido]** sale de nuestro experimento; **[paper]** verificado en el PDF; **[por verificar]** de memoria o de búsqueda, no citar sin revisar.

| Bloque | Tema | Diapo | Prioridad |
|---|---|---|---|
| 1 | Codificación predictiva, GoP, I/P/IDR | 2 | Alta |
| 2 | `frame_num`, POC, DPB: por qué el IDR es el peor caso | 2, R2, 9 | Alta |
| 3 | NAL, Annex B, SEI, RTP | 3 | Alta |
| 4 | Mecanismos de recuperación (el mapa) | 4 | Alta |
| 5 | FrameTrace | 5 | Alta |
| 6 | AGiLE | 6, 7, 9 | Alta |
| 7 | Métricas: PSNR, VMAF, FRR, BD-bitrate | 2, 5, 6, 8 | Media |
| 8 | Transporte: por qué la pérdida llega al decodificador | 4, 7 | Media |
| 9 | La propuesta, sus costos y la pregunta abierta | 7, 8, R3, R4 | Alta |
| 10 | El experimento de la diapositiva 2 | 2, 9 | Media |

---

## Bloque 1 — Codificación predictiva y propagación

**Tienes que poder explicar:** por qué una pérdida no se queda en un frame, y por qué dura hasta el próximo intra.

- Un frame **P** se codifica como predicción desde un frame anterior (vectores de movimiento y residuo). El decodificador reconstruye el P **sumando** el residuo a la referencia que tiene. Si la referencia está mal, el P queda mal aunque haya llegado entero, y sirve de referencia mala para el siguiente.
- Un frame **I** se codifica sin mirar otros frames. Corta la cadena.
- **GoP**: distancia entre intras. A 30 fps con GoP 30 hay un intra por segundo.
- **IDR** (Instantaneous Decoding Refresh) es un I que además le dice al decodificador "olvida todo": vacía el buffer de referencias (DPB) y reinicia la numeración. Nada posterior puede referenciar algo anterior. Un **I no-IDR** decodifica solo, pero no garantiza eso: con varias referencias, un P posterior podría apuntar a frames de antes del I.
- Con **una sola referencia** (lo que usamos), cada P mira solo al anterior; entonces cualquier I, IDR o no, corta la propagación.
- **[medido]** 30 fps, GoP 30: perder un P a mitad de GoP daña 15 frames (0,5 s); perder el I, 30 frames (1 s); perder el IDR, 30 frames y además 13 congelados.

**Autoevaluación**
1. Si pierdo el P número 5 de una GoP de 30, ¿cuántos frames quedan dañados y por qué?
2. ¿Por qué perder el primer P después del intra es casi tan malo como perder el intra, pero menos severo? (pista: el P perdido se oculta con el intra, que es casi igual.)
3. ¿Qué diferencia hay entre un I y un IDR? ¿Cuándo da lo mismo cuál pierdo?
4. ¿Por qué, con varias referencias, un I no-IDR no garantiza recuperación?

## Bloque 2 — `frame_num`, POC y DPB: por qué el IDR es el peor caso

**Tienes que poder explicar:** la fila 3 de la diapositiva 2 (13 congelados) y por qué el I-header en H.264 debe ser I no-IDR.

- **`frame_num`**: contador en la cabecera de cada slice; sube en 1 por cada frame de referencia y vuelve a 0 en cada IDR. Es módulo `MaxFrameNum` (en nuestro flujo, 16). Sirve para detectar huecos: si llega 7 después de 5, falta el 6.
- **POC** (Picture Order Count): orden de **presentación**. Con B-frames difiere del orden de decodificación. Hay tres modos; sin B-frames x264 usa el **tipo 2**, en que el POC se deriva de `frame_num` (≈ 2 × número de frame desde el último IDR).
- **DPB** (Decoded Picture Buffer): las referencias guardadas. `max_num_ref_frames` (en nuestro flujo, 1) dice cuántas.
- **[medido]** Qué pasa al perder el IDR, con FFmpeg 6.1 (visto en el log de depuración):
  1. El frame 29 tenía `frame_num` 13 y POC 58. El IDR perdido reiniciaba todo a 0.
  2. Llega el P siguiente con `frame_num` 1. FFmpeg ve un hueco (13 → 1). Como `max_num_ref_frames` = 1, rellena solo un frame y no se da cuenta de que hubo un reinicio.
  3. Calcula para ese P un POC de 34, **menor** que el 58 ya mostrado. Lo descarta por desordenado ("no picture ooo" en el log). Lo mismo con los 12 frames siguientes, hasta que el POC vuelve a alcanzar 58.
  4. Resultado: 13 frames sin entregar (el perdido + 12) y después artefactos hasta el próximo IDR.
- Al perder un **I no-IDR**, `frame_num` sigue su curso: el hueco es de 1 frame, el decodificador oculta y sigue. Artefactos, sin congelamiento.
- **Consecuencia para el diseño:** si el I-header fuera IDR, al entrar por él el decodificador vaciaría el DPB y reiniciaría la numeración, y los P siguientes (codificados contra el P original, con su `frame_num`) no calzarían. El I-header debe ser **I no-IDR con el `frame_num` y POC del P que reemplaza**. Algunos decodificadores no aceptan arrancar desde un I no-IDR sin un **Recovery Point SEI** (payloadType 6) que lo autorice. **[por verificar]** con el decodificador del receptor real.
- Ojo: el congelamiento es comportamiento de FFmpeg, no del estándar. Otro decodificador puede mostrar basura en vez de congelar. Dilo así si preguntan.

**Autoevaluación**
1. ¿Qué hace un IDR que no hace un I?
2. ¿Por qué FFmpeg descarta 12 frames y no 29?
3. ¿Por qué el I-header no puede ser IDR?
4. ¿Para qué sirve el Recovery Point SEI?

## Bloque 3 — NAL, Annex B, SEI y RTP

**Tienes que poder explicar:** qué viaja por la red y por qué el IDR es el frame más expuesto.

- H.264 separa la **VCL** (lo que codifica la imagen: slices) de la **NAL** (cómo se empaqueta). Cada NAL unit tiene 1 byte de cabecera: `forbidden_zero_bit` (1 bit), `nal_ref_idc` (2 bits, importancia como referencia), `nal_unit_type` (5 bits).
- Tipos que importan: **1** slice no-IDR (P o I no-IDR), **5** slice IDR, **6** SEI, **7** SPS, **8** PPS, **9** AUD.
- **SPS/PPS**: parámetros de secuencia y de imagen (resolución, perfil, `log2_max_frame_num`, tipo de POC...). Sin ellos no se decodifica nada. x264 los repite antes de cada IDR.
- **Access unit**: todas las NAL de un frame. En nuestro flujo, 1 slice por frame (las NAL de parámetros van pegadas al IDR).
- **Annex B**: formato byte stream; las NAL van separadas por start codes `00 00 01` o `00 00 00 01`. Para que un start code no aparezca dentro de los datos se insertan bytes de **prevención de emulación** (`00 00 03`).
- **SEI** (Anexo D): información suplementaria dentro del stream. El decodificador puede ignorarla sin afectar la decodificación. Tipos relevantes: 5 `user_data_unregistered` (candidato para transportar el I-header; **decisión nuestra, AGiLE solo dice "SEI"**), 6 `recovery_point`.
- **RTP, RFC 6184**: tres formas de meter NAL en paquetes. NAL simple (una por paquete); **STAP-A** (tipo 24, varias NAL chicas en un paquete, típico para SPS+PPS); **FU-A** (tipo 28, una NAL grande en fragmentos). Si se pierde un fragmento, la RFC dice que el receptor debería descartar los fragmentos siguientes de esa NAL; la NAL queda rota desde ahí.
- **[medido]** IDR de 55 kB = 47 paquetes de 1200 B; P típico 2 kB = 2 paquetes. Con pérdida independiente p, la probabilidad de dañar un frame de n paquetes es 1 − (1 − p)^n. Con p = 1 %: 38 % para el IDR, 2 % para un P. Un tercio de los paquetes del clip son de IDR.
- Supuesto a declarar si preguntan: pérdida **independiente**. Con ráfagas (modelo Gilbert-Elliott) los números cambian.

**Autoevaluación**
1. Dibuja la cabecera NAL y di qué tipo tiene un IDR, un P y un SEI.
2. ¿Por qué perder un fragmento FU-A arruina la NAL entera?
3. Calcula la probabilidad de dañar un frame de 10 paquetes con 2 % de pérdida.
4. ¿Qué significa que el decodificador "puede ignorar" un SEI y por qué eso le sirve a AGiLE?

## Bloque 4 — Mecanismos de recuperación (el mapa)

**Tienes que poder explicar**, para cada uno: quién actúa, qué cuesta con la red sana y qué cuesta cuando hay pérdida.

| Mecanismo | Qué hace | ¿Lazo al codificador? | Costo con red sana | Costo con pérdida |
|---|---|---|---|---|
| NACK + retransmisión (RFC 4585, RTX RFC 4588) | El receptor pide el paquete de nuevo | No (al emisor o relay) | Nada | Un RTT; inútil si vence el plazo |
| FEC (ULPFEC RFC 5109, FlexFEC RFC 8627) | Paquetes redundantes | No | Siempre (overhead) | Falla con ráfagas |
| PLI / FIR (RFC 4585 / RFC 5104) | El receptor pide un intra | Sí | Nada | RTT + un IDR para **todos** en 1-a-muchos |
| LTR + RPSI | El codificador predice desde una referencia que el receptor confirmó | Sí | Estado por receptor | RTT |
| GoP corto | Intras frecuentes | No | Siempre | — |
| Intra refresh + Recovery Point SEI | Refresca una franja intra por frame (GDR) | No | Siempre | — |
| Redundant pictures (H.264, Baseline/Extended) | Segunda codificación de la misma imagen, siempre enviada | No | Siempre | — |
| GoP adaptativo (FrameTrace) | El cliente reporta, el codificador acorta el GoP | Sí | Bajo | Más intras para todos |
| **Propuesta** | El edge entrega el I-header a quien perdió | **No** | **Nada en la última milla** | Un intra solo al dañado |

- NACK y FEC trabajan a nivel de **paquete**: intentan que la pérdida no llegue. Lo demás trabaja a nivel de **decodificador**: lo resincroniza cuando la pérdida ya llegó.
- Cuidado: NACK también es "sin lazo al codificador y sin costo con red sana". La diferencia es que NACK tiene que recuperar **ese** paquete dentro del plazo; la propuesta no recupera el paquete, resincroniza en la siguiente frontera, llegue cuando llegue. Prepárate para esta pregunta.
- **Redundant pictures** es lo más parecido conceptualmente (una segunda representación de la imagen), pero se envía siempre a todos. **[por verificar]** antes de afirmar novedad frente a esto y a los slices SP/SI.

**Autoevaluación**
1. ¿Por qué PLI es caro en un CDN con miles de espectadores?
2. ¿En qué se diferencia la propuesta del intra refresh con Recovery Point SEI?
3. ¿Por qué no basta con NACK?
4. Ubica cada mecanismo en el mapa sin mirar la diapositiva.

## Bloque 5 — FrameTrace [1]

B. Denizer, L. Winkel, O. Landsiedel. EMS '25 (workshop de ACM SIGCOMM 2025), pp. 31–36. 6 páginas, open access. **[paper]**

- **Problema:** las herramientas miden por conexión o por segmento y esconden dónde ocurren los stalls. Nadie había estudiado el trade-off latencia/calidad **por frame** en MoQ.
- **Diseño:** 4 marcas de tiempo por frame (captura, escritura al segmento, llegada al cliente, render). Sincronización con PTP. Emulación de red con tc-netem.
- **Métricas propias:** **FDR** (frames recibidos / enviados: mide la red) y **FRR** (frames renderizados / enviados: mide la experiencia).
- **Resultados que usas:**
  - GoP vs calidad (Big Buck Bunny 720p, 24 fps, 1 % de pérdida, 500 ms): **VMAF 72,6 con GoP 0,5 s vs 55,7 con GoP 2 s**.
  - Controlador adaptativo (umbrales de FDR, en el cliente): GoP medio **2,02 / 1,56 / 0,88 s** con 0 / 10 / 20 % de pérdida.
  - Bonus: con 10 % de pérdida, LL-DASH colapsa (FRR 14,94 %, ~28 s detrás del vivo); MoQ no.
- **Limitación para ti:** el controlador necesita realimentación cliente → codificador; el refresco lo pagan todos. No caracteriza el cruce entre GoP largo y corto.
- **Dato de defensa:** cita a AGiLE como técnica de *video on demand*; AGiLE es de **live**.
- **No** habla de H.264, H.265 ni NAL: es agnóstico al códec. No lo presentes como literatura NAL.

**Autoevaluación**
1. ¿Qué diferencia hay entre FDR y FRR? ¿Cuál usas y por qué?
2. ¿Qué demuestra la comparación GoP 0,5 s vs 2 s y qué no demuestra?
3. ¿Dónde está el lazo en FrameTrace?

## Bloque 6 — AGiLE [2]

C. Chen, W. Yin, Z. Huang, S. Shi (ByteDance, SJTU). MMSys '24, pp. 34–44. Paper completo. **[paper]**

- **Problema:** el edge cachea el último GoP; un espectador nuevo debe empezar en un I. GoP corto → buen tiempo de entrada, mala eficiencia. Pasar de GoP 2 s a 10 s beneficia a 11 de 20 clips de Douyin (los de poco movimiento).
- **Pseudo-GOP:** separa unidad de **codificación** (GoP largo, G_L = 10 s) de unidad de **transmisión** (pseudo-GOP, 2 s). Cuatro I-headers por GoP.
- **I-header:** la misma imagen fuente del P de la frontera, codificada **además** como I. No cambia las referencias: el P siguiente sigue apuntando al P, no al I-header. Viaja **íntegro dentro del SEI** de ese P (no especifica qué payloadType).
- **Edge:** parsea el SEI, guarda el I-header. Nuevo → I-header + P siguientes. Conectado → se descarta.
- **Implementación:** doble codificador (primario normal, secundario solo para I-headers). TMVP desactivado (costo ~0,23 % de BD-bitrate). Mismos parámetros de tasa para el I-header que para el resto.
- **Deriva:** el I-header no reconstruye exactamente igual que el P (cuantizaciones distintas), así que quien entra por él arrastra un error leve hasta el próximo I real.
- **Resultados:** BD-bitrate −3,54 % (fijo) / −3,71 % (adaptativo) vs GoP fijo de 2 s. I-header = 6,6 % del baseline; datos totales **+2,8 %**. **Fig. 12:** la caída de VMAF disminuye mientras más tarde se entra; entrando por el 1.º, **~1,1** sin B (97,83 → 96,73); peor caso del dataset **2,64**. Imperceptible para los evaluadores.
- **Evaluación offline:** x265, 720p 30 fps; `hevc_mp4toannexb` para separar frames, reemplazar P por I-header, concatenar, VMAF. Esto es lo que reproduces (diapositiva 9).

**Autoevaluación**
1. ¿Qué es un pseudo-GOP y qué es un I-header? (concepto vs herramienta)
2. ¿Por qué hay deriva si la imagen fuente es idéntica?
3. ¿Por qué el +2,8 % "no aumenta el ancho de banda hacia los espectadores" en AGiLE? ¿Y en tu propuesta?
4. ¿Por qué hacen falta dos contextos de codificador?

## Bloque 7 — Métricas

- **PSNR** = 10·log10(255² / MSE), en dB, por frame. Simple y objetiva; la usamos en la diapositiva 2 porque el FFmpeg instalado no trae libvmaf.
- **VMAF** (Netflix): combina varias medidas (VIF, detalle, movimiento) con un modelo entrenado contra opiniones humanas; 0–100. Es la de los papers y la que usarás en la final.
- **FRR**: ver bloque 5. Evita la trampa: congelar la imagen elimina artefactos y destruye la experiencia.
- **Duración del artefacto**: frames desde la pérdida hasta la reconstrucción limpia (idéntica a la decodificación sin pérdida). Es tu métrica principal.
- **BD-bitrate** (Bjøntegaard, VCEG-M33, 2001): se codifica a varios bitrates, se trazan curvas tasa-calidad y se mide la diferencia promedio de bitrate a igual calidad. Negativo = ahorro.

**Autoevaluación:** ¿por qué hacen falta las tres métricas juntas (duración, severidad, congelamiento)? ¿Qué significa −3,5 % de BD-bitrate?

## Bloque 8 — Transporte: por qué la pérdida llega al decodificador

- Sobre **TCP** (HLS, DASH, HTTP-FLV) no hay pérdida para el decodificador: se retransmite y la pérdida se convierte en **stall** (rebuffering), no en artefacto.
- La propuesta aplica donde se descarta lo que llega tarde: **RTP/UDP** (WebRTC), **SRT** (retransmite dentro de una ventana de latencia y descarta lo que no llegó a tiempo, "too-late packet drop"), **MoQ** (puede abandonar objetos o grupos atrasados). **[por verificar]** el mecanismo exacto en el draft vigente de MoQ antes de afirmarlo en el informe.
- **Última milla**: edge → espectador. Es donde ocurre la pérdida que te interesa y donde el costo se multiplica por espectador. En la plataforma, la pérdida va **después** del edge.

**Autoevaluación:** si alguien dice "en streaming moderno no hay pérdida porque todo va sobre QUIC/TCP", ¿qué respondes?

## Bloque 9 — La propuesta, sus costos y la pregunta abierta

- **Cambio mínimo:** la regla del edge pasa de "¿es nuevo?" a "¿es nuevo **o está dañado**?".
- **Qué es gratis:** producir el I-header, llevarlo por el CDN, cachearlo (ya lo hace AGiLE). **Qué se paga:** cada entrega a un dañado en su última milla.
- Frase: *"No elimino el intra. Elimino el intra que se envía a quien no lo necesita."*
- **Costos** (respaldo R4): deriva (~1,1 VMAF); ráfaga en el peor momento (un intra pesa ~20 P en nuestro clip); doble codificación en el STM32; +2,8 % de ingest; estado en el edge; recuperación solo en fronteras de pseudo-GOP; peor en alto movimiento; decodificadores que no arrancan desde I no-IDR.
- **Pregunta abierta: ¿cómo sabe el edge quién perdió?** (a) el receptor avisa: lazo corto al edge, compite con NACK/PLI; (b) el edge infiere por retransmisiones, ACK o congestión: versión fuerte; (c) mandarlo siempre: equivale a GoP corto, no sirve.
- **Riesgo principal:** que el encoder del STM32 no permita doble codificación ni forzar un I no-IDR. Confirmar modelo y encoder es lo primero.

**Autoevaluación:** defiende en 30 segundos por qué tu propuesta no es "lo mismo que PLI" y por qué no es "lo mismo que GoP corto".

## Bloque 10 — El experimento de la diapositiva 2

Código en `avance/experimentos/perdida_gop.py`; figura en `avance/presentacion/figuras.py`.

1. Extrae 90 frames de Big Buck Bunny (640×360) desde el segundo 48,5 (sin cortes de escena) y los trata como 30 fps.
2. Codifica dos veces con x264 a 1 Mbps (VBV 1 s), perfil Baseline, 1 referencia, sin B, 1 slice por frame:
   - A: intra cada 30 frames, todos IDR.
   - B: intra cada 30 frames, pero solo el primero es IDR; los demás se fuerzan como **I no-IDR** con un `qpfile` (tipo `i`).
3. Separa el Annex B en NAL, las agrupa en access units y elimina el frame elegido (con sus NAL pegadas).
4. Decodifica con el H.264 de FFmpeg (vía PyAV), frame a frame con su número; si el decodificador no entrega un frame, el "reproductor" repite el anterior (congelado).
5. Mide por frame: PSNR-Y contra la fuente, si el frame es idéntico al de la decodificación sin pérdida (duración) y si fue entregado (congelamiento).

Para regenerar:

```bash
pip install av numpy matplotlib     # además: ffmpeg, x264 y LaTeX (para la figura)
python3 avance/experimentos/perdida_gop.py big_buck_bunny.mp4 avance/presentacion/datos/perdida_gop.csv
python3 avance/presentacion/figuras.py
```

Limitaciones que debes conocer: el clip es de 24 fps reinterpretado a 30 fps; PSNR en vez de VMAF; un solo decodificador (FFmpeg 6.1); pérdida de frame completo, no de paquete.

**Autoevaluación:** ¿por qué la codificación B sirve como base para generar I-headers en la reproducción?

---

## Preguntas probables y respuesta corta

- **¿En qué se diferencia del Recovery Point SEI / intra refresh?** Ese también es sin lazo, pero refresca siempre y paga eficiencia siempre. Yo reutilizo bits que ya existen para otro fin y solo los entrego a quien perdió.
- **¿Por qué no NACK?** NACK debe recuperar ese paquete dentro del plazo de latencia; si vence o hay ráfaga, la pérdida llega igual. Lo mío actúa después: resincroniza en la siguiente frontera.
- **¿Por qué STM32 y no un servidor?** El lazo cerrado supone un codificador que puede recodificar a pedido y llevar estado por receptor. Un embebido no puede; ahí se ve el valor.
- **¿Por qué H.264 si AGiLE usa H.265?** El mecanismo (SEI + I no-IDR) existe en ambos; H.264 es lo que trae el hardware embebido. La restricción de TMVP de AGiLE probablemente no aplica en H.264 IPPP (**[por verificar]** con el encoder concreto).
- **¿Por qué nadie lo hizo?** FrameTrace cita a AGiLE como VOD: las líneas se citan sin conectarse. No digas "no se han cruzado".
- **¿La ráfaga del intra no empeora la congestión?** Es un costo real (R4). Es el mismo tamaño que el IDR que provocaría un PLI, pero va a un solo receptor y no a todos. Hay que medirlo.
- **¿El congelamiento de la diapositiva 2 depende del decodificador?** Sí, es FFmpeg 6.1. Otros pueden mostrar artefactos en vez de congelar. La duración (hasta el próximo intra) no depende.
- **¿Por qué PSNR y no VMAF en la diapositiva 2?** Para mostrar duración basta PSNR; el FFmpeg disponible no trae libvmaf. En la final, VMAF.

## Cómo seguimos

Propuesta: un bloque por sesión, en orden de prioridad (1, 2, 3, 6, 4, 5, 9, 8, 7). En cada sesión te hago las preguntas de autoevaluación, corregimos lo que falle y pasamos al siguiente. Antes del 20.10, al menos los bloques 1 a 6 y un ensayo cronometrado con el guion.
