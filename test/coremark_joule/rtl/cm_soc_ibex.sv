/* ibex on the study's sim-control platform.
 *
 * Same wrapper contract as the picorv32 and SERV ones -- RAM, the
 * two-register sim-control device, one bus adapter -- so the C runtime,
 * the address map and the CoreMark port are shared. Only ibex_top is
 * hardened.
 *
 * SystemVerilog rather than Verilog, unlike the other two wrappers,
 * because ibex_top's ports carry package types (ibex_mubi_t,
 * prim_ram_1p_pkg::ram_1p_cfg_req_t) that cannot be named from Verilog.
 *
 * The parameters are left at ibex_top's own defaults, which are already
 * the small configuration this study wants: no PMP, no writeback stage,
 * no branch-target ALU, no icache, RegFileFF, SecureIbex off. Current
 * upstream ibex_top also carries CHERIoT; cheriot_enable_i is tied off,
 * which leaves the classic core.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

module cm_soc #(
    parameter int unsigned MemWords = 32768
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
  localparam int unsigned AW = $clog2(MemWords);

  assign trap = 1'b0;

  logic        instr_req;
  logic        instr_gnt;
  logic        instr_rvalid;
  logic [31:0] instr_addr;
  logic [31:0] instr_rdata;

  logic        data_req;
  logic        data_gnt;
  logic        data_rvalid;
  logic        data_we;
  logic [ 3:0] data_be;
  logic [31:0] data_addr;
  logic [31:0] data_wdata;
  logic [31:0] data_rdata;

  logic [31:0] mem[MemWords];

  string meminit_path;
  initial begin
    if (!$value$plusargs("meminit=%s", meminit_path)) begin
      $display("cm_soc: +meminit=<path> is required");
      $finish;
    end
    $readmemh(meminit_path, mem);
  end

  cmj_ibex u_core (
      .clk         (clk),
      .rst_n       (resetn),
      .instr_req   (instr_req),
      .instr_gnt   (instr_gnt),
      .instr_rvalid(instr_rvalid),
      .instr_addr  (instr_addr),
      .instr_rdata (instr_rdata),
      .data_req    (data_req),
      .data_gnt    (data_gnt),
      .data_rvalid (data_rvalid),
      .data_we     (data_we),
      .data_be     (data_be),
      .data_addr   (data_addr),
      .data_wdata  (data_wdata),
      .data_rdata  (data_rdata)
  );

  /* ibex uses a two-phase bus: grant accepts the request, rvalid returns
   * the data a cycle later. Granting combinationally and returning data
   * on the next cycle gives a one-wait-state memory, matching what the
   * other two wrappers present, so the memory is not what distinguishes
   * the cores. */
  assign dbg_instr_addr = instr_addr;

  wire is_device = data_addr[28];
  wire [AW-1:0] dword = data_addr[AW+1:2];
  wire [AW-1:0] iword = instr_addr[AW+1:2];

  /* Both ports are served every cycle. The RAM is a simulation array,
   * so it can answer a fetch and a data access at once, and an arbiter
   * that made them compete would be measuring the arbiter.
   *
   * This is not a detail. An earlier version granted instruction fetch
   * only when no data access was pending, and ibex ran a non-compressed
   * CoreMark more than ten times slower than a compressed one -- a
   * compressed fetch carries two instructions, so it halves the fetch
   * rate and hid the starvation. A wrapper that penalises fetch-hungry
   * code penalises exactly the cores this study is trying to compare. */
  assign data_gnt  = data_req;
  assign instr_gnt = instr_req;

  always_ff @(posedge clk) begin
    instr_rvalid <= 1'b0;
    data_rvalid  <= 1'b0;
    out_valid    <= 1'b0;

    if (!resetn) begin
      halt_valid <= 1'b0;
    end else begin
      if (data_req) begin
        data_rvalid <= 1'b1;

        if (is_device) begin
          data_rdata <= 32'b0;
          if (data_we) begin
            if (data_addr == SimCtrlOut) begin
              out_byte  <= data_wdata[7:0];
              out_valid <= 1'b1;
            end
            if (data_addr == SimCtrlHalt && data_wdata != 32'b0) begin
              halt_valid <= 1'b1;
            end
          end
        end else begin
          data_rdata <= mem[dword];
          if (data_we) begin
            if (data_be[0]) mem[dword][7:0] <= data_wdata[7:0];
            if (data_be[1]) mem[dword][15:8] <= data_wdata[15:8];
            if (data_be[2]) mem[dword][23:16] <= data_wdata[23:16];
            if (data_be[3]) mem[dword][31:24] <= data_wdata[31:24];
          end
        end
      end

      if (instr_req) begin
        instr_rvalid <= 1'b1;
        instr_rdata  <= mem[iword];
      end
    end
  end
endmodule
