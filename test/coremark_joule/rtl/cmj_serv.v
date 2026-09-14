/* The SERV configuration this study measures, frozen.
 *
 * Same purpose as cmj_picorv32.v: config.mk names this module as
 * DESIGN_NAME and cm_soc_serv.v instantiates it, so the simulated core
 * and the hardened core cannot be configured differently.
 *
 * SERV's defaults would already give most of this, but W and WITH_CSR in
 * particular change the datapath and the register file, which is exactly
 * what the per-unit power breakdown is measuring.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module cmj_serv (
	input  wire        clk,
	input  wire        i_rst,

	output wire [31:0] o_ibus_adr,
	output wire        o_ibus_cyc,
	input  wire [31:0] i_ibus_rdt,
	input  wire        i_ibus_ack,

	output wire [31:0] o_dbus_adr,
	output wire [31:0] o_dbus_dat,
	output wire [ 3:0] o_dbus_sel,
	output wire        o_dbus_we,
	output wire        o_dbus_cyc,
	input  wire [31:0] i_dbus_rdt,
	input  wire        i_dbus_ack
);
	serv_rf_top #(
		.RESET_PC(32'h0000_0000),
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
		.i_rst       (i_rst),
		.i_timer_irq (1'b0),

		.o_ibus_adr  (o_ibus_adr),
		.o_ibus_cyc  (o_ibus_cyc),
		.i_ibus_rdt  (i_ibus_rdt),
		.i_ibus_ack  (i_ibus_ack),

		.o_dbus_adr  (o_dbus_adr),
		.o_dbus_dat  (o_dbus_dat),
		.o_dbus_sel  (o_dbus_sel),
		.o_dbus_we   (o_dbus_we),
		.o_dbus_cyc  (o_dbus_cyc),
		.i_dbus_rdt  (i_dbus_rdt),
		.i_dbus_ack  (i_dbus_ack),

		.o_ext_rs1    (),
		.o_ext_rs2    (),
		.o_ext_funct3 (),
		.i_ext_rd     (32'b0),
		.i_ext_ready  (1'b0),
		.o_mdu_valid  ()
	);
endmodule

`default_nettype wire
