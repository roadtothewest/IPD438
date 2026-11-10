#!/usr/bin/env bash
# Vigilante térmico: pausa un grupo de procesos si la CPU se calienta y lo reanuda cuando se enfría.
# Uso: termico.sh PGID [ALTA=85] [BAJA=75]     (temperaturas del paquete, en °C, según `sensors`)
PG=$1; ALTA=${2:-85}; BAJA=${3:-75}
estado=corriendo
while kill -0 -- -"$PG" 2>/dev/null; do
  T=$(sensors | awk '/Package id 0/ {gsub(/[+°C]/, "", $4); print int($4)}')
  if [ "$estado" = corriendo ] && [ "$T" -ge "$ALTA" ]; then
    kill -STOP -- -"$PG"; estado=pausado; echo "$(date +%T) $T°C: pausa"
  elif [ "$estado" = pausado ] && [ "$T" -le "$BAJA" ]; then
    kill -CONT -- -"$PG"; estado=corriendo; echo "$(date +%T) $T°C: sigue"
  fi
  sleep 5
done
