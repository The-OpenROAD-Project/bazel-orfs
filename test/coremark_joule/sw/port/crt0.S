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
/* Vector area, placed first in RAM by link.ld.
 *
 * The three cores do not agree on where execution begins. picorv32 and
 * SERV fetch their first instruction from their reset address, which the
 * wrappers set to 0. ibex fetches from boot_addr_i + 0x80 and places its
 * exception vector table at boot_addr_i itself -- lowRISC's own linker
 * script encodes this as `_entry_point = _vectors_start + 0x80`. Setting
 * ibex's boot_addr_i to 0 therefore does not start the program: it
 * starts 0x80 bytes into it, on whatever instruction happens to live
 * there.
 *
 * So the image carries entry points for both conventions, and the ibex
 * wrapper passes boot_addr_i = 0x100:
 *
 *   0x000          reset entry for a core that starts at its reset address
 *   0x100 .. 0x17c ibex exception vectors
 *   0x180          ibex reset entry (0x100 + 0x80)
 *
 * The exception vectors report and stop rather than returning. Neither
 * SERV nor ibex has a trap output the harness can watch, so without this
 * a fault would silently vector somewhere and the run would look like a
 * hang with no evidence. With it, a fault prints a marker and halts: the
 * CRC gate then fails with something to read.
 */
	.section .text.vectors, "ax"
	.globl _vectors
_vectors:
	j	_start
	.org 0x100
	.rept 32
	j	_trap
	.endr
	j	_start

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

/* Reached only from an exception vector. Writes '!' to the sim-control
 * character register so the marker lands in the captured stdout, then
 * stops the simulation. */
	.globl _trap
	.type _trap, @function
_trap:
	li	t0, 0x10000000
	li	t1, 33			/* '!' */
	sw	t1, 0(t0)
	li	t0, 0x10000008
	li	t1, 1
	sw	t1, 0(t0)
1:	j	1b
	.size _trap, . - _trap
