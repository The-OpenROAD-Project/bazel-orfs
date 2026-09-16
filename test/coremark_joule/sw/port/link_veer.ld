/* The memory map for VeeR EH1.
 *
 * The other three cores in the study share sw/port/link.ld: one flat
 * RAM at 0, load addresses equal to virtual addresses, and no .data copy
 * loop. VeeR cannot use it, and the reason is the measurement rather
 * than the core's convenience.
 *
 * VeeR's L1 data memory is a DCCM at a fixed architectural address
 * (0xf0080000 for this configuration), inside the hardened block. The
 * study's boundary says the benchmark's data belongs there -- that is
 * what "core plus L1" means for this core. But the harness can only
 * preload the *external* memory, because that is the only thing on a
 * bus it can reach; the DCCM is inside the core. So .data and .rodata
 * are linked to run in the DCCM and to load from external memory, and
 * crt0_veer.S copies them across before main. That copy happens once,
 * before the first iteration, and the SAIF window is the last iteration,
 * so it costs the measurement nothing.
 *
 * .text stays in external memory and is fetched through the 16 kB
 * instruction cache. That is deliberate: the icache is the L1 this
 * study exists to measure, and a core running out of a tightly-coupled
 * memory would not exercise it. What leaves the boundary is refill
 * traffic, and cm_soc_veer.sv counts it.
 *
 * Region 8 holds the image because the C runtime marks that region
 * cacheable in MRAC; see crt0_veer.S.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
OUTPUT_ARCH(riscv)
ENTRY(_start)

MEMORY
{
    /* External memory, region 8. Cacheable, no side-effects. 256 KiB is
       what cm_soc_veer.sv instantiates. */
    rom  (rxai) : ORIGIN = 0x80000000, LENGTH = 256K

    /* The DCCM: 64 KiB, inside the hardened block. Everything the hot
       loop reads or writes lives here. */
    dccm (rwa)  : ORIGIN = 0xf0080000, LENGTH = 64K
}

SECTIONS
{
    .text : {
        KEEP(*(.text.start))
        *(.text .text.*)
    } > rom

    /* Read-only data runs from the DCCM rather than from external
       memory. It is small, and leaving it outside would put CoreMark's
       constant tables on the far side of the boundary -- fetched over
       the bus on every access, since the DCCM is not a cache and the
       LSU has nothing else in front of it. */
    .rodata : ALIGN(8) {
        _data_lma = LOADADDR(.rodata);
        _data_start = .;
        *(.rodata .rodata.*)
        *(.srodata .srodata.*)
    } > dccm AT> rom

    .data : ALIGN(4) {
        *(.data .data.*)
        . = ALIGN(8);
        /* __global_pointer$ addresses the 4 KiB window the linker's
           relaxation assumes around it, so it belongs between .data and
           .sdata rather than at either end. */
        PROVIDE(__global_pointer$ = . + 0x800);
        *(.sdata .sdata.*)
        . = ALIGN(4);
        _data_end = .;
    } > dccm AT> rom

    .bss (NOLOAD) : ALIGN(4) {
        _bss_start = .;
        *(.sbss .sbss.*)
        *(.bss .bss.*)
        *(COMMON)
        . = ALIGN(4);
        _bss_end = .;
    } > dccm

    _end = .;

    /* The stack grows down from the top of the DCCM. CoreMark's own data
       block is static (MEM_METHOD=MEM_STATIC), so the stack carries only
       call frames and the 1 KiB ee_printf buffer. */
    _stack_top = ORIGIN(dccm) + LENGTH(dccm);

    /DISCARD/ : { *(.comment) *(.note .note.*) *(.eh_frame .eh_frame.*) }
}
