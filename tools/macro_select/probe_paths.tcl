# Boundary probe, timing half. Run in an odb-debug session with timing on
# a hierarchical synthesis ODB, after `repair_design` has buffered it
# (synthesis-stage slack is a fanout artefact until then). Dumps the
# PROBE_COUNT (default 20000) worst path ends of every group as one line
# each to PROBE_OUT:
#
#   <slack ps> <pins on the path> <endpoint pin> <startpoint pin>
#
# The startpoint is the first pin of the path after the clock network,
# the launching register's clock pin or an input port. Module attribution
# from instance names is timing_table.py's job.
set out [open $::env(PROBE_OUT) w]
set count [expr { [info exists ::env(PROBE_COUNT)] ? $::env(PROBE_COUNT) : 20000 }]
set ends [sta::find_timing_paths -path_delay max -group_path_count $count -sort_by_slack]
set n 0
foreach pe $ends {
  set p [$pe path]
  set pins [$p pins]
  set endp [sta::get_full_name [$pe pin]]
  # pins run from the endpoint back to the clock source; the launch is the
  # last pin that is not a top-level clock port
  set start ""
  for { set i [expr { [llength $pins] - 1 }] } { $i >= 0 } { incr i -1 } {
    set name [sta::get_full_name [lindex $pins $i]]
    if { [string first "/" $name] >= 0 } { set start $name; break }
  }
  if { $start eq "" } { set start [sta::get_full_name [lindex $pins end]] }
  puts $out "[format %.1f [expr { [$pe slack] * 1e12 }]] [llength $pins] $endp $start"
  incr n
}
close $out
puts "paths: $n path ends written to $::env(PROBE_OUT)"
