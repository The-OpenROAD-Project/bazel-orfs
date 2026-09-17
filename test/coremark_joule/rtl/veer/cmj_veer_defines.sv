/* The VeeR EH1 configuration this study measures, frozen.
 *
 * Same job as rtl/cmj_<core>.v does for the other three cores: the core
 * that is simulated and the core that is hardened must not be able to
 * differ, and a reader must be able to see which configuration was
 * measured. VeeR's features are not module parameters but `define`s
 * emitted by upstream's own generator, so the frozen thing here is the
 * defines file rather than a parameter list.
 *
 * config/common_defines.vh is that generator's output, committed
 * byte-for-byte apart from a header that named whoever ran it. The
 * command is in its header:
 *
 *   swerv -set=icache_enable=1 -icache_size=16 -unset=iccm_enable
 *         -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64
 *         -btb_size=512 -bht_size=2048
 *         -ahb_lite -set=fpga_optimize=0
 *
 * A 16 kB instruction cache, a 64 kB DCCM at 0xf0080000, no ICCM, and
 * the 512-entry BTB and 2048-entry BHT that Western Digital's published
 * CoreMark score was taken with. Everything CoreMark touches in its hot
 * loop is inside the hardened block: instructions out of the icache,
 * data and stack out of the DCCM.
 *
 * Why the icache and not the ICCM, given that Western Digital's own
 * CoreMark configuration uses a 64 kB ICCM with the cache switched off
 * (seh1_SweRV_CoreMark_Benchmarking.pdf, 4.94 CoreMark/MHz):
 *
 *   - **The ICCM cannot be filled by the core.** `lsu_addrcheck.sv`
 *     uses the ICCM region only to suppress side-effects; there is no
 *     store path from the LSU into it. Upstream's testbench fills it by
 *     forcing values straight into `ram_core` through a hierarchical
 *     path, and their FPGA flow does it over JTAG with extended OpenOCD
 *     abstract commands. Neither survives to a gate-level netlist,
 *     where the ICCM is a hardened macro with no `ram_core` to force --
 *     and the gate-level run is the one that produces the SAIF. Filling
 *     it properly would mean a DMA master pushing the image in over the
 *     AHB slave port before the benchmark starts: real machinery,
 *     outside the boundary, that exists only to work around the load
 *     path.
 *   - **The icache needs no loader at all.** The program sits in
 *     external memory and is fetched through the cache, so the same
 *     image boots in RTL and at gate level with nothing forced.
 *   - **It is the cache this study says it measures.** §3.1's boundary
 *     is the core and its L1, and with this configuration the L1 is
 *     exercised rather than configured away.
 *
 * What that leaves outside the boundary is the residual miss traffic,
 * and it is measured rather than assumed: the SoC wrapper counts IFU
 * bus transactions, so "CoreMark fits in the instruction cache" is a
 * number in the results and not a claim in a comment.
 *
 * The memory shapes that fall out -- ram_256x34 (icache data),
 * ram_64x21 (icache tag) and ram_2048x39 (DCCM) -- are exactly the
 * three fakeram7 views ASAP7 already carries. A 32 kB icache would need
 * ram_512x34 and ram_128x21, which it does not.
 *
 * Two deliberate departures from upstream's setup besides the cache.
 * `-ahb_lite`, because the external bus here serves only the boot image
 * and the two-word sim-control device, and AHB-Lite is a far smaller
 * adapter than AXI4 for that. And `fpga_optimize=0`: Western Digital's
 * number was taken on a Nexys-4 FPGA prototype at 40 MHz, where the
 * generator's FPGA setting minimises clock gating -- a first-order term
 * in exactly the energy this study reports.
 *
 * Two more departures below, here rather than in the generated file, so
 * the generated file stays byte-comparable against a re-run.
 *
 * ASSERT_ON is undefined. It guards VeeR's SystemVerilog assertions,
 * and one of them -- lsu.sv's `exception_no_lsu_flush`, which uses a
 * `##[1:2]` cycle-delay range -- is a construct Verilator rejects
 * outright rather than ignores. The assertions are simulation-only and
 * synthesise to nothing, so turning them off costs no logic; leaving
 * them on for synthesis and off for simulation would have cost the one
 * guarantee this file exists to give.
 *
 * PHYSICAL stays off, which is the departure from upstream's
 * pd_defines.vh. Defining it swaps the behavioural clock gate for a
 * named technology cell, and that alone would make the Verilog that is
 * simulated differ from the Verilog that is synthesised. The clock gate
 * reaches asap7 through the flow's own CLKGATE_MAP_FILE instead, which
 * is where a technology mapping belongs.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`include "common_defines.vh"

`undef ASSERT_ON
