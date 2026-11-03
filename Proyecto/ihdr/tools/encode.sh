#!/usr/bin/env bash
# Codifica la fuente cruda en tres streams H.264 Annex B con libx264 (via ffmpeg):
#   A  GoP largo (IDR cada GOP_LONG)            -> el stream "normal"
#   B  igual que A + intra no-IDR cada IH_EVERY  -> de aqui se sacan los I-headers
#   C  GoP corto (IDR cada GOP_SHORT)            -> baseline "GoP corto"
# Uso: encode.sh FUENTE.yuv ANCHO ALTO FPS SALIDA_DIR [GOP_LONG GOP_SHORT IH_EVERY KBPS SLICES]
set -euo pipefail
SRC=$1; W=$2; H=$3; FPS=$4; OUT=$5
GL=${6:-90}; GS=${7:-30}; IH=${8:-5}; KBPS=${9:-3000}; SLICES=${10:-0}
mkdir -p "$OUT"
BASE="-v error -y -f rawvideo -pix_fmt yuv420p -s ${W}x${H} -r $FPS -i $SRC -c:v libx264 -profile:v baseline -preset medium -b:v ${KBPS}k"
COMMON="ref=1:bframes=0:scenecut=0:threads=1:slices=$SLICES:aud=0:repeat-headers=1:rc-lookahead=0:vbv-maxrate=${KBPS}:vbv-bufsize=${KBPS}"
ffmpeg $BASE -x264-params "keyint=$GL:min-keyint=$GL:$COMMON" -f h264 "$OUT/A_gop${GL}.h264"
ffmpeg $BASE -x264-params "keyint=$GS:min-keyint=$GS:$COMMON" -f h264 "$OUT/C_gop${GS}.h264"
# B: forzar intra cada IH frames (no-IDR: forced-idr=0), IDR cada GL por keyint.
ffmpeg $BASE -force_key_frames "expr:gte(mod(n,$IH),1)*0+eq(mod(n,$IH),0)" \
  -forced-idr 0 -x264-params "keyint=$GL:min-keyint=$GL:$COMMON" -f h264 "$OUT/B_gop${GL}_ih${IH}.h264"
ls -l "$OUT"
