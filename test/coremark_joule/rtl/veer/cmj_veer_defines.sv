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
 * command is in its header, and it is not a target preset: it is
 * Western Digital's own published CoreMark configuration, copied from
 * upstream's docs/SweRV_CoreMark_Benchmarking.pdf, which is where this
 * core's 4.94 CoreMark/MHz comes from.
 *
 *   swerv -set reset_vec=0xf0090000 -set=iccm_enable=1
 *         -unset=icache_enable
 *         -iccm_region=0xf -iccm_offset=0x90000 -iccm_size=64
 *         -dccm_region=0xf -dccm_offset=0x80000 -dccm_size=64
 *         -btb_size=512 -bht_size=2048
 *         -ahb_lite -set=fpga_optimize=0
 *
 * 64 kB ICCM holding the code, 64 kB DCCM holding the data, the
 * instruction cache switched off, and the 512-entry BTB and 2048-entry
 * BHT that go with the score. Measuring any other configuration would
 * produce a number that cannot be compared with the published one --
 * a default-target build has a 32-entry BTB and a 128-entry BHT, which
 * is a sixteenth of each.
 *
 * It is also the configuration the study's own boundary rule asks for.
 * A core with no cache is measured with the small SRAM that comes with
 * it and holds the program hardened as part of it, and ICCM plus DCCM
 * is exactly that: the memory the hot loop runs out of, inside the
 * boundary. One memory shape falls out of it, ram_2048x39, which is a
 * fakeram7 view asap7 already carries.
 *
 * Two departures from Western Digital's setup, both stated rather than
 * quiet. `-ahb_lite`, because the external bus here serves only the
 * two-word sim-control device and AHB-Lite is a far smaller adapter
 * than AXI4 for that. And `-set=fpga_optimize=0`: their number was
 * taken on a Nexys-4 FPGA prototype at 40 MHz, where the generator's
 * FPGA setting minimises clock gating -- which is a first-order term in
 * exactly the energy this study reports, so it goes back on.
 *
 * Two deliberate departures from the generator's output, both here
 * rather than in the generated file, so the generated file stays
 * byte-comparable against a re-run.
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
