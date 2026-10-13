// Random writes on both ports, a quarter to the same word, and every
// cycle a plain read and a read of every bank at its own index, the
// netlist's outputs compared with the behavioral model's. Every word is
// written once first, unchecked.
#include <cstdint>
#include <cstdio>
#include <random>

#include "Vtb_ram_rb.h"

int main() {
  Vtb_ram_rb tb;
  std::mt19937 rng(1);
  int bad = 0;
  int cycle = 0;
  auto step = [&](bool check, bool we0, int a0, int d0, bool we1, int a1,
                  int d1) {
    tb.clk = 0;
    tb.we0 = we0;
    tb.addr_w0 = a0;
    tb.D0 = d0;
    tb.we1 = we1;
    tb.addr_w1 = a1;
    tb.D1 = d1;
    tb.addr_r0 = rng() % 8;
    tb.addr_rb0_b0 = rng() % 2;
    tb.addr_rb0_b1 = rng() % 2;
    tb.addr_rb0_b2 = rng() % 2;
    tb.addr_rb0_b3 = rng() % 2;
    tb.eval();
    if (check && (tb.Q_model != tb.Q_gen || tb.Qrb_model != tb.Qrb_gen)) {
      std::printf("cycle %d: model %02x %08x, generated %02x %08x\n", cycle,
                  tb.Q_model, tb.Qrb_model, tb.Q_gen, tb.Qrb_gen);
      ++bad;
    }
    tb.clk = 1;
    tb.eval();
    ++cycle;
  };
  for (int w = 0; w < 8; ++w) {
    step(false, true, w, rng() & 0xff, false, 0, 0);
  }
  for (int i = 0; i < 20000 && bad < 10; ++i) {
    const int a0 = rng() % 8;
    const int a1 = rng() % 4 == 0 ? a0 : rng() % 8;
    step(true, rng() % 2, a0, rng() & 0xff, rng() % 2, a1, rng() & 0xff);
  }
  std::printf("%d cycles, %d mismatches\n", cycle, bad);
  return bad == 0 ? 0 : 1;
}
