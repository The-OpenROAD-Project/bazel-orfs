package example

import chisel3._
import circt.stage.ChiselStage
import chisel3.util._

class LifeUniverseTestBench() extends Module {
  val counter = Module(new LifeUniverse(43))
  counter.enable := true.B
  val done = IO(Output(Bool()))
  done := counter.out === 42.U
}
