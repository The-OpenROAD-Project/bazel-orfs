// SPDX-License-Identifier: Apache-2.0
package clockgatefold

import chisel3._
import circt.stage.ChiselStage
import utility.ClockGate

/** Three of Utility's clock gates, in the shapes XiangShan has them.
  *
  * `always` is ExeUnit's for a CSR or fence unit: a WireInit enable that
  * ckAlwaysEn overrides with true.B, the test enable from genTeSink (a
  * dontTouch wire). `live` has a real enable. `off` has both enables false.
  */
class Fold extends Module {
  val io = IO(new Bundle {
    val en = Input(Bool())
    val d = Input(UInt(8.W))
    val always = Output(UInt(8.W))
    val live = Output(UInt(8.W))
  })
  val te = ClockGate.genTeSink
  val alwaysEn = WireInit(false.B)
  alwaysEn := io.en
  alwaysEn := true.B
  io.always := withClock(ClockGate(te.cgen, alwaysEn, clock))(RegNext(io.d))
  io.live := withClock(ClockGate(te.cgen, io.en, clock))(RegNext(io.d))
}

object Main extends App {
  ChiselStage.emitHWDialect(new Fold, Array(), args)
}
