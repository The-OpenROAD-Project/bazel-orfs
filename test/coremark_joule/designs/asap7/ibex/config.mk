export PLATFORM                = asap7

export DESIGN_NAME             = cmj_ibex
export DESIGN_NICKNAME         = ibex

# SystemVerilog, so this design needs the slang frontend rather than
# yosys's own Verilog reader.
# :pkgs before :rtl. The package files are a separate filegroup because
# Verilator resolves in file order and a glob is alphabetical, which puts
# ibex_alu.sv ahead of ibex_pkg.sv; the flow needs both groups listed or
# every type in those packages is an unknown identifier.
export VERILOG_FILES           = @ibex//:pkgs @ibex//:rtl //test/coremark_joule/rtl:cmj_ibex.sv
export SDC_FILE                = $(DESIGN_HOME)/asap7/ibex/constraints.sdc
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

# Off for ibex. Its register file is ibex_register_file_ff -- flops by
# construction, not an inferred memory -- so there is nothing to convert,
# and the detection pass is a slang elaboration of the whole design whose
# only product would be an empty inventory.
# export AUTO_MEMORIES         = 1

export CORE_UTILIZATION        = 40
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
