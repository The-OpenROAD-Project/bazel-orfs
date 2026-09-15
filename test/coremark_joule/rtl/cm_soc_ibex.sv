/* ibex on the study's sim-control platform.
 *
 * Same contract as the picorv32 and SERV wrappers: external memory with
 * an instruction side and a data side, the two-register sim-control
 * device, and counters of everything that crossed the boundary.
 * Everything the benchmark touches once it is running lives in the two
 * memories inside cmj_ibex, which is what gets hardened and what the
 * energy number is reported over. cm_soc_picorv32.v carries the
 * reasoning.
 *
 * SystemVerilog rather than Verilog, unlike the other two wrappers,
 * because cmj_ibex imports ibex_pkg and is written to match.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

module cm_soc #(
    /* 16384 words = 64 KiB at 0x40000000, matching sw/port/link.ld. */
    parameter int unsigned RomWords = 16384
) (
    input  logic       clk,
    input  logic       resetn,

    /* ibex reports faults as traps the software handles, not on a pin.
     * Like SERV, a broken run surfaces as a CRC mismatch or as the cycle
     * budget expiring rather than as a trap. */
    output logic       trap,

    output logic       out_valid,
    output logic [7:0] out_byte,
    output logic       halt_valid,

    /* Fetch address; see cm_soc_picorv32.v. */
    output logic [31:0] dbg_instr_addr
);
  localparam logic [31:0] SimCtrlOut  = 32'h1000_0000;
  localparam logic [31:0] SimCtrlHalt = 32'h1000_0008;
  localparam int unsigned RomAw = $clog2(RomWords);

  assign trap = 1'b0;

  logic        ext_i_req;
  logic [31:0] ext_i_addr;
  logic [31:0] ext_i_rdata;

  logic        ext_d_req;
  logic        ext_d_we;
  logic [31:0] ext_d_addr;
  logic [31:0] ext_d_wdata;
  logic [ 3:0] ext_d_wstrb;
  logic [31:0] ext_d_rdata;

  /* The boundary. Everything hardened, everything the SAIF covers and
   * everything report_power totals is inside this instance. */
  cmj_ibex cpu (
      .clk        (clk),
      .resetn     (resetn),

      .ext_i_req  (ext_i_req),
      .ext_i_addr (ext_i_addr),
      .ext_i_rdata(ext_i_rdata),

      .ext_d_req  (ext_d_req),
      .ext_d_we   (ext_d_we),
      .ext_d_addr (ext_d_addr),
      .ext_d_wdata(ext_d_wdata),
      .ext_d_wstrb(ext_d_wstrb),
      .ext_d_rdata(ext_d_rdata),

      .dbg_instr_addr(dbg_instr_addr)
  );

  logic [31:0] rom[RomWords];

  string meminit_path;
  initial begin
    if (!$value$plusargs("meminit=%s", meminit_path)) begin
      $display("cm_soc: +meminit=<path> is required");
      $finish;
    end
    $readmemh(meminit_path, rom);
  end

  wire is_device = ext_d_addr[28];
  wire [RomAw-1:0] iword = ext_i_addr[RomAw+1:2];
  wire [RomAw-1:0] dword = ext_d_addr[RomAw+1:2];

  /* Everything that crossed the boundary. */
  logic [63:0] ifu_xacts;
  logic [63:0] lsu_xacts;

  always_ff @(posedge clk) begin
    out_valid <= 1'b0;

    if (!resetn) begin
      halt_valid <= 1'b0;
      ifu_xacts  <= 64'd0;
      lsu_xacts  <= 64'd0;
    end else begin
      if (ext_i_req) begin
        ifu_xacts   <= ifu_xacts + 64'd1;
        ext_i_rdata <= rom[iword];
      end

      if (ext_d_req) begin
        lsu_xacts <= lsu_xacts + 64'd1;

        if (is_device) begin
          ext_d_rdata <= 32'b0;
          if (ext_d_we) begin
            if (ext_d_addr == SimCtrlOut) begin
              out_byte  <= ext_d_wdata[7:0];
              out_valid <= 1'b1;
            end
            if (ext_d_addr == SimCtrlHalt && ext_d_wdata != 32'b0) begin
              halt_valid <= 1'b1;
            end
          end
        end else begin
          ext_d_rdata <= rom[dword];
          /* Read-only by construction; see cm_soc_picorv32.v. */
          if (ext_d_we) begin
            $display("cm_soc: write to external memory at %h", ext_d_addr);
            $finish;
          end
        end
      end
    end
  end

  /* Written from a `final` block rather than on the halt write; see
   * cm_soc_picorv32.v. */
  string  busprobe_path;
  bit     busprobe_on;
  integer busprobe_fd;

  initial begin
    busprobe_on = $value$plusargs("busprobe=%s", busprobe_path);
  end

  final begin
    if (busprobe_on) begin
      busprobe_fd = $fopen(busprobe_path, "w");
      $fwrite(busprobe_fd, "ifu_xacts %0d\n", ifu_xacts);
      $fwrite(busprobe_fd, "lsu_xacts %0d\n", lsu_xacts);
      $fclose(busprobe_fd);
    end
  end
endmodule
