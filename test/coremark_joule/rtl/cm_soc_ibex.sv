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
  import ibex_pkg::*;

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

  ibex_top u_core (
      .clk_i (clk),
      .rst_ni(resetn),

      .test_en_i  (1'b0),
      .scan_rst_ni(1'b1),

      .ram_cfg_icache_tag_i ('0),
      .ram_cfg_icache_tag_o (),
      .ram_cfg_icache_data_i('0),
      .ram_cfg_icache_data_o(),

      /* Off: this study measures the classic core. */
      .cheriot_enable_i(IbexMuBiOff),

      .hart_id_i  (32'd0),
      /* ibex fetches its first instruction from boot_addr_i + 0x80 and
       * places its exception vectors at boot_addr_i. crt0.S lays the
       * image out to match: vectors at 0x100, reset entry at 0x180. */
      .boot_addr_i(32'h0000_0100),

      .trvk_heap_base_addr_i('0),

      .instr_req_o       (instr_req),
      .instr_gnt_i       (instr_gnt),
      .instr_rvalid_i    (instr_rvalid),
      .instr_addr_o      (instr_addr),
      .instr_rdata_i     (instr_rdata),
      /* MemECC is off, so the integrity bits are unused. */
      .instr_rdata_intg_i('0),
      .instr_err_i       (1'b0),

      .data_req_o       (data_req),
      .data_gnt_i       (data_gnt),
      .data_rvalid_i    (data_rvalid),
      .data_we_o        (data_we),
      .data_be_o        (data_be),
      .data_addr_o      (data_addr),
      .data_wdata_o     (data_wdata),
      .data_wdata_intg_o(),
      .data_tag_o       (),
      .data_rdata_i     (data_rdata),
      .data_rdata_intg_i('0),
      .data_tag_i       (1'b0),
      .data_err_i       (1'b0),

      .trvk_revbm_req_o       (),
      .trvk_revbm_gnt_i       (1'b0),
      .trvk_revbm_rvalid_i    (1'b0),
      .trvk_revbm_addr_o      (),
      .trvk_revbm_rdata_i     ('0),
      .trvk_revbm_rdata_intg_i('0),
      .trvk_revbm_err_i       (1'b0),

      /* No interrupts anywhere in the study; crt0.S sets up no vector. */
      .irq_software_i(1'b0),
      .irq_timer_i   (1'b0),
      .irq_external_i(1'b0),
      .irq_fast_i    ('0),
      .irq_nm_i      (1'b0),

      /* ICacheScramble is off. */
      .scramble_key_valid_i(1'b0),
      .scramble_key_i      ('0),
      .scramble_nonce_i    ('0),
      .scramble_req_o      (),

      .debug_req_i        (1'b0),
      .crash_dump_o       (),
      .double_fault_seen_o(),

      /* The rvfi_* ports exist only under `ifdef RVFI, which nothing
       * in this study defines: formal tracing would be flops and wires
       * the measurement would then attribute to the core. */

      .fetch_enable_i       (IbexMuBiOn),
      .mcounteren_writable_i(IbexMuBiOff),

      .alert_minor_o         (),
      .alert_major_internal_o(),
      .alert_major_bus_o     (),
      .core_sleep_o          (),

      .lockstep_cmp_en_o(),

      .data_req_shadow_o       (),
      .data_we_shadow_o        (),
      .data_be_shadow_o        (),
      .data_addr_shadow_o      (),
      .data_wdata_shadow_o     (),
      .data_wdata_intg_shadow_o(),
      .instr_req_shadow_o      (),
      .instr_addr_shadow_o     ()
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
