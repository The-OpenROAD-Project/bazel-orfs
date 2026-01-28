// A file to synthesize and clean up:
//
// - unused port

module foo (
  input  logic       clock,
  input  logic       rst_n,
  input  logic [7:0] used_data,
  input  logic [7:0] unused_data, // <--- The specific target for cleanup
  output logic [7:0] dout
);

  always_ff @(posedge clock or negedge rst_n) begin
    if (!rst_n) begin
      dout <= 8'h0;
    end else begin
      // 'unused_data' is never referenced here
      dout <= used_data;
    end
  end

endmodule

module dirty (
  input  logic       clock,
  input  logic       rst_n,
  input  logic [8:0] a,
  output logic [7:0] result
);


  logic [7:0] dout_next;

  foo u_foo (
    .clock        (clock),
    .rst_n        (rst_n),
    .used_data    (a),
    .unused_data  (8'h0),
    .dout         (dout_next)
  );

  always_ff @(posedge clock or negedge rst_n) begin
    if (!rst_n) begin
      result <= 8'h0;
    end else begin
      result <= dout_next;
    end
  end

endmodule

