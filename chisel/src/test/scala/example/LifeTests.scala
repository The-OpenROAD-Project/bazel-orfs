package example

import chisel3._
import chisel3.simulator.scalatest.ChiselSim
import chisel3.simulator.stimulus.{RunUntilFinished, RunUntilSuccess}
import chisel3.util.Counter
import org.scalatest.funspec.AnyFunSpec

class LifeTests extends AnyFunSpec with ChiselSim {
  describe("Baz") {
    it("counts to 42") {
      simulate(new LifeUniverse(42)) { foo =>
        foo.enable.poke(true.B)
        foo.clock.step(1)
        foo.out.expect(1.U)
        foo.clock.step(41)
        foo.out.expect(42.U)
      }
    }
  }
}
