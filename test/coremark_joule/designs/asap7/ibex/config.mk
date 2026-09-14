export PLATFORM                = asap7

export DESIGN_NAME             = cmj_ibex
export DESIGN_NICKNAME         = ibex

# SystemVerilog, so this design needs the slang frontend rather than
# yosys's own Verilog reader.
export VERILOG_FILES           = @ibex//:rtl //test/coremark_joule/rtl:cmj_ibex.sv
export SDC_FILE                = $(DESIGN_HOME)/asap7/ibex/constraints.sdc
export SYNTH_HDL_FRONTEND      = slang

# NOT YET WORKING. slang fails with a bare "Compilation failed" and no
# per-file diagnostic. The likely cause is include paths: ibex sources
# `include "prim_assert.sv" and "dv_fcov_macros.svh", which the Verilator
# build is given through verilog_library's `includes` but which nothing
# here supplies to the flow. VERILOG_INCLUDE_DIRS is the variable, and
# the awkward part is that the directories live inside an external
# repository, so the path is a bazel-mangled one rather than anything
# $(DESIGN_HOME) can reach.
#
# ibex's CoreMark/MHz is measured and unaffected -- that comes from
# simulation. Only its energy number waits on this.

# ibex's pipeline stages are modules, so the kept list reads as a
# pipeline: fetch, decode, execute, load/store, register file, CSR.
export SYNTH_HIERARCHICAL      = 1
export SYNTH_KEEP_MODULES      = ibex_if_stage ibex_prefetch_buffer ibex_fetch_fifo \
                                 ibex_id_stage ibex_decoder ibex_compressed_decoder \
                                 ibex_controller ibex_ex_block ibex_alu \
                                 ibex_multdiv_fast ibex_load_store_unit \
                                 ibex_register_file_ff ibex_cs_registers ibex_counter

export AUTO_MEMORIES           = 1

export CORE_UTILIZATION        = 40
export PLACE_DENSITY           = 0.65
