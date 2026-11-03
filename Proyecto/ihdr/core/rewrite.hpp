// Reescritura del slice header: IDR intra -> intra no-IDR (NAL tipo 1) con el frame_num (y POC) del
// P que va a reemplazar. Es el "I-header". Solo CAVLC, un slice group, frame_mbs_only, POC tipo 0/2.
// En el STM32N6 el codificador entrega "intra no-IDR" de forma nativa; aquí falta solo el frame_num.
#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

#include "h264.hpp"
#include "sei.hpp"

namespace ihdr {

class RawBits {  // lector de bits sobre un RBSP ya sin prevención de emulación
 public:
  RawBits(const uint8_t* d, size_t nbits) : d_(d), n_(nbits) {}
  uint32_t bit() {
    if (p_ >= n_) { err_ = true; return 0; }
    const uint32_t v = (d_[p_ >> 3] >> (7 - (p_ & 7))) & 1u;
    ++p_;
    return v;
  }
  uint32_t u(unsigned k) { uint32_t v = 0; while (k--) v = (v << 1) | bit(); return v; }
  uint32_t ue() {
    unsigned z = 0;
    while (!bit()) { if (err_ || ++z >= 32) { err_ = true; return 0; } }
    return ((1u << z) - 1u) + u(z);
  }
  int32_t se() {
    const uint32_t k = ue();
    return (k & 1u) ? int32_t((k + 1) / 2) : -int32_t(k / 2);
  }
  size_t pos() const { return p_; }
  bool ok() const { return !err_; }
 private:
  const uint8_t* d_;
  size_t n_, p_ = 0;
  bool err_ = false;
};

class BitWriter {
 public:
  BitWriter(uint8_t* d, size_t cap) : d_(d), cap_(cap) {}
  void bit(uint32_t b) {
    if ((p_ >> 3) >= cap_) { err_ = true; return; }
    if ((p_ & 7) == 0) d_[p_ >> 3] = 0;
    if (b) d_[p_ >> 3] |= uint8_t(0x80 >> (p_ & 7));
    ++p_;
  }
  void u(uint32_t v, unsigned k) { while (k--) bit((v >> k) & 1u); }
  void ue(uint32_t v) {
    const uint64_t x = uint64_t(v) + 1;
    unsigned n = 0;
    while ((x >> (n + 1)) != 0) ++n;
    u(0, n);
    for (int i = int(n); i >= 0; --i) bit(uint32_t((x >> i) & 1u));
  }
  void se(int32_t v) { ue(v > 0 ? uint32_t(2 * v - 1) : uint32_t(-2 * v)); }
  size_t bits() const { return p_; }
  size_t bytes() const { return (p_ + 7) >> 3; }
  bool ok() const { return !err_; }
 private:
  uint8_t* d_;
  size_t cap_, p_ = 0;
  bool err_ = false;
};

// ¿Un slice codificado con el PPS `src` se puede decodificar con el PPS `dst` ajustando solo el QP?
inline bool pps_compatible(const PpsInfo& src, const PpsInfo& dst) {
  return src.ok && dst.ok && src.cabac == dst.cabac && src.bottom_poc_present == dst.bottom_poc_present &&
         src.redundant_pic_cnt_present == dst.redundant_pic_cnt_present && src.deblock_ctrl == dst.deblock_ctrl &&
         src.constrained_intra == dst.constrained_intra && src.chroma_qp_offset == dst.chroma_qp_offset;
}

// nal: NAL IDR completo (cabecera incluida, sin start code), codificado con `src_pps`. Devuelve el largo
// del NAL tipo 1 equivalente para decodificarse con `pps` (el del stream de destino), o 0 si falla.
// Ajusta slice_qp_delta si los pic_init_qp difieren. `scratch` >= 2*len + 16 bytes.
inline size_t idr_to_intra(const uint8_t* nal, size_t len, const SpsInfo& sps, const PpsInfo& src_pps,
                           const PpsInfo& pps, uint32_t frame_num, uint32_t poc_lsb, uint8_t* out, size_t cap,
                           uint8_t* scratch, size_t scratch_cap) {
  if (len < 4 || (nal[0] & 0x1F) != kNalIdr || !sps.ok || !pps_compatible(src_pps, pps) || pps.cabac ||
      !sps.frame_mbs_only)
    return 0;
  if (scratch_cap < 2 * len + 16) return 0;
  uint8_t* rbsp = scratch;
  uint8_t* wbuf = scratch + len + 8;
  const size_t n = unescape_rbsp(nal + 1, len - 1, rbsp, len);
  if (n == 0) return 0;
  RawBits rd(rbsp, n * 8);
  BitWriter wr(wbuf, len + 8);
  wr.ue(rd.ue());                      // first_mb_in_slice
  const uint32_t st = rd.ue();
  if (st % 5 != 2) return 0;           // solo slices I
  wr.ue(st);
  wr.ue(rd.ue());                      // pps_id
  rd.u(sps.log2_max_frame_num);
  wr.u(frame_num, sps.log2_max_frame_num);
  rd.ue();                             // idr_pic_id (desaparece)
  if (sps.poc_type == 0) {
    rd.u(sps.log2_max_poc_lsb);
    wr.u(poc_lsb, sps.log2_max_poc_lsb);
    if (pps.bottom_poc_present) {      // delta_pic_order_cnt_bottom: se(v), se copia tal cual
      const size_t a = rd.pos();
      const uint32_t z = rd.ue();
      (void)z;
      RawBits cp(rbsp, n * 8);
      for (size_t i = 0; i < a; ++i) cp.bit();
      for (size_t i = a; i < rd.pos(); ++i) wr.bit(cp.bit());
    }
  }
  if (pps.redundant_pic_cnt_present) wr.ue(rd.ue());
  rd.u(2);                             // no_output_of_prior_pics, long_term_reference (solo IDR)
  wr.bit(0);                           // adaptive_ref_pic_marking_mode_flag = 0
  wr.se(rd.se() + src_pps.pic_init_qp - pps.pic_init_qp);  // slice_qp_delta: mismo QP absoluto
  if (!rd.ok()) return 0;
  // Resto (deblocking, slice_data): copia hasta el bit de parada (último 1).
  size_t last = n * 8;
  while (last > 0 && !((rbsp[(last - 1) >> 3] >> (7 - ((last - 1) & 7))) & 1u)) --last;
  if (last == 0) return 0;
  for (size_t i = rd.pos(); i < last; ++i) {
    wr.bit((rbsp[i >> 3] >> (7 - (i & 7))) & 1u);
  }
  while (wr.bits() & 7) wr.bit(0);
  if (!wr.ok() || cap < 1) return 0;
  out[0] = uint8_t((nal[0] & 0x60) | kNalSlice);
  const size_t e = escape_rbsp(wbuf, wr.bytes(), out + 1, cap - 1);
  return e ? e + 1 : 0;
}

}  // namespace ihdr
