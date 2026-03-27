package gemmini.generator

import chisel3._
import circt.stage.ChiselStage
import gemmini._

/** A minimal tag type that satisfies TagQueueTag. */
class DemoTag extends Bundle with TagQueueTag {
  val bits = UInt(8.W)
  def make_this_garbage(dummy: Int = 0): Unit = {
    bits := 0.U
  }
}

/** Generate FIRRTL for a 16x16 INT8 MeshWithDelays systolic array. */
object GemminiGenerator extends App {
  ChiselStage.emitHWDialect(
    new MeshWithDelays(
      inputType = SInt(8.W),
      weightType = SInt(8.W),
      outputType = SInt(32.W),
      accType = SInt(32.W),
      tagType = new DemoTag,
      df = Dataflow.BOTH,
      tree_reduction = true,
      tile_latency = 1,
      output_delay = 1,
      tileRows = 1,
      tileColumns = 1,
      meshRows = 16,
      meshColumns = 16,
      leftBanks = 16,
      upBanks = 16,
      outBanks = 16,
      n_simultaneous_matmuls = 16
    )(Arithmetic.SIntArithmetic),
    Array(),
    args
  )
}
