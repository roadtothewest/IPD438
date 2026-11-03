// Mux MPEG-TS mínimo (un video H.264, PES con PTS), sin heap. La salida se entrega por callback,
// de a un paquete de 188 B, con metadatos que dicen qué bytes del ES lleva cada paquete.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace ihdr {

inline constexpr size_t kTsPacket = 188;
inline constexpr uint16_t kPidPmt = 0x1000;
inline constexpr uint16_t kPidVideo = 0x100;

struct TsMeta {
  uint32_t es_off = 0;  // posición, dentro del ES del AU, del primer byte de payload del ES
  uint32_t es_len = 0;  // bytes de ES que lleva el paquete (0 en PAT/PMT)
  bool pusi = false;    // inicio de PES
  bool psi = false;     // PAT / PMT
};

inline uint32_t crc32_mpeg(const uint8_t* d, size_t n) {
  uint32_t crc = 0xFFFFFFFFu;
  for (size_t i = 0; i < n; ++i) {
    crc ^= uint32_t(d[i]) << 24;
    for (int b = 0; b < 8; ++b) crc = (crc & 0x80000000u) ? (crc << 1) ^ 0x04C11DB7u : (crc << 1);
  }
  return crc;
}

class TsMuxer {
 public:
  using Sink = void (*)(void* ctx, const uint8_t* pkt188, const TsMeta& meta);
  TsMuxer(Sink sink, void* ctx) : sink_(sink), ctx_(ctx) {}

  // Escribe un access unit. `with_psi` antepone PAT y PMT.
  void write_au(const uint8_t* es, size_t n, uint64_t pts90k, bool with_psi) {
    if (with_psi) {
      emit_psi(0x0000, pat_, pat_n_);
      emit_psi(kPidPmt, pmt_, pmt_n_);
    }
    uint8_t hdr[kPesHdr] = {0, 0, 1, 0xE0, 0, 0, 0x80, 0x80, 5,
                            uint8_t(0x21 | ((pts90k >> 29) & 0x0E)), uint8_t(pts90k >> 22),
                            uint8_t(0x01 | ((pts90k >> 14) & 0xFE)), uint8_t(pts90k >> 7),
                            uint8_t(0x01 | ((pts90k << 1) & 0xFE))};
    const size_t total = kPesHdr + n;
    for (size_t pos = 0; pos < total;) {
      const size_t take = (total - pos > 184) ? 184 : total - pos;
      uint8_t pkt[kTsPacket];
      const bool first = (pos == 0);
      const size_t pad = 184 - take;
      pkt[0] = 0x47;
      pkt[1] = uint8_t((first ? 0x40 : 0) | (kPidVideo >> 8));
      pkt[2] = uint8_t(kPidVideo & 0xFF);
      pkt[3] = uint8_t((pad ? 0x30 : 0x10) | (cc_video_++ & 0x0F));
      size_t o = 4;
      if (pad) {  // campo de adaptación con relleno
        pkt[o++] = uint8_t(pad - 1);
        if (pad > 1) {
          pkt[o++] = 0x00;
          std::memset(pkt + o, 0xFF, pad - 2);
          o += pad - 2;
        }
      }
      size_t es_in_pkt = 0, es_off = 0;
      for (size_t i = 0; i < take; ++i) {
        const size_t p = pos + i;
        pkt[o++] = (p < kPesHdr) ? hdr[p] : es[p - kPesHdr];
        if (p >= kPesHdr) {
          if (es_in_pkt == 0) es_off = p - kPesHdr;
          ++es_in_pkt;
        }
      }
      TsMeta m;
      m.es_off = uint32_t(es_off);
      m.es_len = uint32_t(es_in_pkt);
      m.pusi = first;
      sink_(ctx_, pkt, m);
      pos += take;
    }
  }

 private:
  static constexpr size_t kPesHdr = 14;
  void emit_psi(uint16_t pid, const uint8_t* sec, size_t n) {
    uint8_t pkt[kTsPacket];
    std::memset(pkt, 0xFF, sizeof(pkt));
    uint8_t& cc = (pid == 0) ? cc_pat_ : cc_pmt_;
    pkt[0] = 0x47;
    pkt[1] = uint8_t(0x40 | (pid >> 8));
    pkt[2] = uint8_t(pid & 0xFF);
    pkt[3] = uint8_t(0x10 | (cc++ & 0x0F));
    pkt[4] = 0;  // pointer_field
    std::memcpy(pkt + 5, sec, n);
    TsMeta m;
    m.pusi = true;
    m.psi = true;
    sink_(ctx_, pkt, m);
  }
  // Secciones con CRC precalculado en tiempo de ejecución la primera vez (ver init_tables).
  static constexpr uint8_t pat_body_[12] = {0x00, 0xB0, 0x0D, 0x00, 0x01, 0xC1, 0x00, 0x00, 0x00, 0x01, 0xF0, 0x00};
  static constexpr uint8_t pmt_body_[17] = {0x02, 0xB0, 0x12, 0x00, 0x01, 0xC1, 0x00, 0x00, 0xE1,
                                            0x00, 0xF0, 0x00, 0x1B, 0xE1, 0x00, 0xF0, 0x00};
  struct Tables {
    uint8_t pat[16];
    uint8_t pmt[21];
    Tables() {
      std::memcpy(pat, pat_body_, 12);
      std::memcpy(pmt, pmt_body_, 17);
      put_crc(pat, 12);
      put_crc(pmt, 17);
    }
    static void put_crc(uint8_t* s, size_t n) {
      const uint32_t c = crc32_mpeg(s, n);
      s[n] = uint8_t(c >> 24);
      s[n + 1] = uint8_t(c >> 16);
      s[n + 2] = uint8_t(c >> 8);
      s[n + 3] = uint8_t(c);
    }
  };
  Tables t_;
  const uint8_t* pat_ = t_.pat;
  const uint8_t* pmt_ = t_.pmt;
  static constexpr size_t pat_n_ = 16;
  static constexpr size_t pmt_n_ = 21;
  Sink sink_;
  void* ctx_;
  uint8_t cc_video_ = 0, cc_pat_ = 0, cc_pmt_ = 0;
};

}  // namespace ihdr
