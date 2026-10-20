# El mundo H.264 en simple

Para estudiar, no para la presentación. Cada pregunta tiene primero la respuesta corta y después, si hace falta, un poco más.

---

## 1. El camino de una imagen hasta la red

```
imagen ─► macrobloques ─► slice ─► NAL ─► access unit ─► PES ─► paquetes TS ─► paquete SRT ─► UDP
          (16×16 px)      (trozo    (caja    (todas las     (le pone  (188 B c/u)   (7 TS =
                          de        de red)  NAL de un      la hora)               1316 B)
                          imagen)            frame)
```

| Pieza | Qué es | Dato clave |
|---|---|---|
| **Macrobloque** | Cuadrado de 16×16 píxeles. Es la unidad con que H.264 codifica. En HEVC y VVC se llama CTU. | Cada uno se codifica *intra* (desde la misma imagen) o *inter* (desde otra imagen). |
| **Slice** | Un grupo de macrobloques seguidos, con una cabecera. Se decodifica solo. | Un frame tiene uno o más slices. En el STM32N6 se elige con `sliceSize`. |
| **NAL** | La "caja" en que H.264 entrega datos a la red. | **Una NAL por slice, no por macrobloque.** También hay NAL que no son imagen: SPS, PPS y SEI. |
| **Access unit** | Todas las NAL de un frame. | Con un slice por frame, access unit ≈ frame. |
| **PES** | Envoltorio del estándar MPEG-TS que le agrega a cada frame su **hora**: cuándo decodificarlo (DTS) y cuándo mostrarlo (PTS). | **Aquí entra el PES:** un PES por frame, después del access unit. |
| **Paquete TS** | El PES se corta en paquetes de 188 bytes. | Cada uno trae un contador de 4 bits: si salta, se perdió algo. |
| **Paquete SRT** | 7 paquetes TS = 1316 bytes. SRT los manda sobre UDP. | SRT agrega retransmisión y plazo de entrega. |

**¿Dónde van SPS y PPS?** Son NAL con la configuración del video: perfil, resolución, cómo se numeran los frames. El decodificador no puede empezar sin ellas. Van al comienzo del stream y normalmente se repiten antes de cada IDR. En el STM32N6 eso se elige con `idrHeader`.

## 2. Tipos de frame

| Tipo | Qué necesita para decodificarse | Comentario |
|---|---|---|
| **I** (intra) | Nada: es una imagen completa. | Grande. |
| **IDR** | Nada. Además le dice al decodificador "borra todo y empieza de cero": vacía las referencias y reinicia la numeración. | El punto de entrada "duro". |
| **P** (predicho) | Una imagen **anterior**. | Lleva solo lo que cambió. Chico. |
| **B** (bipredicho) | Imágenes **anteriores y posteriores**. | Obliga a reordenar frames, lo que agrega latencia. **El STM32N6 no hace B.** |

**¿Hay otros puntos de entrada además del IDR?** Sí:
- **I no-IDR con Recovery Point SEI:** un I normal más una SEI que le dice al decodificador "puedes empezar aquí".
- **Refresco intra gradual** (GDR o *intra refresh*): en vez de un I grande, se refresca una franja de macrobloques en cada frame; al cabo de N frames la imagen está limpia.
- En HEVC y VVC hay más tipos (CRA, BLA, GDR); en H.264, los de arriba.

## 3. ¿Un P puede ser keyframe?

**No.** Un keyframe (I) se decodifica solo; un P siempre necesita una imagen anterior.

Lo que hace *P-frame injection* (Mareen et al., 2023): en vez de mandar un I completo, mandan un **P de reparación** que se apoya en una imagen **anterior a la pérdida**, que el receptor todavía tiene bien. Es más chico que un I (en un ejemplo, unas 2 veces un P normal), pero solo sirve si el receptor tiene guardada esa imagen. Es la misma idea de la referencia de largo plazo (LTR).

## 4. AGiLE y keyframe injection en una frase cada uno

- **AGiLE** (Chen et al., ByteDance, 2024): GoP largo de 10 s, más un **I-header** cada 2 s, que es la misma imagen codificada además como I. Viaja **dentro del stream, en una SEI**. El edge se lo da solo a los espectadores nuevos.
- **Keyframe injection** (Mareen y Van Wallendael, Universidad de Gante, 2021–2024): stream con GoP largo, más un **flujo aparte solo de keyframes**. El reproductor que entra **o pierde paquetes** pide un keyframe de ese flujo y sigue con el normal. Lo estudiaron en H.264, HEVC y VVC; es la base de HESP.

## 5. SRT frente a RTP y UDP puro

| | UDP puro | RTP sobre UDP | SRT sobre UDP |
|---|---|---|---|
| Detecta pérdida | No | Sí (número de secuencia) | Sí |
| Recupera pérdida | No | Solo si le agregas NACK/retransmisión o FEC | **Sí, integrado**: retransmite dentro de un plazo fijo (120 ms por defecto) |
| Lo que llega tarde | — | Depende de la aplicación | **Se descarta**: esa pérdida es la que reparamos |
| Cifrado | No | Aparte (SRTP) | Integrado (AES) |
| ¿El emisor sabe qué se perdió? | No | Si hay realimentación RTCP | **Sí**: lleva la cuenta de lo que descartó |

**Por qué SRT:** trae todo armado y, sobre todo, el emisor (nuestro edge) sabe qué no llegó. Así decide a quién darle el I-header sin preguntarle al codificador ni esperar un pedido.

## 6. ¿Qué SEI usaríamos?

Solo dos:
1. **Tipo 5, `user_data_unregistered`:** para transportar el I-header dentro del stream.
2. **Tipo 6, `recovery_point`:** para que el decodificador acepte empezar desde un I que no es IDR.

## 7. ¿El STM32N6 lo permite? (revisado en su API oficial)

Fuente: `Middlewares/Third_Party/VideoEncoder/inc/h264encapi.h` y `source/h264/H264EncApi.c` del repositorio [STM32CubeN6](https://github.com/STMicroelectronics/STM32CubeN6). El codificador es de VeriSilicon.

| Lo que AGiLE necesita | ¿Lo trae? | Cómo |
|---|---|---|
| Elegir por frame IDR, P o **I no-IDR** | **Sí** | `H264ENC_INTRA_FRAME` (IDR), `H264ENC_PREDICTED_FRAME` (P), `H264ENC_NONIDR_INTRA_FRAME` (I no-IDR) |
| Una sola referencia | **Sí** | `refFrameAmount = 1` (con 2: última + largo plazo) |
| Referencia de largo plazo (para P de reparación) | **Sí** | modos `ipf` / `ltrf`, `longTermPicRate` |
| Codificar dos versiones de la misma imagen | **Probablemente** | VENC es multi-instancia: puede intercalar frames de varios streams (según la wiki de ST) |
| Meter el I-header en una SEI | **No, tal cual** | `H264EncSetSeiUserData` acepta máximo **2048 bytes**; un I-header pesa decenas de kB. Hay que armar esa SEI por software. |
| SPS/PPS en cada IDR | Sí | `idrHeader` |
| Refresco intra (alternativa de comparación) | Sí | `cirStart`, `cirInterval`, `gdrDuration` |

**Pendientes:**
1. **Numeración:** el I-header debe llevar el número de frame (`frame_num`) del P que reemplaza. Si sale de una segunda instancia, su número no calza. Probablemente hay que reescribir ese campo de la cabecera del slice; es de largo fijo, así que no hay que mover bits.
2. **Rendimiento:** el datasheet dice 1080p15 y 720p30; otras fuentes dicen 1080p30. Con doble codificación conviene 720p.
