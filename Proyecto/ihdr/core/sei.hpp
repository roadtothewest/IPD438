// SEI del I-header: un NAL de slice intra (tipo 1) viaja dentro de una SEI de datos de usuario
// (NAL tipo 6, payloadType 5), más la SEI recovery point (payloadType 6). Sin heap.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace ihdr {

// UUID que identifica nuestra SEI de usuario ("IHDR-IPD438" + versión 1).
inline constexpr uint8_t kIhdrUuid[16] = {'I', 'H', 'D', 'R', '-', 'I', 'P', 'D',
                                          '4', '3', '8', 0x01, 0, 0, 0, 0};

// Inserta prevención de emulación (00 00 0x, x<=3 -> 00 00 03 0x). Devuelve bytes escritos o 0 si no cabe.
inline size_t escape_rbsp(const uint8_t* in, size_t n, uint8_t* out, size_t cap) {
  size_t o = 0;
  unsigned zeros = 0;
  for (size_t i = 0; i < n; ++i) {
    if (zeros >= 2 && in[i] <= 3) {
      if (o >= cap) return 0;
      out[o++] = 3;
      zeros = 0;
    }
    if (o >= cap) return 0;
    out[o++] = in[i];
    zeros = (in[i] == 0) ? zeros + 1 : 0;
  }
  return o;
}

// Quita la prevención de emulación. Seguro con in == out (escritura <= lectura).
inline size_t unescape_rbsp(const uint8_t* in, size_t n, uint8_t* out, size_t cap) {
  size_t o = 0;
  unsigned zeros = 0;
  for (size_t i = 0; i < n; ++i) {
    if (zeros >= 2 && in[i] == 3) {
      zeros = 0;
      continue;
    }
    if (o >= cap) return 0;
    out[o++] = in[i];
    zeros = (in[i] == 0) ? zeros + 1 : 0;
  }
  return o;
}

// Envuelve un NAL (cabecera incluida, sin start code) en una SEI de usuario.
// Salida: NAL SEI completo (sin start code). Devuelve su largo o 0 si no cabe.
// `scratch` debe tener al menos nal_len + 32 bytes.
inline size_t sei_wrap_ihdr(const uint8_t* nal, size_t nal_len, uint8_t* out, size_t cap,
                            uint8_t* scratch, size_t scratch_cap) {
  size_t s = 0;
  scratch[s++] = 5;  // payloadType: user_data_unregistered
  size_t psize = 16 + nal_len;
  for (; psize >= 255; psize -= 255) scratch[s++] = 0xFF;
  scratch[s++] = uint8_t(psize);
  if (s + 16 + nal_len + 1 > scratch_cap) return 0;
  std::memcpy(scratch + s, kIhdrUuid, 16);
  s += 16;
  std::memcpy(scratch + s, nal, nal_len);
  s += nal_len;
  scratch[s++] = 0x80;  // rbsp_trailing_bits
  if (cap < 1) return 0;
  out[0] = 0x06;  // nal_ref_idc 0, tipo 6
  const size_t e = escape_rbsp(scratch, s, out + 1, cap - 1);
  return e ? e + 1 : 0;
}

// Si `sei` es nuestra SEI, copia el NAL interno a `out` y devuelve su largo; si no, 0.
inline size_t sei_unwrap_ihdr(const uint8_t* sei, size_t len, uint8_t* out, size_t cap) {
  if (len < 2 || (sei[0] & 0x1F) != 6 || len - 1 > cap) return 0;
  const size_t n = unescape_rbsp(sei + 1, len - 1, out, cap);
  size_t i = 0;
  if (n < 2 || out[i++] != 5) return 0;
  size_t psize = 0;
  while (i < n && out[i] == 0xFF) psize += 255, ++i;
  if (i >= n) return 0;
  psize += out[i++];
  if (psize < 17 || i + psize > n || std::memcmp(out + i, kIhdrUuid, 16) != 0) return 0;
  const size_t inner = psize - 16;
  std::memmove(out, out + i + 16, inner);
  return inner;
}

// SEI recovery point (payloadType 6): recovery_frame_cnt=0, exact_match=0 (hay deriva), broken_link=0.
inline size_t sei_recovery_point(uint8_t* out, size_t cap) {
  static constexpr uint8_t k[] = {0x06, 0x06, 0x01, 0x84, 0x80};
  if (cap < sizeof(k)) return 0;
  std::memcpy(out, k, sizeof(k));
  return sizeof(k);
}

}  // namespace ihdr
