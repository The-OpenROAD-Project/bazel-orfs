# config.mk DSL fixture: SYNTH_HIERARCHICAL=1 with SYNTH_KEEP_MODULES
# pinned, the shape of asap7/swerv_wrapper. orfs_design.bzl sets
# SYNTH_NUM_PARTITIONS to the list length and rules.bzl declares one
# re-canonicalization action per named module. Three modules, seconds of
# yosys.
export PLATFORM                = asap7
export DESIGN_NAME             = kept_modules_top
export DESIGN_NICKNAME         = hier_pinned

export VERILOG_FILES           = $(DESIGN_HOME)/asap7/hier_pinned/kept_modules_top.v
export SDC_FILE                = $(DESIGN_HOME)/asap7/hier_pinned/constraint.sdc

export SYNTH_HIERARCHICAL      = 1
export SYNTH_KEEP_MODULES      = adder counter
