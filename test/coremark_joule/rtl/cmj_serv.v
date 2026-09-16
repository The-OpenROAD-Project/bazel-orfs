/* The SERV tile this study measures: the core and its program SRAM.
 *
 * Same purpose as cmj_picorv32.v. config.mk names this module as
 * DESIGN_NAME and cm_soc_serv.v instantiates it, so the simulated core
 * and the hardened core cannot be configured differently, and the
 * boundary the energy number is reported over is a module rather than a
 * convention: SERV plus the 32 KiB instruction memory and 8 KiB data
 * memory it runs out of.
 *
 * SERV's defaults would already give most of the parameters below, but
 * W and WITH_CSR in particular change the datapath and the register
 * file, which is exactly what the per-unit power breakdown is measuring.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cmj_serv (
	input  wire        clk,
	input  wire        resetn,

	/* Everything the tile could not serve itself; see cmj_picorv32.v
	 * for the contract and cm_soc_serv.v for the other end. SERV has
	 * separate instruction and data buses, so both sides can be
	 * outstanding at once -- which they are throughout the boot copy,
	 * where the loop is fetched from external memory while it reads
	 * from it. */
	output wire        ext_i_req,
	output wire [31:0] ext_i_addr,
	input  wire [31:0] ext_i_rdata,

	output wire        ext_d_req,
	output wire        ext_d_we,
	output wire [31:0] ext_d_addr,
	output wire [31:0] ext_d_wdata,
	output wire [ 3:0] ext_d_wstrb,
	input  wire [31:0] ext_d_rdata,

	output wire [31:0] dbg_instr_addr
);
	wire [31:0] ibus_adr;
	wire        ibus_cyc;
	reg         ibus_ack;

	wire [31:0] dbus_adr;
	wire [31:0] dbus_dat;
	wire [ 3:0] dbus_sel;
	wire        dbus_we;
	wire        dbus_cyc;
	reg         dbus_ack;

	wire [31:0] ibus_rdt;
	wire [31:0] dbus_rdt;

	serv_rf_top #(
		/* External memory, not the TCM: the TCM is empty out of reset
		 * and the boot stub that fills it has to live somewhere the
		 * harness can preload. See sw/port/crt0.S. */
		.RESET_PC(32'h4000_0000),
		/* MINI resets what is needed to restart from RESET_PC, which is
		 * what the harness provides. NONE would rely on a power-on
		 * state a netlist does not have. */
		.RESET_STRATEGY("MINI"),
		/* The study's ELFs are built without the C extension, so a
		 * compressed decoder would be area and power nothing here
		 * exercises. */
		.COMPRESSED(1'b0),
		/* No MDU: SERV is RV32I, and CoreMark's multiplies go through
		 * libgcc. That is the honest configuration for a core without
		 * the M extension. */
		.MDU(1'b0),
		.WITH_CSR(1),
		/* Bit-serial: one bit per cycle. This is the parameter that
		 * makes SERV what it is. */
		.W(1)
	) cpu (
		.clk         (clk),
		.i_rst       (~resetn),
		.i_timer_irq (1'b0),

		.o_ibus_adr  (ibus_adr),
		.o_ibus_cyc  (ibus_cyc),
		.i_ibus_rdt  (ibus_rdt),
		.i_ibus_ack  (ibus_ack),

		.o_dbus_adr  (dbus_adr),
		.o_dbus_dat  (dbus_dat),
		.o_dbus_sel  (dbus_sel),
		.o_dbus_we   (dbus_we),
		.o_dbus_cyc  (dbus_cyc),
		.i_dbus_rdt  (dbus_rdt),
		.i_dbus_ack  (dbus_ack),

		.o_ext_rs1    (),
		.o_ext_rs2    (),
		.o_ext_funct3 (),
		.i_ext_rd     (32'b0),
		.i_ext_ready  (1'b0),
		.o_mdu_valid  ()
	);

	assign dbg_instr_addr = ibus_adr;

	/* No arbiter. SERV's two buses address disjoint memories -- the
	 * instruction bus only ever reads cmj_imem, the data bus only ever
	 * reads cmj_dmem -- so both are served every cycle and neither ever
	 * waits for the other. See cmj_progmem.sv for why the study is
	 * built this way rather than around a shared port.
	 *
	 * The one crossing is the boot copy, which writes cmj_imem through
	 * the data bus. That uses the instruction memory's write port while
	 * the fetch uses its read port, which is what 1R1W is for, and in
	 * any case the code being fetched at that moment is in external
	 * memory.
	 *
	 * Bit 30 is external memory, bit 28 the sim-control device, bit 16
	 * the data memory. See link.ld. */
	wire i_ext = ibus_adr[30] | ibus_adr[28];
	wire d_ext = dbus_adr[30] | dbus_adr[28];

	wire i_acc = ibus_cyc && !ibus_ack;
	wire d_acc = dbus_cyc && !dbus_ack;

	wire d_imem = !d_ext && !dbus_adr[16];
	wire d_dmem = !d_ext &&  dbus_adr[16];

	wire [31:0] im_rdata;
	wire [31:0] dm_rdata;

	/* FakeRAM's interface; see cmj_progmem.sv. The instruction memory
	 * is the only one both buses reach -- the data bus writes it during
	 * the boot copy -- and while that copy runs SERV fetches from
	 * external memory, so the two never coincide. The write wins if
	 * they ever do, and the assertion below stops the run rather than
	 * letting a stale instruction through. */
	wire im_rd = i_acc && !i_ext;
	wire im_wr = d_acc && d_imem && dbus_we;

	cmj_imem u_imem (
		.clk     (clk),
		.ce_in   (im_rd || im_wr),
		.we_in   (im_wr),
		.addr_in (im_wr ? dbus_adr[14:2] : ibus_adr[14:2]),
		.wd_in   (dbus_dat),
		.rd_out  (im_rdata)
	);

	cmj_dmem u_dmem (
		.clk      (clk),
		.ce_in    (d_acc && d_dmem),
		.we_in    (dbus_we),
		.addr_in  (dbus_adr[12:2]),
		.wd_in    (dbus_dat),
		.wstrb_in (dbus_sel),
		.rd_out   (dm_rdata)
	);

`ifndef SYNTHESIS
	always @(posedge clk) begin
		if (resetn && im_rd && im_wr) begin
			$display("cmj_serv: instruction memory read and write in one cycle");
			$finish;
		end
		/* And the data side never *reads* the instruction memory:
		 * link.ld puts .rodata in the data memory precisely so that it
		 * does not. A read here would be served by neither macro. */
		if (resetn && d_acc && d_imem && !dbus_we) begin
			$display("cmj_serv: data read from the instruction memory");
			$finish;
		end
	end
`endif

	assign ext_i_req   = i_acc && i_ext;
	assign ext_i_addr  = ibus_adr;

	assign ext_d_req   = d_acc && d_ext;
	assign ext_d_we    = dbus_we;
	assign ext_d_addr  = dbus_adr;
	assign ext_d_wdata = dbus_dat;
	assign ext_d_wstrb = dbus_sel;

	/* Which source answers each bus on the cycle its ack is high. */
	reg i_sel_ext;
	reg d_sel_ext;
	assign ibus_rdt = i_sel_ext ? ext_i_rdata : im_rdata;
	assign dbus_rdt = d_sel_ext ? ext_d_rdata : dm_rdata;

	always @(posedge clk) begin
		ibus_ack <= 1'b0;
		dbus_ack <= 1'b0;

		if (!resetn) begin
			ibus_ack <= 1'b0;
			dbus_ack <= 1'b0;
		end else begin
			if (i_acc) begin
				ibus_ack  <= 1'b1;
				i_sel_ext <= i_ext;
			end
			if (d_acc) begin
				dbus_ack  <= 1'b1;
				d_sel_ext <= d_ext;
			end
		end
	end
endmodule

`default_nettype wire
