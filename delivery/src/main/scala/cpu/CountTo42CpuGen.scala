package cpu

import chisel3._
import circt.stage.ChiselStage

// Standalone generator for CountTo42Cpu (without testbench wrapper).
// Used to produce the gold reference Verilog for LEC.
object CountTo42CpuGen extends App {
  ChiselStage.emitHWDialect(
    new CountTo42Cpu(DataWidth = 32),
    Array(),
    args
  )
}
