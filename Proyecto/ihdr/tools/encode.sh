#!/usr/bin/env bash
# Codifica la fuente cruda con libx264 (vía ffmpeg), de forma determinista (un hilo).
#   A_gop{G}.h264        stream normal: IDR cada G frames, solo P entre medio.
#   B_gop{G}_q{Q}.h264   candidatos de I-header: el mismo video con un intra cada IH frames, a QP constante Q.
#                        El simulador toma, para cada P, el intra del candidato cuyo QP es el más cercano al del P
#                        (así se emula un codificador que codifica el I-header con el QP del P que reemplaza).
#                        Se codifican con el mismo keyint que A para que el SPS sea idéntico.
# Uso: encode.sh FUENTE.yuv ANCHO ALTO FPS SALIDA_DIR GOP [IH KBPS SLICES]
set -euo pipefail
SRC=$1; W=$2; H=$3; FPS=$4; OUT=$5; G=$6
IH=${7:-5}; KBPS=${8:-3000}; SLICES=${9:-45}
QPS="23 26 29 32 35 38 41 44 47 50"
mkdir -p "$OUT"
IN="-v error -y -threads 1 -f rawvideo -pix_fmt yuv420p -s ${W}x${H} -r $FPS -i $SRC"
ENC="-c:v libx264 -profile:v baseline -preset medium -threads 1"
COMMON="keyint=$G:min-keyint=$G:ref=1:bframes=0:scenecut=0:threads=1:slices=$SLICES:aud=0:repeat-headers=1:rc-lookahead=0"
ffmpeg $IN $ENC -b:v ${KBPS}k -x264-params "$COMMON:vbv-maxrate=$KBPS:vbv-bufsize=$KBPS" -f h264 "$OUT/A_gop$G.h264"
for Q in $QPS; do
  ffmpeg $IN $ENC -force_key_frames "expr:eq(mod(n,$IH),0)" -x264-params "$COMMON:qp=$Q" -f h264 "$OUT/B_gop${G}_q$Q.h264"
done
ls "$OUT"/B_gop${G}_q*.h264 | tr '\n' ',' | sed 's/,$//' > "$OUT/candidatos.txt"
