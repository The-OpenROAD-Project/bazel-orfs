/* Minimal RV32 startup for the sim-control platform.
 *
 * Two stages, and the split follows link.ld's two regions.
 *
 * `_boot` runs from external memory, which is the only thing the
 * harness can preload. It copies .text into the instruction memory and
 * .rodata and .data into the data memory -- both hardened inside the
 * core -- paints the region above them, and jumps in. From that point
 * the benchmark never fetches or loads outside the boundary again,
 * which is the condition section 5.1's energy number needs in order to
 * mean what it claims.
 *
 * The copy costs a few tens of thousands of cycles, once, before the
 * first iteration. The measurement is a difference between a two- and a
 * three-iteration run, so it cancels exactly; the SAIF window is the
 * last iteration, so it is not in the window either.
 *
 * `_start` runs from the instruction memory: global pointer, stack,
 * .bss, main.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

/* ---------------------------------------------------------------- *
 * Stage one: external memory.
 * ---------------------------------------------------------------- *
 *
 * The three cores do not agree on where execution begins. picorv32 and
 * SERV fetch their first instruction from their reset address, which
 * the wrappers set to 0x40000000. ibex fetches from boot_addr_i + 0x80
 * and places its exception vector table at boot_addr_i itself --
 * lowRISC's own linker script encodes this as
 * `_entry_point = _vectors_start + 0x80`. Setting ibex's boot_addr_i to
 * the region base therefore does not start the program: it starts 0x80
 * bytes into it, on whatever instruction happens to live there.
 *
 * So this area carries entry points for both conventions, and the ibex
 * wrapper passes boot_addr_i = 0x40000100:
 *
 *   0x000          reset entry for a core that starts at its reset address
 *   0x100 .. 0x17c ibex exception vectors
 *   0x180          ibex reset entry (0x100 + 0x80)
 *
 * The exception vectors report and stop rather than returning. Neither
 * SERV nor ibex has a trap output the harness can watch, so without
 * this a fault would silently vector somewhere and the run would look
 * like a hang with no evidence. With it, a fault prints a marker and
 * halts: the CRC gate then fails with something to read.
 *
 * The vectors stay out here rather than moving into the TCM with the
 * rest of .text because they have to be valid before the copy has run.
 */
	.section .text.boot, "ax"
	.globl _boot_vectors
	/* norvc, and the whole area depends on it. ibex's vector table is
	   fixed at four bytes per entry and its reset entry is a fixed
	   +0x80 from the base, so both are addresses this layout has to
	   hit exactly. With the C extension enabled the assembler
	   compresses `j` to a two-byte `c.j`, the 32 entries occupy 0x40
	   rather than 0x80, and everything after them moves -- which puts
	   something other than a jump at +0x180 and starts the rv32imc
	   build in the middle of an instruction. */
	.option push
	.option norvc
_boot_vectors:
	j	_boot
	.org 0x100
	.rept 32
	j	_trap
	.endr
	j	_boot
	.option pop

	.globl _boot
	.type _boot, @function
_boot:
	/* norvc is not the only assembler option this stage depends on.
	   Everything below runs before `gp` is set, and the linker's
	   relaxation rewrites `la` into a gp-relative `addi` whenever the
	   symbol lands within 2 KiB of __global_pointer$ -- which
	   _data_end does, because gp is placed in the middle of the very
	   sections this loop is copying. Relaxed against an uninitialised
	   gp the loop bound is nonsense and the copy runs off the end of
	   memory.

	   It is a quiet failure on small programs: when every symbol in a
	   loop relaxes, they are all wrong by the same amount and the loop
	   still runs the right number of times. The study's smoke test
	   passed on all three cores like that while CoreMark spun until
	   the cycle budget expired. */
	.option push
	.option norelax

	/* Copy .text into the instruction memory, then .rodata and .data
	   into the data memory. Two loops because the two run in separate
	   address spaces; their load images are contiguous in external
	   memory, but nothing downstream may assume that.

	   No stack yet: the stack lives in the data memory and nothing has
	   been written to it. */
	la	t0, _text_lma
	la	t1, _text_start
	la	t2, _text_end
1:	bgeu	t1, t2, 2f
	lw	t3, 0(t0)
	sw	t3, 0(t1)
	addi	t0, t0, 4
	addi	t1, t1, 4
	j	1b
2:
	la	t0, _data_lma
	la	t1, _data_start
	la	t2, _data_end
3:	bgeu	t1, t2, 4f
	lw	t3, 0(t0)
	sw	t3, 0(t1)
	addi	t0, t0, 4
	addi	t1, t1, 4
	j	3b
4:

	/* Paint [_end, _stack_top) so portable_fini can report how deep
	   the stack actually went. The data memory is sized on that number
	   (8 KiB against a 3.5 KiB image), so "is there enough headroom?"
	   is a measurement on every run rather than a judgement made
	   once. */
	la	t0, _end
	la	t1, _stack_top
	li	t2, 0xDEADBEEF
5:	bgeu	t0, t1, 6f
	sw	t2, 0(t0)
	addi	t0, t0, 4
	j	5b
6:

	/* Into the instruction memory. An absolute jump, not a relative
	   branch: the two regions are a gigabyte apart. */
	la	t0, _start
	jr	t0
	.option pop
	.size _boot, . - _boot

/* Reached only from an exception vector, and therefore also only in
 * external memory. Writes '!' to the sim-control character register so
 * the marker lands in the captured stdout, then stops the simulation. */
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

/* ---------------------------------------------------------------- *
 * Stage two: the instruction memory.
 * ---------------------------------------------------------------- */
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

	/* zero .bss. It is NOLOAD, so the copy above did not bring it. */
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
