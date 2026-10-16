# Runs ORFS's generate_abstract.tcl on a copy of a stage's results and
# checks where the abstract's parasitics came from.
#
# The copy holds the src stage's ODB_FILE and SDC_FILE, e.g. 6_final.odb.
# SPEF: what 6_final.spef is in the copy: "extracted" (the stage's own),
#   "missing" or "leftover" (a file no read_spef can parse).
# EXPECT: the est::parasitics_source the abstract is timed with, or
#   "error" when generate_abstract must fail.
# COPY_SKIPPED_DETAILED_ROUTE: 1 when the copy is of a flow whose final
#   stage skipped detailed route, and so extracted no SPEF.
# OUTPUT: the file written when the case passes.

proc fail { msg } {
  puts "FAIL: $msg"
  exit 1
}

set stem [file rootname [file tail $::env(ODB_FILE)]]
set stage_results [file dirname $::env(ODB_FILE)]
set results [file join $::env(WORK_HOME) results_copy]
file mkdir $results
file copy -force $::env(ODB_FILE) $results
file copy -force $::env(SDC_FILE) [file join $results $stem.sdc]
switch $::env(SPEF) {
  extracted {
    file copy -force [file join $stage_results 6_final.spef] $results
  }
  leftover {
    set stream [open [file join $results 6_final.spef] w]
    puts $stream "a SPEF left behind by another run"
    close $stream
  }
  missing {}
  default { fail "unknown SPEF $::env(SPEF)" }
}
set ::env(RESULTS_DIR) $results
if { [info exists ::env(COPY_SKIPPED_DETAILED_ROUTE)] } {
  set ::env(SKIP_DETAILED_ROUTE) 1
}
set ::env(ABSTRACT_SOURCE) $stem

# Where the parasitics came from; an OpenROAD without 0136 cannot say.
proc parasitics_source { } {
  if { [info commands est::parasitics_source] == "" } {
    return unknown
  }
  return [est::parasitics_source]
}

set failed [catch { source $::env(SCRIPTS_DIR)/generate_abstract.tcl } msg]
if { $::env(EXPECT) == "error" } {
  if { !$failed } {
    fail "generate_abstract succeeded, timed with [parasitics_source] parasitics"
  }
  puts "generate_abstract failed as expected: $msg"
} else {
  if { $failed } {
    fail "generate_abstract failed: $msg"
  }
  set source [parasitics_source]
  if { $source != $::env(EXPECT) } {
    fail "abstract timed with $source parasitics, expected $::env(EXPECT)"
  }
  puts "abstract timed with $source parasitics"
}

set stream [open [file join $::env(WORK_HOME) $::env(OUTPUT)] w]
puts $stream ok
close $stream
