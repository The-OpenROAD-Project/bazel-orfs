export PLATFORM                = asap7

export DESIGN_NAME             = XSCore
export DESIGN_NICKNAME         = xiangshan

# The elaborated Chisel, as one file. XSCore is a module firtool emits, so
# the measurement boundary -- the core with its L1I and L1D, the L2 a
# sibling inside XSTile -- is chosen here rather than carved out of a
# netlist. Everything above XSCore in the elaboration is present in the
# file and unreachable from this top, so yosys discards it.
export VERILOG_FILES           = //test/coremark_joule/xiangshan:xiangshan_flat.sv
export SDC_FILE                = $(DESIGN_HOME)/asap7/xiangshan/constraints.sdc

# firtool emits SystemVerilog.
export SYNTH_HDL_FRONTEND      = slang

# Partitioned synthesis, and the functional-unit breakdown, from one
# mechanism. 2.8 M lines is not a design to synthesise as a single job,
# and these are the modules units.json attributes power to -- the
# categories ACM CF'25 reports for CVA6, CVA6S+ and the C910, so the two
# breakdowns can be read against each other.
export SYNTH_HIERARCHICAL      = 1
export SYNTH_KEEP_MODULES      = Frontend Backend MemBlock CtrlBlock Bpu \
                                 DCacheWrapper DecodeStage Dispatch Ftq \
                                 FusionDecoder IBuffer ICache Ifu L2TLBWrapper \
                                 NewLoadUnit PMP PMPChecker PTWFilter Region \
                                 Region_1 Rename Rob TLB Uncache \
                                 VecRegionModule

# Keep those boundaries in the ODB and the written netlist. Without it the
# flow is flat and there is nothing for report_power -saif -instances to
# attribute power to.
export OPENROAD_HIERARCHICAL   = 1

# XiangShan's caches are most of its area, and firtool emits every
# inferred memory as its own ram_<depth>x<width> module carrying one
# register array -- exactly the shape this converts to an SRAM macro.
# XSCore has 38 of them, about 976 Kbit, which is a megabit of L1 plus
# tags and predictor arrays. Hardened as flip-flops they would dominate
# the energy figure and it would be measuring the wrong thing.
export AUTO_MEMORIES           = 1

export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
