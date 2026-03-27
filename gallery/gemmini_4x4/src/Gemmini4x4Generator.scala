package gemmini.generator

import chisel3._
import circt.stage.ChiselStage
import gemmini._

/** A minimal tag type that satisfies TagQueueTag. */
class DemoTag4x4 extends Bundle with TagQueueTag {
  val bits = UInt(8.W)
  def make_this_garbage(dummy: Int = 0): Unit = {
    bits := 0.U
  }
}

/** Generate FIRRTL for a 4x4 INT8 MeshWithDelays systolic array.
  *
  * Small configuration of the Gemmini systolic array (16 PEs vs 256 in 16x16).
  * Sized to complete the full RTL-to-GDS flow on a 30 GB machine.
  */
object Gemmini4x4Generator extends App {
  ChiselStage.emitHWDialect(
    new MeshWithDelays(
      inputType = SInt(8.W),
      weightType = SInt(8.W),
      outputType = SInt(32.W),
      accType = SInt(32.W),
      tagType = new DemoTag4x4,
      df = Dataflow.BOTH,
      tree_reduction = true,
      tile_latency = 1,
      output_delay = 1,
      tileRows = 1,
      tileColumns = 1,
      meshRows = 4,
      meshColumns = 4,
      leftBanks = 4,
      upBanks = 4,
      outBanks = 4,
      n_simultaneous_matmuls = -1  // auto-compute from latency (requires >= 5 * latency_per_pe)
    )(Arithmetic.SIntArithmetic),
    Array(),
    args
  )
}
