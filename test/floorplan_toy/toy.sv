// The global floorplan planner's toy (tools/floorplan): three blocks and
// the parent's glue, each feature small enough to synthesise in seconds
// and each with one known answer.
//
//   FpCore  registers its request to FpMem and its result to FpVec; a
//           16-bit feedthrough (ft_in -> ft_out, combinational) and a
//           register-to-output adder (deep_out) that, with the glue's
//           adder and FpVec's input adder, is the cross-macro path: three
//           adders, half the period, the rest the wire's
//   FpMem   four 256x34 memories behind a registered request; its pins
//           face FpCore, its memories are most of its area
//   FpVec   the over-wide bus: 1024 bits in, registered and folded to 32
//           bits; its own area is a fraction of what its pins need
//   fp_top  the glue: a flop on the response path, the adder on the
//           cross-macro path, the top ports
module FpCore (
    input  logic            clock,
    input  logic [31:0]     in_top,
    input  logic [135:0]    resp,
    output logic [127:0]    req,
    output logic [1023:0] wide,
    input  logic [15:0]     ft_in,
    output logic [15:0]     ft_out,
    output logic [31:0]     deep_out
);
  logic [31:0] acc, a, b;
  always_ff @(posedge clock) begin
    acc  <= acc ^ in_top ^ resp[31:0] ^ resp[63:32] ^ resp[95:64] ^ resp[127:96] ^ {24'b0, resp[135:128]};
    a    <= in_top + acc;
    b    <= resp[31:0] - acc;
    req  <= {acc, a ^ b, a, b};
    for (int i = 0; i < 32; i++) wide[i*32+:32] <= acc ^ (a << i) ^ (b >> i);
  end
  assign ft_out   = ft_in ^ {ft_in[7:0], ft_in[15:8]};
  // the register-to-output leg of the cross-macro path
  assign deep_out = a + b;
endmodule

module FpMem (
    input  logic         clock,
    input  logic [127:0] req,
    output logic [135:0] resp
);
  logic [7:0] addr[4];
  logic [33:0] wd[4], rd[4];
  logic we[4];
  always_ff @(posedge clock) begin
    for (int i = 0; i < 4; i++) begin
      addr[i] <= req[i*32+:8];
      wd[i]   <= {req[i*32+8+:24], req[(i*32+40)%128+:10]};
      we[i]   <= req[i*32+31];
      resp[i*34+:34] <= rd[i];
    end
  end
  for (genvar i = 0; i < 4; i++) begin : g_mem
    fakeram7_256x34 mem (
        .clk(clock),
        .ce_in(1'b1),
        .we_in(we[i]),
        .addr_in(addr[i]),
        .wd_in(wd[i]),
        .rd_out(rd[i])
    );
  end
endmodule

module FpVec (
    input  logic            clock,
    input  logic [1023:0] wide,
    input  logic [31:0]     deep_in,
    input  logic [15:0]     ft_in,
    output logic [15:0]     ft_out,
    output logic [31:0]     res
);
  logic [1023:0] w;
  logic [31:0] fold, d;
  always_comb begin
    fold = '0;
    for (int i = 0; i < 32; i++) fold ^= w[i*32+:32];
  end
  always_ff @(posedge clock) begin
    w   <= wide;
    // the input-to-register leg of the cross-macro path
    d   <= deep_in + w[31:0];
    res <= fold ^ d;
  end
  assign ft_out = ~ft_in;
endmodule

module fp_top (
    input  logic        clock,
    input  logic [31:0] in_top,
    input  logic [15:0] ft_top,
    output logic [31:0] out_top,
    output logic [15:0] ft_out
);
  logic [127:0] req;
  logic [135:0] resp_mem, resp;
  logic [1023:0] wide;
  logic [31:0] deep, deep_sum, res;
  logic [15:0] ft_mid;
  always_ff @(posedge clock) begin
    resp    <= resp_mem;
    out_top <= res;
  end
  // the glue's leg of the cross-macro path
  assign deep_sum = deep + {deep[15:0], deep[31:16]};
  FpCore core (
      .clock(clock),
      .in_top(in_top),
      .resp(resp),
      .req(req),
      .wide(wide),
      .ft_in(ft_top),
      .ft_out(ft_mid),
      .deep_out(deep)
  );
  FpMem mem (
      .clock(clock),
      .req(req),
      .resp(resp_mem)
  );
  FpVec vec (
      .clock(clock),
      .wide(wide),
      .deep_in(deep_sum),
      .ft_in(ft_mid),
      .ft_out(ft_out),
      .res(res)
  );
endmodule
