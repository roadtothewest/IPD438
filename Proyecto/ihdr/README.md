# ihdr: emulador de I-headers sobre SRT

Emula la cadena codificador → edge → espectador con pérdida, para comparar las cuatro combinaciones UDP/SRT × con/sin I-header.

## Estructura

| Carpeta | Qué hay | Dónde corre |
|---|---|---|
| `core/` | C++17 sin memoria dinámica, sin excepciones y sin SO: parser H.264 (`h264.hpp`), SEI del I-header y recovery point (`sei.hpp`), reescritura IDR → intra no-IDR con `frame_num` y QP (`rewrite.hpp`), mux TS (`ts.hpp`) | PC y STM32N6 (no toca la HAL) |
| `host/` | Modelo de SRT live por eventos discretos (`srt_model.hpp`), canal Gilbert-Elliott y simulador (`main.cpp`), pruebas del núcleo (`test_core.cpp`) | PC |
| `tools/` | `encode.sh` (streams con libx264), `evaluate.py` (escenarios + PSNR), `figuras_informe.py` | PC |
| `results/` | Resultados del informe (CSV y curvas por frame) | |

## Uso

```bash
cmake -S . -B build && cmake --build build -j
./build/test_core A.h264                          # pruebas del núcleo
tools/encode.sh fuente.yuv 1280 720 30 streams 90 30 5 3000 45
# I-headers de buena calidad (B a CRF 23, un intra cada 5 frames):
ffmpeg -f rawvideo -pix_fmt yuv420p -s 1280x720 -r 30 -i fuente.yuv -c:v libx264 -profile:v baseline \
  -crf 23 -force_key_frames "expr:eq(mod(n,5),0)" \
  -x264-params "ref=1:bframes=0:scenecut=0:threads=1:slices=45:aud=0:repeat-headers=1:rc-lookahead=0:keyint=90:min-keyint=90" \
  -f h264 streams/B_crf23.h264
python3 tools/evaluate.py --src fuente.yuv --streams streams --b streams/B_crf23.h264 \
  --loss 0.04 --burst-ms 200 --seeds 1,2,3,4,5,6,7,8 --latencies 250,500,1000 --save results/r2
```

Escenarios de `evaluate.py`:

| Escenario | Qué es |
|---|---|
| `udp` | Sin retransmisión, búfer de 20 ms |
| `udp+ih` | Lo mismo, y el espectador avisa cada descarte |
| `srt` | SRT live con L = 120 ms |
| `srt+ih` | SRT, y el edge infiere el descarte por la marca de tiempo del ACK, sin cambiar el protocolo |
| `srt+ih_rep` | SRT con aviso explícito del espectador (cota superior) |
| `srt_gop30` | SRT con GoP 30 |
| `srt@L` | SRT con otra latencia |

## Métricas

- **PSNR_ref:** PSNR de la luminancia contra el mismo stream decodificado sin pérdida. Solo mide la pérdida, el ocultamiento y la deriva. Dos frames idénticos dan 99 dB.
- **PSNR_src:** PSNR contra la fuente cruda; incluye la compresión.
- **Frame dañado:** PSNR_ref < 35 dB.
- **VMAF:** pendiente, porque el FFmpeg instalado no trae libvmaf.

## Limitaciones conocidas

- El modelo de SRT es de comportamiento: no implementa el protocolo en el cable. Falta validarlo contra libsrt con `tc netem`.
- El edge conoce `owd` sin error: el reloj del ACK es exacto.
- Hay un solo espectador por corrida.
- El tramo codificador → edge no tiene pérdida.
- El modo B, en el que el edge pide activar los I-headers, no está implementado.
- En el PC, el I-header sale de un IDR de otra codificación (B) y se reescribe. En el STM32N6, el codificador da el intra no-IDR directamente.
