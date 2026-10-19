# Apunte IPD438 — transcripción

Transcripción del cuaderno (5 páginas, fotos del 19-10-2026). Se respeta la redacción original. Convenciones:

- `[?]` lectura dudosa; `[ilegible]` no se pudo leer.
- ~~tachado~~ = tachado en el original.
- `→`, `↳`, `⇒` = flechas del original.
- Las notas `[N. del T.: ...]` son mías, no están en el cuaderno.

---

## Página 1

**Proyecto IPD438**

**1. Contenidos Previos**

**i) Códec predictivo, Error propagation**

- La pérdida se arrastra hasta el próximo IDR.
  - \# Wang & Zhu, *Error control and concealment for video communications: a review*, Proc. IEEE 1998.

**ii) VCL / NAL separation in H.264,**

NAL header: (forbidden_zero_bit, nal_ref_idc, nal_unit_type)

NAL types:

| Tipo | Contenido |
|---|---|
| 1 | slice no-IDR |
| 5 | IDR `[N. del T.: escrito sobre un 2 corregido]` |
| 6 | SEI |
| 7/8 | SPS / PPS |
| 9 | delimitador |

Formato Annex B: start codes, y bytes preventivos de emulación.

\# ¿access unit?

\# Wiegand et al., *Overview of the H.264/AVC video coding standard*, IEEE TCSVT 2003.

⇒ \* (continúa en la página 2)

---

## Página 2

\*:

**iii) slice header y gestión de referencias (!!!)**
(frame_num, POC, DPB, marcado de referencias)

- → I-header NO es IDR,
  - [IDR] ↳ vacía DPB, reinicia frame_num.
  - los P siguientes apuntan [?] solo IDR. `[N. del T.: la idea es que, si el I-header fuera IDR, los P siguientes no encontrarían la referencia con la que fueron codificados]`
  - → tiene que ser slice I no-IDR que ocupe el lugar del P que reemplaza.
- → Multi-Referencia ⇒ Rompe Recuperación, un B (P) puede apuntar antes del I-H, no sirve.
  - \# AGiLE: cada P referencia solo el anterior.

**!!! iv) SEI (Annex D – H.264)**

- payload Type 5: I-H. ← "aunque no sea IDR"
- payload Type 6: engaña al decoder.

`[N. del T.: la flecha de "aunque no sea IDR" apunta a la línea del tipo 5; por contenido calza con el tipo 6 (recovery point): le indica al decodificador que puede arrancar desde un I aunque no sea IDR]`

**v) Encapsulación:**

- RTP: NAL simple, STAP-A, FU-A. Liviano (Edge).
- MPEG-TS: ES → PES (PTS/DTS) … → TS packets (188 B), continuity_counter: detección de pérdida.
  - ↖ SRT lo transporta.

---

## Página 3

**\* vi) Ocultamiento de errores en decoder:**

- Disimula daño.
- Nosotros lo eliminamos.
- ↳ congelar, copiar frame anterior, compensación por movimiento.

**\* vii) STM32:** Revisar TMVP de AGiLE, [el] códec podría ser Constrained Baseline, sin B-frames.

**II. SOTA:**

- FrameTrace
- AGiLE

} Recovery Point SEI.
  Refresco Intra Periódico,
  PLI / RPSI / LTR (RFC 8834)

[recuadro] PODRÍA estar hecho → \# Redundant Coded Pictures H.264

**III. Motivación:** – Sin propagación de error no hay anomalía.

**IV. Objetivo:** Mejorar "Métricas":

Métricas:

- Duración del Artefacto.
- Severidad: VMAF / PSNR down × frame contra referencia.
- Congelamiento: FRR, stall duration.
  - Lo [?] ocultar ≠ íntegro.

→ Reducir duración de Artefactos, al mismo BW en el último salto que un GOP largo, cercanos a short GoP sin costo permanente.

---

## Página 4

**V. Resultados a ~~Repro~~ Producir.**

\# Fig 12, AGiLE, VMAF degradation vs I-H index — [recuadro] **H.264**

- ↳ codificar
- ↳ Annex B separation (FFMPEG),
- P → I-H, concatenation, VMAF measure.

**VI. Referencias:**

- \* FrameTrace (EMS/SIGCOMM 2026) `[N. del T.: el paper es de 2025 (EMS '25)]`
- \* AGiLE (MMSys 2024)
- Wiegand 2003
- Wang & Zhu 1998
- Sjöberg 2012
- RFC 6184
- ITU-T H.264 (Annex B, D)
- RFC 8834

**VII. Costos:**

- Exactitud:
  - Reconstruir desde I-Header deriva hasta el próximo IDR.
  - Reducir duración de artefacto, dejar uno leve.
- Worst Moment Burst: SIZE_I >> SIZE_P — Por eso LTR evita esto.
  - Empeora congestión.
- Códec: Doble, en cada frontera:
  - Costo en → Cómputo, → Memoria, → Energía } STM32
- Sobrecarga Ingest: AGiLE → +2.8 % datos, H.265
  - ↳ ? " H.264
- Edge State: No hay lazo al códec, pero necesitamos estado del sender → receptor [?].

---

## Página 5

- Granularidad: Recuperación posible solo en fronteras pseudo-GOP.
- Content-Dependant: AGiLE: ~~Large~~ Long GoP empeora en contenido con mucho movimiento. \# BD-bitrate
  - [al margen] la mejora no es universal.
- Compatibilidad: Decoders sin funciones de recovery point SEI pueden negarse a arrancar desde I no-IDR.

**Index:**

| | Sección | Puntaje |
|---|---|---|
| I. | Contenidos Previos | 15 pts |
| II. | SOTA | 20 pts |
| III. | Motivación (y problema) | 15 pts |
| IV. | Objetivo | 10 pts |
| V. | Resultados a Producir | 5 pts |
| VI. | Referencias | 5 pts |
| VII. | Costos | — |
| | **Total contenido** | **70 pts** |

- \# 15 min + 5 min (preguntas).
- \# Apoyo Visual.
- \# T. Usage (Zoom, presentación, etc.)
- \# Lenguaje
- \# ¿**Promesa**? ¿Idea Fuerte de la presentación?

} 30 pts

→ Slide 1: [?]

---

## Observaciones

1. **FrameTrace:** en el apunte dice SIGCOMM 2026. El paper es de EMS '25 (ACM SIGCOMM **2025**).
2. **Tipo 5 vs tipo 6 de SEI:** el tipo 5 (`user_data_unregistered`) es donde nosotros pondríamos el I-header; AGiLE solo dice "SEI", sin el tipo. El tipo 6 (`recovery_point`) es el que autoriza al decodificador a arrancar desde un I no-IDR.
3. **RFC 8834** trata el uso de RTP en WebRTC y cubre la realimentación PLI, FIR y RPSI. LTR (referencia de largo plazo) es una herramienta del códec, no de esa RFC.
4. **SRT** no está entre tus referencias. Si va en la presentación, hay que citarlo: M. Sharabayko et al., *The SRT Protocol*, IETF Internet-Draft draft-sharabayko-srt-01, 2021.
