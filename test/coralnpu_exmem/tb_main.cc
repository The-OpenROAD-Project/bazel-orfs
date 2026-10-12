// coralnpu's LsuV1 as the snapshot has it, beside the surgered one with
// the EX/MEM register on its inputs, each driven by the same requests
// under its own ready signals. Each side's bus transactions, register
// writebacks, flushes and faults are logged in order, channel by
// channel, and compared, timing aside: the surgered LSU must do the same things a cycle later.
// The negative control, the surgered LSU with the snapshot's ready
// signals, must differ: requests accepted while the register holds
// others overrun the queue and are lost.
//
// The requests stress the LSU harder than coralnpu's dispatch does: up
// to four lanes a cycle, in order (a lane is offered only if every lane
// before it is ready), with random ops, sizes and alignments across
// the ITCM, the DTCM, the peripheral window and the external bus, and
// the instruction, external and flush handshakes stalling at random. A
// float load or store goes on lane 0 only, as dispatch issues them.
#include <cstdint>
#include <cstdio>
#include <map>
#include <random>
#include <string>
#include <vector>

#include "VLsuV1_bad.h"
#include "VLsuV1_exmem.h"
#include "VLsuV1_ref.h"

namespace {

constexpr int kLanes = 4;
constexpr int kRequests = 20000;
constexpr long kMaxCycles = 400000;

struct Request {
  bool store;
  uint32_t reg;
  uint32_t op;
  uint32_t pc;
  uint32_t addr;
  uint32_t data;
  uint32_t flt_data;
};

std::vector<Request> MakeRequests(uint32_t seed) {
  std::mt19937 rng(seed);
  // ITCM, DTCM, the peripheral window and the external bus.
  const uint32_t base[] = {0x0, 0x10000, 0x30000, 0x40000};
  const uint32_t span[] = {0x2000, 0x8000, 0x2000, 0x400};
  std::vector<Request> reqs;
  for (int i = 0; i < kRequests; i++) {
    int region = rng() % 4;
    Request r;
    r.store = rng() & 1;
    r.reg = rng() % 32;
    // 0..7 the integer loads and stores, 8..10 fence.i and the cache
    // flushes, 11 a vector load or store, 12 a float one; mostly memory.
    r.op = (rng() % 8) ? rng() % 8 : 8 + rng() % 5;
    r.pc = 0x100 + 4 * i;
    r.addr = base[region] + rng() % span[region];
    r.data = rng();
    r.flt_data = rng();
    reqs.push_back(r);
  }
  return reqs;
}

uint32_t Hash(uint32_t x) {
  x ^= x >> 16;
  x *= 0x7feb352d;
  x ^= x >> 15;
  x *= 0x846ca68b;
  return x ^ (x >> 16);
}

template <typename W>
std::string Hex(const W& w, int words) {
  std::string s;
  char buf[16];
  for (int i = words - 1; i >= 0; i--) {
    std::snprintf(buf, sizeof buf, "%08x", w[i]);
    s += buf;
  }
  return s;
}

struct Log {
  std::vector<std::string> events;
  long cycles = 0;
  int accepted = 0;
};

#define LANE(m, k, field) m.io_req_##k##_##field
#define SET_LANE(m, k, v, r)                \
  do {                                      \
    LANE(m, k, valid) = (v);                \
    LANE(m, k, bits_store) = (r).store;     \
    LANE(m, k, bits_addr) = (r).reg;        \
    LANE(m, k, bits_op) = (r).op;           \
    LANE(m, k, bits_pc) = (r).pc;           \
    m.io_busPort_addr_##k = (r).addr;       \
    m.io_busPort_data_##k = (r).data;       \
  } while (0)

template <typename M>
Log Run(const std::vector<Request>& reqs, uint32_t seed) {
  M m;
  Log log;
  std::mt19937 rng(seed);
  std::map<uint32_t, std::vector<uint32_t>> dtcm;  // line -> 4 words
  uint32_t line_d = 0, line_i = 0, line_e = 0;
  auto word = [&](uint32_t line, int i) {
    auto it = dtcm.find(line);
    return it == dtcm.end() ? Hash(line * 4 + i) : it->second[i];
  };

  m.clock = 0;
  m.reset = 1;
  for (int i = 0; i < 4; i++) {
    m.clock = !m.clock;
    m.eval();
    m.clock = !m.clock;
    m.eval();
  }
  m.reset = 0;

  size_t next = 0;
  int idle = 0;
  for (long cycle = 0; cycle < kMaxCycles; cycle++) {
    m.clock = 0;
    // Bus responses for last cycle's requests, and this cycle's stalls.
    for (int i = 0; i < 4; i++) {
      m.io_dbus_rdata[i] = word(line_d, i);
      m.io_ibus_rdata[i] = Hash(line_i * 4 + i + 7);
      m.io_ebus_dbus_rdata[i] = Hash(line_e * 4 + i + 13);
    }
    m.io_ibus_ready = rng() % 3 != 0;
    m.io_ebus_dbus_ready = rng() % 4 == 0;
    m.io_flush_ready = rng() % 2;
    m.io_ebus_fault_valid = 0;
    m.io_ebus_fault_bits_write = 0;
    m.io_ebus_fault_bits_addr = 0;
    m.io_ebus_fault_bits_epc = 0;

    // Garbage on every lane, none valid, to read the ready signals.
    auto r32 = [&rng] { return static_cast<uint32_t>(rng()); };
    Request junk{static_cast<bool>(rng() & 1), r32() % 32, r32() % 13, r32(),
                 r32(), r32(), r32()};
    SET_LANE(m, 0, 0, junk);
    SET_LANE(m, 1, 0, junk);
    SET_LANE(m, 2, 0, junk);
    SET_LANE(m, 3, 0, junk);
    m.io_busPort_flt_data_0 = junk.flt_data;
    m.eval();
    bool ready[kLanes] = {static_cast<bool>(m.io_req_0_ready),
                          static_cast<bool>(m.io_req_1_ready),
                          static_cast<bool>(m.io_req_2_ready),
                          static_cast<bool>(m.io_req_3_ready)};
    int offer = (rng() % 3 == 0) ? 0 : 1 + rng() % kLanes;
    int fire = 0;
    // A float load or store only on lane 0: it alone has the float
    // register file's port (io_busPort_flt_data_0).
    while (fire < offer && fire < kLanes && ready[fire] &&
           next + fire < reqs.size() &&
           !(fire > 0 && reqs[next + fire].op == 12)) {
      fire++;
    }
    if (fire > 0) SET_LANE(m, 0, 1, reqs[next + 0]);
    if (fire > 1) SET_LANE(m, 1, 1, reqs[next + 1]);
    if (fire > 2) SET_LANE(m, 2, 1, reqs[next + 2]);
    if (fire > 3) SET_LANE(m, 3, 1, reqs[next + 3]);
    if (fire > 0) m.io_busPort_flt_data_0 = reqs[next].flt_data;
    m.eval();
    next += fire;
    log.accepted += fire;

    char buf[256];
    if (m.io_dbus_valid) {
      uint32_t line = m.io_dbus_addr >> 4;
      std::snprintf(buf, sizeof buf, "dbus %c %08x %04x ",
                    m.io_dbus_write ? 'w' : 'r', m.io_dbus_addr,
                    m.io_dbus_wmask);
      log.events.push_back(buf + (m.io_dbus_write ? Hex(m.io_dbus_wdata, 4)
                                                  : std::string()));
      if (m.io_dbus_write) {
        std::vector<uint32_t> w(4);
        for (int i = 0; i < 4; i++) w[i] = word(line, i);
        for (int b = 0; b < 16; b++) {
          if (m.io_dbus_wmask >> b & 1) {
            uint32_t byte = m.io_dbus_wdata[b / 4] >> (8 * (b % 4)) & 0xff;
            w[b / 4] = (w[b / 4] & ~(0xffu << (8 * (b % 4)))) |
                       byte << (8 * (b % 4));
          }
        }
        dtcm[line] = w;
      }
      line_d = line;
    }
    if (m.io_ibus_valid && m.io_ibus_ready) {
      std::snprintf(buf, sizeof buf, "ibus %08x", m.io_ibus_addr);
      log.events.push_back(buf);
      line_i = m.io_ibus_addr >> 4;
    }
    if (m.io_ebus_dbus_valid && m.io_ebus_dbus_ready) {
      std::snprintf(buf, sizeof buf, "ebus %c %08x %08x %u ",
                    m.io_ebus_dbus_write ? 'w' : 'r', m.io_ebus_dbus_pc,
                    m.io_ebus_dbus_addr, m.io_ebus_dbus_size);
      log.events.push_back(buf + (m.io_ebus_dbus_write
                                      ? Hex(m.io_ebus_dbus_wdata, 4)
                                      : std::string()));
      line_e = m.io_ebus_dbus_addr >> 4;
    }
    if (m.io_flush_valid && m.io_flush_ready) {
      std::snprintf(buf, sizeof buf, "flush %d %08x", m.io_flush_fencei,
                    m.io_flush_pcNext);
      log.events.push_back(buf);
    }
    if (m.io_fault_valid) {
      std::snprintf(buf, sizeof buf, "fault %d %08x %08x",
                    m.io_fault_bits_write, m.io_fault_bits_addr,
                    m.io_fault_bits_epc);
      log.events.push_back(buf);
    }
    if (m.io_rd_valid) {
      std::snprintf(buf, sizeof buf, "rd x%u %08x", m.io_rd_bits_addr,
                    m.io_rd_bits_data);
      log.events.push_back(buf);
    }
    if (m.io_rd_flt_valid) {
      std::snprintf(buf, sizeof buf, "rd f%u %08x", m.io_rd_flt_bits_addr,
                    m.io_rd_flt_bits_data);
      log.events.push_back(buf);
    }

    m.clock = 1;
    m.eval();
    log.cycles = cycle;
    idle = (next == reqs.size() && !m.io_active) ? idle + 1 : 0;
    if (idle > 64) break;
  }
  return log;
}

// The first difference between two logs, or "" if there is none. Each
// channel (dbus, ibus, ebus, flush, fault, rd) is compared in its own
// order: between channels, the order follows the timing, which differs.
std::string Compare(const Log& a, const Log& b) {
  auto split = [](const Log& l) {
    std::map<std::string, std::vector<std::string>> c;
    for (const auto& e : l.events) c[e.substr(0, e.find(' '))].push_back(e);
    return c;
  };
  auto ca = split(a), cb = split(b);
  for (const auto& [name, ea] : ca) {
    const auto& eb = cb[name];
    size_t n = std::min(ea.size(), eb.size());
    for (size_t i = 0; i < n; i++) {
      if (ea[i] != eb[i]) {
        return name + " " + std::to_string(i) + ": '" + ea[i] + "' vs '" +
               eb[i] + "'";
      }
    }
    if (ea.size() != eb.size()) {
      return name + ": " + std::to_string(ea.size()) + " vs " +
             std::to_string(eb.size());
    }
  }
  for (const auto& [name, eb] : cb) {
    if (!ca.count(name)) return name + ": 0 vs " + std::to_string(eb.size());
  }
  return "";
}

}  // namespace

int main() {
  int failures = 0;
  for (uint32_t seed = 1; seed <= 3; seed++) {
    auto reqs = MakeRequests(seed);
    // Each side its own stalls: the same seed, consumed at its own pace.
    Log ref = Run<VLsuV1_ref>(reqs, seed * 101);
    Log exmem = Run<VLsuV1_exmem>(reqs, seed * 101);
    Log bad = Run<VLsuV1_bad>(reqs, seed * 101);
    std::printf(
        "seed %u: %zu events; snapshot %ld cycles, EX/MEM %ld, "
        "negative control %ld (%d of %d accepted)\n",
        seed, ref.events.size(), ref.cycles, exmem.cycles, bad.cycles,
        bad.accepted, kRequests);
    if (ref.accepted != kRequests || exmem.accepted != kRequests) {
      std::printf("  FAIL: requests left unaccepted (%d, %d)\n", ref.accepted,
                  exmem.accepted);
      failures++;
    }
    if (ref.events.size() < kRequests / 2) {
      std::printf("  FAIL: the snapshot did too little to compare\n");
      failures++;
    }
    std::string d = Compare(ref, exmem);
    if (!d.empty()) {
      std::printf("  FAIL: EX/MEM differs from the snapshot at %s\n",
                  d.c_str());
      failures++;
    }
    std::string c = Compare(ref, bad);
    if (c.empty()) {
      std::printf("  FAIL: the negative control matches the snapshot\n");
      failures++;
    } else {
      std::printf("  negative control differs, as it must: %s\n", c.c_str());
    }
  }
  std::printf(failures ? "FAIL\n" : "PASS\n");
  return failures ? 1 : 0;
}
