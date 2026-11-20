// The global floorplan planner's toy (tools/floorplan): three blocks and
// the parent's glue, each feature small enough to synthesise in seconds
// and each with one known answer.
//
//   FpCore  registers its request to FpMem and its result to FpVec; a
//           16-bit feedthrough (ft_in -> ft_out, combinational) and a
//           deep register-to-output cone (deep_out) that, with the glue's
//           adder and FpVec's deep input cone, is the cross-macro path
//   FpMem   two 256x34 memories behind a registered request; its pins
//           face FpCore, its memories are most of its area
//   FpVec   the over-wide bus: 1024 bits in, registered and folded to 32
//           bits; its own area is a fraction of what its pins need
//   fp_top  the glue: a flop on the response path, the adder on the
//           cross-macro path, the top ports
module FpCore (
    input  logic            clock,
    input  logic [31:0]     in_top,
    input  logic [63:0]     resp,
    output logic [63:0]     req,
    output logic [1023:0] wide,
    input  logic [15:0]     ft_in,
    output logic [15:0]     ft_out,
    output logic [31:0]     deep_out
);
  logic [31:0] acc, a, b;
  always_ff @(posedge clock) begin
    acc  <= acc ^ in_top ^ resp[31:0] ^ resp[63:32];
    a    <= in_top + acc;
    b    <= resp[31:0] - acc;
    req  <= {acc, a ^ b};
    for (int i = 0; i < 32; i++) wide[i*32+:32] <= acc ^ (a << i) ^ (b >> i);
  end
  assign ft_out   = ft_in ^ {ft_in[7:0], ft_in[15:8]};
  // the deep register-to-output cone
  assign deep_out = (a * b) + (acc * a);
endmodule

module FpMem (
    input  logic        clock,
    input  logic [63:0] req,
    output logic [63:0] resp
);
  logic [ 7:0] addr0, addr1;
  logic [33:0] wd0, wd1, rd0, rd1;
  logic we0, we1;
  always_ff @(posedge clock) begin
    addr0 <= req[7:0];
    addr1 <= req[15:8];
    wd0   <= req[49:16];
    wd1   <= {req[63:50], req[19:0]};
    we0   <= req[62];
    we1   <= req[63];
    resp  <= {rd1[31:0], rd0[31:0]};
  end
  fakeram7_256x34 mem0 (
      .clk(clock),
      .ce_in(1'b1),
      .we_in(we0),
      .addr_in(addr0),
      .wd_in(wd0),
      .rd_out(rd0)
  );
  fakeram7_256x34 mem1 (
      .clk(clock),
      .ce_in(1'b1),
      .we_in(we1),
      .addr_in(addr1),
      .wd_in(wd1),
      .rd_out(rd1)
  );
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
    // the deep input-to-register cone
    d   <= deep_in * deep_in + deep_in;
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
  logic [63:0] req, resp_mem, resp;
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
