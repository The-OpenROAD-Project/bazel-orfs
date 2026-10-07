// Random reads and writes on riscv32i's register file and on the netlist
// generate_regfile writes for it; every read of both ports compared.
// Every word is written once first, unchecked: an unwritten word reads
// what each side's power-up state happens to be (the generated flops
// hold the inverse of the value).
#include <cstdint>
#include <cstdio>
#include <random>

#include "Vtb_top.h"

namespace {

int Check(Vtb_top& tb, int cycle) {
  tb.eval();
  if (tb.rd1_rtl != tb.rd1_gen || tb.rd2_rtl != tb.rd2_gen) {
    std::printf(
        "cycle %d: ra1 %u ra2 %u: rtl %08x %08x, generated %08x %08x\n",
        cycle, tb.ra1, tb.ra2, tb.rd1_rtl, tb.rd2_rtl, tb.rd1_gen,
        tb.rd2_gen);
    return 1;
  }
  return 0;
}

// One clock: inputs set while the clock is low, the write on its rising
// edge; with `check`, both reads compared before and after it.
int Cycle(Vtb_top& tb, int cycle, bool check, bool we, int wa, uint32_t wd,
          int ra1, int ra2) {
  tb.clk = 0;
  tb.we3 = we;
  tb.wa3 = wa;
  tb.wd3 = wd;
  tb.ra1 = ra1;
  tb.ra2 = ra2;
  tb.eval();
  int bad = check ? Check(tb, cycle) : 0;
  tb.clk = 1;
  tb.eval();
  bad += check ? Check(tb, cycle) : 0;
  return bad;
}

}  // namespace

int main() {
  Vtb_top tb;
  std::mt19937 rng(1);
  int bad = 0;
  int cycle = 0;
  for (int w = 0; w < 32; ++w, ++cycle) {
    Cycle(tb, cycle, false, true, w, rng(), w, w);
  }
  for (int i = 0; i < 20000 && bad < 10; ++i, ++cycle) {
    bad += Cycle(tb, cycle, true, rng() % 2, rng() % 32, rng(), rng() % 32,
                 rng() % 32);
  }
  std::printf("%d cycles, %d mismatches\n", cycle, bad);
  return bad == 0 ? 0 : 1;
}
