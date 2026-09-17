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
export SYNTH_KEEP_MODULES      = Frontend \
                                 Backend \
                                 MemBlock \
                                 CtrlBlock \
                                 FusionDecoder \
                                 NewLoadUnit \
                                 PMP \
                                 PMPChecker \
                                 PTWFilter \
                                 Uncache \
                                 PMPChecker_8 \
                                 PTWNewFilter \
                                 Region \
                                 DecodeStage \
                                 SimpleDecodeChannel \
                                 UopBufferCtrlDecoder

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
# is the floor of the run. The last line of the list cuts the 60-90 k
# line partitions that remained (ExuBlock's CSR, Rename's tables and
# compressor, MemCtrl's SSIT and LFST, Sbuffer's data, LoadQueueReplay's
# age detectors, Ftq's resolve queue) at children of 15-60 k lines.
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

# Hardened blocks. Each is its own flow under block.mk and reaches the
# parent as a LEF/LIB macro; the parent's synthesis blackboxes them by
# name from ADDITIONAL_LIBS. Chosen for size and for having every port
# registered or being off CoreMark's path (the vector and floating-point
# regions), never the integer issue loop or the load-to-use path, which
# stay flat here. Region (int) is not a block. To ease off, remove the
# name here AND put the block's kept modules back into SYNTH_KEEP_MODULES
# below: a kept name that is inside a blackboxed block fails the
# per-module re-canonicalize ("not present in checkpoint"), so the list
# below holds only modules reachable from XSCore without entering a
# block (Bpu's predictors, DCacheWrapper's arrays, VecRegionModule's
# issue queues and the vector register file are in their blocks).
#
# Thirteen blocks, chosen for build time. The first five are the caches,
# predictors and the vector region; the next eight are the rest of the
# core's bulk, read off the generated Verilog by subtree size: decode
# (942 k lines, eight copies of one channel), the reorder buffer (285 k),
# dispatch (153 k), rename (80 k), memory dependence prediction (70 k),
# the integer region (676 k), the floating-point region (257 k) and the
# load/store queues (284 k). What stays in the parent is about 530 k
# lines of glue: the frontend outside Bpu and ICache, MemBlock's TLBs,
# store buffer and prefetchers, and the top-level connections. The blocks
# synthesise and place in parallel, each partitioned inside, so the wall
# time is the slowest block plus a small parent instead of one placement
# of the whole core; and the gate-level simulation sees the blocks as
# RTL, which is what makes it tractable.
#
# Region_1 was a block before, failed legalisation twice on its
# floating-point register files, and came back into the parent. The
# register files are generated macros now (FpRegFilePart0..3.regfile,
# named in Region_1/config.mk), which is what its placement needed.
export BLOCKS                  = VecRegionModule \
                                 Bpu \
                                 ICache \
                                 DCacheWrapper \
                                 L2TLBWrapper \
                                 Rob \
                                 Dispatch \
                                 Rename \
                                 MemCtrl \
                                 Region_1 \
                                 LsqWrapper \
                                 IssueQueueAluCsrFenceLinkBrhNjmp \
                                 IssueQueueAluDivBrhNjmp \
                                 IssueQueueAluI2fBrhNjmp \
                                 IssueQueueAluBkuVset \
                                 IssueQueueAluMul \
                                 IssueQueueLdu \
                                 IssueQueueStaMou \
                                 IssueQueueStaMou_1 \
                                 IssueQueueStdMoud \
                                 IssueQueueStdMoud_1 \
                                 DataPath \
                                 ExuBlock \
                                 VectorDecodeChannel \
                                 Sbuffer \
                                 TLBNonBlock \
                                 TLBNonBlock_1 \
                                 TLBNonBlock_2 \
                                 PrefetcherWrapper \
                                 HPerfMonitor_3 \
                                 Ifu \
                                 Ftq \
                                 IBuffer \
                                 TLB

# The register files, generated rather than synthesised. As flops the
# four FpRegFilePart arrays stopped the fp region block's legalisation
# twice and IntRegFile did the same to the parent (5.5 M violations to
# 17 k in three hours, then a thousand fewer per 50 iterations); as
# blocks of their own at 20 % utilisation they legalised in 17
# iterations at 5x their cell area. Now each is a placed standard-cell
# macro from tools/structured_gen, listed here by its spec, checked
# against the module's ports at synthesis, and blackboxed like an
# AUTO_MEMORIES memory; the RTL stays as it is and is the simulation
# model. IntRegFile is the banked variant, one address and data bus per
# bank on every read port. The lib each gets is a model until its own
# block flow replaces it with a routed abstract. The four Ftq queues are
# register files by XiangShan patch 0002 (Reg(Vec) arrays given a module
# boundary, utils.RegVecFile): 64 words each, one write, 1-4 reads, and
# together 53 kbit of the Ftq partition's flops behind 64:1 read muxes.
# (The Ftq register files moved with Ftq into its block; the parent has
# no generated register file of its own now.)

# Turnaround: no repair inside global placement. Flat, the first
# timing-driven iteration inserted 527,027 buffers over 9.8 M pins and
# was still removing them hours later. Flip back for the measured run.
export GPL_TIMING_DRIVEN       = 0
# And no routability inflation either: on the vector region block it
# undid the placer's convergence (overflow 0.31 back to 0.66). Global
# route will say what that costs; flip back for the measured run.
export GPL_ROUTABILITY_DRIVEN  = 0
# Floorplan's repair_timing visits every violating endpoint (ORFS runs it
# with -repair_tns 100): on Bpu that was 4248 latch endpoints at zero
# slack, one STA pass each on 650 k instances, 944 no-op iterations and
# counting after 20 minutes. One percent still repairs the worst path
# and bounds the visit; ORFS's own note on the knob says 5 for runtime.
export TNS_END_PERCENT         = 1
# TURNAROUND SETTINGS -- flip to 0 for the measured run. The repairs
# after clock tree synthesis and inside global route are the hours of a
# design this size, and the number this flow is being put together for
# is read at global route from the placed netlist's power; the timing
# these would buy is not in it yet. Last gasp is the tail of every
# repair_timing.
export SKIP_CTS_REPAIR_TIMING  = 1
export SKIP_INCREMENTAL_REPAIR = 1
export SKIP_LAST_GASP          = 1
# extract_fa was most of the arithmetic partitions' time (83% of the
# vector converter, 51% of a vector FMA); skipped, adders take the
# generic techmap. ORFS patch 0074 adds the knob. Turnaround only.
export SKIP_EXTRACT_FA         = 1
# The detailed-placement improvement pass (improve_placement, ENABLE_DPO)
# is a wirelength polish after legalisation: 13 minutes on Rob and on
# the load/store block, an unknown on the parent. Off while the flow is
# being put together; back on for the measured run.
export ENABLE_DPO              = 0
# The parent's legaliser. The negotiation legaliser, OpenROAD's default,
# stalled at 210 k violations and 19 k illegal cells after 80 iterations
# (1.5 % fewer per ten): the glue is 167 k um^2 of cells on a 10.7 mm^2
# core of 44 macros, and repair_design drops wire buffers over macro
# interiors up to 330 um from a free site. The diamond legaliser with
# its default window (500 sites x 100 rows) fails on 4,755 of those;
# a window spanning the largest macro (665 um) reaches them.
export DETAIL_PLACEMENT_ARGS   = -use_diamond_legalizer -max_displacement {7000 1400}

# No pre-placement repair_timing. With REMOVE_ABC_BUFFERS unset, the
# floorplan stage runs repair_timing on wire-load models before anything
# is placed; on 10.8 M instances that found 131,661 violating endpoints
# and moved through 40 of them in eight minutes -- days, for a repair
# that the place stage redoes with real parasitics. Set, the floorplan
# strips abc's buffers instead and repair_design rebuffers after
# placement. The other four cores run the default; for them it is
# seconds, and its effect is a pre-sizing the later repairs revisit.
export REMOVE_ABC_BUFFERS      = 1

# TURNAROUND SETTING -- flip to 0 (or delete) for the measured run.
# report_metrics at the end of each stage is a full STA; at floorplan on
# 10.8 M instances it was 75 of the stage's 80 minutes. The study takes
# its numbers from its own scripts at global route, not from these
# reports, but the reports are what a reader of the flow expects to
# find, so the measured run keeps them.
export SKIP_REPORT_METRICS     = 1

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

# Macro placement: the bank groups by our annealer, the rest by RTL-MP.
#
# 303 macros in 16 shapes, nearly all of them banks of something: 64 TAGE
# tables, 32 ways of L1D data, 32 of L1I data, 16 L2 TLB pages. RTL-MP
# is asked to rediscover that from a flat list; anneal_in_flow.tcl reads
# it off the hierarchy instead, tiles each group into one block, anneals
# the blocks against the standard-cell modules they talk to, and places
# every bank FIRM before rtl_macro_placer runs on what is left. See
# //test/coremark_joule/flow/macro_anneal.
export MACRO_PLACEMENT_TCL     = $(DESIGN_HOME)/asap7/xiangshan/anneal_in_flow.tcl
export ANNEAL_DUMP_TCL         = //test/coremark_joule/flow/macro_anneal:dump_macros.tcl
export ANNEAL_PY               = //test/coremark_joule/flow/macro_anneal:macro_anneal.py

# Seeded: the same die gives the same bytes. Depth 3 clusters at the
# level of frontend/inner_bpu/<predictor> and memblock/dcache/<array>;
# a group of fewer than 4 is left to RTL-MP. fill is the fraction of
# the core the macro blocks and the logic ballast are packed into, the
# rest being what RTL-MP and the placer get to work with.
#
# Two spacings, and the first run taught the difference. Between the
# banks of one block the channel is exactly two halos, so the halos
# abut and no standard-cell row exists between banks: at 4.4 um there
# was a 0.38 um sliver of rows between every pair, seven sites wide,
# and pdngen failed (PDN-0179) trying to power 60-odd of them. Between
# blocks the gap is two strap pitches (M5/M6 pitch 5.4 um), so the
# logic the placer puts there gets a grid.
export ANNEAL_SEED             = 1
export ANNEAL_DEPTH            = 3
# Every macro is placed here, singletons included: with three left for
# rtl_macro_placer and fill 0.6 it failed to fit its standard-cell
# clusters around 300 fixed blocks (MPL-0040). Fill 0.5 packs the
# blocks tighter and leaves the placer contiguous room.
export ANNEAL_MIN_CLUSTER      = 1
export ANNEAL_CHANNEL_UM       = 4.0
export ANNEAL_BLOCK_GAP_UM     = 10.8
export ANNEAL_FILL             = 0.5

# The power grid of a parent with hardened blocks. The platform's flat
# grid (grid_strategy-M1-M2-M5-M6.tcl) powers a macro by connecting its
# M4 rails to the parent's M5 stripes, which is right for the SRAM
# banks; a block abstract has its power pins on M5 and everything up to
# M5 obstructed, so that grid found no shapes over any of the five
# blocks (PDN-0232 x5, PDN-0233). ORFS's BLOCKS grid is for this case:
# M5 and M6 stripes to a core ring, and a macro grid over every macro
# connecting M5 to M6, so a block's M5 pins meet the parent's M6. The
# platform selects it when make sees BLOCKS; here it has to be said.
export PDN_TCL                 = $(PLATFORM_DIR)/openRoad/pdn/BLOCKS_grid_strategy.tcl
# The BLOCKS grid's core ring (M5 0.504 + M6 0.544 wide, 0.096 apart,
# 0.504 off the core) needs 1.65 um between core and die; the platform's
# 1 um margin leaves the ring 0.66 um outside the die (PDN-0351). Two
# microns, as ORFS's own asap7 BLOCKS design has.
export CORE_MARGIN             = 2

# The parent's vertical power stripes, so a macro narrower than one
# stripe pitch is placed with a stripe pair inside its rails. The BLOCKS
# grid draws M5 stripes 0.12 wide, 0.072 apart, pitch 2.16, first at
# 1.50 from the core edge. With the caches and predictors hardened, one
# SRAM bank is left at this level; the numbers still have to match
# PDN_TCL for it.
export ANNEAL_STRAP_PITCH_UM   = 2.16
export ANNEAL_STRAP_OFFSET_UM  = 1.5
export ANNEAL_STRAP_PAIR_UM    = 0.312

# 2 um, not the platform's 10: at 10 the halos alone turn 0.13 mm2 of
# macro into 0.51 mm2 of footprint, and the channels the annealer leaves
# are already sized for the power straps.
export MACRO_PLACE_HALO        = 2 2
