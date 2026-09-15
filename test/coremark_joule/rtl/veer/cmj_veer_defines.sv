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
 *   swerv -target=default_ahb -set=fpga_optimize=0
 *
 * which gives a 16 kB instruction cache, a 64 kB DCCM, no ICCM, and an
 * AHB-Lite external bus. The program therefore lives in external memory
 * and is fetched through the icache, so the L1 this study means to
 * measure is exercised rather than bypassed.
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
