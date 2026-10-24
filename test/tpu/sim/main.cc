// Clocks tpu_meso_tb until its stream is done and its pipelines have
// drained, then fails unless every result of tpu in its rig matched tpu
// alone, there were results and not all zero, and no FIFO was ever
// written full.
#include <cstdio>
#include <memory>

#include "Vtpu_meso_tb.h"
#include "verilated.h"

int main(int argc, char** argv)
{
  auto ctx = std::make_unique<VerilatedContext>();
  ctx->commandArgs(argc, argv);
  auto tb = std::make_unique<Vtpu_meso_tb>(ctx.get());
  const int kSets = 4, kRows = 24;
  int drain = 0;
  for (int cycle = 0; cycle < 100000 && drain < 64; cycle++) {
    tb->clk = 0;
    tb->eval();
    tb->clk = 1;
    tb->eval();
    if (tb->done) {
      drain++;
    }
  }
  std::printf("compared %u, nonzero %u, errors %u, overflows %u, max fill %u\n",
              tb->compared,
              tb->nonzero,
              tb->errors,
              tb->overflows,
              tb->max_fill);
  tb->final();
  const bool ok = tb->done && tb->errors == 0 && tb->overflows == 0
                  && tb->compared == unsigned(kSets * kRows) && tb->nonzero > 0;
  return ok ? 0 : 1;
}
