// The simulation SoC for the CoreMark-per-Joule study.
//
// XSTop brings its memory and peripheral AXI out as top-level Verilog ports
// unconditionally -- `val memory = InModuleBody { memAXI4SlaveNode.makeIOs() }`
// -- so nothing can be attached to those nodes from outside, and every
// upstream flow ties them off in a testbench. This is that testbench, in
// Chisel rather than SystemVerilog, so the AXI protocol on both ports stays
// XiangShan's own verified code and the only thing written here is wiring
// and two registers.
//
// Nothing in this file is synthesised. The study hardens XSCore, which
// firtool emits as its own module; everything here exists so that XSCore can
// run CoreMark and be measured while it does.

package coremark_joule.xiangshan

import chisel3._
import chisel3.experimental.dataview._
import device.{AXI4Memory, AXI4SlaveModule, AXI4SlaveModuleImp}
import freechips.rocketchip.amba.axi4._
import freechips.rocketchip.diplomacy.{AddressSet, IdRange, InModuleBody, LazyModule, LazyModuleImp}
import org.chipsalliance.cde.config.Parameters
import top.XSTop
import utility.MaskExpand

/** The two memory-mapped words that are the whole bare-metal contract.
  *
  * Identical to the contract the study's other three cores answer to, at the
  * same address, which is not a coincidence worth losing: XiangShan's default
  * PMA marks the region at 0x1000_0000 accessible, writable and uncached, and
  * no on-chip device claims it, so it routes out the peripheral AXI port.
  * One C runtime and one output checker therefore serve all four cores.
  */
class CmjCtrlIO extends Bundle {
  val putchar_valid = Output(Bool())
  val putchar_data = Output(UInt(8.W))
  val halt = Output(Bool())
}

class CmjCtrl(address: Seq[AddressSet])(implicit p: Parameters)
    extends AXI4SlaveModule(address, executable = false, beatBytes = 8, _extra = new CmjCtrlIO) {
  override lazy val module = new AXI4SlaveModuleImp[CmjCtrlIO](this) {
    val ctrl = io.extra.get

    // Writes only, and side effects rather than state: the harness watches
    // these two wires, exactly as it watches the sim-control device on the
    // other three cores.
    val write = in.w.fire
    val offset = waddr(15, 0)
    ctrl.putchar_valid := write && offset === 0x0.U
    ctrl.putchar_data := in.w.bits.data(7, 0)
    ctrl.halt := write && offset === 0x8.U && in.w.bits.data(0)

    // Reads return zero. Nothing in the port reads this device.
    in.r.bits.data := 0.U
  }
}

/** Memory, with its storage in the harness.
  *
  * device.AXI4Memory is XiangShan's own AXI4 slave, and its array is a
  * DifftestMem -- an ExtModule whose reads and writes are DPI calls. So the
  * AXI protocol is upstream's, the storage is ours in C++, and neither
  * appears in any netlist.
  */
class CmjMemory(base: Long, sizeBytes: Long, beatBytes: Int, idBits: Int, burstLen: Int)(
    implicit p: Parameters
) extends LazyModule {
  val master = AXI4MasterNode(
    Seq(
      AXI4MasterPortParameters(
        masters = Seq(AXI4MasterParameters(name = "cmj_mem", id = IdRange(0, 1 << idBits)))
      )
    )
  )

  val ram = LazyModule(
    new AXI4Memory(
      address = Seq(AddressSet(base, sizeBytes - 1)),
      memByte = sizeBytes,
      useBlackBox = false,
      executable = true,
      beatBytes = beatBytes,
      burstLen = burstLen
    )
  )
  ram.node := master

  val io_axi4 = InModuleBody { master.makeIOs() }

  lazy val module = new LazyModuleImp(this) {}
}

/** The control device, wrapped so its AXI can be driven from outside. */
class CmjCtrlWrapper(address: Seq[AddressSet], beatBytes: Int, idBits: Int)(implicit
    p: Parameters
) extends LazyModule {
  val master = AXI4MasterNode(
    Seq(
      AXI4MasterPortParameters(
        masters = Seq(AXI4MasterParameters(name = "cmj_ctrl", id = IdRange(0, 1 << idBits)))
      )
    )
  )

  val dev = LazyModule(new CmjCtrl(address))
  dev.node := master

  val io_axi4 = InModuleBody { master.makeIOs() }
  val io_ctrl = InModuleBody {
    val port = IO(new CmjCtrlIO)
    port.suggestName("ctrl")
    port
  }

  lazy val module = new LazyModuleImp(this) {
    io_ctrl <> dev.module.io.extra.get
  }
}

/** XSTop with memory and a control device attached, and everything else
  * tied off.
  *
  * The only ports are a clock, a reset and the two wires the harness
  * watches. Everything the SoC needs to come out of reset -- interrupts,
  * JTAG, the PMA check port, the reset vector -- is driven here.
  */
class CoreMarkJouleSoC(bootAddr: Long, memBase: Long, memBytes: Long)(implicit p: Parameters)
    extends LazyModule {
  val soc = LazyModule(new XSTop())

  // Widths come from XSTop's own ports rather than from constants: memory is
  // 256-bit with 14-bit ids, peripheral is 64-bit with 2-bit ids, and both
  // are decided by elaboration.
  val mem = LazyModule(
    new CmjMemory(memBase, memBytes, beatBytes = 32, idBits = 14, burstLen = 2)
  )
  val ctrl = LazyModule(
    new CmjCtrlWrapper(Seq(AddressSet(0x10000000L, 0xfff)), beatBytes = 8, idBits = 2)
  )

  lazy val module = new LazyModuleImp(this) {
    val cmj = IO(new CmjCtrlIO)

    val socMod = soc.module
    socMod.io.clock := clock
    socMod.io.reset := reset.asAsyncReset

    mem.io_axi4.head <> socMod.memory.viewAs[AXI4Bundle]
    ctrl.io_axi4.head <> socMod.peripheral.viewAs[AXI4Bundle]
    cmj <> ctrl.io_ctrl

    // Boot address. XiangShan takes it as an input rather than from a
    // bootrom, so the study's image needs no first-stage loader.
    socMod.io.riscv_rst_vec.foreach(_ := bootAddr.U)

    // Non-maskable interrupts and the IMSIC's AXI slave port are separate
    // IOs on XSTop rather than members of io, and firtool refuses a sink it
    // cannot see driven, so both are tied off explicitly.
    soc.nmi.foreach(_ := 0.U.asTypeOf(chiselTypeOf(soc.nmi.head)))

    // The IMSIC's AXI slave port is driven by a platform interrupt
    // controller that this testbench does not have. Idle it: no requests,
    // no responses accepted.
    socMod.imsic_axi4.foreach { port =>
      val axi = port.viewAs[AXI4Bundle]
      axi.aw.valid := false.B
      axi.aw.bits := DontCare
      axi.w.valid := false.B
      axi.w.bits := DontCare
      axi.b.ready := false.B
      axi.ar.valid := false.B
      axi.ar.bits := DontCare
      axi.r.ready := false.B
    }

    socMod.io.sram_config := 0.U
    socMod.io.extIntrs := 0.U
    socMod.io.pll0_lock := true.B
    socMod.io.rtc_clock := clock

    socMod.io.systemjtag.jtag.TCK := false.B.asClock
    socMod.io.systemjtag.jtag.TMS := false.B
    socMod.io.systemjtag.jtag.TDI := false.B
    socMod.io.systemjtag.reset := true.B.asAsyncReset
    socMod.io.systemjtag.mfr_id := 0.U
    socMod.io.systemjtag.part_number := 0.U
    socMod.io.systemjtag.version := 0.U

    socMod.io.cacheable_check.req.foreach { r =>
      r.valid := false.B
      r.bits := 0.U.asTypeOf(r.bits)
    }

    socMod.io.traceCoreInterface.foreach { t =>
      t.fromEncoder.enable := false.B
      t.fromEncoder.stall := false.B
    }
  }
}

object CoreMarkJouleSoCGenerator extends App {
  XSCoreGeneratorBase.emitSoC(new CoreMarkJouleConfig(1), args)
}

object CoreMarkJouleSoCGeneratorMinimal extends App {
  XSCoreGeneratorBase.emitSoC(new CoreMarkJouleMinimalConfig(1), args)
}
