// generate_ram's two-write RAM with -reset_value 0xa5: after a reset
// every word reads 0xa5 on both the netlist and the behavioral model;
// then random writes on both ports, a quarter to the same word, with an
// asynchronous reset now and then, a read compared every cycle.
#include <cstdint>
#include <cstdio>
#include <random>

#include "Vtb_ram_2w_rst.h"

int main() {
  Vtb_ram_2w_rst tb;
  std::mt19937 rng(1);
  int bad = 0;
  int cycle = 0;
  auto compare = [&](int ra) {
    tb.addr_r0 = ra;
    tb.eval();
    if (tb.Q_model != tb.Q_gen) {
      std::printf("cycle %d: read %d: model %02x, generated %02x\n", cycle,
                  ra, tb.Q_model, tb.Q_gen);
      ++bad;
    }
  };
  auto reset = [&]() {
    tb.clk = 0;
    tb.we0 = 0;
    tb.we1 = 0;
    tb.rst_n = 0;
    tb.eval();
    tb.rst_n = 1;
    tb.eval();
    for (int w = 0; w < 8; ++w) {
      compare(w);
      if (tb.Q_model != 0xa5) {
        std::printf("cycle %d: word %d after reset: model %02x\n", cycle, w,
                    tb.Q_model);
        ++bad;
      }
    }
  };
  tb.rst_n = 1;
  tb.clk = 0;
  tb.eval();
  reset();
  for (int i = 0; i < 20000 && bad < 10; ++i, ++cycle) {
    if (rng() % 500 == 0) {
      reset();
    }
    const int a0 = rng() % 8;
    tb.clk = 0;
    tb.we0 = rng() % 2;
    tb.addr_w0 = a0;
    tb.D0 = rng() & 0xff;
    tb.we1 = rng() % 2;
    tb.addr_w1 = rng() % 4 == 0 ? a0 : rng() % 8;
    tb.D1 = rng() & 0xff;
    compare(rng() % 8);
    tb.clk = 1;
    tb.eval();
  }
  std::printf("%d cycles, %d mismatches\n", cycle, bad);
  return bad == 0 ? 0 : 1;
}
