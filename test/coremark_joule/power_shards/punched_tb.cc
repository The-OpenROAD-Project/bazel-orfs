// The capture of punched.sv's Punched: the RTL, Punched and PunCore each
// behind a wrapper of its ports (scripts/capture_wrap.py), traced as a
// VCD of those wrappers alone, from cycle 0, at both clock phases, the
// input random (capture_tb.cc's, for the toy's other units).
//
//   punched_tb <vcd> <cycles> <clk_period_ps>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#include "VPunched.h"
#include "verilated.h"
#include "verilated_vcd_c.h"

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s <vcd> <cycles> <clk_period_ps>\n", argv[0]);
        return 2;
    }
    const uint64_t cycles = strtoull(argv[2], nullptr, 0);
    const uint64_t half = strtoull(argv[3], nullptr, 0) / 2;

    Verilated::traceEverOn(true);
    VPunched *dut = new VPunched;
    VerilatedVcdC *vcd = new VerilatedVcdC;
    dut->trace(vcd, 99);
    vcd->open(argv[1]);

    uint64_t state = 0x9e3779b97f4a7c15ULL;
    uint64_t t = 0;
    for (uint64_t c = 0; c < cycles; c++) {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        dut->clock = 0;
        // reset asserted in cycles 2 to 4, released at cycle 5's start
        dut->reset = c >= 2 && c < 5;
        dut->din = state & 0xf;
        dut->eval();
        vcd->dump(t);
        t += half;
        dut->clock = 1;
        dut->eval();
        vcd->dump(t);
        t += half;
    }
    vcd->close();
    dut->final();
    delete vcd;
    delete dut;
    return 0;
}
