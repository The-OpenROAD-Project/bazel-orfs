// RegVecFile.read's hard stop, from XiangShan patch 0002: a read under a
// when connects the read port's address conditionally, a mux ahead of
// the read that upstream's vec(idx) does not have, so read() refuses to
// be called there. Elaborated twice: the read ahead of the when, as the
// Ftq's train read is, must elaborate; the same read inside an elsewhen,
// as the train read was, must stop with the module and the port named.
package ftqlec

import chisel3._
import circt.stage.ChiselStage
import utils.RegVecFile

class Reader(underWhen: Boolean) extends Module {
  val io = IO(new Bundle {
    val flush = Input(Bool())
    val fire = Input(Bool())
    val idx = Input(UInt(3.W))
    val data = Output(UInt(4.W))
  })
  val rf = Module(new RegVecFile(UInt(4.W), 8, numRead = 1, numWrite = 1, "TrainMeta"))
  rf.idle()
  val captured = RegInit(0.U(4.W))
  io.data := captured
  if (underWhen) {
    when(io.flush) {
      captured := 0.U
    }.elsewhen(io.fire) {
      captured := rf.read(0, io.idx)
    }
  } else {
    val meta = rf.read(0, io.idx)
    when(io.flush) {
      captured := 0.U
    }.elsewhen(io.fire) {
      captured := meta
    }
  }
}

object Main extends App {
  ChiselStage.emitCHIRRTL(new Reader(underWhen = false))
  println("ReadUnderWhen: the read ahead of the when elaborates")
  val stop =
    try {
      ChiselStage.emitCHIRRTL(new Reader(underWhen = true))
      None
    } catch {
      case e: Throwable =>
        Some(
          Iterator
            .iterate[Throwable](e)(_.getCause)
            .takeWhile(_ != null)
            .map(t => String.valueOf(t.getMessage))
            .mkString(" | ")
        )
    }
  stop match {
    case Some(m) if m.contains("TrainMeta.read(0) under a when") =>
      println("ReadUnderWhen: the read under the when stops: " + m)
    case Some(m) =>
      println("ReadUnderWhen: the read under the when stopped for another reason: " + m)
      sys.exit(1)
    case None =>
      println("ReadUnderWhen: the read under the when elaborated")
      sys.exit(1)
  }
}
