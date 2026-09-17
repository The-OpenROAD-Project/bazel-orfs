/* Every SRAM this study hardens, as one behavioural model each.
 *
 * Two readers, one file. The simulators read it for the gate-level
 * runs, where the netlist has a blackbox where each memory was and a
 * blackbox stores nothing -- without these bodies CoreMark fails its
 * CRCs rather than reporting low memory power (§3.2). And
 * tools/memory_macro_scaler reads it to emit each module's LEF and
 * Liberty from the module's own port widths: rows from the address
 * width, bits from the data width, one read-write port. The two views
 * therefore cannot disagree about a memory's shape, because there is
 * one declaration of it.
 *
 * The port names are firtool's -- RW0_addr, RW0_en, RW0_clk,
 * RW0_wmode, RW0_wmask, RW0_wdata, RW0_rdata -- because that is the
 * convention the scaler classifies and emits. Nothing in the study's
 * RTL speaks it: each core-facing memory (cmj_imem, cmj_dmem_lane,
 * VeeR's ram_*, ibex's prim_ram_1p) is a wiring wrapper around one of
 * these, so a memory can be swapped for another model by changing the
 * wrapper's instance and nothing else.
 *
 * Synchronous read, one wait state, bit-granular write mask -- what the
 * generated Liberty characterises.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

/* the 32 KiB instruction memory of the cacheless tiles: 8192 x 32. */
module cmj_imem_sram (
	input  wire            RW0_clk,
	input  wire            RW0_en,
	input  wire            RW0_wmode,
	input  wire [12:0] RW0_addr,
	input  wire [31:0] RW0_wmask,
	input  wire [31:0] RW0_wdata,
	output reg  [31:0] RW0_rdata
);
	reg [31:0] mem [0:8191];

	/* A read of a location never written returns X otherwise, and
	 * in a 4-state simulation that X reaches the fetch path and
	 * stops the core -- VeeR reads its DCCM and its cache arrays
	 * before it writes them. Verilator is 2-state and has always
	 * behaved as though this initialisation were here, so adding
	 * it aligns the two rather than changing either. A real macro
	 * powers up undefined; real silicon does not propagate X. */
	integer init_i;
	initial for (init_i = 0; init_i <= 8191; init_i = init_i + 1)
		mem[init_i] = 32'b0;
	integer b;

	always @(posedge RW0_clk) begin
		if (RW0_en) begin
			if (RW0_wmode) begin
				for (b = 0; b < 32; b = b + 1) begin
					if (RW0_wmask[b]) mem[RW0_addr][b] <= RW0_wdata[b];
				end
			end else begin
				RW0_rdata <= mem[RW0_addr];
			end
		end
	end
endmodule

/* one byte lane of the tiles' 8 KiB data memory: 2048 x 8. */
module cmj_dmem_lane_sram (
	input  wire            RW0_clk,
	input  wire            RW0_en,
	input  wire            RW0_wmode,
	input  wire [10:0] RW0_addr,
	input  wire [7:0] RW0_wmask,
	input  wire [7:0] RW0_wdata,
	output reg  [7:0] RW0_rdata
);
	reg [7:0] mem [0:2047];

	/* A read of a location never written returns X otherwise, and
	 * in a 4-state simulation that X reaches the fetch path and
	 * stops the core -- VeeR reads its DCCM and its cache arrays
	 * before it writes them. Verilator is 2-state and has always
	 * behaved as though this initialisation were here, so adding
	 * it aligns the two rather than changing either. A real macro
	 * powers up undefined; real silicon does not propagate X. */
	integer init_i;
	initial for (init_i = 0; init_i <= 2047; init_i = init_i + 1)
		mem[init_i] = 8'b0;
	integer b;

	always @(posedge RW0_clk) begin
		if (RW0_en) begin
			if (RW0_wmode) begin
				for (b = 0; b < 8; b = b + 1) begin
					if (RW0_wmask[b]) mem[RW0_addr][b] <= RW0_wdata[b];
				end
			end else begin
				RW0_rdata <= mem[RW0_addr];
			end
		end
	end
endmodule

/* ibex_icache's tag array: 256 x 22. */
module cmj_ic_tag_sram (
	input  wire            RW0_clk,
	input  wire            RW0_en,
	input  wire            RW0_wmode,
	input  wire [7:0] RW0_addr,
	input  wire [21:0] RW0_wmask,
	input  wire [21:0] RW0_wdata,
	output reg  [21:0] RW0_rdata
);
	reg [21:0] mem [0:255];

	/* A read of a location never written returns X otherwise, and
	 * in a 4-state simulation that X reaches the fetch path and
	 * stops the core -- VeeR reads its DCCM and its cache arrays
	 * before it writes them. Verilator is 2-state and has always
	 * behaved as though this initialisation were here, so adding
	 * it aligns the two rather than changing either. A real macro
	 * powers up undefined; real silicon does not propagate X. */
	integer init_i;
	initial for (init_i = 0; init_i <= 255; init_i = init_i + 1)
		mem[init_i] = 22'b0;
	integer b;

	always @(posedge RW0_clk) begin
		if (RW0_en) begin
			if (RW0_wmode) begin
				for (b = 0; b < 22; b = b + 1) begin
					if (RW0_wmask[b]) mem[RW0_addr][b] <= RW0_wdata[b];
				end
			end else begin
				RW0_rdata <= mem[RW0_addr];
			end
		end
	end
endmodule

/* ibex_icache's data array: 256 x 64. */
module cmj_ic_data_sram (
	input  wire            RW0_clk,
	input  wire            RW0_en,
	input  wire            RW0_wmode,
	input  wire [7:0] RW0_addr,
	input  wire [63:0] RW0_wmask,
	input  wire [63:0] RW0_wdata,
	output reg  [63:0] RW0_rdata
);
	reg [63:0] mem [0:255];

	/* A read of a location never written returns X otherwise, and
	 * in a 4-state simulation that X reaches the fetch path and
	 * stops the core -- VeeR reads its DCCM and its cache arrays
	 * before it writes them. Verilator is 2-state and has always
	 * behaved as though this initialisation were here, so adding
	 * it aligns the two rather than changing either. A real macro
	 * powers up undefined; real silicon does not propagate X. */
	integer init_i;
	initial for (init_i = 0; init_i <= 255; init_i = init_i + 1)
		mem[init_i] = 64'b0;
	integer b;

	always @(posedge RW0_clk) begin
		if (RW0_en) begin
			if (RW0_wmode) begin
				for (b = 0; b < 64; b = b + 1) begin
					if (RW0_wmask[b]) mem[RW0_addr][b] <= RW0_wdata[b];
				end
			end else begin
				RW0_rdata <= mem[RW0_addr];
			end
		end
	end
endmodule

/* VeeR's DCCM bank: 2048 x 39. */
module sram_2048x39 (
	input  wire            RW0_clk,
	input  wire            RW0_en,
	input  wire            RW0_wmode,
	input  wire [10:0] RW0_addr,
	input  wire [38:0] RW0_wmask,
	input  wire [38:0] RW0_wdata,
	output reg  [38:0] RW0_rdata
);
	reg [38:0] mem [0:2047];

	/* A read of a location never written returns X otherwise, and
	 * in a 4-state simulation that X reaches the fetch path and
	 * stops the core -- VeeR reads its DCCM and its cache arrays
	 * before it writes them. Verilator is 2-state and has always
	 * behaved as though this initialisation were here, so adding
	 * it aligns the two rather than changing either. A real macro
	 * powers up undefined; real silicon does not propagate X. */
	integer init_i;
	initial for (init_i = 0; init_i <= 2047; init_i = init_i + 1)
		mem[init_i] = 39'b0;
	integer b;

	always @(posedge RW0_clk) begin
		if (RW0_en) begin
			if (RW0_wmode) begin
				for (b = 0; b < 39; b = b + 1) begin
					if (RW0_wmask[b]) mem[RW0_addr][b] <= RW0_wdata[b];
				end
			end else begin
				RW0_rdata <= mem[RW0_addr];
			end
		end
	end
endmodule

/* VeeR's instruction-cache data array: 256 x 34. */
module sram_256x34 (
	input  wire            RW0_clk,
	input  wire            RW0_en,
	input  wire            RW0_wmode,
	input  wire [7:0] RW0_addr,
	input  wire [33:0] RW0_wmask,
	input  wire [33:0] RW0_wdata,
	output reg  [33:0] RW0_rdata
);
	reg [33:0] mem [0:255];

	/* A read of a location never written returns X otherwise, and
	 * in a 4-state simulation that X reaches the fetch path and
	 * stops the core -- VeeR reads its DCCM and its cache arrays
	 * before it writes them. Verilator is 2-state and has always
	 * behaved as though this initialisation were here, so adding
	 * it aligns the two rather than changing either. A real macro
	 * powers up undefined; real silicon does not propagate X. */
	integer init_i;
	initial for (init_i = 0; init_i <= 255; init_i = init_i + 1)
		mem[init_i] = 34'b0;
	integer b;

	always @(posedge RW0_clk) begin
		if (RW0_en) begin
			if (RW0_wmode) begin
				for (b = 0; b < 34; b = b + 1) begin
					if (RW0_wmask[b]) mem[RW0_addr][b] <= RW0_wdata[b];
				end
			end else begin
				RW0_rdata <= mem[RW0_addr];
			end
		end
	end
endmodule

/* VeeR's instruction-cache tag array: 64 x 21. */
module sram_64x21 (
	input  wire            RW0_clk,
	input  wire            RW0_en,
	input  wire            RW0_wmode,
	input  wire [5:0] RW0_addr,
	input  wire [20:0] RW0_wmask,
	input  wire [20:0] RW0_wdata,
	output reg  [20:0] RW0_rdata
);
	reg [20:0] mem [0:63];

	/* A read of a location never written returns X otherwise, and
	 * in a 4-state simulation that X reaches the fetch path and
	 * stops the core -- VeeR reads its DCCM and its cache arrays
	 * before it writes them. Verilator is 2-state and has always
	 * behaved as though this initialisation were here, so adding
	 * it aligns the two rather than changing either. A real macro
	 * powers up undefined; real silicon does not propagate X. */
	integer init_i;
	initial for (init_i = 0; init_i <= 63; init_i = init_i + 1)
		mem[init_i] = 21'b0;
	integer b;

	always @(posedge RW0_clk) begin
		if (RW0_en) begin
			if (RW0_wmode) begin
				for (b = 0; b < 21; b = b + 1) begin
					if (RW0_wmask[b]) mem[RW0_addr][b] <= RW0_wdata[b];
				end
			end else begin
				RW0_rdata <= mem[RW0_addr];
			end
		end
	end
endmodule

`default_nettype wire
