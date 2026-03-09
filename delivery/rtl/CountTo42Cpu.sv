// CountTo42Cpu — idiomatic SystemVerilog rewrite
//
// This file is the production deliverable: a 32-bit-fixed, verification-friendly
// SystemVerilog rewrite of the Chisel-generated Verilog. It is verified against
// the generator output via LEC (kepler-formal / eqy).
//
// Design: minimal RISC-V-like CPU executing a hardcoded program that counts to 42.
//   li   x1, 0
//   li   x2, 42
//   loop: addi x1, x1, 1
//         bne  x1, x2, loop
//   halt
//
// Conventions:
//   - always_ff / always_comb (no always @*)
//   - logic instead of reg/wire
//   - Explicit reset (synchronous, active-high, matching Chisel convention)
//   - Named types for instruction fields
//   - No packed arrays (Verilator/slang compatible)

module CountTo42Cpu(
  input  logic        clock,
  input  logic        reset,
  output logic        io_done,
  output logic [31:0] io_result
);

  // --- Instruction encoding types ---
  localparam int unsigned DATA_WIDTH  = 32;
  localparam int unsigned NUM_REGS    = 32;
  localparam int unsigned PROG_LEN    = 5;
  localparam int unsigned PC_WIDTH    = 3;  // ceil(log2(PROG_LEN + 1))
  localparam int unsigned INSN_WIDTH  = 30;

  // Opcodes
  localparam logic [3:0] OP_LI   = 4'd0;
  localparam logic [3:0] OP_ADDI = 4'd1;
  localparam logic [3:0] OP_BNE  = 4'd2;
  localparam logic [3:0] OP_HALT = 4'd3;

  // --- Program ROM ---
  // Format: {opcode[3:0], rd[4:0], rs1[4:0], imm[15:0]}
  logic [INSN_WIDTH-1:0] program_rom [PROG_LEN];
  assign program_rom[0] = {OP_LI,   5'd1, 5'd0, 16'd0};     // li  x1, 0
  assign program_rom[1] = {OP_LI,   5'd2, 5'd0, 16'd42};    // li  x2, 42
  assign program_rom[2] = {OP_ADDI, 5'd1, 5'd1, 16'd1};     // addi x1, x1, 1
  assign program_rom[3] = {OP_BNE,  5'd1, 5'd2, 16'hFFFF};  // bne x1, x2, -1
  assign program_rom[4] = {OP_HALT, 5'd0, 5'd0, 16'd0};     // halt

  // --- State ---
  logic [DATA_WIDTH-1:0] reg_file [NUM_REGS];
  logic [PC_WIDTH-1:0]   pc;
  logic                   halted;

  // --- Decode (combinational) ---
  logic [INSN_WIDTH-1:0] insn;
  logic [3:0]            opcode;
  logic [4:0]            rd;
  logic [4:0]            rs1;
  logic [15:0]           imm16;
  logic [DATA_WIDTH-1:0] imm_sext;
  logic [DATA_WIDTH-1:0] rs1_val;

  always_comb begin
    insn     = program_rom[pc];
    opcode   = insn[INSN_WIDTH-1 -: 4];
    rd       = insn[INSN_WIDTH-5 -: 5];
    rs1      = insn[INSN_WIDTH-10 -: 5];
    imm16    = insn[15:0];
    imm_sext = {{(DATA_WIDTH - 16){imm16[15]}}, imm16};
    rs1_val  = (rs1 == 5'd0) ? {DATA_WIDTH{1'b0}} : reg_file[rs1];
  end

  // --- Execute (sequential) ---
  always_ff @(posedge clock) begin
    if (reset) begin
      pc     <= {PC_WIDTH{1'b0}};
      halted <= 1'b0;
      for (int unsigned i = 0; i < NUM_REGS; i++) begin
        reg_file[i] <= {DATA_WIDTH{1'b0}};
      end
    end else if (!halted) begin
      unique case (opcode)
        OP_LI: begin
          if (rd != 5'd0)
            reg_file[rd] <= imm_sext;
          pc <= pc + PC_WIDTH'(1);
        end
        OP_ADDI: begin
          if (rd != 5'd0)
            reg_file[rd] <= rs1_val + imm_sext;
          pc <= pc + PC_WIDTH'(1);
        end
        OP_BNE: begin
          // rd and rs1 fields hold the two source registers
          if (((rd == 5'd0)  ? {DATA_WIDTH{1'b0}} : reg_file[rd]) !=
              ((rs1 == 5'd0) ? {DATA_WIDTH{1'b0}} : reg_file[rs1])) begin
            pc <= PC_WIDTH'($signed({1'b0, pc}) + $signed(imm_sext[PC_WIDTH-1:0]));
          end else begin
            pc <= pc + PC_WIDTH'(1);
          end
        end
        OP_HALT: begin
          halted <= 1'b1;
        end
        default: begin
          pc <= pc + PC_WIDTH'(1);
        end
      endcase
    end
  end

  // --- Outputs ---
  assign io_done   = halted;
  assign io_result = reg_file[1];

endmodule
