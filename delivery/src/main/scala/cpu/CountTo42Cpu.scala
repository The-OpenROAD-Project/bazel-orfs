package cpu

import chisel3._
import chisel3.util._

// Minimal RISC-V-like CPU that executes a hardcoded program:
//   li   x1, 0        # counter = 0
//   li   x2, 42       # target = 42
//   loop:
//     addi x1, x1, 1  # counter++
//     bne  x1, x2, loop
//   done: x1 == 42
//
// DataWidth is configurable (32 or 64) to demonstrate parameterized
// generation. The delivered SystemVerilog is fixed at 32 bits.

class CountTo42Cpu(val DataWidth: Int = 32) extends Module {
  require(DataWidth == 32 || DataWidth == 64, "DataWidth must be 32 or 64")

  val io = IO(new Bundle {
    val done    = Output(Bool())
    val result  = Output(UInt(DataWidth.W))
  })

  // --- Register file (x0-x31) ---
  val NumRegs = 32
  val regFile = RegInit(VecInit(Seq.fill(NumRegs)(0.U(DataWidth.W))))

  // --- Program ROM ---
  // Encoding: {opcode[3:0], rd[4:0], rs1[4:0], rs2_or_imm[15:0]}
  // Opcodes:
  //   0 = LI   rd, imm        (rd := imm)
  //   1 = ADDI rd, rs1, imm   (rd := rs1 + sext(imm))
  //   2 = BNE  rs1, rs2, imm  (if rs1 != rs2, pc += sext(imm))
  //   3 = HALT

  val InsnWidth = 30
  val program = VecInit(Seq(
    // 0: LI x1, 0
    Cat(0.U(4.W), 1.U(5.W), 0.U(5.W), 0.U(16.W)),
    // 1: LI x2, 42
    Cat(0.U(4.W), 2.U(5.W), 0.U(5.W), 42.U(16.W)),
    // 2: ADDI x1, x1, 1
    Cat(1.U(4.W), 1.U(5.W), 1.U(5.W), 1.U(16.W)),
    // 3: BNE x1, x2, -1 (jump back to instruction 2)
    Cat(2.U(4.W), 1.U(5.W), 2.U(5.W), "hFFFF".U(16.W)),
    // 4: HALT
    Cat(3.U(4.W), 0.U(5.W), 0.U(5.W), 0.U(16.W)),
  ))

  // --- Program counter ---
  val pc = RegInit(0.U(log2Ceil(program.length + 1).W))

  // --- Decode ---
  val insn   = program(pc)
  val opcode = insn(InsnWidth - 1, InsnWidth - 4)
  val rd     = insn(InsnWidth - 5, InsnWidth - 9)
  val rs1    = insn(InsnWidth - 10, InsnWidth - 14)
  val imm16  = insn(15, 0)

  // Sign-extend immediate to DataWidth
  val immSext = Wire(UInt(DataWidth.W))
  immSext := Cat(Fill(DataWidth - 16, imm16(15)), imm16)

  // rs2 field reuses the imm16 lower bits for BNE
  val rs2 = insn(InsnWidth - 10, InsnWidth - 14)

  // --- Read register file ---
  val rs1Val = Mux(rs1 === 0.U, 0.U, regFile(rs1))
  val rs2Idx = imm16(4, 0)
  // For BNE, rs2 is encoded in the rd field of the instruction format
  // Actually let's decode it properly: BNE uses rd as rs1, rs1 as rs2
  // Re-decode: for BNE, the two source registers are in rd and rs1 fields

  // --- Execute ---
  val halted = RegInit(false.B)

  when(!halted) {
    switch(opcode) {
      is(0.U) { // LI
        when(rd =/= 0.U) {
          regFile(rd) := immSext
        }
        pc := pc + 1.U
      }
      is(1.U) { // ADDI
        when(rd =/= 0.U) {
          regFile(rd) := rs1Val + immSext
        }
        pc := pc + 1.U
      }
      is(2.U) { // BNE rs1=rd field, rs2=rs1 field
        val cmpA = Mux(rd === 0.U, 0.U, regFile(rd))
        val cmpB = Mux(rs1 === 0.U, 0.U, regFile(rs1))
        when(cmpA =/= cmpB) {
          // PC-relative branch: imm is signed offset
          pc := (pc.asSInt + immSext(pc.getWidth - 1, 0).asSInt).asUInt
        }.otherwise {
          pc := pc + 1.U
        }
      }
      is(3.U) { // HALT
        halted := true.B
      }
    }
  }

  io.done   := halted
  io.result := regFile(1.U)
}
