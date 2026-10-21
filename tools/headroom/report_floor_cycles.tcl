# The one-flop-loop floor, reported at the end of global route: the worst
# path from a register's clock pin back to its own data pin. No useful
# clock skew and no retiming can take the period below it, so a floor above
# the target says no clocking reaches the target, and names the register
# whose loop must get faster (its wire, its cells or its logic). Read at grt
# because that is after the last repair that changes cells: the loop's
# clock cancels, its wire and cells do not.
#
#   POST_GLOBAL_ROUTE_TCL = report_floor_cycles.tcl
#
# writes "One-flop-loop floor: <period> at <register> ..." to the log and
# the metric globalroute__timing__floor_cycles (the loop's period, in the
# liberty's time unit) beside the stage's worst slack.
#
# Exact, and cheap by a bound: a register's loop is one of the paths into
# its own data pin, so the register's endpoint period is at least its loop.
# The worst register-to-register endpoints are visited worst first, in
# growing batches, a loop search each, and the visit stops at the first
# endpoint whose period is below the worst loop found: no register after it
# can have a worse one. The same algorithm as tools/odb_debug/headroom.tcl's
# hr_floor_cycles (.claude/skills/repair-headroom).
#
# A prototype in Tcl. The loop searches are OpenSTA filtered searches, one
# per visited register; a C++ pass over the timing graph could find the
# worst loop faster, but on the designs measured so far the visit stops
# within a few thousand endpoints, noise on top of a global route.

proc report_floor_cycles {} {
  set t0 [clock milliseconds]
  set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
  set worst ""
  set worst_reg ""
  set loops 0
  set visited 0
  set seen [dict create]
  set stop ""
  set batch 1000
  set fetched 0
  while { $stop eq "" } {
    # each endpoint's period and register as values first: the next
    # find_timing_paths frees the path ends this one returned
    set order {}
    foreach pe [find_timing_paths {*}$r2r -sort_by_slack -endpoint_path_count 1 \
                  -group_path_count $batch -unique_paths_to_endpoint] {
      set clk [get_property $pe endpoint_clock]
      if { $clk eq "" } { continue }
      lappend order [expr { [get_property $clk period] - [get_property $pe slack] }] \
        [get_full_name [get_cells -of_objects [get_property $pe endpoint]]]
    }
    set n [expr { [llength $order] / 2 }]
    foreach { period reg } [lrange $order [expr { 2 * $fetched }] end] {
      if { $worst ne "" && $period < $worst } {
        set stop [format "endpoint period %.1f below the worst loop" $period]
        break
      }
      incr visited
      if { [dict exists $seen $reg] } { continue }
      dict set seen $reg 1
      set cell [get_cells $reg]
      set ck [get_pins -quiet -of_objects $cell -filter "is_register_clock == 1"]
      set d [get_pins -quiet -of_objects $cell \
               -filter "direction == input && is_register_clock == 0"]
      if { [llength $ck] != 1 || ![llength $d] } { continue }
      set loop [lindex [find_timing_paths -from $ck -to $d -group_path_count 1] 0]
      if { $loop eq "" } { continue }
      incr loops
      set lclk [get_property $loop endpoint_clock]
      set per [expr { [get_property $lclk period] - [get_property $loop slack] }]
      if { $worst eq "" || $per > $worst } {
        set worst $per
        set worst_reg $reg
      }
    }
    if { $stop eq "" } {
      if { $n < $batch } {
        set stop "every register-to-register endpoint visited"
      } else {
        set fetched $n
        set batch [expr { 4 * $batch }]
      }
    }
  }
  set secs [expr { ([clock milliseconds] - $t0) / 1000.0 }]
  if { $worst eq "" } {
    puts "One-flop-loop floor: no register loops back to itself ($visited endpoints, $secs s)"
    return
  }
  puts [format "One-flop-loop floor: %.1f at %s (%d loops, %d endpoints visited, %s; %.1f s)" \
    $worst $worst_reg $loops $visited $stop $secs]
  utl::metric_float "timing__floor_cycles" $worst
}

report_floor_cycles
