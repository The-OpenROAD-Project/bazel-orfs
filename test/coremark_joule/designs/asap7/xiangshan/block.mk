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

# Parallel synthesis inside the block, partitions discovered rather than
# listed; the parent's list names modules that are now on this side of
# the boundary and would not be worth re-deriving per block.
export SYNTH_HIERARCHICAL      = 1
export OPENROAD_HIERARCHICAL   = 1
export AUTO_MEMORIES           = 1

# The parent's turnaround settings, for the same reasons: flip ABC_AREA
# and SKIP_REPORT_METRICS back for a measured run; REMOVE_ABC_BUFFERS
# and GPL_TIMING_DRIVEN=0 skip the pre-placement and in-placement
# repairs that made the flat run infeasible.
export ABC_AREA                = 1
export REMOVE_ABC_BUFFERS      = 1
export SKIP_REPORT_METRICS     = 1
export GPL_TIMING_DRIVEN       = 0

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
