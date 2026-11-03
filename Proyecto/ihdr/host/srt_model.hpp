// Modelo de comportamiento de SRT en modo live (draft-sharabayko-srt): NAK inmediato y periódico,
// retransmisión con prioridad, TSBPD (entrega a ts+latencia) y Too-Late Packet Drop con ACK falso.
// NO es el protocolo en el cable: modela solo lo que importa para pérdida/latencia, sobre un
// simulador de eventos discretos. Solo para el PC (usa contenedores estándar).
#pragma once
#include <algorithm>
#include <cstdint>
#include <functional>
#include <queue>
#include <set>
#include <vector>

namespace sim {

using Time = int64_t;  // microsegundos

class EventQueue {
 public:
  void at(Time t, std::function<void()> fn) { q_.push(E{t, n_++, std::move(fn)}); }
  void run(Time end) {
    while (!q_.empty() && q_.top().t <= end) {
      E e = q_.top();
      q_.pop();
      now_ = e.t;
      e.fn();
    }
    now_ = std::max(now_, end);
  }
  Time now() const { return now_; }

 private:
  struct E {
    Time t;
    uint64_t n;
    std::function<void()> fn;
    bool operator<(const E& o) const { return t != o.t ? t > o.t : n > o.n; }
  };
  std::priority_queue<E> q_;
  uint64_t n_ = 0;
  Time now_ = 0;
};

inline uint64_t splitmix(uint64_t& s) {
  uint64_t z = (s += 0x9E3779B97F4A7C15ull);
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
  z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
  return z ^ (z >> 31);
}

// Pérdida por ráfagas (Gilbert-Elliott con pérdida total en el estado malo), evaluada por ranuras de
// 1 ms. El estado es función solo del tiempo y la semilla: dos escenarios con la misma semilla ven
// la misma historia de pérdidas aunque envíen streams distintos (comparación pareada).
class Channel {
 public:
  Channel(double loss, double burst_ms, uint64_t seed) : seed_(seed) {
    p_bg_ = 1.0 / std::max(1.0, burst_ms);
    p_gb_ = (loss <= 0) ? 0.0 : loss * p_bg_ / (1.0 - loss);
  }
  bool lost(Time t) {
    const size_t slot = size_t(std::max<Time>(0, t) / 1000);
    while (bad_.size() <= slot) {
      const bool prev = bad_.empty() ? false : bad_.back();
      const double u = double(splitmix(seed_) >> 11) / 9007199254740992.0;
      bad_.push_back(prev ? (u >= p_bg_) : (u < p_gb_));
    }
    return bad_[slot];
  }

 private:
  uint64_t seed_;
  double p_bg_, p_gb_;
  std::vector<bool> bad_;
};

struct SrtConfig {
  Time latency = 120000;     // SRTO_RCVLATENCY (por defecto 120 ms)
  Time owd = 15000;          // retardo unidireccional edge -> espectador
  Time jitter = 0;           // jitter uniforme [0, jitter], determinista por (seq, intento)
  Time ack_period = 10000;   // SYN de SRT: 10 ms
  Time nak_floor = 20000;    // piso del NAK periódico
  double pace_bps = 6e6;     // ritmo de envío del emisor (cola de pacing)
  Time detect_margin = 0;    // margen de la inferencia por ACK (ver on_ack_skip)
  size_t overhead = 16 + 28; // cabecera SRT + UDP/IP por paquete
  Time end = 0;              // hasta cuándo siguen los temporizadores
  bool arq = true;           // false: UDP simple (sin NAK ni retransmisión), mismo búfer de recepción
};

struct SrtStats {
  uint64_t tx_first = 0, tx_retx = 0;           // paquetes
  uint64_t bytes_first = 0, bytes_retx = 0;     // bytes en el cable (con cabeceras)
  uint64_t lost_fwd = 0, lost_rev = 0;          // perdidos por el canal
  uint64_t naks = 0, acks = 0;
  uint64_t recovered = 0;                       // faltantes que llegaron por retransmisión a tiempo
  uint64_t skipped = 0;                         // descartados por llegar tarde (lo que el video sufre)
  uint64_t late_discard = 0, retx_suppressed = 0;
};

class SrtLink {
 public:
  SrtLink(EventQueue& q, SrtConfig c, Channel fwd, Channel rev)
      : q_(q), c_(c), fwd_(std::move(fwd)), rev_(std::move(rev)) {
    q_.at(c_.ack_period, [this] { ack_tick(); });
    q_.at(c_.nak_floor, [this] { nak_tick(); });
  }

  // Lado espectador (receptor SRT).
  std::function<void(uint32_t seq, int pid)> on_deliver, on_skip;
  // Lado edge (emisor SRT): se invoca cuando el ACK que cubre `seq` fue generado en o después de su
  // plazo TSBPD, es decir, el receptor lo dio por perdido (ACK falso). No hay mensaje nuevo en SRT.
  std::function<void(uint32_t seq, int pid)> on_ack_skip;

  uint32_t send(int pid, size_t bytes) {
    const uint32_t seq = uint32_t(snd_.size());
    snd_.push_back({pid, bytes, q_.now(), 0, true, false, -1});
    const Time at = std::max(q_.now(), next_free_);
    next_free_ = at + Time(double(bytes + c_.overhead) * 8e6 / c_.pace_bps);
    q_.at(at, [this, seq] { transmit(seq, false); });
    return seq;
  }

  Time deadline(uint32_t seq) const { return snd_[seq].ts + c_.owd + c_.latency; }
  int payload_of(uint32_t seq) const { return snd_[seq].pid; }
  const SrtStats& stats() const { return st_; }

  // Cierra la entrega: lo que falta se descarta (fin del stream).
  void finish() {
    if (snd_.empty()) return;
    deliver_upto(uint32_t(snd_.size() - 1));
  }

 private:
  struct Snd { int pid; size_t bytes; Time ts; int tx; bool in_buf; bool naked = false; Time last_retx = -1; };
  struct Rcv { bool present = false; };

  Time jit(uint32_t seq, int tx) const {
    if (c_.jitter <= 0) return 0;
    uint64_t s = (uint64_t(seq) << 8) ^ uint64_t(tx) ^ 0xA5A5ull;
    return Time(splitmix(s) % uint64_t(c_.jitter + 1));
  }

  void transmit(uint32_t seq, bool retx) {
    Snd& s = snd_[seq];
    ++s.tx;
    if (retx) s.last_retx = q_.now();
    const uint64_t wire = s.bytes + c_.overhead;
    if (retx) { ++st_.tx_retx; st_.bytes_retx += wire; } else { ++st_.tx_first; st_.bytes_first += wire; }
    if (fwd_.lost(q_.now())) { ++st_.lost_fwd; return; }
    q_.at(q_.now() + c_.owd + jit(seq, s.tx), [this, seq] { rx_data(seq); });
  }

  void rx_data(uint32_t seq) {
    if (seq < deliver_ptr_) { ++st_.late_discard; return; }
    if (seq >= rcv_.size()) rcv_.resize(seq + 1);
    if (rcv_[seq].present) return;
    rcv_[seq].present = true;
    if (missing_.erase(seq)) ++st_.recovered;
    if (int64_t(seq) > highest_) {
      std::vector<uint32_t> gap;
      for (int64_t s = highest_ + 1; s < int64_t(seq); ++s) {
        if (!rcv_[s].present) { missing_.insert(uint32_t(s)); gap.push_back(uint32_t(s)); }
      }
      highest_ = seq;
      if (!gap.empty()) send_nak(gap);
    }
    q_.at(std::max(q_.now(), deadline(seq)), [this, seq] { deliver_upto(seq); });
  }

  void deliver_upto(uint32_t seq) {
    while (deliver_ptr_ <= seq) {
      const uint32_t s = deliver_ptr_++;
      if (s < rcv_.size() && rcv_[s].present) {
        if (on_deliver) on_deliver(s, snd_[s].pid);
      } else {
        missing_.erase(s);
        ++st_.skipped;
        if (on_skip) on_skip(s, snd_[s].pid);
      }
    }
  }

  void send_nak(std::vector<uint32_t> list) {
    if (!c_.arq) return;
    ++st_.naks;
    if (rev_.lost(q_.now())) { ++st_.lost_rev; return; }
    const Time arrive = q_.now() + c_.owd + jit(list[0], 99);
    q_.at(arrive, [this, list = std::move(list)] {
      for (uint32_t s : list) {
        if (s >= snd_.size() || !snd_[s].in_buf) continue;
        snd_[s].naked = true;
        if (q_.now() + c_.owd > deadline(s)) { ++st_.retx_suppressed; continue; }  // no llegaría a tiempo
        transmit(s, true);
      }
    });
  }

  void nak_tick() {
    if (!missing_.empty()) send_nak(std::vector<uint32_t>(missing_.begin(), missing_.end()));
    const Time rtt = 2 * c_.owd;
    q_.at(q_.now() + std::max(c_.nak_floor, (rtt + 4 * (rtt / 8)) / 2), [this] { nak_tick(); });
  }

  void ack_tick() {
    const uint32_t ack = missing_.empty() ? uint32_t(highest_ + 1) : *missing_.begin();
    if (ack != last_ack_) {
      last_ack_ = ack;
      ++st_.acks;
      if (rev_.lost(q_.now())) {
        ++st_.lost_rev;
      } else {
        const Time g = q_.now();  // marca de tiempo del ACK (la lleva en su cabecera)
        q_.at(g + c_.owd, [this, ack, g] { rx_ack(ack, g); });
      }
    }
    if (q_.now() < c_.end) q_.at(q_.now() + c_.ack_period, [this] { ack_tick(); });
  }

  void rx_ack(uint32_t ack, Time g) {
    for (; acked_ < ack && acked_ < snd_.size(); ++acked_) {
      snd_[acked_].in_buf = false;
      // g: marca de tiempo del ACK (receptor). Un ACK generado en/después del plazo TSBPD de un paquete
      // que el edge vio en un NAK implica descarte (ACK falso), salvo que su última retransmisión
      // llegara a tiempo y el ACK sea el tick siguiente a esa llegada.
      const Snd& x = snd_[acked_];
      if (!on_ack_skip || !x.naked || g + c_.detect_margin < deadline(acked_)) continue;
      const bool explained = x.last_retx >= 0 && x.last_retx + c_.owd <= deadline(acked_) &&
                             g <= x.last_retx + c_.owd + c_.ack_period + c_.detect_margin;
      if (!explained) on_ack_skip(acked_, x.pid);
    }
  }

  EventQueue& q_;
  SrtConfig c_;
  Channel fwd_, rev_;
  SrtStats st_;
  std::vector<Snd> snd_;
  std::vector<Rcv> rcv_;
  std::set<uint32_t> missing_;
  int64_t highest_ = -1;
  uint32_t deliver_ptr_ = 0, last_ack_ = 0xFFFFFFFFu, acked_ = 0;
  Time next_free_ = 0;
};

}  // namespace sim
