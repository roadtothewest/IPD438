// Emulador edge -> espectador: stream H.264 -> SEI de I-headers -> TS -> SRT (modelo) -> canal con
// pérdida -> espectador. Escribe el TS que el espectador reconstruyó y un resumen.
//
//   ihdr_sim --a A.h264 [--b B.h264] --mode plain|report|ack --out recv.ts
//            [--loss 0.02 --burst-ms 20 --seed 1 --latency-ms 120 --owd-ms 15 --jitter-ms 0]
//            [--ih-every 5 --fps 30 --frames N --pace-mbps 6 --force-ih K --arq 1]
//  --arq 0: sin retransmisión (UDP simple); la latencia queda como búfer de jitter.
//
//  plain  : SRT tal cual con el stream A (A puede ser GoP largo o corto).
//  report : A + I-headers; el espectador avisa al edge cada descarte (extensión, cota superior).
//  ack    : A + I-headers; el edge infiere el descarte con la marca de tiempo de los ACK (SRT sin cambios).
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "../core/h264.hpp"
#include "../core/rewrite.hpp"
#include "../core/sei.hpp"
#include "../core/ts.hpp"
#include "srt_model.hpp"

using Bytes = std::vector<uint8_t>;
using namespace ihdr;

namespace {

enum class Kind { Idr, Intra, P };

struct Au {
  Bytes es;
  Kind kind = Kind::P;
  uint32_t frame_num = 0;
  int qp = -1;
};

Bytes read_file(const std::string& p) {
  Bytes b;
  FILE* f = std::fopen(p.c_str(), "rb");
  if (!f) { std::fprintf(stderr, "no puedo abrir %s\n", p.c_str()); std::exit(1); }
  std::fseek(f, 0, SEEK_END);
  b.resize(size_t(std::ftell(f)));
  std::fseek(f, 0, SEEK_SET);
  if (std::fread(b.data(), 1, b.size(), f) != b.size()) std::exit(1);
  std::fclose(f);
  return b;
}

// Parte un Annex B en access units. Inicio de AU: no-VCL tras un VCL, o slice con first_mb == 0.
std::vector<Au> split_aus(const Bytes& s) {
  std::vector<Au> aus;
  SpsInfo sps;
  PpsInfo pps;
  NalIter it(s.data(), s.size());
  Nal n;
  Au cur;
  bool has_vcl = false;
  size_t au_begin = 0;
  auto close = [&](size_t end) {
    if (!has_vcl) return;
    cur.es.assign(s.begin() + long(au_begin), s.begin() + long(end));
    aus.push_back(std::move(cur));
    cur = Au();
    has_vcl = false;
  };
  while (it.next(n)) {
    const size_t sc = (n.off >= 4 && s[n.off - 4] == 0) ? n.off - 4 : n.off - 3;
    if (n.type == kNalSps && !sps.ok) sps = parse_sps(&s[n.off], n.len);
    if (n.type == kNalPps && !pps.ok) pps = parse_pps(&s[n.off], n.len);
    if (is_vcl(n.type)) {
      const SliceInfo si = parse_slice(&s[n.off], n.len, sps);
      if (has_vcl && si.first_mb == 0) { close(sc); au_begin = sc; }
      if (!has_vcl) { cur.qp = slice_qp(&s[n.off], n.len, sps, pps); cur.frame_num = si.frame_num; cur.kind = n.type == kNalIdr ? Kind::Idr : (si.type == 2 ? Kind::Intra : Kind::P); }
      has_vcl = true;
    } else if (has_vcl) {
      close(sc);
      au_begin = sc;
    }
  }
  close(s.size());
  return aus;
}

void append_sc(Bytes& o, const uint8_t* nal, size_t n) {
  static const uint8_t sc[4] = {0, 0, 0, 1};
  o.insert(o.end(), sc, sc + 4);
  o.insert(o.end(), nal, nal + n);
}

// Lado codificador (lo que correrá en el STM32): AU de A + cada slice intra de B, reescrito como
// intra no-IDR con el frame_num del P que reemplaza y envuelto en una SEI.
struct Params { SpsInfo sps; PpsInfo pps; };

Bytes build_encoder_au(const Au& a, const Au* b, const PpsInfo* pps_b, const Params& pr) {
  Bytes o = a.es;
  if (!b) return o;
  NalIter it(b->es.data(), b->es.size());
  Nal n;
  Bytes sei(b->es.size() + 64), scratch(b->es.size() * 3 + 64), intra(b->es.size() + 64);
  while (it.next(n)) {
    if (n.type != kNalIdr) continue;
    const size_t k = idr_to_intra(&b->es[n.off], n.len, pr.sps, *pps_b, pr.pps, a.frame_num, 0, intra.data(), intra.size(),
                                  scratch.data(), scratch.size());
    if (!k) { std::fprintf(stderr, "idr_to_intra fallo\n"); std::exit(1); }
    const size_t m = sei_wrap_ihdr(intra.data(), k, sei.data(), sei.size(), scratch.data(), scratch.size());
    if (m) append_sc(o, sei.data(), m);
  }
  return o;
}

// Lado edge: quita las SEI de I-header (espectador sano) o las desenvuelve (espectador que perdió).
Bytes edge_variant(const Bytes& enc, bool use_ihdr) {
  Bytes out, tmp(enc.size() + 16);
  NalIter it(enc.data(), enc.size());
  Nal n;
  Bytes ih;
  bool have_ih = false;
  while (it.next(n)) {
    if (n.type == kNalSei) {
      const size_t m = sei_unwrap_ihdr(&enc[n.off], n.len, tmp.data(), tmp.size());
      if (m) {  // SEI de I-header
        have_ih = true;
        append_sc(ih, tmp.data(), m);
        continue;
      }
    }
    if (use_ihdr && is_vcl(n.type)) continue;  // el I-header reemplaza al P
    append_sc(out, &enc[n.off], n.len);
  }
  if (use_ihdr && have_ih) {
    uint8_t rp[8];
    const size_t m = sei_recovery_point(rp, sizeof(rp));
    Bytes r;
    append_sc(r, rp, m);
    r.insert(r.end(), ih.begin(), ih.end());
    r.insert(r.end(), out.begin(), out.end());  // lo no-VCL que traiga el AU original (si hay)
    return r;
  }
  return out;
}

struct TsPkt { uint8_t d[kTsPacket]; TsMeta m; };
struct Payload { int au; std::vector<TsPkt> ts; size_t bytes() const { return ts.size() * kTsPacket; } };

struct Args {
  std::string a, b, mode = "plain", out = "recv.ts", ref;
  double loss = 0.02, burst_ms = 20, pace_mbps = 6;
  uint64_t seed = 1;
  int arq = 1, force_ih = -1, latency_ms = 120, owd_ms = 15, jitter_ms = 0, ih_every = 5, fps = 30, frames = 0;
};

}  // namespace

int main(int argc, char** argv) {
  Args g;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string k = argv[i], v = argv[i + 1];
    if (k == "--a") g.a = v; else if (k == "--b") g.b = v; else if (k == "--mode") g.mode = v;
    else if (k == "--out") g.out = v; else if (k == "--loss") g.loss = std::atof(v.c_str());
    else if (k == "--burst-ms") g.burst_ms = std::atof(v.c_str());
    else if (k == "--seed") g.seed = std::strtoull(v.c_str(), nullptr, 10);
    else if (k == "--latency-ms") g.latency_ms = std::atoi(v.c_str());
    else if (k == "--owd-ms") g.owd_ms = std::atoi(v.c_str());
    else if (k == "--jitter-ms") g.jitter_ms = std::atoi(v.c_str());
    else if (k == "--ih-every") g.ih_every = std::atoi(v.c_str());
    else if (k == "--fps") g.fps = std::atoi(v.c_str());
    else if (k == "--frames") g.frames = std::atoi(v.c_str());
    else if (k == "--arq") g.arq = std::atoi(v.c_str());
    else if (k == "--force-ih") g.force_ih = std::atoi(v.c_str());
    else if (k == "--pace-mbps") g.pace_mbps = std::atof(v.c_str());
    else { std::fprintf(stderr, "opción desconocida %s\n", k.c_str()); return 1; }
  }
  if (g.a.empty()) { std::fprintf(stderr, "falta --a\n"); return 1; }
  const bool use_ih = g.mode != "plain";
  if (use_ih && g.b.empty()) { std::fprintf(stderr, "el modo %s necesita --b\n", g.mode.c_str()); return 1; }

  std::vector<Au> A = split_aus(read_file(g.a));
  size_t N = A.size();
  if (g.frames > 0 && size_t(g.frames) < N) N = size_t(g.frames);

  // Parámetros del stream A (SPS/PPS) para reescribir los headers.
  Params pr;
  {
    const Bytes raw = read_file(g.a);
    NalIter it(raw.data(), raw.size());
    Nal n;
    while (it.next(n) && !(pr.sps.ok && pr.pps.ok)) {
      if (n.type == kNalSps && !pr.sps.ok) pr.sps = parse_sps(&raw[n.off], n.len);
      if (n.type == kNalPps && !pr.pps.ok) pr.pps = parse_pps(&raw[n.off], n.len);
    }
    if (!pr.sps.ok || !pr.pps.ok) { std::fprintf(stderr, "SPS/PPS no soportados\n"); return 1; }
  }
  // Candidatos de I-header: --b acepta varios streams separados por coma (p. ej. a distintos QP).
  // En cada AU se usa el intra cuyo QP es el más cercano al del P que reemplaza, como haría el
  // codificador si codifica el I-header con el QP del P (menos deriva).
  struct Cand { std::vector<Au> aus; PpsInfo pps; SpsInfo sps; };
  std::vector<Cand> cands;
  if (use_ih) {
    size_t from = 0;
    while (from <= g.b.size()) {
      const size_t to = std::min(g.b.find(',', from), g.b.size());
      const std::string path = g.b.substr(from, to - from);
      from = to + 1;
      if (path.empty()) continue;
      Cand c;
      const Bytes rb = read_file(path);
      c.aus = split_aus(rb);
      NalIter ib(rb.data(), rb.size());
      Nal n;
      while (ib.next(n) && !(c.pps.ok && c.sps.ok)) {
        if (n.type == kNalPps && !c.pps.ok) c.pps = parse_pps(&rb[n.off], n.len);
        if (n.type == kNalSps && !c.sps.ok) c.sps = parse_sps(&rb[n.off], n.len);
      }
      if (!pps_compatible(c.pps, pr.pps)) { std::fprintf(stderr, "PPS de %s incompatible con el de A\n", path.c_str()); return 1; }
      // La reescritura usa el SPS de A para leer y escribir el encabezado: deben coincidir.
      if (c.sps.log2_max_frame_num != pr.sps.log2_max_frame_num || c.sps.poc_type != pr.sps.poc_type ||
          c.sps.log2_max_poc_lsb != pr.sps.log2_max_poc_lsb || c.sps.frame_mbs_only != pr.sps.frame_mbs_only) {
        std::fprintf(stderr, "SPS de %s distinto del de A (codificar con el mismo keyint)\n", path.c_str());
        return 1;
      }
      if (c.aus.size() < N) { std::fprintf(stderr, "%s tiene menos frames que A\n", path.c_str()); return 1; }
      cands.push_back(std::move(c));
    }
  }
  std::vector<const Au*> ih(N, nullptr);
  std::vector<const PpsInfo*> ih_pps(N, nullptr);
  size_t bad_fn = 0, n_ih = 0;
  double qp_gap = 0;
  for (size_t k = 0; k < N && use_ih; ++k) {
    if (A[k].kind != Kind::P) continue;
    int best = -1, gap = 1 << 20;
    for (size_t c = 0; c < cands.size(); ++c) {
      const Au& x = cands[c].aus[k];
      if (x.kind != Kind::Idr) continue;
      const int d = (A[k].qp >= 0 && x.qp >= 0) ? std::abs(x.qp - A[k].qp) : 0;
      if (d < gap) { gap = d; best = int(c); }
    }
    if (best < 0) continue;
    ih[k] = &cands[size_t(best)].aus[k];
    ih_pps[k] = &cands[size_t(best)].pps;
    qp_gap += gap;
    ++n_ih;
  }

  using namespace sim;
  EventQueue q;
  const Time frame_us = 1000000 / g.fps;
  const Time end = Time(N) * frame_us + 5000000;
  SrtConfig cfg;
  cfg.latency = g.latency_ms * 1000;
  cfg.owd = g.owd_ms * 1000;
  cfg.jitter = g.jitter_ms * 1000;
  cfg.pace_bps = g.pace_mbps * 1e6;
  cfg.end = end;
  cfg.arq = g.arq != 0;
  SrtLink link(q, cfg, Channel(g.loss, g.burst_ms, g.seed * 2 + 1), Channel(g.loss, g.burst_ms, g.seed * 2 + 2));

  std::vector<Payload> payloads;
  std::vector<Bytes> sent_es(N);
  std::vector<char> sent_ih(N, 0);
  std::vector<std::vector<char>> got(N);  // por AU: máscara de bytes del ES recibidos
  std::vector<char> au_pusi(N, 0);
  uint64_t enc_bytes = 0, enc_bytes_noih = 0;
  bool need = false;
  size_t skipped_true = 0, detected = 0, detect_tp = 0;
  std::vector<char> truly_skipped;  // por seq

  link.on_deliver = [&](uint32_t, int pid) {
    const Payload& p = payloads[size_t(pid)];
    for (const TsPkt& t : p.ts) {
      if (t.m.psi) continue;
      if (t.m.pusi) au_pusi[size_t(p.au)] = 1;
      auto& m = got[size_t(p.au)];
      std::fill(m.begin() + t.m.es_off, m.begin() + t.m.es_off + t.m.es_len, char(1));
    }
  };
  link.on_skip = [&](uint32_t seq, int) {
    ++skipped_true;
    if (truly_skipped.size() <= seq) truly_skipped.resize(seq + 1, 0);
    truly_skipped[seq] = 1;
    if (g.mode == "report") q.at(q.now() + cfg.owd, [&] { need = true; });  // aviso espectador -> edge
  };
  if (g.mode == "ack") {
    link.on_ack_skip = [&](uint32_t seq, int) {
      ++detected;
      if (seq < truly_skipped.size() && truly_skipped[seq]) ++detect_tp;
      need = true;
    };
  }

  size_t n_sent_ih = 0, au_max_ih = 0, p_count = 0;
  uint64_t p_bytes = 0;
  for (size_t k = 0; k < N; ++k) {
    q.at(Time(k) * frame_us, [&, k] {
      const Bytes enc = build_encoder_au(A[k], ih[k], ih_pps[k], pr);
      enc_bytes += enc.size();
      enc_bytes_noih += A[k].es.size();
      bool use = false;
      if (int(k) == g.force_ih) need = true;  // prueba: medir la deriva sola
      if (use_ih && ih[k] && need) { use = true; need = false; ++n_sent_ih; }
      sent_ih[k] = use;
      sent_es[k] = edge_variant(enc, use);
      if (use) au_max_ih = std::max(au_max_ih, sent_es[k].size());
      if (A[k].kind == Kind::P) { p_bytes += A[k].es.size(); ++p_count; }
      got[k].assign(sent_es[k].size(), 0);
      // un AU -> paquetes TS -> grupos de 7 -> paquetes SRT (el último, parcial)
      std::vector<TsPkt> all;
      struct C2 { std::vector<TsPkt>* v; } c2{&all};
      TsMuxer m2([](void* c, const uint8_t* pkt, const TsMeta& mm) {
        TsPkt t; std::memcpy(t.d, pkt, kTsPacket); t.m = mm;
        static_cast<C2*>(c)->v->push_back(t);
      }, &c2);
      m2.write_au(sent_es[k].data(), sent_es[k].size(), uint64_t(k) * 90000 / uint64_t(g.fps),
                  A[k].kind == Kind::Idr || use || k == 0);
      for (size_t i = 0; i < all.size(); i += 7) {
        Payload p;
        p.au = int(k);
        for (size_t j = i; j < all.size() && j < i + 7; ++j) p.ts.push_back(all[j]);
        const int pid = int(payloads.size());
        payloads.push_back(std::move(p));
        link.send(pid, payloads.back().bytes());
      }
    });
  }
  q.run(end);
  link.finish();

  // Reconstrucción del espectador: NAL con bytes faltantes se trunca (slice) o se descarta.
  FILE* fo = std::fopen(g.out.c_str(), "wb");
  if (!fo) return 1;
  struct Out { FILE* f; } of{fo};
  TsMuxer wmux([](void* c, const uint8_t* pkt, const TsMeta&) { std::fwrite(pkt, 1, kTsPacket, static_cast<Out*>(c)->f); }, &of);
  size_t au_lost = 0, au_partial = 0, nal_cut = 0;
  for (size_t k = 0; k < N; ++k) {
    if (!au_pusi[k]) { ++au_lost; continue; }
    const Bytes& es = sent_es[k];
    const auto& m = got[k];
    Bytes rec;
    NalIter it(es.data(), es.size());
    Nal n;
    bool partial = false;
    while (it.next(n)) {
      const size_t sc = (n.off >= 4 && es[n.off - 4] == 0) ? n.off - 4 : n.off - 3;
      size_t first_missing = n.off + n.len;
      for (size_t i = sc; i < n.off + n.len; ++i) if (!m[i]) { first_missing = i; break; }
      if (first_missing == n.off + n.len) { rec.insert(rec.end(), es.begin() + long(sc), es.begin() + long(n.off + n.len)); continue; }
      partial = true;
      ++nal_cut;
      if (is_vcl(n.type) && first_missing >= n.off + 2) rec.insert(rec.end(), es.begin() + long(sc), es.begin() + long(first_missing));
    }
    if (partial) ++au_partial;
    if (!rec.empty()) wmux.write_au(rec.data(), rec.size(), uint64_t(k) * 90000 / uint64_t(g.fps), k == 0 || A[k].kind == Kind::Idr);
  }
  std::fclose(fo);

  const SrtStats& s = link.stats();
  const double secs = double(N) / g.fps;
  std::printf("modo=%s frames=%zu ih_disponibles=%zu ih_enviados=%zu frame_num_distinto=%zu dif_qp_media=%.2f\n", g.mode.c_str(), N, n_ih, n_sent_ih, bad_fn, n_ih ? qp_gap / double(n_ih) : 0.0);
  std::printf("srt: tx=%llu retx=%llu perdidos_fwd=%llu recuperados=%llu descartados=%llu tarde=%llu retx_suprimidas=%llu\n",
              (unsigned long long)s.tx_first, (unsigned long long)s.tx_retx, (unsigned long long)s.lost_fwd,
              (unsigned long long)s.recovered, (unsigned long long)s.skipped, (unsigned long long)s.late_discard,
              (unsigned long long)s.retx_suppressed);
  std::printf("au: perdidos=%zu parciales=%zu nal_cortados=%zu\n", au_lost, au_partial, nal_cut);
  std::printf("kbps: edge->viewer=%.0f retx_kbps=%.0f encoder->edge=%.0f encoder->edge_sin_ih=%.0f\n",
              double(s.bytes_first + s.bytes_retx) * 8 / secs / 1000, double(s.bytes_retx) * 8 / secs / 1000,
              double(enc_bytes) * 8 / secs / 1000, double(enc_bytes_noih) * 8 / secs / 1000);
  std::printf("pico: au_ih_max=%zu p_medio=%.0f\n", au_max_ih, p_count ? double(p_bytes) / double(p_count) : 0.0);
  if (g.mode == "ack")
    std::printf("deteccion_ack: marcados=%zu verdaderos=%zu descartes_reales=%zu\n", detected, detect_tp, skipped_true);
  return 0;
}
