/* The ibex tile this study measures: the core and its program SRAM.
 *
 * Same purpose as cmj_picorv32.v: config.mk names this module as
 * DESIGN_NAME and cm_soc_ibex.sv instantiates it, so the simulated core
 * and the hardened core cannot be configured differently, and the
 * boundary the energy number is reported over is a module -- ibex plus
 * the 32 KiB instruction memory and 8 KiB data memory it runs out of.
 * It matters more here
 * than for the other two, because ibex_top carries around thirty
 * parameters and its defaults are what this study calls the "small"
 * configuration -- no PMP, no writeback stage, no branch-target ALU, no
 * icache, RegFileFF, SecureIbex off.
 *
 * It also confines the tie-offs. Upstream ibex_top now carries CHERIoT
 * and lockstep plumbing, and the shadow, revocation and scrambling ports
 * have nothing to do with what is being measured; they belong next to
 * the parameters rather than in the middle of a bus adapter.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

module cmj_ibex #(
    /* ibex's instruction cache. Off for the point this study reports,
     * and the reason is a measurement rather than convenience -- see
     * section 5.1. Behind a single-cycle tightly-coupled memory the
     * cache has nothing to speed up, and ibex's is 4 kB against
     * CoreMark's 24-30 kB of .text, so it cannot hold the benchmark
     * either. //test/coremark_joule/designs/asap7/ibex_icache builds
     * it on, which is what keeps the ASAP7 prim_ram_1p and its macros
     * from rotting. */
    parameter bit ICache = 1'b0
) (
    input  logic        clk,
    input  logic        resetn,

    /* Everything the tile could not serve itself; see cmj_picorv32.v
     * for the contract and cm_soc_ibex.sv for the other end. Both sides
     * can be outstanding at once, which they are throughout the boot
     * copy. */
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
  import ibex_pkg::*;

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

  /* ECC and scrambling stay at ibex_top's defaults (off) whichever way
   * ICache goes. Both add RAM width and logic the other three cores
   * have no counterpart for, and neither is part of what "has an
   * instruction cache" means. */
  ibex_top #(
      .ICache(ICache)
  ) u_core (
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
       * boot area out to match: vectors at +0x100, reset entry at
       * +0x180. External memory, not the TCM -- the TCM is empty out of
       * reset and the stub that fills it has to live somewhere the
       * harness can preload. */
      .boot_addr_i(32'h4000_0100),

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

  assign dbg_instr_addr = instr_addr;

  /* No arbiter, and on ibex that is not only a performance choice.
   *
   * The instruction and data sides address disjoint memories -- the
   * fetch path only ever reads cmj_imem, the data path only ever reads
   * cmj_dmem -- so both grants are unconditional, exactly as they were
   * when the memory was a simulation array outside the core. The one
   * crossing is the boot copy, which writes cmj_imem through the data
   * side; that uses the instruction memory's write port while the fetch
   * uses its read port, and at that moment the code being fetched is in
   * external memory anyway.
   *
   * An earlier version of this tile shared one memory and made
   * instr_gnt depend on data_req. ibex's grants already sit inside its
   * own combinational loops -- Verilator reports UNOPTFLAT on
   * instr_executing_spec, id_in_ready and en_wb -- and joining them
   * through an arbiter left the grant without a single settled value:
   * the memory read port and the instruction grant disagreed about who
   * owned the cycle, and the smoke test printed every other character
   * of its string. The disjoint map is what makes the question moot.
   *
   * Bit 30 is external memory, bit 28 the sim-control device, bit 16
   * the data memory. See link.ld. */
  wire i_ext = instr_addr[30] | instr_addr[28];
  wire d_ext = data_addr[30] | data_addr[28];

  wire d_imem = !d_ext && !data_addr[16];
  wire d_dmem = !d_ext && data_addr[16];

  assign instr_gnt = instr_req;
  assign data_gnt  = data_req;

  wire [31:0] im_rdata;
  wire [31:0] dm_rdata;

  /* FakeRAM's interface; see cmj_progmem.sv. Same argument as the SERV
   * tile: the data side writes the instruction memory only during the
   * boot copy, and ibex is fetching from external memory then. */
  wire im_rd = instr_req && !i_ext;
  wire im_wr = data_req && d_imem && data_we;

  cmj_imem u_imem (
      .clk    (clk),
      .ce_in  (im_rd || im_wr),
      .we_in  (im_wr),
      .addr_in(im_wr ? data_addr[14:2] : instr_addr[14:2]),
      .wd_in  (data_wdata),
      .rd_out (im_rdata)
  );

  cmj_dmem u_dmem (
      .clk     (clk),
      .ce_in   (data_req && d_dmem),
      .we_in   (data_we),
      .addr_in (data_addr[12:2]),
      .wd_in   (data_wdata),
      .wstrb_in(data_be),
      .rd_out  (dm_rdata)
  );

`ifndef SYNTHESIS
  always_ff @(posedge clk) begin
    if (resetn && im_rd && im_wr) begin
      $display("cmj_ibex: instruction memory read and write in one cycle");
      $finish;
    end
    /* And the data side never *reads* the instruction memory: link.ld
     * puts .rodata in the data memory precisely so that it does not. */
    if (resetn && data_req && d_imem && !data_we) begin
      $display("cmj_ibex: data read from the instruction memory");
      $finish;
    end
  end
`endif

  assign ext_i_req   = instr_req && i_ext;
  assign ext_i_addr  = instr_addr;

  assign ext_d_req   = data_req && d_ext;
  assign ext_d_we    = data_we;
  assign ext_d_addr  = data_addr;
  assign ext_d_wdata = data_wdata;
  assign ext_d_wstrb = data_be;

  /* Which source answers each port on the cycle its rvalid is high. */
  logic i_sel_ext;
  logic d_sel_ext;
  assign instr_rdata = i_sel_ext ? ext_i_rdata : im_rdata;
  assign data_rdata  = d_sel_ext ? ext_d_rdata : dm_rdata;

  always_ff @(posedge clk) begin
    instr_rvalid <= 1'b0;
    data_rvalid  <= 1'b0;

    if (resetn) begin
      if (data_req) begin
        data_rvalid <= 1'b1;
        d_sel_ext   <= d_ext;
      end
      if (instr_req) begin
        instr_rvalid <= 1'b1;
        i_sel_ext    <= i_ext;
      end
    end
  end

endmodule
