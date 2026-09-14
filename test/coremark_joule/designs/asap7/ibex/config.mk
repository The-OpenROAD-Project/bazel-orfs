export PLATFORM                = asap7

export DESIGN_NAME             = cmj_ibex
export DESIGN_NICKNAME         = ibex

# SystemVerilog, so this design needs the slang frontend rather than
# yosys's own Verilog reader.
export VERILOG_FILES           = @ibex//:rtl @ibex//:hdrs //test/coremark_joule/rtl:cmj_ibex.sv
export SDC_FILE                = $(DESIGN_HOME)/asap7/ibex/constraints.sdc
export SYNTH_HDL_FRONTEND      = slang

# ibex sources `include "prim_assert.sv" and "dv_fcov_macros.svh" from
# the vendored OpenTitan tree inside the fetched archive.
#
# The directories are named by their sandbox path rather than by a label:
# an include dir is normally a package of this repository with a
# files("include") group, and a directory inside an archive has no
# package to name. The headers themselves are staged by @ibex//:hdrs in
# VERILOG_FILES below -- they are macro definitions, so slang reading
# them as sources costs nothing and guarantees they are present.
export VERILOG_INCLUDE_DIRS    = external/+http_archive+ibex/vendor/lowrisc_ip/ip/prim/rtl \
                                 external/+http_archive+ibex/vendor/lowrisc_ip/dv/sv/dv_utils

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

export AUTO_MEMORIES           = 1

export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
