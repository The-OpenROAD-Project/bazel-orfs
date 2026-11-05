# Every crossing set top_level.tcl wrote, measured by crossing_headroom.tcl,
# each in a fresh openroad of its own with every thread, one after another.
# Not crossing_time_sets.tcl's fork: a forked child runs OpenSTA on one
# thread (fork.tcl says why), and the headroom tools ask for many periods
# of a whole set, hours each on one thread for XSTile's.
#
#   CROSSING_SETS   the sets file (crossing_plan.tcl), one set per line
#   SETS_DIR        their designs: set.<n>.odb, .sdc, .spef
#   CROSSING_TXT    the reports, CROSSING_TXT.<n>; under Bazel
#                   RUN_OUTPUT_DIR/cross.txt.<n>
#   CROSSING_TIME   crossing_headroom.tcl
#   HR_SETS         the set numbers to measure; empty: every set
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
set which [lsearch -all $sets *]
if { [info exists ::env(HR_SETS)] && [string trim $::env(HR_SETS)] ne "" } {
  set which $::env(HR_SETS)
}
foreach n $which {
  if { $n < 0 || $n >= [llength $sets] } {
    error "crossing_headroom_sets: no set $n, the sets file has [llength $sets]"
  }
  set base $::env(SETS_DIR)/set.$n
  set ::env(SET_ODB) $base.odb
  set ::env(SET_SDC) $base.sdc
  set ::env(SET_SPEF) $base.spef
  set ::env(CONE_MACROS) [lindex $sets $n]
  set ::env(CROSSING_TXT) $crossing_txt.$n
  puts "crossing_headroom_sets: set $n ([lindex $sets $n])"
  flush stdout
  exec [info nameofexecutable] -exit -no_init -no_splash -threads max \
    $::env(CROSSING_TIME) >@ stdout 2>@ stderr
}
