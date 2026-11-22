// The toy's capture: the all-RTL simulation, each unit behind a wrapper
// of its ports (scripts/capture_wrap.py), traced as a VCD of those
// wrappers alone, from cycle 0, at both clock phases, the stimulus
// tb.cc's.
//
//   capture_tb <vcd> <cycles> <clk_period_ps> <outputs>
//
// The replays (flow/power.bzl's shard_replay) start from the same
// state as this simulation did and follow it from time 0; the warm-up
// is part of the capture, the SAIF window starts after it.

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#include "Vmini_top.h"
#include "verilated.h"
#include "verilated_vcd_c.h"

namespace {

uint64_t next(uint64_t &state) {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return state;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr, "usage: %s <vcd> <cycles> <clk_period_ps> <outputs>\n", argv[0]);
        return 2;
    }
    const uint64_t cycles = strtoull(argv[2], nullptr, 0);
    const uint64_t half = strtoull(argv[3], nullptr, 0) / 2;
    const int warmup = 16;
    FILE *outputs = fopen(argv[4], "w");

    Verilated::traceEverOn(true);
    Vmini_top *dut = new Vmini_top;
    VerilatedVcdC *vcd = new VerilatedVcdC;
    dut->trace(vcd, 99);
    vcd->open(argv[1]);

    uint64_t state = 0x9e3779b97f4a7c15ULL;
    uint64_t t = 0;
    for (uint64_t c = 0; c < warmup + cycles; c++) {
        dut->clock = 0;
        dut->seed = next(state);
        dut->blockb_ext_in = static_cast<uint16_t>(next(state));
        dut->eval();
        vcd->dump(t);
        t += half;
        dut->clock = 1;
        dut->eval();
        vcd->dump(t);
        t += half;
        if (c >= warmup) {
            fprintf(outputs, "%016llx", static_cast<unsigned long long>(dut->sum));
            fprintf(outputs, " %04x\n", static_cast<unsigned>(dut->blockb_ext_out));
        }
    }
    vcd->close();
    fclose(outputs);
    dut->final();
    delete vcd;
    delete dut;
    return 0;
}
