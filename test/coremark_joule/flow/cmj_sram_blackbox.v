/* The flow's view of every SRAM in the study: ports, no body.
 *
 * rtl/cmj_sram_models.sv is the behavioural view and is deliberately
 * not in any VERILOG_FILES -- handing both to one tool would leave it
 * to choose which to synthesise, and the answer would be flip-flops.
 * But a module that is nowhere defined fails yosys's hierarchy check,
 * so the flow gets each module's boundary and nothing else, and the
 * scaler's LEF and Liberty (ADDITIONAL_LEFS / ADDITIONAL_LIBS in each
 * config.mk) make it a macro. Modules a design does not instantiate
 * are dropped at hierarchy.
 *
 * Port names and widths match cmj_sram_models.sv exactly; a boundary
 * that disagreed would link against the LEF master and connect
 * nothing, silently, with plausible area.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

(* blackbox *)
module cmj_imem_sram (
	input  wire        RW0_clk,
	input  wire        RW0_en,
	input  wire        RW0_wmode,
	input  wire [12:0] RW0_addr,
	input  wire [31:0] RW0_wmask,
	input  wire [31:0] RW0_wdata,
	output wire [31:0] RW0_rdata
);
endmodule

(* blackbox *)
module cmj_dmem_lane_sram (
	input  wire        RW0_clk,
	input  wire        RW0_en,
	input  wire        RW0_wmode,
	input  wire [10:0] RW0_addr,
	input  wire [7:0] RW0_wmask,
	input  wire [7:0] RW0_wdata,
	output wire [7:0] RW0_rdata
);
endmodule

(* blackbox *)
module cmj_ic_tag_sram (
	input  wire        RW0_clk,
	input  wire        RW0_en,
	input  wire        RW0_wmode,
	input  wire [7:0] RW0_addr,
	input  wire [21:0] RW0_wmask,
	input  wire [21:0] RW0_wdata,
	output wire [21:0] RW0_rdata
);
endmodule

(* blackbox *)
module cmj_ic_data_sram (
	input  wire        RW0_clk,
	input  wire        RW0_en,
	input  wire        RW0_wmode,
	input  wire [7:0] RW0_addr,
	input  wire [63:0] RW0_wmask,
	input  wire [63:0] RW0_wdata,
	output wire [63:0] RW0_rdata
);
endmodule

(* blackbox *)
module sram_2048x39 (
	input  wire        RW0_clk,
	input  wire        RW0_en,
	input  wire        RW0_wmode,
	input  wire [10:0] RW0_addr,
	input  wire [38:0] RW0_wmask,
	input  wire [38:0] RW0_wdata,
	output wire [38:0] RW0_rdata
);
endmodule

(* blackbox *)
module sram_256x34 (
	input  wire        RW0_clk,
	input  wire        RW0_en,
	input  wire        RW0_wmode,
	input  wire [7:0] RW0_addr,
	input  wire [33:0] RW0_wmask,
	input  wire [33:0] RW0_wdata,
	output wire [33:0] RW0_rdata
);
endmodule

(* blackbox *)
module sram_64x21 (
	input  wire        RW0_clk,
	input  wire        RW0_en,
	input  wire        RW0_wmode,
	input  wire [5:0] RW0_addr,
	input  wire [20:0] RW0_wmask,
	input  wire [20:0] RW0_wdata,
	output wire [20:0] RW0_rdata
);
endmodule

`default_nettype wire
