package example

import chisel3._
import circt.stage.ChiselStage
import chisel3.util._


class LifeUniverse(MaxCount: Int) extends Module {
  val width = log2Ceil(MaxCount)
  val out = IO(Output(UInt(width.W)))
  val enable = IO(Input(Bool()))

  val cnt = RegInit(0.U(width.W))
  when(enable) {
    cnt := Mux(cnt < MaxCount.U, cnt + 1.U, 0.U)
  }
  out := cnt
}

