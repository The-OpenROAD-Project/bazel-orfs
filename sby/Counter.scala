import chisel3._
import circt.stage.ChiselStage
import chisel3.util._

class TestCounter() extends Module {
  val MaxCount = 10
  val counter = Module(new Counter(MaxCount))
  counter.enable := true.B
  val formal = Module(new Formal)
  formal.io.clock := clock
  formal.io.reset := reset
  formal.io.cnt := counter.out
}

class Counter(MaxCount: Int) extends Module {
  val width = log2Ceil(MaxCount)
  val out = IO(Output(UInt(width.W)))
  val enable = IO(Input(Bool()))

  val cnt = RegInit(0.U(width.W))
  when(enable) {
    cnt := Mux(cnt < MaxCount.U, cnt + 1.U, 0.U)
  }
  out := cnt
}

class Formal extends BlackBox with HasBlackBoxResource {
  val io = IO(new Bundle {
    val clock = Input(Clock())
    val reset = Input(Bool())
    val cnt = Input(UInt(4.W))
    val fv = Output(UInt(4.W))
  })
  addResource("/FormalCounter.v")
}

object CodeGen extends App {
  val constructor = Class.forName(args(0)).getConstructors().head

println(
    ChiselStage.emitSystemVerilog(
      gen = new TestCounter(),
      firtoolOpts = Array(
        "-disable-all-randomization",
        "-strip-debug-info",
        "-enable-layers=Verification",
        "-enable-layers=Verification.Assert",
        "-enable-layers=Verification.Assume",
        "-enable-layers=Verification.Cover"
      )
    )
  )

  println("firtool: " + args.drop(1).mkString(" "))

  ChiselStage.emitHWDialect(
    constructor.newInstance().asInstanceOf[chisel3.RawModule],
    // chisel args
    args = Array(),
    firtoolOpts = args.drop(1)
  )
}
