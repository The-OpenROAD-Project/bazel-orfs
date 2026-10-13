// Random writes on both ports of generate_ram's two-write-port RAM, a
// quarter of them to the same word in the same cycle, and a read every
// cycle compared between the netlist and the behavioral model. Every
// word is written once first, unchecked: an unwritten word reads each
// side's power-up state.
#include <cstdint>
#include <cstdio>
#include <random>

#include "Vtb_ram_2w.h"

#ifndef WORDS
#define WORDS 8
#endif

int main() {
  Vtb_ram_2w tb;
  std::mt19937 rng(1);
  int bad = 0;
  int cycle = 0;
  auto step = [&](bool check, bool we0, int a0, int d0, bool we1, int a1,
                  int d1, int ra) {
    tb.clk = 0;
    tb.we0 = we0;
    tb.addr_w0 = a0;
    tb.D0 = d0;
    tb.we1 = we1;
    tb.addr_w1 = a1;
    tb.D1 = d1;
    tb.addr_r0 = ra;
    tb.eval();
    if (check && tb.Q_model != tb.Q_gen) {
      std::printf("cycle %d: read %d: model %02x, generated %02x\n", cycle,
                  ra, tb.Q_model, tb.Q_gen);
      ++bad;
    }
    tb.clk = 1;
    tb.eval();
    ++cycle;
  };
  for (int w = 0; w < WORDS; ++w) {
    step(false, true, w, rng() & 0xff, false, 0, 0, w);
  }
  for (int i = 0; i < 20000 && bad < 10; ++i) {
    const int a0 = rng() % WORDS;
    const int a1 = rng() % 4 == 0 ? a0 : rng() % WORDS;
    step(true, rng() % 2, a0, rng() & 0xff, rng() % 2, a1, rng() & 0xff,
         rng() % WORDS);
  }
  std::printf("%d cycles, %d mismatches\n", cycle, bad);
  return bad == 0 ? 0 : 1;
}
