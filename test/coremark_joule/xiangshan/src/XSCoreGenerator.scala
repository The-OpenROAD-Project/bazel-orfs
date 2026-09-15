// Elaborate XiangShan for the CoreMark-per-Joule study.
//
// The study hardens XSCore -- the core with its L1I and L1D, which is the
// measurement boundary -- but XSCore is a diplomacy LazyModule whose nodes
// bind upward to L2Top, so it cannot be elaborated on its own without
// hand-writing the tie-off. Elaborating upstream's own XSTop avoids that
// entirely: firtool emits one Verilog module per Chisel module, so XSCore
// arrives as its own module with its own ports, and the synthesis top is a
// choice made in config.mk rather than surgery done here.
//
// Everything outside XSCore is elaborated because the core cannot run
// without it, and hardened by nobody.

package coremark_joule.xiangshan

import circt.stage.ChiselStage
import freechips.rocketchip.diplomacy.{DisableMonitors, LazyModule}
import org.chipsalliance.cde.config.{Config, Parameters}
import top._
import utility._
import xiangshan.DebugOptionsKey

/** XiangShan V3 (Kunminghu) as the study measures it.
  *
  * Derived from upstream's DefaultConfig with two changes, both outside the
  * measurement boundary:
  *
  *   - A small last-level cache. XiangShan V3 hardcodes enableCHI, so the
  *     non-CHI path with its plain AXI SoC is dead code and OpenLLC is not
  *     optional: XSTop instantiates it whenever CHI is on, and a config
  *     without OpenLLCParamsOpt fails to elaborate. It shrinks from 32 MB
  *     to 1 MB instead, which is simulation cost avoided and nothing else,
  *     since the study hardens no cache past L1.
  *   - A small L2. CoreMark's working set fits in L1 after the first
  *     iteration, so L2 capacity has no measurable effect on the cycle
  *     count, and a 2 MB L2 is expensive to simulate.
  *
  * The L1s are untouched: 64 KB each for instruction and data, which is
  * also the size ACM CF'25 normalized its cores to, so the two studies
  * measure the same amount of cache.
  */
class CoreMarkJouleConfig(n: Int = 1)
    extends Config(
      OpenLLCConfig("1MB", ways = 8, banks = 1)
        ++ L2CacheConfig("512KB", inclusive = true, banks = 1, tp = false)
        ++ WithNKBL1D(64, ways = 4, numMemChannels = 1)
        ++ new BaseConfig(n)
    )

/** The same shape at MinimalConfig, for proving the pipeline cheaply.
  *
  * Not a measurement configuration -- its caches and structures are far
  * smaller -- but it elaborates in a fraction of the time and memory, which
  * makes it the right thing to fail on first.
  */
class CoreMarkJouleMinimalConfig(n: Int = 1) extends Config(new MinimalConfig(n))

object XSCoreGeneratorBase {
  /** The two keys upstream sets in ArgParser rather than in any Config.
    *
    * Elaborating a Config directly, without going through the command-line
    * parser, leaves them undefined and XSTop fails partway through with
    * "Key PerfCounterOptionsKey is not defined in Parameters". The values
    * here are what upstream derives for a build with no debug options.
    */
  private def withArgParserKeys(config: Config): Parameters =
    config.alter((site, here, up) => {
      // Measure the design, not the instrumentation.
      //
      // XiangShan's default build carries ChiselDB instruction tables,
      // difftest probes and performance-counter timestamps through the
      // pipeline. All of it is analysis apparatus, none of it is the CPU,
      // and synthesising it would put its area and its switching into the
      // energy figure.
      //
      // FPGAPlatform is upstream's name for "no simulation-only
      // instrumentation" -- it reads oddly for an ASIC flow, but it is the
      // switch that turns the apparatus off, and it is not used anywhere
      // in the memory implementations, so it does not change the design
      // being measured. Leaving it false with EnablePerfDebug off also
      // does not elaborate: Rob.scala reads perfDebugInfo.get from a
      // block guarded only by !FPGAPlatform.
      case DebugOptionsKey =>
        up(DebugOptionsKey).copy(
          FPGAPlatform = true,
          EnablePerfDebug = false,
          EnableDifftest = false,
          // AlwaysBasicDiff stays at upstream's default of true. It is
          // tempting to turn off, but Backend.scala reads
          // vecRegion.out.diff.get unconditionally, so a build without the
          // difftest bundles does not elaborate. They are output-only taps
          // with no consumer once the difftest gateway is not
          // instantiated, so synthesis should prune them -- which is
          // checked at 1_synth rather than assumed.
          EnableChiselDB = false,
          EnableConstantin = false
        )
      case LogUtilsOptionsKey =>
        LogUtilsOptions(
          enableDebug = here(DebugOptionsKey).EnableDebug,
          enablePerf = here(DebugOptionsKey).EnablePerfDebug,
          fpgaPlatform = here(DebugOptionsKey).FPGAPlatform,
          enableXMR = here(DebugOptionsKey).EnableXMR
        )
      case PerfCounterOptionsKey =>
        PerfCounterOptions(
          enablePerfPrint = here(DebugOptionsKey).EnablePerfDebug && !here(DebugOptionsKey).FPGAPlatform,
          enablePerfDB = here(DebugOptionsKey).EnableRollingDB && !here(DebugOptionsKey).FPGAPlatform,
          perfLevel = XSPerfLevel.withName(here(DebugOptionsKey).PerfLevel),
          perfDBHartID = 0
        )
    })

  def emit(config: Config, args: Array[String]): Unit = {
    // Both write files into the working directory as a side effect of
    // elaboration; neither is wanted here.
    Constantin.init(false)
    ChiselDB.init(false)

    val soc = DisableMonitors(p => LazyModule(new XSTop()(p)))(withArgParserKeys(config))
    ChiselStage.emitHWDialect(soc.module, Array(), args)
  }
}

object XSCoreGenerator extends App {
  XSCoreGeneratorBase.emit(new CoreMarkJouleConfig(1), args)
}

object XSCoreGeneratorMinimal extends App {
  XSCoreGeneratorBase.emit(new CoreMarkJouleMinimalConfig(1), args)
}
