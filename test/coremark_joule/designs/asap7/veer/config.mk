export PLATFORM                = asap7

# swerv_wrapper, not a cmj_ wrapper of our own. This core's
# configuration lives in `define`s rather than in module parameters, so
# the thing that has to be frozen is the defines file -- see
# //test/coremark_joule/rtl/veer/cmj_veer_defines.sv, which says why it
# undefines ASSERT_ON and leaves PHYSICAL alone.
#
# swerv_wrapper is also already the study's boundary: it contains both
# `swerv` (the core) and `mem` (the 16 kB instruction cache and the
# 64 kB DCCM), so core-plus-L1 is a module here rather than a
# convention. Nothing outside it is hardened, and one hot CoreMark
# iteration sends zero transfers on either external bus -- measured, see
# //test/coremark_joule/sim:veer_rv32imc_bus_traffic.
export DESIGN_NAME             = swerv_wrapper
export DESIGN_NICKNAME         = veer

# SystemVerilog, so this design needs the slang frontend rather than
# yosys's own Verilog reader.
export SYNTH_HDL_FRONTEND      = slang

# Two flags VeeR does not compile without, both found by running slang
# on it directly rather than guessed:
#
#   --single-unit
#     SystemVerilog makes each file its own compilation unit, so a macro
#     defined in one is invisible in the next. VeeR's whole configuration
#     is macros -- every `RV_*` in common_defines.vh -- and its own
#     flist.questa assumes a single-unit flow by listing that file first.
#     Without this, every reference to a configuration macro is an
#     "unknown macro or compiler directive" and the file order in
#     VERILOG_FILES above buys nothing. Verilator hides the difference by
#     making macros global, which is why the simulator built and the
#     flow did not.
#
#   --allow-use-before-declare
#     VeeR declares signals after the always blocks that use them, in
#     dec.sv among others. The LRM requires declaration first for
#     variables and slang enforces it; yosys's own reader and Verilator
#     do not. This is a property of the RTL, not something this study can
#     fix without patching the design it is measuring.
export SYNTH_SLANG_ARGS        = --single-unit --allow-use-before-declare

# Order matters and is load-bearing:
#
#   cmj_veer_defines.sv  the frozen configuration. Every file after it
#                        tests `RV_*` defines, so it has to be read first.
#   @veer//:pkgs         swerv_types, imported by most of the design.
#   @veer//:rtl          the core. mem_lib.sv is deliberately not in this
#                        filegroup: it is the behavioural view of the
#                        three memories, and macros.v below is the
#                        hardening view of the same three module names.
#   macros.v             ram_* -> fakeram7_*, this package.
#
# No CLKGATE_MAP_FILE, unlike ORFS's own swerv_wrapper. That design needs
# one because its vendored copy has PHYSICAL defined and TEC_RV_ICG
# pointing at a TSMC cell name. Here PHYSICAL is left undefined -- which
# is what keeps the simulated and the synthesised Verilog identical --
# and beh_lib.sv then defines the clock gate module itself.
export VERILOG_FILES           = //test/coremark_joule/rtl:veer/cmj_veer_defines.sv \
                                 @veer//:pkgs \
                                 @veer//:rtl \
                                 $(DESIGN_HOME)/asap7/veer/macros.v

export SDC_FILE                = $(DESIGN_HOME)/asap7/veer/constraints.sdc

# VeeR `include`s build.vh and global.vh from its own design/include, and
# common_defines.vh and pic_map_auto.vh from the committed configuration.
#
# Named by sandbox path rather than by label, as ibex's are: an include
# dir is normally a package with a files("include") group, and a
# directory inside a fetched archive has no package to name.
export VERILOG_INCLUDE_DIRS    = external/+http_archive+veer/design/include \
                                 test/coremark_joule/rtl/veer/config

# Staged, never handed to the frontend: these are include fragments that
# declare localparams against the enclosing module's own parameters, so
# compiling them standalone fails on undeclared identifiers.
export VEER_HEADERS            = @veer//:hdrs \
                                 //test/coremark_joule/rtl/veer/config:hdrs

# The three SRAM shapes this configuration needs, all of which ASAP7
# already carries. They are platform files rather than design files:
# ORFS's own asap7/swerv_wrapper keeps them as symlinks into exactly
# these paths, so nothing is vendored here.
export ADDITIONAL_LEFS         = $(PLATFORM_DIR)/lef/fakeram7_2048x39.lef \
                                 $(PLATFORM_DIR)/lef/fakeram7_256x34.lef \
                                 $(PLATFORM_DIR)/lef/fakeram7_64x21.lef

export ADDITIONAL_LIBS         = $(PLATFORM_DIR)/lib/NLDM/fakeram7_2048x39.lib \
                                 $(PLATFORM_DIR)/lib/NLDM/fakeram7_256x34.lib \
                                 $(PLATFORM_DIR)/lib/NLDM/fakeram7_64x21.lib

# Hierarchical synthesis with an explicit kept list, so report_power can
# attribute power to functional units.
#
# This list is not ours: it is the one ORFS's asap7/swerv_wrapper already
# carries, which is itself a capture of the modules VeeR marks
# keep_hierarchy. It maps onto architectural units almost one for one --
# see units.json.
export SYNTH_HIERARCHICAL      = 1
export SYNTH_KEEP_MODULES      = ifu_ifc_ctl ifu_aln_ctl ifu_bp_ctl ifu_mem_ctl \
                                 dec_decode_ctl dec_ib_ctl dec_tlu_ctl dec_trigger \
                                 exu exu_alu_ctl exu_div_ctl \
                                 lsu_lsc_ctl lsu_dccm_ctl lsu_dccm_mem lsu_stbuf \
                                 lsu_bus_buffer lsu_bus_intf lsu_ecc lsu_trigger \
                                 pic_ctrl dma_ctrl dbg

# Run OpenROAD hierarchically, so the module boundaries SYNTH_KEEP_MODULES
# preserved survive into the ODB and the written netlist. Without it the
# ODB carries no module structure and write_verilog emits one flattened
# module, leaving nothing for `report_power -saif -instances` to
# attribute power to.
export OPENROAD_HIERARCHICAL   = 1

# Off. VeeR's memories are already modules with their own hardening view
# (macros.v), so there is nothing to infer -- and the detection pass is a
# slang elaboration of the whole design whose only product would be an
# empty inventory.
# export AUTO_MEMORIES         = 1

export IO_CONSTRAINTS           = $(DESIGN_HOME)/asap7/veer/io.tcl

# Starting points. The auto_floorplan derivation measures and pins these.
#
# Everything below is ORFS's, from its own asap7/swerv_wrapper, taken
# because someone has already closed this core on this PDK with them and
# a starting point that works beats one that is ours. Each is a
# convergence knob rather than a measurement choice: they decide whether
# the flow finishes, not what it reports.
export CORE_UTILIZATION        = 30
export PLACE_DENSITY           = 0.60

# Macro designs place badly at the default lower bound.
export PLACE_DENSITY_LB_ADDON  = 0.20

# Derate routing resources. A design this size with three macros in it
# congests, and the router does better told so up front.
export ROUTING_LAYER_ADJUSTMENT = 0.2

# Pinned, not defaulted. ORFS picked this seed for this design; for a
# measurement study a pinned seed is right regardless, because an
# unpinned one makes every number a sample from a distribution nobody
# stated.
export GPL_RANDOM_SEED         = 2

# Two things ORFS's swerv_wrapper does that this study deliberately does
# not:
#
#   LIB_MODEL = CCS
#     A better delay model, and the wrong choice here. The other three
#     cores are characterised against NLDM, and a power number is not
#     comparable across delay models. The study's whole claim is that the
#     comparison is apples-to-apples; buying accuracy on one point at the
#     cost of that would be a poor trade.
#
#   SYNTH_USE_SYN = 1
#     OpenROAD-native synthesis instead of yosys. bazel-orfs's own
#     orfs_design_builds.bzl lists swerv_wrapper under SYN_SLOW_DESIGNS
#     as "not yet run to completion under OpenROAD-SYN in this
#     environment", and the yosys + slang path here works.

# Metrics reporting off. This is the only line of the FAST_SETTINGS dict
# in //test:BUILD that a measurement study can take -- every other entry
# in it changes the netlist, and a study cannot buy speed with the thing
# it measures. §3.6 of the paper has the list and the reasoning.
#
# Nothing here reads ORFS's metrics: power comes from
# flow/power_grt.tcl, the achieved period from flow/period_probe.tcl,
# and auto_floorplan takes WNS from sta::worst_slack_cmd directly.
export SKIP_REPORT_METRICS     = 1
