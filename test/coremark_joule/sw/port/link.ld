/* One memory map for every core in the study.
 *
 * RAM starts at 0 because that is where picorv32 and SERV both fetch
 * their first instruction by default (PROGADDR_RESET / RESET_PC), and
 * ibex's reset vector is a parameter the wrapper sets to match. A core
 * whose reset address cannot be moved would need its own script; none
 * of the three do.
 *
 * 128 KiB is well clear of what CoreMark's 2K performance profile needs
 * (a few tens of KiB of text plus ~2 KiB of data), and the harness RAM
 * is a simulation array rather than anything that gets hardened, so the
 * size costs nothing.
 *
 * Load addresses equal virtual addresses throughout, which is what lets
 * crt0.S omit a .data copy loop.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    ram (rwxai) : ORIGIN = 0x00000000, LENGTH = 128K
}

SECTIONS
{
    .text : {
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
