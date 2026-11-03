// Pruebas del núcleo: ida y vuelta de la SEI, escape de emulación, parser sobre un stream real.
#include <cstdio>
#include <cstdlib>
#include <vector>
#include "../core/h264.hpp"
#include "../core/sei.hpp"
#include "../core/ts.hpp"
using namespace ihdr;
#define CHECK(c) do { if (!(c)) { std::printf("FALLA %s:%d %s\n", __FILE__, __LINE__, #c); return 1; } } while (0)

int main(int argc, char** argv) {
  // 1. SEI ida y vuelta con bytes que exigen prevención de emulación y payload > 255 B.
  std::vector<uint8_t> nal(700);
  nal[0] = 0x21;  // ref_idc 1, tipo 1
  for (size_t i = 1; i < nal.size(); ++i) nal[i] = (i % 7 < 3) ? 0 : uint8_t(i);
  std::vector<uint8_t> sei(nal.size() * 2), scratch(nal.size() + 64), back(nal.size() * 2);
  const size_t m = sei_wrap_ihdr(nal.data(), nal.size(), sei.data(), sei.size(), scratch.data(), scratch.size());
  CHECK(m > nal.size());
  for (size_t i = 0; i + 2 < m; ++i) CHECK(!(sei[i] == 0 && sei[i + 1] == 0 && sei[i + 2] <= 2));  // sin falsos start codes
  const size_t r = sei_unwrap_ihdr(sei.data(), m, back.data(), back.size());
  CHECK(r == nal.size());
  for (size_t i = 0; i < r; ++i) CHECK(back[i] == nal[i]);
  uint8_t other[4] = {0x06, 0x05, 0x01, 0x80};
  CHECK(sei_unwrap_ihdr(other, sizeof(other), back.data(), back.size()) == 0);  // SEI ajena

  // 2. TS: todo paquete mide 188 B, empieza con 0x47 y los ES suman lo escrito.
  struct C { size_t pk = 0, es = 0, pusi = 0; bool sync = true; } c;
  TsMuxer mux([](void* x, const uint8_t* p, const TsMeta& mt) {
    auto* cc = static_cast<C*>(x);
    ++cc->pk; cc->es += mt.es_len; cc->pusi += mt.pusi && !mt.psi; cc->sync &= p[0] == 0x47;
  }, &c);
  std::vector<uint8_t> es(5000, 0x55);
  mux.write_au(es.data(), es.size(), 123456, true);
  CHECK(c.sync && c.es == es.size() && c.pusi == 1);
  CHECK(c.pk == 2 + (5000 + 14 + 183) / 184);

  // 3. Parser sobre un stream real (opcional).
  if (argc > 1) {
    FILE* f = std::fopen(argv[1], "rb");
    if (f) {
      std::vector<uint8_t> b(1 << 22);
      b.resize(std::fread(b.data(), 1, b.size(), f));
      std::fclose(f);
      NalIter it(b.data(), b.size());
      Nal n; SpsInfo sps; size_t slices = 0, idr = 0;
      while (it.next(n)) {
        if (n.type == kNalSps && !sps.ok) sps = parse_sps(&b[n.off], n.len);
        if (is_vcl(n.type)) { SliceInfo s = parse_slice(&b[n.off], n.len, sps); CHECK(s.ok); ++slices; idr += s.idr; }
      }
      CHECK(sps.ok && slices > 0);
      std::printf("stream: %zu slices, %zu IDR, log2_max_frame_num=%d\n", slices, idr, sps.log2_max_frame_num);
    }
  }
  std::printf("core OK\n");
  return 0;
}
