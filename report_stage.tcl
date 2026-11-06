# The <stage>_report target: ORFS's report_metrics on a stage's saved
# .odb/.sdc, in a process of its own (docs/performance.md).
#
# The stage builds with SKIP_REPORT_METRICS=1 and goes straight on to the
# next one; the timing, power and area metrics are built here, only when
# asked for, and in parallel with the rest of the flow. A stage's
# report_metrics reads nothing that its .odb, its .sdc and the parasitics
# redone below do not hold: test/metrics_split checks the two agree.
#
# Read by this script, not by ORFS (orfs_flow sets them):
#   REPORT_ODB, REPORT_SDC  the stage's saved results
#   REPORT_PARASITICS       placement, global_routing or spef
#   REPORT_METRICS_STAGE    the stage's metrics prefix, e.g. cts
#   REPORT_NUM, REPORT_WHEN report_metrics's stage and when, as in-stage
#   REPORT_FLAGS            report_metrics's include_erc/include_clock_skew
#   REPORT_JSON, REPORT_RPT the outputs, relative to WORK_HOME

source $::env(SCRIPTS_DIR)/load.tcl

set json [file join $::env(WORK_HOME) $::env(REPORT_JSON)]
utl::open_metrics $json
utl::set_metrics_stage "$::env(REPORT_METRICS_STAGE)__{}"

load_design $::env(REPORT_ODB) $::env(REPORT_SDC)

switch $::env(REPORT_PARASITICS) {
  placement {
    log_cmd estimate_parasitics -placement
  }
  global_routing {
    log_cmd estimate_parasitics -global_routing
  }
  spef {
    log_cmd read_spef $::env(RESULTS_DIR)/6_final.spef
  }
  default {
    error "report_stage.tcl: unknown REPORT_PARASITICS\
      '$::env(REPORT_PARASITICS)'"
  }
}

# report_metrics writes its .rpt under REPORTS_DIR with a name made from
# REPORT_WHEN, the stage's own report name: keep it out of the stage's
# reports and rename it to the declared output.
set ::env(REPORTS_DIR) [file join $::env(WORK_HOME) $::env(REPORT_RPT).d]
file mkdir $::env(REPORTS_DIR)
set ::env(SKIP_REPORT_METRICS) 0
report_metrics $::env(REPORT_NUM) $::env(REPORT_WHEN) {*}$::env(REPORT_FLAGS)
file rename -force \
  [file join $::env(REPORTS_DIR) \
    "$::env(REPORT_NUM)_[string map {" " "_"} $::env(REPORT_WHEN)].rpt"] \
  [file join $::env(WORK_HOME) $::env(REPORT_RPT)]

utl::close_metrics $json
