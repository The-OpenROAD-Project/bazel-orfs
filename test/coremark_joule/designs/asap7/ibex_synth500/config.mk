# ibex, the reported design, constrained for 500 MHz and taken to
# synthesis only. Not a point on Figure 1.
#
# §4.8's cross-check: the nearest published CoreMark energy for ibex
# was taken on a post-synthesis netlist constrained for 500 MHz, with no
# clock tree and no wires. This package takes this study's number the
# same way, so the disagreement between the two can be assigned to the
# stage and the period rather than argued about. Everything except the
# nickname and the SDC is byte-identical to designs/asap7/ibex/config.mk.
export PLATFORM                = asap7

export DESIGN_NAME             = cmj_ibex
export DESIGN_NICKNAME         = ibex_synth500

# SystemVerilog, so this design needs the slang frontend rather than
# yosys's own Verilog reader.
# :pkgs before :rtl. The package files are a separate filegroup because
# Verilator resolves in file order and a glob is alphabetical, which puts
# ibex_alu.sv ahead of ibex_pkg.sv; the flow needs both groups listed or
# every type in those packages is an unknown identifier.
export VERILOG_FILES           = @ibex//:pkgs @ibex//:rtl //test/coremark_joule/rtl:cmj_ibex.sv \
                                 //test/coremark_joule/flow:cmj_progmem_macros.v \
                                 //test/coremark_joule/rtl:cmj_dmem.v
export SDC_FILE                = $(DESIGN_HOME)/asap7/ibex_synth500/constraints.sdc
export SYNTH_HDL_FRONTEND      = slang

# ibex sources `include "prim_assert.sv" and "dv_fcov_macros.svh" from
# the vendored OpenTitan tree inside the fetched archive.
#
# The directories are named by their sandbox path rather than by a label:
# an include dir is normally a package of this repository with a
# files("include") group, and a directory inside an archive has no
# package to name.
#
# The headers are staged by IBEX_HEADERS below rather than listed in
# VERILOG_FILES. They are include fragments, not sources: prim_util_memload.svh
# is `include`d inside a module and refers to that module's own
# parameters, so compiling it standalone fails on undeclared identifiers.
# A user_sources var stages the files into the sandbox without handing
# them to the frontend, which is exactly what an include path needs.
export VERILOG_INCLUDE_DIRS    = external/+http_archive+ibex/vendor/lowrisc_ip/ip/prim/rtl \
                                 external/+http_archive+ibex/vendor/lowrisc_ip/dv/sv/dv_utils

# Staged, never read: see VERILOG_INCLUDE_DIRS above.
export IBEX_HEADERS            = @ibex//:hdrs

export SYNTH_HIERARCHICAL      = 1
export SYNTH_KEEP_MODULES      = ibex_if_stage ibex_prefetch_buffer ibex_fetch_fifo \
                                 ibex_id_stage ibex_decoder ibex_compressed_decoder \
                                 ibex_controller ibex_ex_block ibex_alu \
                                 ibex_multdiv_fast ibex_load_store_unit \
                                 ibex_register_file_ff ibex_cs_registers ibex_counter

# Run OpenROAD hierarchically, so the module boundaries SYNTH_KEEP_MODULES
# preserved survive into the ODB and the written netlist.
#
# Without it the flow is flat: the ODB carries no module structure and
# write_verilog emits one flattened module, so there is nothing for
# `report_power -saif -instances` to attribute power to. Keeping the
# hierarchy through synthesis and then discarding it in OpenROAD would
# leave the whole functional-unit breakdown with a single unit in it.
export OPENROAD_HIERARCHICAL    = 1

# On, for the two tightly-coupled memories below. ibex's own register
# file is ibex_register_file_ff -- flops by construction, not an
# inferred memory -- so detection finds nothing in the core itself, and
# everything AUTO_MEMORIES converts here comes from ADDITIONAL_MEMORIES.
export AUTO_MEMORIES           = 1

# The two tightly-coupled memories the tile hardens.
#
# Hardened by ORFS's AUTO_MEMORIES path, which calls FakeRAM2.0 -- the
# same generator that produced the platform's own fakeram7_* views, and
# therefore the same generator VeeR's ICCM, DCCM and cache arrays
# already use. That is the point: the memory is 58-85 % of every point's
# power in this study, so a cross-core energy comparison cannot afford
# to have it come from two different models.
#
# The scanner cannot find these memories, and that is deliberate.
# rtl/cmj_progmem.sv is the simulation view and is not in VERILOG_FILES
# above, so the modules reach synthesis undefined and there is no
# inferred $mem to detect. ADDITIONAL_MEMORIES carries the geometry
# instead -- the mechanism variables.yaml documents as "or to describe
# one the scanner cannot find", and the same one asap7/tinyRocket uses
# for its tag and data arrays.
export ADDITIONAL_MEMORIES     = //test/coremark_joule/flow:cmj_progmem.memories

# Two macros in a design whose standard-cell half is small. Taken from
# the veer config, which is the design in this study that already had
# macros in it.
export PLACE_DENSITY_LB_ADDON  = 0.20
export MACRO_PLACE_HALO        = 2 2

# 50, not the 40 the cacheless cores used before section 5.1. The
# memories are most of the design area now, so utilization decides
# almost nothing about the standard cells and everything about how much
# empty die the clock tree has to cross.
#
# Macro placement is RTL-MP's. An earlier revision placed the two macros
# by hand because RTL-MP could not partition two of them against a
# standard-cell half this small (MPL-0045); with the data memory split
# into four byte lanes there are five, and the placer converges on its
# own. What that gives up is a placement identical across the three
# cores, so the memory's wirelength -- and the switching power in it --
# is no longer a controlled constant between them.
export CORE_UTILIZATION        = 50
export PLACE_DENSITY           = 0.65

# Metrics reporting off. This is the only line of the FAST_SETTINGS dict
# in //test:BUILD that a measurement study can take -- every other entry
# in it changes the netlist, and a study cannot buy speed with the thing
# it measures. §3.6 of the paper has the list and the reasoning.
#
# Nothing here reads ORFS's metrics: power comes from
# flow/power_grt.tcl, the achieved period from flow/period_probe.tcl,
# and auto_floorplan takes WNS from sta::worst_slack_cmd directly.
export SKIP_REPORT_METRICS     = 1
