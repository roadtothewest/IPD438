#!/bin/sh
# ic.sh <salida_de_ping> <N>: IC 95% de la perdida round-trip segun el apunte (experimento binario)
grep -o 'seq=[0-9]*' "$1" | cut -d= -f2 | awk -v N="$2" '
function tq(df,  z) { z = 1.959964; return z + (z*z*z + z)/(4*df) + (5*z*z*z*z*z + 16*z*z*z + 3*z)/(96*df*df) }
{ ok[$1] = 1 }
END {
  printf "%6s %5s %7s %7s %6s %9s %8s %s\n", "N", "perd", "M(%)", "s", "t", "t*s/vN", "0.05M", "cumple"
  k = 0; first = 0
  for (i = 0; i < N; i++) {
    if (!(i in ok)) k++
    n = i + 1
    if (n < 30) continue
    M = k/n; s = sqrt(k/(n-1)*(1 - k/n)); t = tq(n-1); h = t*s/sqrt(n)
    if (h <= 0.05*M && !first) first = n
    if (n % 1000 == 0) printf "%6d %5d %7.2f %7.4f %6.3f %8.2f%% %7.2f%% %s\n", n, k, 100*M, s, t, 100*h, 5*M, (h <= 0.05*M ? "si" : "no")
  }
  printf "Primer N que cumple t*s/sqrt(N) <= 0.05*M: %d\n", first
  printf "Perdida round-trip: M = %.2f%%   IC95%% = [%.2f%%, %.2f%%]\n", 100*M, 100*(M-h), 100*(M+h)
  printf "Perdida por sentido: p = 1-sqrt(1-M) = %.2f%%   IC95%% = [%.2f%%, %.2f%%]\n", 100*(1-sqrt(1-M)), 100*(1-sqrt(1-(M-h))), 100*(1-sqrt(1-(M+h)))
}'
