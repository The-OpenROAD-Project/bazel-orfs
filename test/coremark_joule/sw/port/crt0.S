/* Minimal RV32 startup for the sim-control platform.
 *
 * No .data copy loop: the linker script places every section at its
 * load address, and the harness loads the whole image into RAM before
 * releasing reset, so .data is already where it belongs. That removes
 * the one piece of startup code that differs between a ROM-based and a
 * RAM-based target, and keeps this file identical for all three cores.
 *
 * .bss is still zeroed here rather than by the loader, so the ELF and
 * the memory image agree about what the program expects on entry.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
	.section .text.start, "ax"
	.globl _start
	.type _start, @function
_start:
	/* No interrupts are enabled anywhere in this study, and no core is
	   required to implement the CSRs that would disable them, so there
	   is deliberately nothing here that touches mstatus or mtvec. */
	.option push
	.option norelax
	la	gp, __global_pointer$
	.option pop
	la	sp, _stack_top

	/* zero .bss */
	la	t0, _bss_start
	la	t1, _bss_end
1:	bgeu	t0, t1, 2f
	sw	zero, 0(t0)
	addi	t0, t0, 4
	j	1b
2:

	/* CoreMark is built with MAIN_HAS_NOARGC=1, so main takes no
	   arguments and returns int; the return value is discarded because
	   the CRC lines on stdout are what decides pass or fail. */
	call	main

	/* Falls through on a main that returns; sim_halt's own loop covers
	   a core that ignores the halt write. */
	li	t0, 0x10000008
	li	t1, 1
	sw	t1, 0(t0)
3:	j	3b
	.size _start, . - _start
