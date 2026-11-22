// Random stimulus for the power-shards toy's gate-level netlist, and the
// SAIF of it.
//
//   tb <saif> <cycles> <clk_period_ps> [<outputs>]
//
// <outputs>: every traced cycle's outputs, one line each, for comparing
// simulations of the same design. Which scopes the SAIF carries is the
// model's (sims.bzl: a Verilator tracing_on -scope configuration).
//
// The toy has no reset and no program: its parent XORs `seed` into the
// register of every block output it feeds back, and BlockB's ext_in goes
// straight in, so random inputs every cycle keep every block busy. A
// fixed generator seed makes the SAIF the same on every run.
//
// As the study's harness (sim/main.cc): both clock phases are dumped, a
// SAIF records real time, half a clock period per dump, and a few warm-up
// cycles run before the SAIF opens, so registers that start at zero have
// settled into the stimulus.

#include <cstdint>
#include <cstdio>
#include <cstdlib>

#include "Vmini_top.h"
#include "verilated.h"
#include "verilated_saif_c.h"

namespace {

uint64_t next(uint64_t &state) {
    // xorshift64
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return state;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc < 4 || argc > 5) {
        fprintf(stderr, "usage: %s <saif> <cycles> <clk_period_ps> [<outputs>]\n", argv[0]);
        return 2;
    }
    FILE *outputs = argc > 4 ? fopen(argv[4], "w") : nullptr;
    const char *saif_path = argv[1];
    const uint64_t cycles = strtoull(argv[2], nullptr, 0);
    const uint64_t half = strtoull(argv[3], nullptr, 0) / 2;
    const int warmup = 16;

    Verilated::traceEverOn(true);
    Vmini_top *dut = new Vmini_top;
    VerilatedSaifC *saif = new VerilatedSaifC;
    dut->trace(saif, 99);

    uint64_t state = 0x9e3779b97f4a7c15ULL;
    uint64_t t = 0;
    for (uint64_t c = 0; c < warmup + cycles; c++) {
        if (c == warmup) {
            saif->open(saif_path);
        }
        dut->clock = 0;
        dut->seed = next(state);
        dut->blockb_ext_in = static_cast<uint16_t>(next(state));
        dut->eval();
        if (c >= warmup) {
            saif->dump(t);
            t += half;
        }
        dut->clock = 1;
        dut->eval();
        if (c >= warmup) {
            saif->dump(t);
            t += half;
            if (outputs != nullptr) {
                fprintf(outputs, "%016llx", static_cast<unsigned long long>(dut->sum));
                fprintf(outputs, " %04x\n", static_cast<unsigned>(dut->blockb_ext_out));
            }
        }
    }
    saif->close();
    if (outputs != nullptr) {
        fclose(outputs);
    }
    dut->final();
    delete saif;
    delete dut;
    return 0;
}
