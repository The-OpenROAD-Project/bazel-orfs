# Scratch: report_metrics on a stage's saved .odb/.sdc, in a fresh process.
source $::env(SCRIPTS_DIR)/load.tcl
utl::open_metrics [file join $::env(WORK_HOME) $::env(OUT_JSON)]
utl::set_metrics_stage "$::env(MSTAGE)__{}"
load_design $::env(IN_ODB) $::env(IN_SDC)
if { $::env(PARA) == "rcx" } {
  read_spef $::env(RESULTS_DIR)/6_final.spef
} elseif { $::env(PARA) != "none" } {
  estimate_parasitics -$::env(PARA)
}
set ::env(REPORTS_DIR) $::env(WORK_HOME)
set ::env(SKIP_REPORT_METRICS) 0
report_metrics $::env(NUM) "$::env(WHEN)" {*}$::env(FLAGS)
utl::close_metrics [file join $::env(WORK_HOME) $::env(OUT_JSON)]
