// Clock the counter and check it counted. The answer is not the point --
// a simulator that links and runs is.
#include <cstdio>
#include <cstdlib>

#include "Vcounter.h"
#include "verilated.h"

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  Vcounter top;

  top.rst = 1;
  for (int i = 0; i < 4; i++) {
    top.clk = 0; top.eval();
    top.clk = 1; top.eval();
  }
  top.rst = 0;

  const int kCycles = 100;
  for (int i = 0; i < kCycles; i++) {
    top.clk = 0; top.eval();
    top.clk = 1; top.eval();
  }
  top.final();

  if (top.count != kCycles) {
    std::fprintf(stderr, "counter: got %u after %d cycles, expected %d\n",
                 (unsigned)top.count, kCycles, kCycles);
    return 1;
  }
  std::printf("verilator smoke: counted %d cycles\n", kCycles);
  return 0;
}
