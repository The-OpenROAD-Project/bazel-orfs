import chisel3._
import circt.stage.ChiselStage
import chisel3.util._

class SimpleCounter(MaxCount: Int) extends Module {
  val width = log2Ceil(MaxCount)
  val out = IO(Output(UInt(width.W)))
  val enable = IO(Input(Bool()))

  val cnt = RegInit(0.U(width.W))
  when(enable) {
    cnt := Mux(cnt < MaxCount.U, cnt + 1.U, 0.U)
  }
  out := cnt
}

class Formal extends BlackBox {
  val io = IO(new Bundle {
    val clock = Input(Clock())
    val reset = Input(Bool())
    val cnt = Input(UInt(4.W))
    val fv = Output(UInt(4.W))
  })
  // FormalCounter.v is provided separately, we're just defining
  // the module interface in Chisel speak here.
}
