# The carve's check, on the flat top level at global route: every
# register-to-register path that needs more than BUDGET_PS, by the macros
# it starts and ends in (the first level of its instances' names, the
# instance each was dissolved from). A crossing path over the budget is
# the carve's: merge or move the two macros. A path inside one macro is
# that macro's own. CROSSING_TXT: one line per path, worst first, then a
# count of each.
# top_level.tcl sources this with its routed design loaded and estimated
if { ![info exists ::crossing_paths_loaded] } {
  source $::env(SCRIPTS_DIR)/load.tcl
  load_design 5_1_grt.odb 5_1_grt.sdc
  estimate_parasitics -global_routing
}

set budget $::env(BUDGET_PS)
set clock [lindex [all_clocks] 0]
set period [get_property $clock period]
set paths [find_timing_paths -path_delay max -group_path_count 1000000 \
  -endpoint_path_count 1 -slack_max [expr { $period - $budget }]]

# an instance name's first level, at the first divider not escaped (a
# top-level clock buffer carries its net's name, clkbuf_0_u_Rob\/...)
proc macro_of { pin } {
  set name [get_full_name $pin]
  set slash [string first / $name]
  while { $slash > 0 && [string index $name [expr { $slash - 1 }]] eq "\\" } {
    set slash [string first / $name [expr { $slash + 1 }]]
  }
  if { $slash < 0 } { return "" }
  return [string range $name 0 [expr { $slash - 1 }]]
}

set rows {}
foreach path $paths {
  set start [get_property $path startpoint]
  set end [get_property $path endpoint]
  # register to register: a port has no instance
  if { [$start is_top_level_port] || [$end is_top_level_port] } {
    continue
  }
  set need [expr { $period - [get_property $path slack] }]
  set from [macro_of $start]
  set to [macro_of $end]
  # the macros its logic passes through on the way, other than the two
  # it starts and ends in
  set through {}
  foreach point [get_property $path points] {
    set m [macro_of [get_property $point pin]]
    if { $m ne "" && $m ne $from && $m ne $to && $m ni $through } {
      lappend through $m
    }
  }
  lappend rows [list $need $from $to [get_full_name $start] [get_full_name $end] \
    [expr { [llength $through] ? [join [lsort $through] ,] : "-" }]]
}
set crossing 0
set inside 0
set f [open $::env(CROSSING_TXT) w]
puts $f "# reg2reg paths over $budget ps at global route; period $period ps"
puts $f "# need_ps kind from_macro to_macro startpoint endpoint through_macros"
foreach row [lsort -real -decreasing -index 0 $rows] {
  lassign $row need from to start end through
  # crossing: it starts and ends in different macros, or passes through
  # another macro's logic on the way
  if { $from ne $to || $through ne "-" } {
    set kind crossing
    incr crossing
  } else {
    set kind inside
    incr inside
  }
  puts $f [format "%.1f %s %s %s %s %s %s" $need $kind $from $to $start $end $through]
}
puts $f "crossing $crossing"
puts $f "inside $inside"
close $f
puts "crossing_paths: $crossing crossing and $inside inside paths over $budget ps"
