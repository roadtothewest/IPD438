"""Propagación de la pérdida de un frame en H.264 (30 fps, GoP 30, una referencia).

Codifica N frames con x264 (perfil Baseline, sin B, 1 referencia, 1 slice por
frame), elimina el access unit de un frame (un P, un I no-IDR o un IDR),
decodifica con el decodificador H.264 de FFmpeg (ocultamiento por defecto) y
mide, frame a frame:

  - PSNR-Y contra la fuente (severidad),
  - si el frame mostrado es idéntico al de la decodificación sin pérdida
    (duración del artefacto: frames hasta la reconstrucción limpia),
  - si el decodificador entregó el frame o el reproductor repitió el anterior
    (congelamiento, base del FRR).

Dos codificaciones:
  A) keyint 30: cada frame intra es IDR.
  B) intra cada 30 frames, pero solo el primero es IDR; los siguientes se
     fuerzan como I no-IDR con un qpfile (como sería el I-header de AGiLE).

Uso:
  python3 perdida_gop.py VIDEO SALIDA.csv [--inicio 48.5] [--frames 90]

Requiere ffmpeg, x264 (CLI) y PyAV (pip install av numpy).
"""

import argparse
import csv
import math
import subprocess
import tempfile
from pathlib import Path

import av
import numpy as np

W, H, FPS, GOP = 640, 360, 30, 30
MTU_PAYLOAD = 1200  # bytes de payload por paquete RTP (FU-A), aproximado
P_PERDIDA = 0.01    # pérdida de paquetes independiente, para la exposición


def extraer_fuente(video, inicio, n, destino):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(inicio), "-i", video,
         "-frames:v", str(n), "-vf", f"scale={W}:{H}", "-pix_fmt", "yuv420p",
         "-f", "rawvideo", destino], check=True)
    datos = np.fromfile(destino, dtype=np.uint8)
    return datos.reshape(n, H * W * 3 // 2)[:, :H * W].reshape(n, H, W)


def codificar(fuente_yuv, destino, n, intra_no_idr):
    """x264, 1 Mbps con VBV de 1 s. Intra cada GOP frames: IDR, o I no-IDR."""
    cmd = ["x264", "--quiet", "--no-progress", "--input-res", f"{W}x{H}",
           "--fps", str(FPS), "--profile", "baseline", "--preset", "medium",
           "--bitrate", "1000", "--vbv-maxrate", "1000", "--vbv-bufsize", "1000",
           "--scenecut", "0", "--ref", "1", "--bframes", "0", "--threads", "1",
           "-o", destino]
    if intra_no_idr:
        # Solo el frame 0 es IDR; los demás intras se fuerzan como I no-IDR.
        qpfile = destino + ".qp"
        Path(qpfile).write_text(
            "".join(f"{k} i\n" for k in range(GOP, n, GOP)))
        cmd += ["--keyint", str(10 * n), "--min-keyint", str(10 * n),
                "--qpfile", qpfile]
    else:
        cmd += ["--keyint", str(GOP), "--min-keyint", str(GOP)]
    subprocess.run(cmd + [fuente_yuv], check=True, capture_output=True)
    return Path(destino).read_bytes()


def separar_nal(flujo):
    """Divide un flujo Annex B en NAL units (sin start code)."""
    inicios, i = [], 0
    while True:
        i = flujo.find(b"\x00\x00\x01", i)
        if i < 0:
            break
        inicios.append(i + 3)
        i += 3
    nals = []
    for k, ini in enumerate(inicios):
        fin = inicios[k + 1] - 3 if k + 1 < len(inicios) else len(flujo)
        nal = flujo[ini:fin]
        while nal.endswith(b"\x00"):  # cero inicial del start code de 4 bytes
            nal = nal[:-1]
        nals.append(nal)
    return nals


def tipo_slice(nal):
    """Lee slice_type (ue(v)) tras first_mb_in_slice; ignora prevención de emulación."""
    rbsp = nal[1:9].replace(b"\x00\x00\x03", b"\x00\x00")
    bits = "".join(f"{b:08b}" for b in rbsp)
    pos = 0
    valores = []
    for _ in range(2):
        ceros = 0
        while bits[pos] == "0":
            ceros += 1
            pos += 1
        valores.append(int(bits[pos:pos + ceros + 1], 2) - 1)
        pos += ceros + 1
    return valores[1] % 5  # 0 P, 1 B, 2 I


def access_units(flujo):
    """Agrupa NAL en access units: las no-VCL se pegan al slice siguiente."""
    aus, pendiente = [], []
    for nal in separar_nal(flujo):
        t = nal[0] & 0x1F
        pendiente.append(nal)
        if t in (1, 5):
            if t == 5:
                tipo = "IDR"
            else:
                tipo = {0: "P", 1: "B", 2: "I"}[tipo_slice(nal)]
            datos = b"".join(b"\x00\x00\x00\x01" + n for n in pendiente)
            aus.append({"tipo": tipo, "datos": datos,
                        "bytes_slice": len(nal) + 4})
            pendiente = []
    return aus


def decodificar(aus, perdidos):
    """Decodifica los AU no perdidos; devuelve {indice: plano Y}."""
    ctx = av.CodecContext.create("h264", "r")
    ctx.thread_count = 1
    salida = {}
    for i, au in enumerate(aus):
        if i in perdidos:
            continue
        pkt = av.Packet(au["datos"])
        pkt.pts = i
        for f in ctx.decode(pkt):
            salida[f.pts] = f.to_ndarray(format="gray")[:H, :W].copy()
    for f in ctx.decode(None):
        salida[f.pts] = f.to_ndarray(format="gray")[:H, :W].copy()
    return salida


def mostrar(decodificados, n):
    """Línea de tiempo del reproductor: si falta un frame, repite el anterior."""
    mostrado, entregado, ultimo = [], [], None
    for i in range(n):
        if i in decodificados:
            ultimo = decodificados[i]
            entregado.append(1)
        else:
            entregado.append(0)
        mostrado.append(ultimo)
    return mostrado, entregado


def psnr(a, b):
    if a is None:
        return 0.0
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("salida")
    ap.add_argument("--inicio", type=float, default=48.5)
    ap.add_argument("--frames", type=int, default=90)
    args = ap.parse_args()
    n = args.frames

    with tempfile.TemporaryDirectory() as tmp:
        fuente_yuv = f"{tmp}/fuente.yuv"
        fuente = extraer_fuente(args.video, args.inicio, n, fuente_yuv)
        solo_idr = access_units(codificar(fuente_yuv, f"{tmp}/a.h264", n, False))
        con_i = access_units(codificar(fuente_yuv, f"{tmp}/b.h264", n, True))

    assert len(solo_idr) == len(con_i) == n
    # Escenarios: (columna, codificación, frames perdidos). Cada pérdida se
    # compara contra la decodificación sin pérdida de su misma codificación.
    escenarios = [
        ("sin_perdida", solo_idr, set()),
        ("sin_perdida_B", con_i, set()),
        ("pierde_P45", solo_idr, {45}),
        ("pierde_P31", solo_idr, {31}),
        ("pierde_IDR30", solo_idr, {30}),
        ("pierde_I30", con_i, {30}),
    ]
    referencia = mostrar(decodificar(solo_idr, set()), n)[0]
    referencia_b = mostrar(decodificar(con_i, set()), n)[0]

    columnas = {}
    for nombre, aus, perdidos in escenarios:
        limpio = referencia_b if aus is con_i else referencia
        mostrado, entregado = mostrar(decodificar(aus, perdidos), n)
        columnas[f"psnr_{nombre}"] = [psnr(m, s) for m, s in zip(mostrado, fuente)]
        columnas[f"danado_{nombre}"] = [
            int(m is None or not np.array_equal(m, l))
            for m, l in zip(mostrado, limpio)]
        columnas[f"entregado_{nombre}"] = entregado

    with open(args.salida, "w", newline="") as f:
        w = csv.writer(f)
        cab = ["frame", "t", "tipo_A", "tipo_B", "bytes_A", "paquetes_A",
               "p_golpe_A"] + list(columnas)
        w.writerow(cab)
        for i in range(n):
            paquetes = math.ceil(solo_idr[i]["bytes_slice"] / MTU_PAYLOAD)
            fila = [i, f"{i / FPS:.4f}", solo_idr[i]["tipo"], con_i[i]["tipo"],
                    solo_idr[i]["bytes_slice"], paquetes,
                    f"{1 - (1 - P_PERDIDA) ** paquetes:.4f}"]
            fila += [f"{columnas[c][i]:.3f}" if c.startswith("psnr")
                     else columnas[c][i] for c in columnas]
            w.writerow(fila)

    # Resumen en consola
    sigla = {"IDR": "D", "I": "i", "P": "p", "B": "b"}
    print("tipos A:", "".join(sigla[au["tipo"]] for au in solo_idr))
    print("tipos B:", "".join(sigla[au["tipo"]] for au in con_i))
    for tipo in ("IDR", "P"):
        tam = [au["bytes_slice"] for au in solo_idr if au["tipo"] == tipo]
        print(f"{tipo}: {len(tam)} frames, media {np.mean(tam):.0f} B")
    for nombre, _, _ in escenarios:
        d = columnas[f"danado_{nombre}"]
        e = columnas[f"entregado_{nombre}"]
        print(f"{nombre:14s} dañados={sum(d):3d}  no entregados={n - sum(e):3d}  "
              f"PSNR medio={np.mean(columnas[f'psnr_{nombre}']):.2f} dB")


if __name__ == "__main__":
    main()
