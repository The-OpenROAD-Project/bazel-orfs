package cpu

import chisel3._

// Testbench wrapper for Verilator C++ harness.
// Exposes done/result at the top level with standard clock/reset.
class CountTo42CpuTestBench extends Module {
  val cpu = Module(new CountTo42Cpu(DataWidth = 32))
  val done   = IO(Output(Bool()))
  val result = IO(Output(UInt(32.W)))
  done   := cpu.io.done
  result := cpu.io.result
}
