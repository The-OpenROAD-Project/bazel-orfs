// The register file as RTL writes one. With AUTO_MEMORIES_REGFILES naming
// its spec the flow never synthesises this body: OpenROAD's generate_ram
// builds it of placed standard cells instead.
module Rf25x72(
  input         clock,
  input  [4:0]  io_r0_addr,
  output [71:0] io_r0_data,
  input         io_w0_en,
  input  [4:0]  io_w0_addr,
  input  [71:0] io_w0_data
);
  reg [71:0] mem [0:24];
  always @(posedge clock)
    if (io_w0_en) mem[io_w0_addr] <= io_w0_data;
  assign io_r0_data = mem[io_r0_addr];
endmodule
