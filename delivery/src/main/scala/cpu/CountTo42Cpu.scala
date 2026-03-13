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

object Opcode extends ChiselEnum {
  val LI, ADDI, BNE, HALT = Value
}

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
  // Encoding: {opcode[3:0], rd[4:0], rs1[4:0], imm[15:0]}
  val InsnWidth = 30
  def encode(op: Opcode.Type, rd: Int, rs1: Int, imm: UInt): UInt =
    Cat(op.asUInt.pad(4), rd.U(5.W), rs1.U(5.W), imm.pad(16))

  val program = VecInit(Seq(
    encode(Opcode.LI,   1, 0, 0.U),         // li  x1, 0
    encode(Opcode.LI,   2, 0, 42.U),        // li  x2, 42
    encode(Opcode.ADDI, 1, 1, 1.U),         // addi x1, x1, 1
    encode(Opcode.BNE,  1, 2, "hFFFF".U),   // bne x1, x2, -1
    encode(Opcode.HALT, 0, 0, 0.U),         // halt
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

  // --- Read register file ---
  val rs1Val = Mux(rs1 === 0.U, 0.U, regFile(rs1))

  // --- Execute ---
  val halted = RegInit(false.B)

  when(!halted) {
    switch(opcode) {
      is(Opcode.LI.asUInt) {
        when(rd =/= 0.U) {
          regFile(rd) := immSext
        }
        pc := pc + 1.U
      }
      is(Opcode.ADDI.asUInt) {
        when(rd =/= 0.U) {
          regFile(rd) := rs1Val + immSext
        }
        pc := pc + 1.U
      }
      is(Opcode.BNE.asUInt) {
        val cmpA = Mux(rd === 0.U, 0.U, regFile(rd))
        val cmpB = Mux(rs1 === 0.U, 0.U, regFile(rs1))
        when(cmpA =/= cmpB) {
          pc := (pc.asSInt + immSext(pc.getWidth - 1, 0).asSInt).asUInt
        }.otherwise {
          pc := pc + 1.U
        }
      }
      is(Opcode.HALT.asUInt) {
        halted := true.B
      }
    }
  }

  io.done   := halted
  io.result := regFile(1.U)
}
