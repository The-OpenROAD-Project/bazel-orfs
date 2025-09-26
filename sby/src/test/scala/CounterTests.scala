import chisel3._
import circt.stage.ChiselStage
import chisel3.util._

class TestCounter() extends Module {
  val MaxCount = 10
  val counter = Module(new SimpleCounter(MaxCount))
  counter.enable := true.B
  val formal = Module(new Formal)
  formal.io.clock := clock
  formal.io.reset := reset
  formal.io.cnt := counter.out
}

object CodeGen extends App {
  val constructor = Class.forName(args(0)).getConstructors().head

  ChiselStage.emitHWDialect(
    constructor.newInstance().asInstanceOf[chisel3.RawModule],
    // chisel args
    args = Array(),
    firtoolOpts = args.drop(1)
  )
}
