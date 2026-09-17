// A parent whose register file is replaced by name. rf32x32 is the RTL
// the spec stands in for -- a Reg(Vec)-style file with one-hot writes
// -- and rf_parent is the logic around it. STRUCTURED_MEMORIES names the
// spec; synthesis blackboxes rf32x32 and the generated macro takes its
// place, and this RTL remains the simulation model.
module rf32x32(
  input         clock,
  input  [4:0]  io_readPorts_0_addr,
                io_readPorts_1_addr,
                io_readPorts_2_addr,
                io_readPorts_3_addr,
  output [31:0] io_readPorts_0_data,
                io_readPorts_1_data,
                io_readPorts_2_data,
                io_readPorts_3_data,
  input  [4:0]  io_writePorts_0_addr,
  input  [31:0] io_writePorts_0_data,
  input         io_writePorts_0_wen,
  input  [4:0]  io_writePorts_1_addr,
  input  [31:0] io_writePorts_1_data,
  input         io_writePorts_1_wen
);
  reg [31:0] mem [0:31];
  integer i;
  always @(posedge clock) begin
    for (i = 0; i < 32; i = i + 1) begin
      if ((io_writePorts_0_wen && io_writePorts_0_addr == i) ||
          (io_writePorts_1_wen && io_writePorts_1_addr == i))
        mem[i] <= ({32{io_writePorts_0_wen && io_writePorts_0_addr == i}} & io_writePorts_0_data) |
                  ({32{io_writePorts_1_wen && io_writePorts_1_addr == i}} & io_writePorts_1_data);
    end
  end
  assign io_readPorts_0_data = mem[io_readPorts_0_addr];
  assign io_readPorts_1_data = mem[io_readPorts_1_addr];
  assign io_readPorts_2_data = mem[io_readPorts_2_addr];
  assign io_readPorts_3_data = mem[io_readPorts_3_addr];
endmodule

module rf_parent(
  input         clock,
  input  [4:0]  ra0, ra1, ra2, ra3, wa0, wa1,
  input  [31:0] wd0, wd1,
  input         we0, we1,
  output [31:0] sum
);
  reg [4:0]  ra0_q, ra1_q, ra2_q, ra3_q, wa0_q, wa1_q;
  reg [31:0] wd0_q, wd1_q;
  reg        we0_q, we1_q;
  always @(posedge clock) begin
    ra0_q <= ra0; ra1_q <= ra1; ra2_q <= ra2; ra3_q <= ra3;
    wa0_q <= wa0; wa1_q <= wa1; wd0_q <= wd0; wd1_q <= wd1;
    we0_q <= we0; we1_q <= we1;
  end
  wire [31:0] d0, d1, d2, d3;
  rf32x32 rf (
    .clock(clock),
    .io_readPorts_0_addr(ra0_q), .io_readPorts_1_addr(ra1_q),
    .io_readPorts_2_addr(ra2_q), .io_readPorts_3_addr(ra3_q),
    .io_readPorts_0_data(d0), .io_readPorts_1_data(d1),
    .io_readPorts_2_data(d2), .io_readPorts_3_data(d3),
    .io_writePorts_0_addr(wa0_q), .io_writePorts_0_data(wd0_q), .io_writePorts_0_wen(we0_q),
    .io_writePorts_1_addr(wa1_q), .io_writePorts_1_data(wd1_q), .io_writePorts_1_wen(we1_q)
  );
  reg [31:0] sum_q;
  always @(posedge clock) sum_q <= d0 + d1 + d2 + d3;
  assign sum = sum_q;
endmodule
