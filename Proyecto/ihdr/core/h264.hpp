// Núcleo portable (sin heap, sin excepciones, sin iostream): lectura de bitstream H.264 Annex B.
// Es la parte que correrá igual en el PC y en el STM32N6; no depende de HAL ni del SO.
#pragma once
#include <cstddef>
#include <cstdint>

namespace ihdr {

enum : uint8_t { kNalSlice = 1, kNalIdr = 5, kNalSei = 6, kNalSps = 7, kNalPps = 8, kNalAud = 9 };

inline bool is_vcl(uint8_t nal_type) { return nal_type == kNalSlice || nal_type == kNalIdr; }

struct Nal {
  size_t off = 0;  // posición del byte de cabecera del NAL
  size_t len = 0;  // bytes del NAL (incluye la cabecera; sin start code ni ceros finales)
  uint8_t type = 0;
  uint8_t ref_idc = 0;
};

// Recorre los NAL de un buffer Annex B.
class NalIter {
 public:
  NalIter(const uint8_t* d, size_t n) : d_(d), n_(n), pos_(find_sc(0)) {}
  bool next(Nal& out) {
    while (pos_ < n_) {
      const size_t start = pos_;
      const size_t nxt = find_sc(start);
      size_t end = (nxt >= n_) ? n_ : nxt - 3;
      while (end > start && d_[end - 1] == 0) --end;  // ceros finales / 1er cero del start code largo
      pos_ = nxt;
      if (end > start) {
        out.off = start;
        out.len = end - start;
        out.type = d_[start] & 0x1F;
        out.ref_idc = (d_[start] >> 5) & 3;
        return true;
      }
    }
    return false;
  }

 private:
  // Devuelve el índice del primer byte tras un start code 00 00 01 en [from, n), o n si no hay.
  size_t find_sc(size_t from) const {
    for (size_t i = from; i + 3 <= n_; ++i)
      if (d_[i] == 0 && d_[i + 1] == 0 && d_[i + 2] == 1) return i + 3;
    return n_;
  }
  const uint8_t* d_;
  size_t n_;
  size_t pos_;
};

// Lector de bits sobre un RBSP; elimina los bytes de prevención de emulación (00 00 03).
class BitReader {
 public:
  BitReader(const uint8_t* d, size_t n) : d_(d), n_(n) {}
  uint32_t bit() {
    if (left_ == 0 && !load()) {
      err_ = true;
      return 0;
    }
    --left_;
    return (cur_ >> left_) & 1u;
  }
  uint32_t u(unsigned k) {
    uint32_t v = 0;
    while (k--) v = (v << 1) | bit();
    return v;
  }
  uint32_t ue() {
    unsigned z = 0;
    while (!bit()) {
      if (err_ || ++z >= 32) {
        err_ = true;
        return 0;
      }
    }
    return ((1u << z) - 1u) + u(z);
  }
  int32_t se() {
    const uint32_t k = ue();
    return (k & 1u) ? int32_t((k + 1) / 2) : -int32_t(k / 2);
  }
  bool ok() const { return !err_; }

 private:
  bool load() {
    if (pos_ >= n_) return false;
    uint8_t b = d_[pos_++];
    if (zeros_ >= 2 && b == 3) {
      zeros_ = 0;
      if (pos_ >= n_) return false;
      b = d_[pos_++];
    }
    zeros_ = (b == 0) ? zeros_ + 1 : 0;
    cur_ = b;
    left_ = 8;
    return true;
  }
  const uint8_t* d_;
  size_t n_;
  size_t pos_ = 0;
  unsigned left_ = 0;
  unsigned zeros_ = 0;
  uint32_t cur_ = 0;
  bool err_ = false;
};

struct SpsInfo {
  uint8_t log2_max_frame_num = 4;
  uint8_t poc_type = 0;
  uint8_t log2_max_poc_lsb = 4;  // solo si poc_type == 0
  bool frame_mbs_only = true;
  bool ok = false;
};

struct PpsInfo {
  int pic_init_qp = 26;
  int chroma_qp_offset = 0;
  uint32_t num_ref_idx_l0 = 0;
  bool deblock_ctrl = false, constrained_intra = false, weighted = false;
  bool cabac = false;
  bool bottom_poc_present = false;
  bool redundant_pic_cnt_present = false;
  bool ok = false;
};

// SPS mínimo: solo lo necesario para leer frame_num en el slice header.
inline SpsInfo parse_sps(const uint8_t* nal, size_t len) {
  SpsInfo s;
  if (len < 5) return s;
  BitReader br(nal + 1, len - 1);
  const uint32_t profile = br.u(8);
  br.u(8);
  br.u(8);
  br.ue();  // sps_id
  switch (profile) {
    case 100: case 110: case 122: case 244: case 44: case 83: case 86:
    case 118: case 128: case 138: case 139: case 134: case 135: {
      if (br.ue() == 3) br.u(1);
      br.ue();
      br.ue();
      br.u(1);
      if (br.u(1)) return s;  // matrices de escalado: no soportado aún
      break;
    }
    default: break;
  }
  const uint32_t l = br.ue();
  if (!br.ok() || l > 12) return s;
  s.log2_max_frame_num = uint8_t(l + 4);
  s.poc_type = uint8_t(br.ue());
  if (s.poc_type == 0) {
    s.log2_max_poc_lsb = uint8_t(br.ue() + 4);
  } else if (s.poc_type == 1) {
    return s;  // no soportado
  }
  br.ue();  // max_num_ref_frames
  br.u(1);  // gaps_in_frame_num_value_allowed
  br.ue();  // ancho en MB - 1
  br.ue();  // alto en MB - 1
  s.frame_mbs_only = br.u(1) != 0;
  s.ok = br.ok();
  return s;
}

inline PpsInfo parse_pps(const uint8_t* nal, size_t len) {
  PpsInfo p;
  if (len < 4) return p;
  BitReader br(nal + 1, len - 1);
  br.ue();  // pps_id
  br.ue();  // sps_id
  p.cabac = br.u(1) != 0;
  p.bottom_poc_present = br.u(1) != 0;
  if (br.ue() != 0) return p;  // grupos de slices: no soportado
  p.num_ref_idx_l0 = br.ue();
  br.ue();
  p.weighted = br.u(1) != 0;
  br.u(2);
  p.pic_init_qp = 26 + br.se();
  br.se();  // pic_init_qs
  p.chroma_qp_offset = br.se();
  p.deblock_ctrl = br.u(1) != 0;
  p.constrained_intra = br.u(1) != 0;
  p.redundant_pic_cnt_present = br.u(1) != 0;
  p.ok = br.ok();
  return p;
}

struct SliceInfo {
  uint32_t first_mb = 0;
  uint32_t frame_num = 0;
  uint8_t type = 0;  // slice_type % 5: 0 P, 1 B, 2 I
  bool idr = false;
  bool ok = false;
};

inline SliceInfo parse_slice(const uint8_t* nal, size_t len, const SpsInfo& sps) {
  SliceInfo s;
  if (len < 3 || !sps.ok) return s;
  BitReader br(nal + 1, len - 1);
  s.first_mb = br.ue();
  s.type = uint8_t(br.ue() % 5);
  br.ue();  // pps_id
  s.frame_num = br.u(sps.log2_max_frame_num);
  s.idr = (nal[0] & 0x1F) == kNalIdr;
  s.ok = br.ok();
  return s;
}

// QP del slice (pic_init_qp + slice_qp_delta) para slices P/I de Baseline (CAVLC, sin pesos).
// Devuelve -1 si no se puede leer.
inline int slice_qp(const uint8_t* nal, size_t len, const SpsInfo& sps, const PpsInfo& pps) {
  if (len < 3 || !sps.ok || !pps.ok || pps.cabac || pps.weighted || !sps.frame_mbs_only) return -1;
  const bool idr = (nal[0] & 0x1F) == kNalIdr;
  const bool ref = ((nal[0] >> 5) & 3) != 0;
  BitReader br(nal + 1, len - 1);
  br.ue();
  const uint32_t st = br.ue() % 5;
  if (st != 0 && st != 2) return -1;  // solo P e I
  br.ue();
  br.u(sps.log2_max_frame_num);
  if (idr) br.ue();
  if (sps.poc_type == 0) {
    br.u(sps.log2_max_poc_lsb);
    if (pps.bottom_poc_present) br.se();
  }
  if (pps.redundant_pic_cnt_present) br.ue();
  if (st == 0) {
    if (br.u(1)) br.ue();  // num_ref_idx_active_override
    if (br.u(1)) {         // ref_pic_list_modification
      for (uint32_t op = br.ue(); op != 3 && br.ok(); op = br.ue()) br.ue();
    }
  }
  if (ref) {
    if (idr) {
      br.u(2);
    } else if (br.u(1)) {  // adaptive_ref_pic_marking
      for (uint32_t op = br.ue(); op != 0 && br.ok(); op = br.ue()) {
        if (op == 1 || op == 3) br.ue();
        if (op == 2) br.ue();
        if (op == 3 || op == 6) br.ue();
        if (op == 4) br.ue();
      }
    }
  }
  const int qp = pps.pic_init_qp + br.se();
  return br.ok() ? qp : -1;
}

}  // namespace ihdr
