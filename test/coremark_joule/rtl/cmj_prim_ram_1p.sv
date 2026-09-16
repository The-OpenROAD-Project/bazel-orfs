/* prim_ram_1p for ASAP7: ibex's instruction-cache RAMs as macros.
 *
 * lowRISC's prim library carries prim_ram_1p twice -- a prim_generic
 * implementation that is a behavioural array, and a prim_xilinx one
 * beside it -- which is the library saying that a real target supplies
 * its own. This is that file for this study, and supplying it is
 * faithful to how ibex is meant to be built rather than a change to the
 * core: ibex_top's instantiation, its parameters and its ports are
 * untouched, and no ibex source is modified.
 *
 * Without it the cache RAMs synthesise as flip-flops. AUTO_MEMORIES
 * sees an inline array inside prim_ram_1p and refuses to convert it,
 * correctly -- an inline array is a design asking for flops -- so a
 * 4 kB cache becomes 44,032 flip-flops against a core of about two
 * thousand. The cache would then cost twenty times the core it
 * accelerates, which is not a measurement of anything.
 *
 * Two shapes, and only two. ICache=1 with ICacheECC=0 gives
 * IC_SIZE_BYTES=4096, IC_NUM_WAYS=2 and IC_LINE_SIZE=64, so
 * IC_NUM_LINES=256 and each way carries
 *
 *   tag_bank    256 x 22   (IC_TAG_SIZE = 32 - 8 - 3 + 1)
 *   data_bank   256 x 64   (IC_LINE_SIZE)
 *
 * The generate below dispatches on Width, which is what distinguishes
 * them; Depth is 256 for both. An unrecognised shape is a build
 * failure rather than a silent fallback to flops, because a silent
 * fallback is exactly the failure this file exists to prevent.
 *
 * No write mask. ibex asks for DataBitsPerMask = Width on both banks,
 * so wmask_i is all-ones on every write and the macro needs no byte
 * enable -- which is just as well, because FakeRAM's ASAP7 RAM has
 * none. The mask is checked rather than assumed: a partial write would
 * silently write the whole word.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

module prim_ram_1p import prim_ram_1p_pkg::*; #(
  parameter  int Width           = 32,
  parameter  int Depth           = 128,
  parameter  int DataBitsPerMask = 1,
  parameter      MemInitFile     = "",

  localparam int Aw              = $clog2(Depth)
) (
  input  logic             clk_i,
  input  logic             rst_ni,

  input  logic             req_i,
  input  logic             write_i,
  input  logic [Aw-1:0]    addr_i,
  input  logic [Width-1:0] wdata_i,
  input  logic [Width-1:0] wmask_i,
  output logic [Width-1:0] rdata_o,
  input  ram_1p_cfg_req_t  cfg_i,
  output ram_1p_cfg_rsp_t  cfg_o
);
  /* Nothing here is configurable; the ports exist because ibex_top
   * drives them. */
  assign cfg_o = '0;

  generate
    if (Width == 22 && Depth == 256) begin : gen_tag
      cmj_ic_tag_sram u_ram (
          .RW0_clk  (clk_i),
          .RW0_en   (req_i),
          .RW0_wmode(write_i),
          .RW0_addr (addr_i),
          .RW0_wmask(wmask_i),
          .RW0_wdata(wdata_i),
          .RW0_rdata(rdata_o)
      );
    end else if (Width == 64 && Depth == 256) begin : gen_data
      cmj_ic_data_sram u_ram (
          .RW0_clk  (clk_i),
          .RW0_en   (req_i),
          .RW0_wmode(write_i),
          .RW0_addr (addr_i),
          .RW0_wmask(wmask_i),
          .RW0_wdata(wdata_i),
          .RW0_rdata(rdata_o)
      );
    end else begin : gen_unsupported
      /* A shape this file has no macro for. Failing at elaboration is
       * the point: the alternative is flip-flops nobody asked for. */
      $error("prim_ram_1p: no ASAP7 macro for %0d x %0d", Depth, Width);
    end
  endgenerate

endmodule
