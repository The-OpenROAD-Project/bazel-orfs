// Clocks sched.py's testbench, both arms of a kind under the same random
// stimulus, until it is done. Fails on any differing output, and when
// the picks, wakeups or ready decodes hit too rarely for the comparison
// to mean anything. EXPECT_MISMATCH: a negative control, which passes
// only when some output differs.
#include <cstdio>

#include "Vtb.h"

int main() {
  Vtb tb;
  int cycles = 0;
  for (; cycles < 10000000 && !tb.done; ++cycles) {
    tb.clock = 0;
    tb.eval();
    tb.clock = 1;
    tb.eval();
  }
  std::printf("%d cycles, %u mismatches; hits: %u n_match, %u n_wake, %u ready\n",
              cycles, tb.bad, tb.n_match, tb.n_wake, tb.n_ready);
  if (!tb.done) {
    std::printf("testbench never finished\n");
    return 1;
  }
#ifdef EXPECT_MISMATCH
  return tb.bad > 0 ? 0 : 1;
#else
  const unsigned floor = cycles / 100;
  if (tb.n_match < floor || tb.n_wake < floor || tb.n_ready < floor) {
    std::printf("too few hits (floor %u): the comparison proves little\n", floor);
    return 1;
  }
  return tb.bad == 0 ? 0 : 1;
#endif
}
