package gemmini.generator

import chisel3._
import circt.stage.ChiselStage
import gemmini._

class DemoTag8x8 extends Bundle with TagQueueTag {
  val bits = UInt(8.W)
  def make_this_garbage(dummy: Int = 0): Unit = { bits := 0.U }
}

/** Generate FIRRTL for an 8x8 INT8 MeshWithDelays systolic array (64 PEs). */
object Gemmini8x8Generator extends App {
  ChiselStage.emitHWDialect(
    new MeshWithDelays(
      inputType = SInt(8.W), weightType = SInt(8.W),
      outputType = SInt(32.W), accType = SInt(32.W),
      tagType = new DemoTag8x8, df = Dataflow.BOTH,
      tree_reduction = true, tile_latency = 1, output_delay = 1,
      tileRows = 1, tileColumns = 1,
      meshRows = 8, meshColumns = 8,
      leftBanks = 8, upBanks = 8, outBanks = 8,
      n_simultaneous_matmuls = -1
    )(Arithmetic.SIntArithmetic), Array(), args)
}
