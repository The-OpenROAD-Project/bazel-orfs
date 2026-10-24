// tpu in its rig against tpu alone: one stream into both, with bubbles
// anywhere, weight loads and activation rows alike, and the results
// compared row by row, in order. Also how full the FIFOs ever get: a
// write into a full one would lose a word, and the rig has no
// back-pressure to prevent it.
//
// The stream: SETS times, a weight load of N rows, ROWS rows of A, then
// enough quiet cycles for the array to drain; each cycle of a phase is a
// bubble with probability 1/4. Values from a 32-bit LFSR, every bit
// used.
module tpu_meso_tb #(
    parameter int N    = 8,
    parameter int DW   = 8,
    parameter int ACCW = 32,
    parameter int SETS = 4,
    parameter int ROWS = 24
) (
    input  logic        clk,
    output logic        done,
    output int unsigned errors,
    output int unsigned compared,
    output int unsigned nonzero,
    output int unsigned overflows,
    output int unsigned max_fill
);
  logic [31:0] lfsr = 32'h1234_5678;
  function automatic logic [31:0] step(input logic [31:0] s);
    return {s[30:0], s[31] ^ s[21] ^ s[1] ^ s[0]};
  endfunction

  logic rst;
  logic w_valid, a_valid;
  logic [N*DW-1:0] w_data, a_data;
  logic r_c_valid, d_c_valid;
  logic [N*ACCW-1:0] r_c_data, d_c_data;

  tpu #(
      .N(N),
      .DW(DW),
      .ACCW(ACCW)
  ) u_ref (
      .clk(clk),
      .rst(rst),
      .w_valid(w_valid),
      .w_data(w_data),
      .a_valid(a_valid),
      .a_data(a_data),
      .c_valid(r_c_valid),
      .c_data(r_c_data)
  );

  tpu_meso #(
      .N(N),
      .DW(DW),
      .ACCW(ACCW)
  ) u_dut (
      .clk(clk),
      .rst(rst),
      .w_valid(w_valid),
      .w_data(w_data),
      .a_valid(a_valid),
      .a_data(a_data),
      .c_valid(d_c_valid),
      .c_data(d_c_data)
  );

  // The stream.
  typedef enum logic [1:0] {
    RESET,
    LOAD,
    STREAM,
    DRAIN
  } phase_t;
  phase_t phase = RESET;
  int unsigned count = 0;
  int unsigned set = 0;
  logic bubble;
  assign bubble = lfsr[31:30] == 2'b00;
  logic [2*N*DW-1:0] noise;
  always_comb begin
    noise = '0;
    for (int k = 0; k < 2 * N * DW; k += 32) noise[k+:32] = lfsr ^ (32'(k) * 32'h9e37_79b9);
  end

  always_comb begin
    rst = phase == RESET;
    w_valid = phase == LOAD && !bubble;
    a_valid = phase == STREAM && !bubble;
    w_data = noise[N*DW-1:0];
    a_data = noise[2*N*DW-1:N*DW];
  end

  always_ff @(posedge clk) begin
    lfsr <= step(lfsr);
    case (phase)
      RESET:
      if (count == 4) begin
        phase <= LOAD;
        count <= 0;
      end else count <= count + 1;
      LOAD:
      if (w_valid && count == N - 1) begin
        phase <= STREAM;
        count <= 0;
      end else if (w_valid) count <= count + 1;
      STREAM:
      if (a_valid && count == ROWS - 1) begin
        phase <= DRAIN;
        count <= 0;
      end else if (a_valid) count <= count + 1;
      DRAIN:
      if (count == 4 * N + 16) begin
        set <= set + 1;
        // after the last set, quiet for good
        if (set + 1 < SETS) phase <= LOAD;
        count <= 0;
      end else if (set < SETS) count <= count + 1;
    endcase
  end
  assign done = set == SETS;

  // The scoreboard: tpu's results in order, the rig's checked against
  // them.
  logic [N*ACCW-1:0] expected[$];
  // in the pointers' own width, lap bit included
  logic [$bits(u_dut.u_in.widx)-1:0] fill_in, fill_out;
  assign fill_in = u_dut.u_in.widx - u_dut.u_in.ridx;
  assign fill_out = u_dut.u_out.widx - u_dut.u_out.ridx;
  initial begin
    errors = 0;
    compared = 0;
    nonzero = 0;
    overflows = 0;
    max_fill = 0;
  end
  always_ff @(posedge clk) begin
    if (r_c_valid) expected.push_back(r_c_data);
    if (d_c_valid) begin
      if (expected.size() == 0 || expected[0] != d_c_data) errors <= errors + 1;
      if (expected.size() != 0) void'(expected.pop_front());
      compared <= compared + 1;
      if (d_c_data != '0) nonzero <= nonzero + 1;
    end
    if (u_dut.u_in.overflow || u_dut.u_out.overflow) overflows <= overflows + 1;
    if (32'(fill_in) > max_fill) max_fill <= 32'(fill_in);
    if (32'(fill_out) > max_fill) max_fill <= 32'(fill_out);
  end
endmodule
