/* Elaboration gate for upstream VeeR EH1.
 *
 * There is nothing to run here. The point is the link: a cc_binary is
 * the only thing that forces Verilator to run over the core and the C++
 * compiler to build what it emits, because verilator_cc_library returns
 * a CcInfo whose default outputs are empty until something links it.
 *
 * What it gates is the thing that made ORFS's vendored copy unusable
 * for this study -- a core that no longer elaborates as its authors
 * wrote it. Elaborating is not simulating, and passing here says
 * nothing about behaviour; the CRC gate on a full CoreMark run is what
 * says that. This is the rung below it, and it is the one that runs in
 * minutes after a bump.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include "Vswerv_wrapper.h"
#include "verilated.h"

int main(int argc, char **argv)
{
    Verilated::commandArgs(argc, argv);
    /* Constructing the model is what pulls the verilated translation
     * unit into the link. Without it the linker is free to drop the
     * whole archive and the gate would pass on an empty binary. */
    auto *dut = new Vswerv_wrapper;
    dut->final();
    delete dut;
    return 0;
}
