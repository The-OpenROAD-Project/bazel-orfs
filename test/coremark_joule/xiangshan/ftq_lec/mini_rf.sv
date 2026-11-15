// The generated register file's shape (FtqMetaQueueResolve, the
// RegVecFile model, at 8 x 4 here): a combinational read, one write port.
module RfMini(
  input        clock,
  input  [2:0] io_readPorts_0_addr,
  output [3:0] io_readPorts_0_data,
  input        io_writePorts_0_wen,
  input  [2:0] io_writePorts_0_addr,
  input  [3:0] io_writePorts_0_data
);
  reg [3:0] mem_0;
  reg [3:0] mem_1;
  reg [3:0] mem_2;
  reg [3:0] mem_3;
  reg [3:0] mem_4;
  reg [3:0] mem_5;
  reg [3:0] mem_6;
  reg [3:0] mem_7;
  reg [3:0] casez_tmp;
  always @(*) begin
    casez (io_readPorts_0_addr)
      3'b000: casez_tmp = mem_0;
      3'b001: casez_tmp = mem_1;
      3'b010: casez_tmp = mem_2;
      3'b011: casez_tmp = mem_3;
      3'b100: casez_tmp = mem_4;
      3'b101: casez_tmp = mem_5;
      3'b110: casez_tmp = mem_6;
      default: casez_tmp = mem_7;
    endcase
  end
  always @(posedge clock) begin
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h0) mem_0 <= io_writePorts_0_data;
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h1) mem_1 <= io_writePorts_0_data;
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h2) mem_2 <= io_writePorts_0_data;
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h3) mem_3 <= io_writePorts_0_data;
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h4) mem_4 <= io_writePorts_0_data;
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h5) mem_5 <= io_writePorts_0_data;
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h6) mem_6 <= io_writePorts_0_data;
    if (io_writePorts_0_wen & io_writePorts_0_addr == 3'h7) mem_7 <= io_writePorts_0_data;
  end
  assign io_readPorts_0_data = casez_tmp;
endmodule
