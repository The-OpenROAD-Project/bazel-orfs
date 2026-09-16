/* The sim-control device: the whole of this study's bare-metal I/O.
 *
 * Two memory-mapped words are the entire platform contract, and every
 * core in the study sees the same two. That is what lets one C runtime,
 * one linker script and one CoreMark port serve cores whose buses,
 * privilege models and CSR support have nothing in common.
 *
 * The convention is not invented here. lowRISC's ibex simple_system
 * uses a character register and a halt register at 0x20000/0x20008, and
 * picorv32's testbench.v uses 0x1000_0000 for putchar and 0x2000_0000
 * for exit. This study picks one address pair and gives every core its
 * own small bus adapter, rather than adopting one vendor's testbench
 * and porting the software three times.
 *
 * 0x1000_0000 is chosen so the decode is a single high address bit,
 * which keeps the adapters trivial on a bit-serial core where every
 * comparator costs cycles.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#ifndef CM_SIM_CTRL_H
#define CM_SIM_CTRL_H

#define SIM_CTRL_BASE 0x10000000u
#define SIM_CTRL_OUT  (SIM_CTRL_BASE + 0x0u) /* byte write: one stdout char */
#define SIM_CTRL_HALT (SIM_CTRL_BASE + 0x8u) /* write 1: stop the simulation */

#define DEV_WRITE(addr, val) (*((volatile unsigned int *)(addr)) = (val))

static inline void sim_putchar(char c)
{
    DEV_WRITE(SIM_CTRL_OUT, (unsigned char)c);
}

/* Never returns: the harness stops the clock on this write. The loop is
 * what the core executes in the cycle or two before that takes effect,
 * and on a core that ignores the write entirely it is what makes the
 * failure a harness timeout rather than a runaway fetch.
 */
static inline void sim_halt(void)
{
    DEV_WRITE(SIM_CTRL_HALT, 1);
    for (;;) {
    }
}

#endif /* CM_SIM_CTRL_H */
