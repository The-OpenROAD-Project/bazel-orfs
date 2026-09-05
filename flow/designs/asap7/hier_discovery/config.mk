# config.mk DSL fixture: SYNTH_HIERARCHICAL=1 with no SYNTH_KEEP_MODULES.
#
# This is the shape of every hierarchical ORFS design without a pinned
# list (asap7/coralnpu, asap7/riscv32i, sky130hd/microwatt, ...), and the
# path orfs_design.bzl takes for it: a static SYNTH_NUM_PARTITIONS, the
# kept modules discovered by synth_keep.tcl at build time, a load-time
# note that pinning buys per-module caching. Three modules, seconds of
# yosys. SYNTH_MINIMUM_KEEP_SIZE=0 keeps adder and counter, which are far
# below asap7's platform default of 1000 estimated gates.
export PLATFORM                = asap7
export DESIGN_NAME             = kept_modules_top
export DESIGN_NICKNAME         = hier_discovery

export VERILOG_FILES           = $(DESIGN_HOME)/asap7/hier_discovery/kept_modules_top.v
export SDC_FILE                = $(DESIGN_HOME)/asap7/hier_discovery/constraint.sdc

export SYNTH_HIERARCHICAL      = 1
export SYNTH_MINIMUM_KEEP_SIZE = 0
