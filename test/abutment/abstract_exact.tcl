# A macro's abstract with exact obstructions: write_abstract_lef without
# -bloat_occupied_layers obstructs only what the macro's cells and wires
# occupy, so a parent macro's notch stays free for the macros that
# abut it. The timing model as ORFS writes it.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 5_1_grt.odb 5_1_grt.sdc
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing
write_abstract_lef $::env(LEF_OUT)
write_timing_model $::env(LIB_OUT)
