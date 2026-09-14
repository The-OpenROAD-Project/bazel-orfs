/* The ibex configuration this study measures, frozen.
 *
 * Same purpose as cmj_picorv32.v: config.mk names this module as
 * DESIGN_NAME and cm_soc_ibex.sv instantiates it, so the simulated core
 * and the hardened core cannot be configured differently. It matters
 * more here than for the other two, because ibex_top carries around
 * thirty parameters and its defaults are what this study calls the
 * "small" configuration -- no PMP, no writeback stage, no branch-target
 * ALU, no icache, RegFileFF, SecureIbex off.
 *
 * It also confines the tie-offs. Upstream ibex_top now carries CHERIoT
 * and lockstep plumbing, and the shadow, revocation and scrambling ports
 * have nothing to do with what is being measured; they belong next to
 * the parameters rather than in the middle of a bus adapter.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

module cmj_ibex (
    input  logic        clk,
    input  logic        rst_n,

    output logic        instr_req,
    input  logic        instr_gnt,
    input  logic        instr_rvalid,
    output logic [31:0] instr_addr,
    input  logic [31:0] instr_rdata,

    output logic        data_req,
    input  logic        data_gnt,
    input  logic        data_rvalid,
    output logic        data_we,
    output logic [ 3:0] data_be,
    output logic [31:0] data_addr,
    output logic [31:0] data_wdata,
    input  logic [31:0] data_rdata
);
  import ibex_pkg::*;

  ibex_top u_core (
      .clk_i (clk),
      .rst_ni(rst_n),

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

endmodule
