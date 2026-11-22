// punched.sv's Punched as a hierarchical global route leaves it, by hand:
// PunCore keeps its module, its clock arrives on a clock-tree leaf, and
// repair_design has buffered two of its loads' nets in the parent and
// fed them back in through ports its RTL lacks:
//
//   net7_0       PunCore's own output q[0], through two buffers in the
//                parent (place1, place2): the load computing q[1] reads it
//   \u_in.q_2_   PunIn's output q[2], PunCore's d[2], through a buffer
//                in the parent (place3), named like an RTL net: the load
//                computing q[2] reads it instead of d[2]
//
// and PunCore's output mode, a register its RTL only ever writes 2'b10,
// is folded to that constant, tie cells, its enable `en` no port of
// PunCore, and a buffer in the parent (place4) loads mode[1]. The shape
// measured on XiangShan's VecRegionModule (issuePipes: 1,532 such inputs).
// PunCore's input tag, which it never uses, gets r[0] on its bit 0 and
// a net nothing drives, _98_, on its bit 1, as MemBlock's netlist leaves
// VirtualStoreQueue's numLsElem. PunCore's data[0] is r[0] through
// `assign dsel`, the line punched_dontcare.v and punched_matters.v
// replace with a gate that makes it differ from the RTL while v is 0,
// and while v is 1. PunCore's rdy is its register through
// `assign rdy = rdyq`, which punched_rdy_*.v replace to make it differ
// from the RTL before the first reset, during it, or after it.
module Punched (clock, reset, din, dout);
 input clock;
 input reset;
 input [3:0] din;
 output [3:0] dout;
 wire [3:0] r;
 wire clknet_1_0__leaf_clock;
 wire net7_1;
 wire net7_0;
 wire net8_0;
 wire _98_;
 wire [1:0] mode_w;
 wire mode_load;
 wire dsel;
 assign dsel = r[0];
 BUFx4_ASAP7_75t_R clkbuf_1_0__f_clock (.A(clock),
    .Y(clknet_1_0__leaf_clock));
 PunIn u_in (.clock(clknet_1_0__leaf_clock),
    .d(din),
    .q(r));
 BUFx3_ASAP7_75t_R place1 (.A(dout[0]),
    .Y(net7_1));
 BUFx3_ASAP7_75t_R place2 (.A(net7_1),
    .Y(net7_0));
 BUFx2_ASAP7_75t_R place3 (.A(r[2]),
    .Y(net8_0));
 BUFx2_ASAP7_75t_R place4 (.A(mode_w[1]),
    .Y(mode_load));
 PunCore u_core (.clknet_1_0__leaf_clock(clknet_1_0__leaf_clock),
    .reset(reset),
    .d(r),
    .tag({_98_, r[0]}),
    .v(r[3]),
    .data({r[1], dsel}),
    .q(dout),
    .mode(mode_w),
    .net7_0(net7_0),
    .\u_in.q_2_ (net8_0));
endmodule
module PunIn (clock, d, q);
 input clock;
 input [3:0] d;
 output [3:0] q;
 wire qn0;
 wire qn1;
 wire qn2;
 wire qn3;
 DFFHQNx1_ASAP7_75t_R q_reg_0_ (.CLK(clock),
    .D(d[0]),
    .QN(qn0));
 DFFHQNx1_ASAP7_75t_R q_reg_1_ (.CLK(clock),
    .D(d[1]),
    .QN(qn1));
 DFFHQNx1_ASAP7_75t_R q_reg_2_ (.CLK(clock),
    .D(d[2]),
    .QN(qn2));
 DFFHQNx1_ASAP7_75t_R q_reg_3_ (.CLK(clock),
    .D(d[3]),
    .QN(qn3));
 INVx1_ASAP7_75t_R _0_ (.A(qn0),
    .Y(q[0]));
 INVx1_ASAP7_75t_R _1_ (.A(qn1),
    .Y(q[1]));
 INVx1_ASAP7_75t_R _2_ (.A(qn2),
    .Y(q[2]));
 INVx1_ASAP7_75t_R _3_ (.A(qn3),
    .Y(q[3]));
endmodule
module PunCore (clknet_1_0__leaf_clock, reset, d, tag, v, data, q, mode, acc, rdy, net7_0, \u_in.q_2_ );
 input clknet_1_0__leaf_clock;
 input reset;
 output rdy;
 wire nreset;
 wire rdyn;
 wire rdyq;
 input [3:0] d;
 input [1:0] tag;
 input v;
 input [1:0] data;
 output [1:0] acc;
 wire nv;
 wire [1:0] ta;
 wire [1:0] tb;
 wire [1:0] na;
 wire [1:0] aqn;
 output [3:0] q;
 output [1:0] mode;
 input net7_0;
 input \u_in.q_2_ ;
 wire n0;
 wire n1;
 wire n2;
 wire n3;
 wire qn0;
 wire qn1;
 wire qn2;
 wire qn3;
 XOR2xp5_ASAP7_75t_R _0_ (.A(q[3]),
    .B(d[0]),
    .Y(n0));
 XOR2xp5_ASAP7_75t_R _1_ (.A(net7_0),
    .B(d[1]),
    .Y(n1));
 XOR2xp5_ASAP7_75t_R _2_ (.A(q[1]),
    .B(\u_in.q_2_ ),
    .Y(n2));
 XOR2xp5_ASAP7_75t_R _3_ (.A(q[2]),
    .B(d[3]),
    .Y(n3));
 DFFHQNx1_ASAP7_75t_R q_reg_0_ (.CLK(clknet_1_0__leaf_clock),
    .D(n0),
    .QN(qn0));
 DFFHQNx1_ASAP7_75t_R q_reg_1_ (.CLK(clknet_1_0__leaf_clock),
    .D(n1),
    .QN(qn1));
 DFFHQNx1_ASAP7_75t_R q_reg_2_ (.CLK(clknet_1_0__leaf_clock),
    .D(n2),
    .QN(qn2));
 DFFHQNx1_ASAP7_75t_R q_reg_3_ (.CLK(clknet_1_0__leaf_clock),
    .D(n3),
    .QN(qn3));
 INVx1_ASAP7_75t_R _4_ (.A(qn0),
    .Y(q[0]));
 INVx1_ASAP7_75t_R _5_ (.A(qn1),
    .Y(q[1]));
 INVx1_ASAP7_75t_R _6_ (.A(qn2),
    .Y(q[2]));
 INVx1_ASAP7_75t_R _7_ (.A(qn3),
    .Y(q[3]));
 TIEHIx1_ASAP7_75t_R _8_ (.H(mode[1]));
 TIELOx1_ASAP7_75t_R _9_ (.L(mode[0]));
 INVx1_ASAP7_75t_R _r0_ (.A(reset),
    .Y(nreset));
 DFFHQNx1_ASAP7_75t_R rdy_reg (.CLK(clknet_1_0__leaf_clock),
    .D(nreset),
    .QN(rdyn));
 INVx1_ASAP7_75t_R _r1_ (.A(rdyn),
    .Y(rdyq));
 assign rdy = rdyq;
 INVx1_ASAP7_75t_R _10_ (.A(v),
    .Y(nv));
 AND2x2_ASAP7_75t_R _a0_ (.A(v),
    .B(data[0]),
    .Y(ta[0]));
 AND2x2_ASAP7_75t_R _b0_ (.A(nv),
    .B(acc[0]),
    .Y(tb[0]));
 OR2x2_ASAP7_75t_R _o0_ (.A(ta[0]),
    .B(tb[0]),
    .Y(na[0]));
 DFFHQNx1_ASAP7_75t_R acc_reg_0_ (.CLK(clknet_1_0__leaf_clock),
    .D(na[0]),
    .QN(aqn[0]));
 INVx1_ASAP7_75t_R _i0_ (.A(aqn[0]),
    .Y(acc[0]));
 AND2x2_ASAP7_75t_R _a1_ (.A(v),
    .B(data[1]),
    .Y(ta[1]));
 AND2x2_ASAP7_75t_R _b1_ (.A(nv),
    .B(acc[1]),
    .Y(tb[1]));
 OR2x2_ASAP7_75t_R _o1_ (.A(ta[1]),
    .B(tb[1]),
    .Y(na[1]));
 DFFHQNx1_ASAP7_75t_R acc_reg_1_ (.CLK(clknet_1_0__leaf_clock),
    .D(na[1]),
    .QN(aqn[1]));
 INVx1_ASAP7_75t_R _i1_ (.A(aqn[1]),
    .Y(acc[1]));
endmodule
