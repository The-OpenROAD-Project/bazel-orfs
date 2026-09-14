// Verilator harness for the study's sim-control platform.
//
// One binary per core (and per stage, for the gate-level runs), driving
// whichever program +meminit= points at. It counts cycles, captures
// stdout, and decides why a run ended.
//
// Cycles are counted here rather than read from a CSR inside the core.
// ibex has mcycle, picorv32 has no machine-mode CSRs at all, and SERV's
// CSR block is a build option -- counting posedges is the only method
// all three can be measured with, and it costs the designs nothing.
//
// The count starts when reset deasserts and ends at the halt write, so
// it covers the identical prologue in both programs. That is deliberate:
// the study never uses an absolute count, only the difference between a
// three-iteration and a two-iteration run, and everything common to both
// cancels.
//
// SPDX-License-Identifier: Apache-2.0

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "Vcm_soc.h"
#include "verilated.h"

namespace {

// Long enough for any reset strategy in the study; SERV's "MINI" needs
// only a few, picorv32 one.
constexpr int kResetCycles = 16;

// Exit codes. Distinct so a sweep can tell a core that cannot run a
// binary at all from one that ran it and got the wrong answer -- the
// former is an ISA or toolchain mistake, the latter a hardware bug.
constexpr int kExitOk = 0;
constexpr int kExitTrap = 2;
constexpr int kExitTimeout = 3;

const char *plusarg(int argc, char **argv, const char *key, const char *fallback)
{
    const size_t n = strlen(key);
    for (int i = 1; i < argc; i++) {
        if (argv[i][0] == '+' && strncmp(argv[i] + 1, key, n) == 0 &&
            argv[i][1 + n] == '=') {
            return argv[i] + 2 + n;
        }
    }
    return fallback;
}

}  // namespace

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);

    const char *stdout_path = plusarg(argc, argv, "stdout", nullptr);
    const char *cycles_path = plusarg(argc, argv, "cycles", nullptr);
    // A budget rather than an unbounded run: a core that never reaches
    // the halt write would otherwise hang a build forever. SERV needs
    // ~10^8 cycles for one CoreMark iteration, so the default is well
    // clear of a working run on the slowest core in the study.
    const uint64_t max_cycles =
        strtoull(plusarg(argc, argv, "max_cycles", "2000000000"), nullptr, 0);

    FILE *out = stdout;
    if (stdout_path != nullptr) {
        out = fopen(stdout_path, "w");
        if (out == nullptr) {
            fprintf(stderr, "cm_sim: cannot write %s\n", stdout_path);
            return 1;
        }
    }

    Vcm_soc *dut = new Vcm_soc;

    dut->resetn = 0;
    for (int i = 0; i < kResetCycles; i++) {
        dut->clk = 0;
        dut->eval();
        dut->clk = 1;
        dut->eval();
    }
    dut->resetn = 1;

    uint64_t cycles = 0;
    int status = kExitTimeout;

    while (cycles < max_cycles) {
        dut->clk = 0;
        dut->eval();
        dut->clk = 1;
        dut->eval();
        cycles++;

        if (dut->out_valid) {
            fputc(static_cast<int>(dut->out_byte), out);
        }
        if (dut->trap) {
            // Illegal instruction or misaligned access: the program and
            // the core disagree about the ISA. Report the cycle, since
            // that plus a disassembly locates it immediately.
            fprintf(stderr, "cm_sim: core trapped at cycle %llu\n",
                    static_cast<unsigned long long>(cycles));
            status = kExitTrap;
            break;
        }
        if (dut->halt_valid) {
            status = kExitOk;
            break;
        }
    }

    if (status == kExitTimeout) {
        fprintf(stderr,
                "cm_sim: no halt within %llu cycles; the program never "
                "reached portable_fini\n",
                static_cast<unsigned long long>(max_cycles));
    }

    fflush(out);
    if (out != stdout) {
        fclose(out);
    }

    // The cycle count goes to its own file so a genrule can declare it
    // as an output without having to parse the program's stdout, which
    // belongs to CoreMark rather than to us.
    if (cycles_path != nullptr) {
        FILE *cf = fopen(cycles_path, "w");
        if (cf == nullptr) {
            fprintf(stderr, "cm_sim: cannot write %s\n", cycles_path);
            return 1;
        }
        fprintf(cf, "%llu\n", static_cast<unsigned long long>(cycles));
        fclose(cf);
    }

    dut->final();
    delete dut;
    return status;
}
