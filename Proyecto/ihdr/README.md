# ihdr: emulador de I-headers sobre SRT

Emula la cadena codificador → edge → espectador con pérdida, para comparar UDP y SRT, con y sin I-header.
El codificador (libx264) y el decodificador (FFmpeg, con su ocultamiento de errores) son reales; solo la red y SRT se emulan.

## Reproducir los resultados del informe

```bash
cd Proyecto/ihdr
tools/reproducir.sh            # fuente → codificar → compilar → simular → analizar
tools/reproducir.sh analizar   # solo rehace figuras y resumen desde results/final
```

- **Requisitos:** ffmpeg con libx264, cmake, g++ (C++17), python3 con numpy, scipy y matplotlib. Se necesita 1 GB de disco en `media/`.
- **Fuente:** los primeros 300 frames de `aspen_1080p` de Xiph.org, escalados a 720p. Se leen por streaming, sin guardar el y4m.
- **Ejecución:** todo corre en serie, con un hilo y `nice -n 19`. Son unas 1250 corridas, de unos 5 s cada una. El script retoma donde quedó si se interrumpe.
- **Si el equipo se calienta:** `tools/termico.sh PGID 85 72` pausa el grupo de procesos sobre 85 °C y lo reanuda bajo 72 °C.
- **Determinismo:** el codificador y el decodificador usan un hilo y el canal depende solo de la semilla. `results/final/MANIFIESTO.txt` guarda las versiones y el SHA-256 de cada entrada, y se compara con `tools/sha256_esperado.txt`. Otra versión de ffmpeg o x264 puede dar streams distintos.
- **Salida:** `results/final/gop{90,30}/<escenario>.{npz,csv}`, `results/final/resumen.txt` y `../informe/fig_resultados_gop{90,30}.pdf`.

## Estructura

| Carpeta | Qué hay | Dónde corre |
|---|---|---|
| `core/` | C++17 sin memoria dinámica, sin excepciones y sin SO: parser H.264 (`h264.hpp`), SEI del I-header y recovery point (`sei.hpp`), reescritura IDR → intra no-IDR con `frame_num` y QP (`rewrite.hpp`), mux TS (`ts.hpp`) | PC y STM32N6 (no toca la HAL) |
| `host/` | Modelo de SRT live por eventos discretos (`srt_model.hpp`), canal Gilbert-Elliott y simulador (`main.cpp`), pruebas del núcleo (`test_core.cpp`) | PC |
| `tools/` | `reproducir.sh` (todo), `encode.sh` (streams), `evaluate.py` (corridas y métricas por frame), `analizar.py` (figuras y resumen), `termico.sh` | PC |
| `results/final/` | Resultados del informe | |

## Escenarios

| Caso | Qué es |
|---|---|
| `udp` | Sin retransmisión, búfer de 20 ms |
| `udp+ih` | Lo mismo, y el espectador avisa cada descarte |
| `srt[@L]` | SRT live, L = 120 ms por defecto |
| `srt+ih[@L]` | SRT, y el edge infiere el descarte por la marca de tiempo del ACK (regla (2) del informe), sin cambiar el protocolo |

Regímenes de corte (Gilbert-Elliott): `r20` (2 % del tiempo, cortes de 20 ms en media), `r200` y `r600` (4 %, 200 y 600 ms). `deriva`: sin pérdida, con un I-header forzado por corrida.

## Métrica

SSIM (Wang et al., 2004), implementado en `tools/evaluate.py`:
- luminancia promediada en bloques de 3×3;
- ventana gaussiana de 11×11 con σ = 1,5;
- C1 = (0,01·255)², C2 = (0,03·255)².

Por frame se calcula `dSSIM = SSIM(fuente, sin pérdida) − SSIM(fuente, recibido)`, y el frame tiene un artefacto visible si dSSIM > 0,05. También se informan los umbrales 0,02 y 0,1, y la pérdida acumulada Σ max(0, dSSIM)/fps, que no usa umbral.

## Limitaciones conocidas

- El modelo de SRT es de comportamiento: no implementa el protocolo en el cable. Falta validarlo contra libsrt con `tc netem`.
- El edge conoce `owd` sin error: el reloj del ACK es exacto.
- Hay un solo espectador por corrida.
- El tramo codificador → edge no tiene pérdida.
- En el PC, el I-header sale de un IDR de otra codificación (B, a QP fijo, el más cercano al del P) y se reescribe. En el STM32N6, el codificador da el intra no-IDR directamente.
