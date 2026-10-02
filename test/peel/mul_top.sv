// The parent of the multiplier example: a 2 x 2 array of mul macros and
// the pipelined adder tree that sums their partial products, after
// test/estimation_ladder/multiplier_top.sv.
module mul_top #(
    parameter WIDTH = 64,
    parameter MW = 32
) (
    input  logic               clk,
    input  logic               rst,
    input  logic               valid_in,
    input  logic [WIDTH-1:0]   a,
    input  logic [WIDTH-1:0]   b,
    output logic               valid_out,
    output logic [2*WIDTH-1:0] product
);
  localparam N = WIDTH / MW;
  logic [2*MW-1:0] pp[N][N];
  logic vp[N][N];
  genvar i, j;
  generate
    for (i = 0; i < N; i++) begin : gen_i
      for (j = 0; j < N; j++) begin : gen_j
        mul u_mac (
            .clk(clk),
            .rst(rst),
            .valid_in(valid_in),
            .a(a[i*MW+:MW]),
            .b(b[j*MW+:MW]),
            .valid_out(vp[i][j]),
            .product(pp[i][j])
        );
      end
    end
  endgenerate

  logic [2*WIDTH-1:0] row_sum[N];
  always_comb begin
    for (int r = 0; r < N; r++) begin
      row_sum[r] = '0;
      for (int c = 0; c < N; c++) begin
        row_sum[r] = row_sum[r] + ({{(2 * WIDTH - 2 * MW) {1'b0}}, pp[r][c]} << ((r + c) * MW));
      end
    end
  end
  logic [2*WIDTH-1:0] stage1[N];
  logic v1;
  always_ff @(posedge clk) begin
    for (int r = 0; r < N; r++) stage1[r] <= row_sum[r];
  end
  logic [2*WIDTH-1:0] total;
  always_comb begin
    total = '0;
    for (int r = 0; r < N; r++) total = total + stage1[r];
  end
  always_ff @(posedge clk) product <= total;
  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      v1        <= 1'b0;
      valid_out <= 1'b0;
    end else begin
      v1        <= vp[0][0];
      valid_out <= v1;
    end
  end
endmodule
