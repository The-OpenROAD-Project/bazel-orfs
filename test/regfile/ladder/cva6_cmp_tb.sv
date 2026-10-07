// cva6's ariane_regfile as ORFS has it (renamed ariane_regfile_orig)
// against the one SYNTH_VERILOG_SURGERY rewrites, with its register file
// as generate_regfile's netlist, both at cv32a65x's configuration: 32
// bits, four reads, two writes, x0 zero. The same interface as
// gen_tb.py's benches, for tb_main.cc; colliding writes are driven, and
// the later port must win on both sides.
module tb_top (
    input clk,
    input rst_act,
    input init_mode,
    input [4:0] init_addr,
    input [127:0] stim,
    output mismatch
);
  localparam config_pkg::cva6_cfg_t Cfg =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  logic [3:0][4:0] raddr;
  logic [1:0][4:0] waddr;
  logic [1:0][31:0] wdata;
  logic [1:0] we;
  assign raddr = stim[19:0];
  assign waddr = init_mode ? {stim[29:25], init_addr} : stim[29:20];
  assign wdata = stim[93:30];
  assign we = init_mode ? 2'b01 : stim[95:94];
  logic [3:0][31:0] rd_orig, rd_new;
  ariane_regfile_orig #(
      .CVA6Cfg(Cfg),
      .DATA_WIDTH(32),
      .NR_READ_PORTS(4),
      .ZERO_REG_ZERO(1)
  ) u_orig (
      .clk_i(clk),
      .rst_ni(~rst_act),
      .test_en_i(1'b0),
      .raddr_i(raddr),
      .rdata_o(rd_orig),
      .waddr_i(waddr),
      .wdata_i(wdata),
      .we_i(we)
  );
  ariane_regfile #(
      .CVA6Cfg(Cfg),
      .DATA_WIDTH(32),
      .NR_READ_PORTS(4),
      .ZERO_REG_ZERO(1)
  ) u_new (
      .clk_i(clk),
      .rst_ni(~rst_act),
      .test_en_i(1'b0),
      .raddr_i(raddr),
      .rdata_o(rd_new),
      .waddr_i(waddr),
      .wdata_i(wdata),
      .we_i(we)
  );
  assign mismatch = rd_orig != rd_new;
  // The first few mismatches, both sides, for the log.
  int shown = 0;
  always @(posedge clk) begin
    if (mismatch && shown < 3) begin
      shown <= shown + 1;
      $display("raddr %h orig %h new %h we %b waddr %h", raddr, rd_orig, rd_new, we, waddr);
    end
  end
endmodule
