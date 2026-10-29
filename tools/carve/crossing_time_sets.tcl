# Every crossing set top_level.tcl wrote (CROSSING_ODB_DIR), timed by
# crossing_time.tcl, each in a forked child of this process, which loads
# nothing itself: every child starts as a fresh process holding its own
# set only. CROSSING_JOBS at a time (1).
#
#   CROSSING_SETS   the sets file (crossing_plan.tcl), one set per line
#   SETS_DIR        their designs: set.<n>.odb, .sdc, .spef
#   CROSSING_TXT    the reports, CROSSING_TXT.<n>; under Bazel
#                   RUN_OUTPUT_DIR/cross.txt.<n>
#   CROSSING_TIME   crossing_time.tcl
#   CROSSING_PATHS, BUDGET_PS   as crossing_time.tcl reads them
source $::env(ORFS_FORK_TCL)
set f [open $::env(CROSSING_SETS)]
set sets {}
foreach line [split [read $f] "\n"] {
  if { [string trim $line] ne "" && ![string match "#*" $line] } {
    lappend sets [string trim $line]
  }
}
close $f
if { [info exists ::env(CROSSING_TXT)] && $::env(CROSSING_TXT) ne "" } {
  set crossing_txt $::env(CROSSING_TXT)
} else {
  set crossing_txt $::env(RUN_OUTPUT_DIR)/cross.txt
}
set jobs 1
if { [info exists ::env(CROSSING_JOBS)] && $::env(CROSSING_JOBS) ne "" } {
  set jobs $::env(CROSSING_JOBS)
}
set statuses [fork -jobs $jobs crossing_set [lsearch -all $sets *] {
  set base $::env(SETS_DIR)/set.$crossing_set
  set ::env(SET_ODB) $base.odb
  set ::env(SET_SDC) $base.sdc
  set ::env(SET_SPEF) $base.spef
  set ::env(CONE_MACROS) [lindex $sets $crossing_set]
  set ::env(CROSSING_TXT) $crossing_txt.$crossing_set
  source $::env(CROSSING_TIME)
}]
dict for {n code} $statuses {
  if { $code != 0 } {
    error "crossing_time_sets: set $n ([lindex $sets $n]) exited $code"
  }
}
