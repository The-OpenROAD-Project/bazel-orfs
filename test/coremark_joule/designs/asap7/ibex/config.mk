export PLATFORM                = asap7

export DESIGN_NAME             = cmj_ibex
export DESIGN_NICKNAME         = ibex

# SystemVerilog, so this design needs the slang frontend rather than
# yosys's own Verilog reader.
export VERILOG_FILES           = @ibex//:rtl //test/coremark_joule/rtl:cmj_ibex.sv
export SDC_FILE                = $(DESIGN_HOME)/asap7/ibex/constraints.sdc
export SYNTH_HDL_FRONTEND      = slang

# NOT YET SYNTHESIZING, and the blocker is specific.
#
# ibex sources `include "prim_assert.sv" and "dv_fcov_macros.svh", which
# live in the vendored OpenTitan tree inside the fetched archive. The
# Verilator build reaches them through verilog_library's `includes`; the
# flow wants VERILOG_INCLUDE_DIRS. config_mk_parser passes that through
# as a plain string, but the rules treat it as path-typed and turn it
# into a label -- and a directory inside a fetched archive has no label
# to become, so analysis fails with "no such package
# 'external/.../prim/rtl'".
#
# Neither obvious way out works as-is: the overlay's patch_cmds delete
# the vendored BUILD files so the root glob can cross into that tree,
# which is also what stops those directories being packages; and a
# package label would not be a directory path in any case.
#
# ibex's CoreMark/MHz is measured and unaffected -- that comes from
# simulation -- so only its energy point waits on this.

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
