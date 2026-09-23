// A 16 x 8 register file with two read and two write ports, in the port
// shape utils.RegVecFile gives XiangShan's files: what STRUCTURED_MEMORIES
// replaces. Behavioural, for simulation; the flow never synthesises it.
module SmallFile(
  input         clock,
  input  [3:0]  io_readPorts_0_addr,
  output [7:0]  io_readPorts_0_data,
  input  [3:0]  io_readPorts_1_addr,
  output [7:0]  io_readPorts_1_data,
  input         io_writePorts_0_wen,
  input  [3:0]  io_writePorts_0_addr,
  input  [7:0]  io_writePorts_0_data,
  input         io_writePorts_1_wen,
  input  [3:0]  io_writePorts_1_addr,
  input  [7:0]  io_writePorts_1_data
);
  reg [7:0] mem [0:15];
  always @(posedge clock) begin
    if (io_writePorts_0_wen) mem[io_writePorts_0_addr] <= io_writePorts_0_data;
    if (io_writePorts_1_wen) mem[io_writePorts_1_addr] <= io_writePorts_1_data;
  end
  assign io_readPorts_0_data = mem[io_readPorts_0_addr];
  assign io_readPorts_1_data = mem[io_readPorts_1_addr];
endmodule

// The parent: registers around one file, some logic of its own.
module small_top(
  input         clock,
  input         reset,
  input  [3:0]  ra0, ra1, wa0, wa1,
  input  [7:0]  wd0, wd1,
  input         we0, we1,
  output [7:0]  rd0, rd1,
  output [7:0]  sum
);
  reg [3:0] ra0_q, ra1_q, wa0_q, wa1_q;
  reg [7:0] wd0_q, wd1_q;
  reg       we0_q, we1_q;
  wire [7:0] d0, d1;
  always @(posedge clock) begin
    ra0_q <= ra0; ra1_q <= ra1; wa0_q <= wa0; wa1_q <= wa1;
    wd0_q <= wd0; wd1_q <= wd1; we0_q <= we0; we1_q <= we1;
  end
  SmallFile u_file(
    .clock(clock),
    .io_readPorts_0_addr(ra0_q), .io_readPorts_0_data(d0),
    .io_readPorts_1_addr(ra1_q), .io_readPorts_1_data(d1),
    .io_writePorts_0_wen(we0_q), .io_writePorts_0_addr(wa0_q), .io_writePorts_0_data(wd0_q),
    .io_writePorts_1_wen(we1_q), .io_writePorts_1_addr(wa1_q), .io_writePorts_1_data(wd1_q)
  );
  // Bit 0 of the file is never read: a dead column, which the synth ODB
  // step's eliminate_dead_logic removes from the placed netlist. The
  // parent's placement script has to skip those cells (FLW-0008) rather
  // than stop on the first one, as it did on XiangShan's RobEntryFile.
  reg [6:0] rd0_q, rd1_q, sum_q;
  always @(posedge clock) begin
    rd0_q <= d0[7:1]; rd1_q <= d1[7:1]; sum_q <= d0[7:1] + d1[7:1];
  end
  assign rd0 = {rd0_q, 1'b0};
  assign rd1 = {rd1_q, 1'b0};
  assign sum = {sum_q, 1'b0};
endmodule
