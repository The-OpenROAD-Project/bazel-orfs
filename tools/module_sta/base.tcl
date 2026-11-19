# The whole synthesised design as a hierarchical database, the baseline
# every module's timing context is cut from (context_db.tcl), and the
# liberty it is timed with. Run by orfs_run on the synthesis stage.
#
#   PSTA_BASE_DB   out: the hierarchical database
#   PSTA_LIBS_TAR  out: the liberty files, for the timing steps (libs.tcl)
#   PSTA_LIBS_TCL  libs.tcl
#
# The reading is ORFS's load_design's (load.tcl), the LEFs and liberty the
# stage reads, the netlist linked with -hier, but for its read_sdc: the
# timing steps apply a clock and nothing else, and the stage's 1_2_yosys.sdc
# is not among orfs_run's inputs. Unlike synth_odb.tcl's 1_synth.odb, no
# dead logic is eliminated: the baseline is the netlist synthesis wrote,
# the one timed flat.
source $::env(SCRIPTS_DIR)/load.tcl
source_env_var_if_exists PLATFORM_TCL
source $::env(SCRIPTS_DIR)/read_liberty.tcl
read_lef $::env(TECH_LEF)
read_lef $::env(SC_LEF)
if { [env_var_exists_and_non_empty ADDITIONAL_LEFS] } {
  foreach lef $::env(ADDITIONAL_LEFS) {
    read_lef $lef
  }
}
foreach lef [auto_memories_views .lef] {
  read_lef $lef
}
read_verilog $::env(RESULTS_DIR)/1_2_yosys.v
link_design -hier $::env(DESIGN_NAME)
write_db $::env(PSTA_BASE_DB)

source $::env(PSTA_LIBS_TCL)
