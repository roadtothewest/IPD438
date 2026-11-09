# Pendiente para la sesión de emulación (2026-11-09, más tarde)

Esta mañana no se simuló nada. El informe (`informe_avance.tex`) usa solo los resultados ya guardados en `Proyecto/ihdr/results/` (GoP 90). Lo de abajo requiere correr el emulador.

## 0. Preparar
- Los streams del scratchpad se borraron al apagar el PC. Hay que regenerarlos:
  - `ihdr/tools/encode.sh` a partir de `/home/ludicolo/b2p/aspen_alta_calidad.mp4`: produce A (GoP 90), C (GoP 30) y los candidatos de I-header `Bq23`…`Bq50`.
  - Compilar `ihdr` con `cmake` y correr `test_core`.
- Esta vez, guardar los streams dentro del repo, ignorados por git (`ihdr/media/`), y no en el scratchpad.

## 1. Regla de detección simplificada (ecuación 2 del informe)
- En el informe, la regla quedó como `g_s > max(τ_s, r_s + d + T_ACK)`. Si no hubo retransmisión, solo cuenta τ_s.
- Llevar esa misma expresión a `ihdr/host/srt_model.hpp` (`rx_ack`, líneas ~217–226). Hoy usa la forma larga.
- Es equivalente si toda retransmisión enviada cumple `r_s + d ≤ τ_s`, porque el modelo suprime las que llegarían tarde.
- **Verificar:** repetir r1, r2 y r3 con GoP 90 y comprobar que los CSV dan lo mismo. Si cambian, corregir el informe.

## 2. GoP 30: los mismos 4 casos (lo pidió Vicente: una figura por GoP, sin mezclar)
- `evaluate.py` hoy solo corre `srt_gop30`. Hay que agregar una opción `--gop 30` que use C como stream base en los 4 casos (`udp`, `udp+ih`, `srt`, `srt+ih`), con los mismos I-headers ajustados en QP.
- Regímenes iguales a los de GoP 90 (2 % y 20 ms; 4 % y 200 ms; 4 % y 600 ms), con 8 semillas. Guardar en `ihdr/results/gop30/`.
- Medir la tasa de subida de GoP 30 (C, y C + I-header cada 5 P) y escribirla en `SUBIDA["30"]` de `tools/figuras_informe.py`.
- Generar la figura: `python3 tools/figuras_informe.py results/gop30 ../informe 30`.
- En el informe: agregar la figura de GoP 30 (figure*) y una frase que compare GoP 30 con GoP 90 en tasa y calidad. Sacar "(i) GoP 30" del trabajo futuro.

## 3. Más eventos (validez)
- Hoy hay solo 7 cortes de SRT no recuperados en 16 corridas. Subir a unas 32 semillas, o usar un clip más largo, e informar el número de eventos.

## 4. Latencia recomendada
- Repetir los regímenes de 4 % con `--latency-ms 180`: es la recomendación de Haivision para hasta 7 % de pérdida con RTT de 30 ms.
- Comprobar que el resultado se mantiene (se espera que sí, por la ecuación 1).

## 5. Revisar casos raros
- Corte de 20 ms, semilla 3: SRT deja 12 frames dañados y SRT + I-header 97. Confirmar si es deriva en la parte de QP alto contada bajo el umbral de 35 dB. Si lo es, decirlo en el informe.
- Medir el pico de tasa al enviar un I-header (kbps en una ventana de 1 frame) y registrar la tasa de subida en el CSV. En la tabla de costos figuran como "no medido".

## 6. VMAF (decide Vicente)
- Opciones:
  - autorizar el build de libvmaf;
  - usar un FFmpeg estático que traiga libvmaf;
  - medir en otro equipo con los `.ts`.
- Sirve para separar la deriva del macroblocking (límite 4 del informe).

## Decisiones de Vicente (2026-11-09)
- "Qué perdemos" es un resultado: va en Resultados (Tabla I).
- La regla de detección debe estar definida, pero con una expresión simple.
- Comparaciones siempre con el mismo GoP: una figura para GoP 30 y otra para GoP 90, ambas a 30 fps.
- Las figuras y los esquemas son lo más importante: deben entenderse solos.
- El objetivo es mejorar la experiencia de usuario reduciendo el macroblocking. No presentar resultados que no se apliquen en la realidad.
