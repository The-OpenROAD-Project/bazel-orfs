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

# yosys's own reader, not slang. firtool emits SystemVerilog, but the
# lowering options the generator passes -- disallowPackedArrays,
# disallowLocalVariables, noAlwaysComb -- exist precisely so the output
# stays inside what a plain Verilog reader handles, and that is what the
# retired gallery relied on for BOOM and gemmini. slang rejects it with
# "Compilation failed" and no diagnostic.

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
                                 VecRegionModule \
                                 IssuePipeVialuVfmaVfdivVidiv \
                                 IssuePipeVialuVimacVmoveVfcvtVfma \
                                 IssuePipeVialuVfma IssuePipeVialuVfma_1 \
                                 IssueQueueVialuVimacVmoveVfcvtVfma \
                                 IssueQueueVialuVfmaVfdivVidiv \
                                 IssueQueueVialuVfma IssueQueueVialuVfma_1 \
                                 IssueQueueVstd VfRegFile \
                                 IssueQueueLdu IssueQueueAluMul ExuBlock DataPath \
                                 IssueQueueAluI2fBrhNjmp IssueQueueAluBkuVset \
                                 IssueQueueAluCsrFenceLinkBrhNjmp \
                                 IssueQueueAluDivBrhNjmp \
                                 IssueQueueStdMoud IssueQueueStdMoud_1 \
                                 IssueQueueStaMou IssueQueueStaMou_1 \
                                 IssueQueueFaluFmacFdiv ExuBlock_1 DataPath_1 \
                                 IssueQueueFaluFmacFcvtFcmp IssueQueueFaluFmac \
                                 LsqWrapper Sbuffer TLBNonBlock \
                                 PrefetcherWrapper MemCtrl \
                                 LoadQueueReplay LoadQueueRAW LoadQueueRAR \
                                 VirtualLoadQueue LoadQueueUncache StoreQueue \
                                 VectorDecodeChannel SimpleDecodeChannel \
                                 UopBufferCtrlDecoder \
                                 MainBtbAlignBank Tage Sc AheadBtb Phr \
                                 MicroTage Ittage \
                                 RenameBuffer VTypeBuffer \
                                 TLBNonBlock_1 TLBNonBlock_2 PMPChecker_8 \
                                 PTWNewFilter \
                                 MissQueue BankedDataArray L1ErrorMetaArray \
                                 L1PrefetchSourceArray L1CohMetaArray \
                                 L1FlagMetaArray BusyTable BusyTable_1 \
                                 IntRegFile PhysicalStoreQueue VirtualStoreQueue

# The second block of that list, from IssuePipeVialuVfmaVfdivVidiv on, is
# kept for synthesis turnaround, not for the breakdown. yosys and abc are
# single-threaded and superlinear in module size; on a 48-core machine the
# first full run spent 89 minutes on VecRegionModule alone -- 58 of them
# in yosys before abc -- while every other core idled; with the execution
# regions split, the tail was LsqWrapper (57+ min), Rob, DecodeStage and
# Bpu (42+ min each). These are the children that carry the bulk of each
# of those, read out of the elaborated hierarchy by generated-Verilog
# size. Each becomes its own partition, and a module instantiated more
# than once is synthesised once: DecodeStage's 33 MB was eight copies of
# VectorDecodeChannel. Rob's own body, 12 MB, has no children to keep and
# is the floor of the run.
#
# units.json does not list them: report_power on a kept parent's
# instance sums everything beneath it, children included, so the
# breakdown is unchanged. What changes is the optimisation boundary --
# constants and dead logic no longer propagate across these lines, which
# for an idle vector unit is a small pessimism. Inline any of them again
# by deleting the name; the partition cache re-runs only what changed.

# Keep those boundaries in the ODB and the written netlist. Without it the
# flow is flat and there is nothing for report_power -saif -instances to
# attribute power to.
export OPENROAD_HIERARCHICAL   = 1

# TURNAROUND SETTING -- flip to 0 (or delete) for the measured run.
#
# ORFS's default abc script is the speed one: five rounds of resynthesis
# and timing-driven sizing against the SDC period. On this design it is
# two thirds to seven eighths of every partition's time, and Rob -- a
# 12 MB module with nothing to partition -- spends 43 minutes in it. The
# area script is one mapping round; it brings the tail to about 20
# minutes while the flow is being put together.
#
# It is not what the other four cores were synthesised with, so a number
# taken with it is not comparable to theirs. The published XiangShan run
# is made with this set to 0, once.
export ABC_AREA                = 1

# XiangShan's caches are most of its area, and firtool emits every
# inferred memory as its own ram_<depth>x<width> module carrying one
# register array -- exactly the shape this converts to an SRAM macro.
# XSCore has 38 of them, about 976 Kbit, which is a megabit of L1 plus
# tags and predictor arrays. Hardened as flip-flops they would dominate
# the energy figure and it would be measuring the wrong thing.
export AUTO_MEMORIES           = 1

export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
