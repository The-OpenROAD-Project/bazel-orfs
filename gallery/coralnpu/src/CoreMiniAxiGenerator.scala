package coralnpu.generator

import chisel3._
import circt.stage.ChiselStage
import coralnpu._

/** Generate FIRRTL for the CoreMiniAxi NPU core.
  *
  * Configuration matches upstream core_mini_axi_cc_library:
  *   - Scalar-only (no RVV), with floating-point
  *   - 8KB ITCM + 32KB DTCM
  *   - 128-bit fetch/LSU data bus
  *   - AXI interfaces
  */
object CoreMiniAxiGenerator extends App {
  val p = new Parameters(m = MemoryRegions.default)
  p.enableFetchL0 = false
  p.fetchDataBits = 128
  p.lsuDataBits = 128
  p.enableFloat = true

  ChiselStage.emitHWDialect(
    new CoreAxi(p, "CoreMini"),
    Array(),
    args
  )
}
