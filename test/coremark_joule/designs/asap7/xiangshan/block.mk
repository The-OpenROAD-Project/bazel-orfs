# One config for every BLOCKS= sub-macro of XSCore. ORFS instantiates it
# per block with DESIGN_NAME=<block> and DESIGN_NICKNAME=xiangshan_<block>
# (flow/Makefile's generate_abstract rule; bazel-orfs's config parser
# does the same), so what is written here is what every block shares.
#
# Why blocks at all: flat, XSCore is 10.8 M instances, and global
# placement alone ran past three hours at 54 GB without global route in
# sight. Each block below is hardened on its own, in parallel, and the
# parent sees a LEF outline with pins and a .lib -- the same mechanism as
# the SRAM macros, one level up. README §4.9 and the plan in the PR say
# which blocks and why; the short form is: big, off CoreMark's path or
# registered at every port, and never the integer issue loop or the
# load-to-use path.
#
# Blocks use every metal layer. At the parent they are opaque and the
# parent routes in the channels between them, which the annealer already
# sizes for the SRAM banks; leaving the top layers free for the parent
# to route over would need a different PDN and pin strategy per block
# and buys nothing while the block count is single digits.
export PLATFORM                = asap7

# The same flat Verilog as the parent; yosys keeps the block's subtree.
export VERILOG_FILES           = //test/coremark_joule/xiangshan:xiangshan_flat.sv

# The parent's SDC works unchanged as a block SDC: create_clock on the
# `clock` port every Chisel module has, the platform's set_max_delay IO
# budgets as fractions of the period, the reset false path, and -- the
# part that matters for an abstract -- no set_input_delay or
# set_output_delay, because the clock insertion latency at a block's
# clock pin is the parent's CTS to decide, not a number to assert here.
export SDC_FILE                = $(DESIGN_HOME)/asap7/xiangshan/constraints.sdc

export SYNTH_HIERARCHICAL      = 1
export OPENROAD_HIERARCHICAL   = 1
export AUTO_MEMORIES           = 1

# Parallel synthesis inside each block with an explicit kept list, set
# in the block's own <Block>/config.mk after it includes this file. The
# lists are the parent's turnaround list split by block, plus the
# largest unkept modules under each, and every name must exist in the
# block: the per-module re-canonicalize fails on a name that is not in
# its checkpoint. The subtree of each block was read off the generated
# Verilog, one module per file, instantiations by name. Explicit rather than
# discovered because discovery is `keep_hierarchy -min_cost`, which wants
# a gate cost on every blackbox, and the blackbox AUTO_MEMORIES leaves
# for an SRAM has none ("Missing cost information on instanced blackbox
# array_256x66"). ICache is small enough to synthesise flat.

# Placement without its in-loop repair or routability inflation. On the
# vector region the two together sent Nesterov from overflow 0.31 back to
# 0.66 and past 1,900 iterations; off, placement is one descent. Both
# are place-stage variables, so flipping them re-runs only placement.
export GPL_TIMING_DRIVEN       = 0
export GPL_ROUTABILITY_DRIVEN  = 0

# The parent's three turnaround knobs, now that the block synthesis is
# redone anyway (parent config.mk says why each): the area abc script,
# no report_metrics STA at every stage, and abc's buffers stripped at
# floorplan instead of repaired. The last is the one that matters most
# here: without it floorplan runs repair_timing over every violating
# endpoint, and on Bpu that was 4248 latch endpoints at zero slack, one
# STA pass each on 650 k instances, 944 no-op iterations in 20 minutes
# with the rest of the machine idle. TNS_END_PERCENT bounds whatever
# repair still runs later to the worst percent.
export ABC_AREA                = 1
export SKIP_REPORT_METRICS     = 1
export REMOVE_ABC_BUFFERS      = 1
export TNS_END_PERCENT         = 1
export SKIP_LAST_GASP          = 1
# extract_fa was most of the arithmetic partitions' time (83% of the
# vector converter, 51% of a vector FMA); skipped, adders take the
# generic techmap. ORFS patch 0074 adds the knob. Turnaround only.
export SKIP_EXTRACT_FA         = 1

export CORE_UTILIZATION        = 40
export CORE_ASPECT_RATIO       = 1
export PLACE_DENSITY           = 0.6
export MACRO_PLACE_HALO        = 2 2

# A block's own SRAM banks are placed by RTL-MP. The counts per block are
# a fraction of the 303 the flat design had, which is the regime RTL-MP
# handles; if a block trips MPL-0040 the annealer is the fallback.

# All layers, and the block grid: this is a hard macro, not a chip.
export PDN_TCL                 = $(PLATFORM_DIR)/openRoad/pdn/BLOCK_grid_strategy.tcl
export MIN_ROUTING_LAYER       = M2
export MAX_ROUTING_LAYER       = M9
export PLACE_PINS_ARGS         = -annealing
