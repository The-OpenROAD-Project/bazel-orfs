/* XiangShan's memory map: one flat RAM at 0x8000_0000.
 *
 * The core takes its reset vector as an input and fetches from external
 * memory, which the harness models as a C++ array behind DPI with index
 * zero at this address. Load addresses equal run addresses throughout,
 * so crt0_flat.S needs no copy loop.
 *
 * A megabyte rather than 128 KiB: the RV64 build is larger, and this
 * memory is a simulation array that is never hardened, so the size
 * costs nothing. The vector area stays first, as in the flat map the
 * small cores used to share, because crt0_flat.S is that runtime.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    ram (rwxai) : ORIGIN = 0x80000000, LENGTH = 1M
}

SECTIONS
{
    /* The vector area must be first: it carries the entry points both
       reset conventions in the study land on. See crt0.S. */
    .text : {
        KEEP(*(.text.vectors))
        KEEP(*(.text.start))
        *(.text .text.*)
    } > ram

    .rodata : {
        . = ALIGN(4);
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
    } > ram

    .data : {
        . = ALIGN(4);
        *(.data .data.*)
        . = ALIGN(8);
        /* __global_pointer$ addresses the 4 KiB window the linker's
           relaxation assumes around it, so it belongs between .data and
           .sdata rather than at either end. */
        PROVIDE(__global_pointer$ = . + 0x800);
        *(.sdata .sdata.*)
    } > ram

    .bss (NOLOAD) : {
        . = ALIGN(4);
        _bss_start = .;
        *(.sbss .sbss.*)
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        _bss_end = .;
    } > ram

    _end = .;

    /* The stack grows down from the top of RAM. CoreMark's own data
       block is static (MEM_METHOD=MEM_STATIC), so the stack carries only
       call frames and the 1 KiB ee_printf buffer. */
    _stack_top = ORIGIN(ram) + LENGTH(ram);

    /DISCARD/ : { *(.comment) *(.note .note.*) *(.eh_frame .eh_frame.*) }
}
