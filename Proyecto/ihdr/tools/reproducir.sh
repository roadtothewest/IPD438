#!/usr/bin/env bash
# Reproduce todos los resultados del informe, desde la fuente pública hasta las figuras.
#   cd Proyecto/ihdr && tools/reproducir.sh            (todo)
#   tools/reproducir.sh fuente|codificar|compilar|simular|analizar   (un paso)
# Todo corre en serie, con un hilo y prioridad baja (nice), para no sobrecargar el equipo.
# Requisitos: ffmpeg con libx264, cmake, g++ (C++17), python3 con numpy, scipy y matplotlib.
# El resultado es determinista: las mismas versiones de herramientas dan los mismos archivos
# (los SHA-256 de entrada quedan en results/final/MANIFIESTO.txt; tools/sha256_esperado.txt los fija).
set -euo pipefail
cd "$(dirname "$0")/.."
PASO=${1:-todo}
URL=https://media.xiph.org/video/derf/y4m/aspen_1080p.y4m   # secuencia de prueba pública de Xiph.org
W=1280; H=720; FPS=30; N=300
MEDIA=media; OUT=results/final
SEEDS=1-30
NICE="nice -n 19"
mkdir -p "$MEDIA" "$OUT"

fuente() {
  # Los primeros 300 frames (10 s) de aspen_1080p, escalados a 720p. Se lee por streaming: no se guarda el y4m.
  [ -f "$MEDIA/src720.yuv" ] || $NICE ffmpeg -v error -y -threads 1 -i "$URL" -frames:v $N \
      -vf scale=$W:$H:flags=bicubic -pix_fmt yuv420p -f rawvideo "$MEDIA/src720.yuv"
}

codificar() {
  for G in 90 30; do
    [ -f "$MEDIA/gop$G/candidatos.txt" ] || $NICE tools/encode.sh "$MEDIA/src720.yuv" $W $H $FPS "$MEDIA/gop$G" $G 5 3000 45
  done
}

compilar() {
  mkdir -p build && (cd build && cmake -DCMAKE_BUILD_TYPE=Release .. >/dev/null && $NICE make -j1 >/dev/null && ./test_core)
}

manifiesto() {
  {
    echo "fecha: $(date -u +%FT%TZ)"
    echo "git: $(git rev-parse HEAD 2>/dev/null) $(git diff --quiet 2>/dev/null || echo '(con cambios sin commit)')"
    echo "fuente: $URL, $N frames, ${W}x${H}, $FPS fps"
    ffmpeg -version | head -1
    echo "x264: $(strings "$MEDIA/gop90/A_gop90.h264" | grep -m1 -o 'x264 - core [0-9]* [^ ]*')"
    g++ --version | head -1
    python3 -c "import numpy, scipy, matplotlib; print('numpy', numpy.__version__, 'scipy', scipy.__version__, 'matplotlib', matplotlib.__version__)"
    echo "sha256:"
    (cd "$MEDIA" && sha256sum src720.yuv gop90/*.h264 gop30/*.h264)
  } > "$OUT/MANIFIESTO.txt"
  if [ -f tools/sha256_esperado.txt ]; then
    if diff <(grep -E '^[0-9a-f]{64} ' "$OUT/MANIFIESTO.txt") tools/sha256_esperado.txt >/dev/null; then
      echo "entradas idénticas a las del informe"
    else
      echo "AVISO: las entradas difieren de tools/sha256_esperado.txt (otra versión de ffmpeg/x264?)"
    fi
  fi
}

simular() {
  manifiesto
  local EV="$NICE python3 tools/evaluate.py --src $MEDIA/src720.yuv --frames $N --w $W --h $H --fps $FPS"
  for G in 90 30; do
    local D="$OUT/gop$G"
    # Deriva sola: sin pérdida, un I-header forzado en cada P múltiplo de 5 (sin los IDR).
    [ -f "$D/deriva.npz" ] || $EV --streams $MEDIA/gop$G --gop $G --out $D --tag deriva \
        --force-ih "$(seq 5 5 $((N - 5)) | awk -v g=$G '$1 % g' | paste -sd,)"
    # Los 4 casos con la misma historia de cortes; SRT también con la L recomendada (180 ms).
    [ -f "$D/r20.npz" ]  || $EV --streams $MEDIA/gop$G --gop $G --out $D --tag r20  --loss 0.02 --burst-ms 20  --seeds $SEEDS \
        --cases udp,udp+ih,srt,srt+ih
    [ -f "$D/r200.npz" ] || $EV --streams $MEDIA/gop$G --gop $G --out $D --tag r200 --loss 0.04 --burst-ms 200 --seeds $SEEDS \
        --cases udp,udp+ih,srt,srt+ih,srt@180,srt+ih@180
    [ -f "$D/r600.npz" ] || $EV --streams $MEDIA/gop$G --gop $G --out $D --tag r600 --loss 0.04 --burst-ms 600 --seeds $SEEDS \
        --cases udp,udp+ih,srt,srt+ih,srt@180,srt+ih@180
  done
  # Alternativa de subir L para todos (solo GoP 90).
  for R in "r200 200" "r600 600"; do
    set -- $R
    [ -f "$OUT/gop90/$1_L.npz" ] || $EV --streams $MEDIA/gop90 --gop 90 --out $OUT/gop90 --tag $1_L --loss 0.04 --burst-ms $2 \
        --seeds $SEEDS --cases srt@250,srt@500,srt@1000
  done
}

analizar() {
  python3 tools/analizar.py "$OUT" ../informe
}

case $PASO in
  todo) fuente; codificar; compilar; simular; analizar ;;
  *) $PASO ;;
esac
