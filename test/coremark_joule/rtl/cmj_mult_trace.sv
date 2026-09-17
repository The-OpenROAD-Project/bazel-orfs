/* Record what ibex's multiplier is asked to do, from the RTL simulation.
 *
 * The glitch measurement (5.2) cannot drive a whole core: annotating
 * its combinational cells stops it executing, and an event-driven gate
 * simulation of ibex runs at 50 cycles per second, so reaching the
 * cycles where CoreMark multiplies costs hours before anything is
 * measured. The multiplier can be driven on its own -- it is a
 * preserved module boundary of 3,199 cells -- but only if something
 * supplies the operands it would really have seen.
 *
 * This is that something. Verilator on the RTL covers a whole CoreMark
 * iteration in minutes, so the operand stream is taken there and
 * replayed into the extracted module.
 *
 * `bind` rather than an edit: ibex is vendored, and a monitor attached
 * from outside cannot change what it observes. It is also inert unless
 * +multtrace=<path> is given, so the simulator that measures cycles and
 * checks CRCs is unaffected.
 *
 * Every cycle is recorded, not only the multiplying ones. An idle
 * multiplier still sees its operand buses change -- they are driven from
 * the ALU's operands whether or not a multiply was issued -- and
 * whether that idle toggling glitches is the question that decides
 * whether multiplier glitch power grows with a core's performance or
 * stays flat.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
module cmj_mult_trace (
    input logic        clk_i,
    input logic        rst_ni,
    input logic        mult_en_i,
    input logic        div_en_i,
    input logic        mult_sel_i,
    input logic        div_sel_i,
    input logic [ 1:0] operator_i,
    input logic [ 1:0] signed_mode_i,
    input logic [31:0] op_a_i,
    input logic [31:0] op_b_i,
    input logic [33:0] alu_adder_ext_i,
    input logic [31:0] alu_adder_i,
    input logic        equal_to_zero_i,
    input logic        data_ind_timing_i,
    input logic [33:0] imd_val_q_0_i,
    input logic [33:0] imd_val_q_1_i,
    input logic        multdiv_ready_id_i
);
  int unsigned cyc = 0, first = 0, last = 0;
  int fd = 0;
  string path;

  /* A window, because the whole run is 16 MB of operands and the
   * measurement only needs cycles the multiplier is alive in. The
   * trace itself is what says where those are: on ibex running
   * CoreMark, the first multiply is at cycle 69,243. */
  initial begin
    if ($value$plusargs("multtrace=%s", path)) begin
      void'($value$plusargs("multtrace_first=%d", first));
      void'($value$plusargs("multtrace_last=%d", last));
      fd = $fopen(path, "w");
      $fwrite(fd, "# cycle en(mult,div,msel,dsel,eqz,dit) operator signed_mode");
      $fwrite(fd, " op_a op_b alu_adder_ext alu_adder imd0 imd1\n");
    end
  end

  /* Every input the module has, because the replay has to reproduce
   * what it saw and this unit is not self-contained: it borrows the
   * ALU's adder (alu_adder_i, alu_adder_ext_i) and carries its partial
   * products in registers outside itself (imd_val_q). Tracing only the
   * operands would leave the replay to invent the rest. */
  always @(posedge clk_i) begin
    if (rst_ni) cyc <= cyc + 1;
    if (fd != 0 && rst_ni && cyc >= first && (last == 0 || cyc <= last))
      $fwrite(fd, "%0d %0d%0d%0d%0d%0d%0d %0d %0d %08h %08h %09h %08h %09h %09h\n",
              cyc, mult_en_i, div_en_i, mult_sel_i, div_sel_i,
              equal_to_zero_i, data_ind_timing_i,
              operator_i, signed_mode_i, op_a_i, op_b_i,
              alu_adder_ext_i, alu_adder_i, imd_val_q_0_i, imd_val_q_1_i);
  end

  final if (fd != 0) $fclose(fd);
endmodule

bind ibex_multdiv_fast cmj_mult_trace u_cmj_mult_trace (
    .clk_i             (clk_i),
    .rst_ni            (rst_ni),
    .mult_en_i         (mult_en_i),
    .div_en_i          (div_en_i),
    .mult_sel_i        (mult_sel_i),
    .div_sel_i         (div_sel_i),
    .operator_i        (operator_i),
    .signed_mode_i     (signed_mode_i),
    .op_a_i            (op_a_i),
    .op_b_i            (op_b_i),
    .alu_adder_ext_i   (alu_adder_ext_i),
    .alu_adder_i       (alu_adder_i),
    .equal_to_zero_i   (equal_to_zero_i),
    .data_ind_timing_i (data_ind_timing_i),
    .imd_val_q_0_i     (imd_val_q_i[0]),
    .imd_val_q_1_i     (imd_val_q_i[1]),
    .multdiv_ready_id_i(multdiv_ready_id_i)
);
