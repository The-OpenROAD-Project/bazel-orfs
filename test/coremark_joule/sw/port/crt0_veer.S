/* RV32 startup for VeeR EH1 on the sim-control platform.
 *
 * Three things this has that sw/port/crt0.S does not, each forced by
 * VeeR rather than chosen:
 *
 * 1. **MRAC.** VeeR decides per 256 MB region whether fetches are
 *    cacheable and whether accesses have side-effects, from a 32-bit
 *    CSR at 0x7c0. The layout is two bits per region: cacheable at bit
 *    2R, side-effect at bit 2R+1 (see lsu_addrcheck.sv's csr_idx and
 *    ifu_ifc_ctl.sv's cacheable_select). Until this is written, region 8
 *    is not cacheable and every instruction fetch goes to the bus -- the
 *    instruction cache this study exists to measure would sit idle and
 *    the energy number would be of something else entirely.
 *
 *      region 8 (the image):   cacheable, no side-effects -> bit 16 set,
 *                              bit 17 clear
 *      region 1 (the device):  side-effects, not cacheable -> bit 3 set,
 *                              bit 2 clear
 *      every other region:     side-effects, not cacheable, which is the
 *                              safe default for an address nothing maps
 *
 *    That is 0xAAA9AAAA: all the odd bits (side-effects everywhere) with
 *    bit 17 cleared and bit 16 set.
 *
 * 2. **A .data copy loop.** The DCCM is inside the core, so the harness
 *    cannot preload it; link_veer.ld gives .rodata and .data a load
 *    address in external memory and a run address in the DCCM, and the
 *    loop below moves them. It runs once, before the first iteration,
 *    and the SAIF window is the last iteration.
 *
 * 3. **mtvec.** VeeR implements machine mode properly, so a fault
 *    vectors through mtvec rather than through the fixed table
 *    crt0.S builds for cores without it.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
/* Zicsr is enabled for this file alone rather than through -march.
 * VeeR implements the CSRs; ibex does too, but the study compares the
 * two at the same -march string, and the only code here that needs a
 * CSR instruction is the four lines below. Confining the extension to
 * the startup file keeps the ISA label on the result honest. */
	.option arch, +zicsr

	.equ MRAC,          0x7c0
	.equ SIM_CTRL_OUT,  0x10000000
	.equ SIM_CTRL_HALT, 0x10000008

	.section .text.start, "ax"
	.globl _start
	.type _start, @function
_start:
	/* Region attributes first: everything after this point wants the
	   image cacheable and the device side-effecting. */
	li	t0, 0xAAA9AAAA
	csrw	MRAC, t0

	/* Faults report and stop rather than looping silently. Direct mode:
	   the low two bits of mtvec are the mode field and _trap is aligned
	   well past them. */
	la	t0, _trap
	csrw	mtvec, t0

	.option push
	.option norelax
	la	gp, __global_pointer$
	.option pop
	la	sp, _stack_top

	/* Copy .rodata and .data from their load addresses in external
	   memory to their run addresses in the DCCM. */
	la	t0, _data_lma
	la	t1, _data_start
	la	t2, _data_end
1:	bgeu	t1, t2, 2f
	lw	t3, 0(t0)
	sw	t3, 0(t1)
	addi	t0, t0, 4
	addi	t1, t1, 4
	j	1b
2:

	/* zero .bss */
	la	t0, _bss_start
	la	t1, _bss_end
3:	bgeu	t0, t1, 4f
	sw	zero, 0(t0)
	addi	t0, t0, 4
	j	3b
4:

	/* CoreMark is built with MAIN_HAS_NOARGC=1, so main takes no
	   arguments and returns int; the return value is discarded because
	   the CRC lines on stdout are what decides pass or fail. */
	call	main

	li	t0, SIM_CTRL_HALT
	li	t1, 1
	sw	t1, 0(t0)
5:	j	5b
	.size _start, . - _start

/* Reached through mtvec. Writes '!' to the sim-control character
 * register so the marker lands in the captured stdout, then stops the
 * simulation. */
	.balign 4
	.globl _trap
	.type _trap, @function
_trap:
	li	t0, SIM_CTRL_OUT
	li	t1, 33			/* '!' */
	sw	t1, 0(t0)
	li	t0, SIM_CTRL_HALT
	li	t1, 1
	sw	t1, 0(t0)
1:	j	1b
	.size _trap, . - _trap
