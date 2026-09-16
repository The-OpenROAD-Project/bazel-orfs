/* ibex with its instruction cache on: the same tile, one parameter.
 *
 * This exists to keep the ASAP7 prim_ram_1p (cmj_prim_ram_1p.sv) and
 * the cache-RAM macros exercised. Section 5.1 explains why the reported
 * ibex point has ICache=0 -- the short version is that a cache behind a
 * single-cycle tightly-coupled memory cannot buy a cycle, and ibex's
 * 4 kB cannot hold CoreMark's .text, so turning it on adds hardware
 * that changes nothing a reader should attribute to the core.
 *
 * Built to global route only. A cheap manual target is enough to prove
 * the substitution still works: that the four cache RAMs convert to
 * macros rather than flip-flops, that the kept-module list matches a
 * configuration with no prefetch buffer, and that the design places and
 * routes with the macros in it.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

module cmj_ibex_ic (
    input  logic        clk,
    input  logic        resetn,

    output logic        ext_i_req,
    output logic [31:0] ext_i_addr,
    input  logic [31:0] ext_i_rdata,

    output logic        ext_d_req,
    output logic        ext_d_we,
    output logic [31:0] ext_d_addr,
    output logic [31:0] ext_d_wdata,
    output logic [ 3:0] ext_d_wstrb,
    input  logic [31:0] ext_d_rdata,

    output logic [31:0] dbg_instr_addr
);
  cmj_ibex #(
      .ICache(1'b1)
  ) u_tile (
      .clk           (clk),
      .resetn        (resetn),
      .ext_i_req     (ext_i_req),
      .ext_i_addr    (ext_i_addr),
      .ext_i_rdata   (ext_i_rdata),
      .ext_d_req     (ext_d_req),
      .ext_d_we      (ext_d_we),
      .ext_d_addr    (ext_d_addr),
      .ext_d_wdata   (ext_d_wdata),
      .ext_d_wstrb   (ext_d_wstrb),
      .ext_d_rdata   (ext_d_rdata),
      .dbg_instr_addr(dbg_instr_addr)
  );
endmodule
