/* One memory map for picorv32, SERV and ibex.
 *
 * Three regions, and the split is the study's boundary rather than a
 * convenience.
 *
 *   imem  32 KiB at 0x00000000. Instruction memory, hardened *inside*
 *         the core (cmj_progmem.sv). .text runs here.
 *
 *   dmem   8 KiB at 0x00010000. Data memory, also inside the core.
 *         .rodata, .data, .bss and the stack live here. .rodata is
 *         here rather than next to the code it belongs to so that the
 *         data side never reads the instruction memory, which is what
 *         lets a fetch and a load proceed in the same cycle with no
 *         arbiter -- see cmj_progmem.sv for why that matters.
 *
 *   rom   64 KiB at 0x40000000. External memory, outside the boundary.
 *         It holds the boot stub and the load images of the sections
 *         above, and nothing reads it again after crt0.S has copied
 *         them across. That copy happens once, before the first
 *         iteration; the SAIF window is the last one, so it costs the
 *         measurement nothing -- and the two- minus three-iteration
 *         difference cancels it from the cycle count as well.
 *
 * Section 3.1's rule says a core with no cache is measured with the
 * memory its hot loop runs out of, and imem+dmem is that memory. The
 * earlier version of this file was one flat 128 KiB RAM at 0 that lived
 * in the simulation wrapper and was never hardened. It made the three
 * cacheless cores look better than they are, because the memory their
 * instruction stream comes out of contributed no power at all. Section
 * 4.6 predicted how much that was worth and section 5.1 is the
 * measurement.
 *
 * The addresses are chosen so the decode inside each tile is three bit
 * tests: bit 30 selects rom, bit 28 the sim-control device, bit 16
 * dmem, and imem is what is left. A wide comparator would cost real
 * cycles on the bit-serial core this map also has to serve.
 *
 * The sizes are from the images, not from feel. Across the three
 * marches the largest .text is 30,204 B (rv32i) and the largest
 * .rodata+.data+.bss is 3,588 B, against a measured stack high-water
 * mark of 388 B -- portable_fini reports it on every run and
 * check_coremark.py gates it. One pair of sizes for all three marches
 * and all three cores, because a memory that changed between the points
 * being compared would be a variable in a comparison that exists to
 * have only one. The ASSERTs at the end are what keep that true when
 * the compiler or the port layer moves.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
OUTPUT_ARCH(riscv)
ENTRY(_boot)

MEMORY
{
    imem (rxai) : ORIGIN = 0x00000000, LENGTH = 32K
    dmem (rwa)  : ORIGIN = 0x00010000, LENGTH = 8K
    rom  (rxai) : ORIGIN = 0x40000000, LENGTH = 64K
}

SECTIONS
{
    /* Runs from external memory, before either TCM has anything in it.
       Carries the reset entry points for both conventions in the study
       and the exception vectors; see crt0.S. */
    .boot : {
        KEEP(*(.text.boot))
        /* Load-address alignment for everything that follows, not
           cosmetics. .text's *run* address is 0 and so is aligned by
           construction, but its *load* address is wherever .boot
           happened to end -- and under the C extension .boot ends on a
           two-byte boundary, because the assembler compresses most of
           the boot stub. crt0.S copies words, so an odd .boot size
           shifts the whole image by two bytes. ibex splits the
           resulting misaligned loads into two bus transactions and
           copies a corrupted image without complaining; the ASSERT
           below is what turns that back into a build failure. */
        . = ALIGN(4);
    } > rom

    .text : {
        _text_start = .;
        KEEP(*(.text.start))
        *(.text .text.*)
        . = ALIGN(4);
        _text_end = .;
    } > imem AT> rom

    .rodata : {
        _data_start = .;
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
        . = ALIGN(4);
    } > dmem AT> rom

    .data : {
        *(.data .data.*)
        . = ALIGN(8);
        /* __global_pointer$ addresses the 4 KiB window the linker's
           relaxation assumes around it, so it belongs between .data and
           .sdata rather than at either end. */
        PROVIDE(__global_pointer$ = . + 0x800);
        *(.sdata .sdata.*)
        . = ALIGN(4);
        _data_end = .;
    } > dmem AT> rom

    /* NOLOAD, so it gets no load address and no bytes in the image.
       crt0.S zeroes it after the copy. */
    .bss (NOLOAD) : {
        . = ALIGN(4);
        _bss_start = .;
        *(.sbss .sbss.*)
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        _bss_end = .;
    } > dmem

    . = ALIGN(4);
    _end = .;

    /* Where each copy reads from. LOADADDR rather than ORIGIN(rom):
       the linker decides where the previous section ended. */
    _text_lma = LOADADDR(.text);
    _data_lma = LOADADDR(.rodata);

    /* The stack grows down from the top of the data memory. CoreMark's
       own data block is static (MEM_METHOD=MEM_STATIC), so the stack
       carries only call frames and ee_printf's buffer -- 388 B at its
       deepest, over every core and march in the study. */
    _stack_top = ORIGIN(dmem) + LENGTH(dmem);

    ASSERT((_text_lma & 3) == 0,
           "crt0.S copies words: the load address of .text must be 4-byte aligned")
    ASSERT((_data_lma & 3) == 0,
           "crt0.S copies words: the load address of .rodata must be 4-byte aligned")
    ASSERT(_text_end <= ORIGIN(imem) + LENGTH(imem),
           ".text does not fit in the instruction memory; see LENGTH(imem)")
    ASSERT(_end <= _stack_top,
           "data and bss do not fit in the data memory; see LENGTH(dmem)")

    /DISCARD/ : { *(.comment) *(.note .note.*) *(.eh_frame .eh_frame.*) }
}
