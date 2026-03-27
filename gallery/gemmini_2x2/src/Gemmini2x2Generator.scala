package gemmini.generator

import chisel3._
import circt.stage.ChiselStage
import gemmini._

/** A minimal tag type that satisfies TagQueueTag. */
class DemoTag2x2 extends Bundle with TagQueueTag {
  val bits = UInt(8.W)
  def make_this_garbage(dummy: Int = 0): Unit = {
    bits := 0.U
  }
}

/** Generate FIRRTL for a 2x2 INT8 MeshWithDelays systolic array.
  *
  * Minimal configuration (4 PEs) for minutes-scale turnaround.
  */
object Gemmini2x2Generator extends App {
  ChiselStage.emitHWDialect(
    new MeshWithDelays(
      inputType = SInt(8.W),
      weightType = SInt(8.W),
      outputType = SInt(32.W),
      accType = SInt(32.W),
      tagType = new DemoTag2x2,
      df = Dataflow.BOTH,
      tree_reduction = true,
      tile_latency = 1,
      output_delay = 1,
      tileRows = 1,
      tileColumns = 1,
      meshRows = 2,
      meshColumns = 2,
      leftBanks = 2,
      upBanks = 2,
      outBanks = 2,
      n_simultaneous_matmuls = -1
    )(Arithmetic.SIntArithmetic),
    Array(),
    args
  )
}
