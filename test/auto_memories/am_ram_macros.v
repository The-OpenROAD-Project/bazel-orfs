/* The flow's view of am_ram_2048x32: ports, no body.
 *
 * am_top.v instantiates this module and nothing defines it, which is the
 * shape a .memories override is for -- the geometry comes from
 * am_ram_2048x32.memories and AUTO_MEMORIES emits the macro. But
 * blackboxing happens after canonicalization, and yosys's hierarchy
 * check runs during it:
 *
 *   ERROR: Module `\am_ram_2048x32' referenced in module `\am_top' in
 *   cell `\u_ram' is not part of the design.
 *
 * So the flow needs the module boundary and nothing else. The port names
 * are FakeRAM's exactly: a .memories override describes a boundary but
 * does not rename the generated macro's pins, and a module declared any
 * other way links against the LEF master and connects nothing.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

module am_ram_2048x32 (
	input  wire        clk,
	input  wire        ce_in,
	input  wire        we_in,
	input  wire [10:0] addr_in,
	input  wire [31:0] wd_in,
	output wire [31:0] rd_out
);
endmodule

`default_nettype wire
