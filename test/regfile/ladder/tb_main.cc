// Random reads, writes and (with an asynchronous reset) resets on a
// generated register file and its reference, every read compared before
// and after each clock edge. tb_top (gen_tb.py) packs the spec's inputs
// into `stim`, so this driver knows no port names. Every word is first
// written (or the array reset), unchecked: power-up state is each side's
// own.
#include <cstdint>
#include <cstdio>
#include <random>

#include "Vtb_top.h"

// From the spec, written by gen_tb.py.
extern const int kWords;
extern const int kStimWords;
extern const bool kAsyncReset;
extern const bool kExpectMismatch;  // a negative control

namespace {

void Randomize(Vtb_top& tb, std::mt19937& rng) {
  for (int i = 0; i < kStimWords; ++i) {
    tb.stim[i] = rng();
  }
}

int Check(Vtb_top& tb, int cycle, const char* when) {
  tb.eval();
  if (tb.mismatch) {
    std::printf("cycle %d (%s): generated and reference reads differ\n",
                cycle, when);
    return 1;
  }
  return 0;
}

}  // namespace

int main() {
  Vtb_top tb;
  std::mt19937 rng(1);
  int bad = 0;
  int cycle = 0;
  tb.rst_act = 0;
  tb.init_mode = 1;
  for (int w = 0; w < kWords; ++w, ++cycle) {
    Randomize(tb, rng);
    tb.init_addr = w;
    tb.clk = 0;
    tb.eval();
    tb.clk = 1;
    tb.eval();
  }
  tb.init_mode = 0;
  int resets = 0;
  for (int i = 0; i < 20000 && bad < 10; ++i, ++cycle) {
    Randomize(tb, rng);
    tb.clk = 0;
    bad += Check(tb, cycle, "clock low");
    if (kAsyncReset && rng() % 500 == 0) {
      tb.rst_act = 1;
      bad += Check(tb, cycle, "reset asserted");
      tb.rst_act = 0;
      bad += Check(tb, cycle, "reset released");
      ++resets;
    }
    tb.clk = 1;
    bad += Check(tb, cycle, "clock high");
  }
  std::printf("%d cycles, %d resets, %d mismatches\n", cycle, resets, bad);
  if (kAsyncReset && resets == 0) {
    std::printf("no reset exercised\n");
    return 1;
  }
  if (kExpectMismatch) {
    std::printf("negative control: %s\n",
                bad > 0 ? "caught, as it must be" : "NOT caught");
    return bad > 0 ? 0 : 1;
  }
  return bad == 0 ? 0 : 1;
}
