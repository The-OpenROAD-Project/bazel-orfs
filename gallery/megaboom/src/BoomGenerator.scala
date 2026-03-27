package megaboom.generator

import chisel3._
import circt.stage.ChiselStage
import org.chipsalliance.cde.config._
import freechips.rocketchip.subsystem._
import freechips.rocketchip.devices.tilelink._
import freechips.rocketchip.diplomacy._
import freechips.rocketchip.prci._
import freechips.rocketchip.rocket._
import freechips.rocketchip.tilelink._
import freechips.rocketchip.tile._
import freechips.rocketchip.util._
import freechips.rocketchip.interrupts._
import freechips.rocketchip.resources.BindingScope
import boom.v4.common._

/** Minimal config for standalone MegaBoom tile. */
class StandaloneMegaBoomConfig extends Config(
  new boom.v4.common.WithNMegaBooms(1) ++
  new WithNBanks(1) ++
  new WithCoherentBusTopology ++
  new BaseSubsystemConfig
)

/** Standalone wrapper that elaborates a BoomTile.
  *
  * Terminates all TileLink and interrupt Diplomacy nodes so the tile
  * can be elaborated without a full SoC context.
  */
class BoomTileStandalone(implicit p: Parameters) extends LazyModule with BindingScope {
  val tileParams = p(TilesLocated(InSubsystem)).head.tileParams.asInstanceOf[BoomTileParams]
  val crossing = RocketCrossingParams()

  val tile = LazyModule(new BoomTile(
    tileParams,
    crossing,
    HartsWontDeduplicate(tileParams)
  ))

  // Coherent manager that supports Acquire (needed by DCache)
  val managerNode = TLManagerNode(Seq(TLSlavePortParameters.v1(
    managers = Seq(TLSlaveParameters.v1(
      address = Seq(AddressSet(0x0, 0x7FFFFFFFL)),
      regionType = RegionType.CACHED,
      executable = true,
      supportsAcquireT = TransferSizes(1, 64),
      supportsAcquireB = TransferSizes(1, 64),
      supportsGet = TransferSizes(1, 64),
      supportsPutFull = TransferSizes(1, 64),
      supportsPutPartial = TransferSizes(1, 64),
      supportsArithmetic = TransferSizes(1, 8),
      supportsLogical = TransferSizes(1, 8)
    )),
    beatBytes = 16,
    endSinkId = 16
  )))
  managerNode := tile.masterNode

  // Provide hart ID to the tile
  val hartIdSource = BundleBridgeSource(() => UInt(tileParams.tileId.U.getWidth.W))
  tile.hartIdNode := hartIdSource

  // Provide reset vector to the tile
  val resetVectorSource = BundleBridgeSource(() => UInt(31.W))
  tile.resetVectorNode := resetVectorSource

  // Provide MMIO address prefix
  val mmioSource = BundleBridgeSource(() => UInt(1.W))
  tile.mmioAddressPrefixNexusNode := mmioSource

  // Provide trace aux input
  val traceAuxSource = BundleBridgeSource(() => new TraceAux)
  tile.traceAuxNode := traceAuxSource

  // Provide interrupt sources to the tile's intInwardNode
  val nInterrupts = {
    val nlips = tileParams.core.nLocalInterrupts
    val nseip = if (tileParams.core.hasSupervisorMode) 1 else 0
    4 + nseip + nlips  // debug + msip + mtip + meip + seip? + lips
  }
  val intSource = IntSourceNode(IntSourcePortSimple(nInterrupts))
  tile.intInwardNode := intSource

  // Terminate tile's outward interrupt nodes (halt, cease, wfi)
  val haltSink = IntSinkNode(IntSinkPortSimple())
  val ceaseSink = IntSinkNode(IntSinkPortSimple())
  val wfiSink = IntSinkNode(IntSinkPortSimple())
  haltSink := tile.haltNode
  ceaseSink := tile.ceaseNode
  wfiSink := tile.wfiNode

  // Terminate tile's outward bundle bridges (trace, bpwatch)
  val traceSink = tile.traceSourceNode.makeSink()
  val traceCoreSink = tile.traceCoreSourceNode.makeSink()
  val bpwatchSink = BundleBridgeSink[Vec[BPWatch]]()
  bpwatchSink := tile.bpwatchNode

  lazy val module = new Impl
  class Impl extends LazyModuleImp(this) {
    // Tie off interrupt inputs to zero
    val ints = intSource.out(0)._1
    ints.foreach(_ := false.B)
    // Tie hart ID and reset vector
    hartIdSource.bundle := tileParams.tileId.U
    resetVectorSource.bundle := 0x80000000L.U
    // Tie MMIO address prefix
    mmioSource.bundle := 0.U
    // Tie trace aux
    val aux = traceAuxSource.bundle
    aux.enable := false.B
    aux.stall := false.B
  }
}

/** Generate FIRRTL for a 4-wide MegaBoom tile. */
object BoomGenerator extends App {
  implicit val p: Parameters = new StandaloneMegaBoomConfig

  ChiselStage.emitHWDialect(
    LazyModule(new BoomTileStandalone).module,
    Array(),
    args
  )
}
