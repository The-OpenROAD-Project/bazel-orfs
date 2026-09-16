/* Startup for a core whose program runs where it is loaded.
 *
 * This is the runtime the study's small cores used before their memory
 * map grew a boot ROM and a copy loop (crt0.S). XiangShan still wants
 * the simple form: its harness loads the whole image into one external
 * memory at 0x8000_0000 and the core fetches from there, so every
 * section already sits at its run address and nothing has to be copied.
 * .bss is zeroed here so the ELF and the memory image agree about what
 * the program expects on entry, and the headroom above it is painted so
 * the stack high-water mark portable_fini reports is a measurement.
 *
 * Paired with link_xiangshan.ld. ISA-neutral: the 32-bit stores in the
 * .bss loop are fine on RV64 too, four bytes at a time.
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

	/* Paint the headroom above .bss so portable_fini can report how deep
	   the stack went (check_coremark.py gates it). 64-bit stores on RV64:
	   the region is a quarter megabyte and this runs in a simulator that
	   manages a few hundred cycles a second. */
	la	t0, _end
	la	t1, _stack_top
#if __riscv_xlen == 64
	li	t2, 0xDEADBEEFDEADBEEF
5:	bgeu	t0, t1, 6f
	sd	t2, 0(t0)
	addi	t0, t0, 8
	j	5b
#else
	li	t2, 0xDEADBEEF
5:	bgeu	t0, t1, 6f
	sw	t2, 0(t0)
	addi	t0, t0, 4
	j	5b
#endif
6:

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
