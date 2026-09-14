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

// Built only for the gate-level configuration, where rules_verilator's
// trace_mode = "saif" defines this. The RTL simulators are compiled
// without tracing at all, so they pay none of its cost.
#if VM_TRACE_SAIF
#include "verilated_saif_c.h"
#endif

namespace {

// A bounded trace window, kept in a ring buffer rather than written to a
// waveform. A hang in a program that only prints at the end gives no
// other evidence, and a full VCD of a CoreMark run is hundreds of
// megabytes to produce a dozen useful lines. This records the distinct
// fetch addresses in order, which is enough to see whether a run is
// looping and over what.
constexpr int kTraceSlots = 16;

struct FetchTrace
{
    uint32_t addr[kTraceSlots] = {};
    uint64_t cycle[kTraceSlots] = {};
    int      count = 0;

    // Only transitions are recorded: a fetch address held for many
    // cycles is one entry, so the window covers a loop body rather than
    // a dozen cycles of one stall.
    void sample(uint32_t a, uint64_t c)
    {
        if (count > 0 && addr[(count - 1) % kTraceSlots] == a) {
            return;
        }
        addr[count % kTraceSlots]  = a;
        cycle[count % kTraceSlots] = c;
        count++;
    }

    void dump(FILE *f) const
    {
        const int n = count < kTraceSlots ? count : kTraceSlots;
        const int first = count < kTraceSlots ? 0 : count % kTraceSlots;
        fprintf(f, "cm_sim: last %d distinct fetch addresses:\n", n);
        for (int i = 0; i < n; i++) {
            const int s = (first + i) % kTraceSlots;
            fprintf(f, "cm_sim:   cycle %-12llu 0x%08x\n",
                    static_cast<unsigned long long>(cycle[s]), addr[s]);
        }
    }
};


// Long enough for any reset strategy in the study; SERV's "MINI" needs
// only a few, picorv32 one.
constexpr int kResetCycles = 16;

// Exit codes. Distinct so a sweep can tell a core that cannot run a
// binary at all from one that ran it and got the wrong answer -- the
// former is an ISA or toolchain mistake, the latter a hardware bug.
constexpr int kExitOk = 0;
constexpr int kExitTrap = 2;
constexpr int kExitTimeout = 3;

#if VM_TRACE_SAIF
// A SAIF over a whole CoreMark run would be enormous and is not needed:
// switching activity is stationary once the benchmark is in its steady
// state, so a window inside it represents the run. The window is given
// in cycles rather than inferred, so the same window can be stated in
// the write-up and re-used across cores.
struct SaifWindow
{
    uint64_t start = 0;
    uint64_t end = 0;

    bool active(uint64_t cycle) const
    {
        return cycle >= start && (end == 0 || cycle < end);
    }
};
#endif

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

#if VM_TRACE_SAIF
    const char *saif_path = plusarg(argc, argv, "saif", nullptr);
    SaifWindow window;
    window.start = strtoull(plusarg(argc, argv, "saif_start", "0"), nullptr, 0);
    window.end = strtoull(plusarg(argc, argv, "saif_end", "0"), nullptr, 0);
#endif

    FILE *out = stdout;
    if (stdout_path != nullptr) {
        out = fopen(stdout_path, "w");
        if (out == nullptr) {
            fprintf(stderr, "cm_sim: cannot write %s\n", stdout_path);
            return 1;
        }
    }

    Vcm_soc *dut = new Vcm_soc;

#if VM_TRACE_SAIF
    VerilatedSaifC *saif = nullptr;
    bool saif_open = false;
    if (saif_path != nullptr) {
        Verilated::traceEverOn(true);
        saif = new VerilatedSaifC;
        dut->trace(saif, 99);
    }
#endif

    dut->resetn = 0;
    for (int i = 0; i < kResetCycles; i++) {
        dut->clk = 0;
        dut->eval();
        dut->clk = 1;
        dut->eval();
    }
    dut->resetn = 1;

    uint64_t   cycles = 0;
    int        status = kExitTimeout;
    FetchTrace trace;

    while (cycles < max_cycles) {
        dut->clk = 0;
        dut->eval();
        dut->clk = 1;
        dut->eval();
        cycles++;

#if VM_TRACE_SAIF
        // Opening at the window's first cycle rather than at time zero
        // keeps the reset and the whole pre-steady-state prologue out of
        // the activity that report_power sees.
        if (saif != nullptr && window.active(cycles)) {
            if (!saif_open) {
                saif->open(saif_path);
                saif_open = true;
            }
            saif->dump(static_cast<uint64_t>(cycles));
        } else if (saif_open && !window.active(cycles)) {
            saif->close();
            saif_open = false;
            // The window is the measurement; running on past it only
            // costs wall time on a gate-level simulator.
            status = kExitOk;
            break;
        }
#endif

        trace.sample(static_cast<uint32_t>(dut->dbg_instr_addr), cycles);

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
        // The fetch address at the moment the budget ran out separates a
        // run that was merely slow from one stuck in a loop. A core that
        // traps with no vector installed lands back at the reset
        // address, so a value of 0 here says "trap loop", not "hung".
        fprintf(stderr,
                "cm_sim: no halt within %llu cycles; the program never "
                "reached portable_fini (last fetch address 0x%08x)\n",
                static_cast<unsigned long long>(max_cycles),
                static_cast<unsigned>(dut->dbg_instr_addr));
        trace.dump(stderr);
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

#if VM_TRACE_SAIF
    if (saif_open) {
        saif->close();
    }
    delete saif;
#endif

    dut->final();
    delete dut;
    return status;
}
