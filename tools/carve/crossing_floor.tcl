# How much of each crossing is wire: one crossing set (crossing_time_sets.tcl
# runs this as CROSSING_TIME), its crossing paths timed twice in one
# process with crossing_paths.tcl's search (register to register, start
# and end in different macros or through a third): as placed, and with
# every signal wire's resistance and capacitance near zero while the
# clock's wires stay as placed. What is still over the budget with no
# signal wire is not the data wires'. Both readings' parasitics are
# estimated from placement: an estimate, not the routed crossing report's
# numbers. The set's SPEF is not read.
#
# Not tools/odb_debug/headroom.tcl's zero-wire floor, which takes the
# clock's wires to zero too. A placement estimate gives a net that reaches
# a register's clock pin the signal wires' RC (OpenROAD's est,
# isNonLeafClock), so after the signal wires go to zero the platform's RC
# is put back and every net of the clock network is estimated again. Each
# end of the first reading carries its capture clock delay in both
# readings; crossing_floor_check.py requires them equal. The pins' via
# resistance stays in both readings.
#
#   SET_ODB, CONE_MACROS, PARENT_INST   as crossing_time.tcl
#   BUDGET_PS, CROSSING_DATA_MIN_PS     as crossing_paths.tcl: every
#                   crossing end over the smaller of the two is a row
#   FLOOR_CONTROL   1: the control, the signal wires as placed in the
#                   second reading too, which must then equal the first
#   CROSSING_TXT    the report: two comment lines, then one row per
#                   crossing end, worst as placed first, its fields
#                   separated by tabs:
#
#   # crossing_floor mode=<floor|control> period_ps=<p> data_min_ps=<m>
#   # placed_ps floor_ps clock_placed_ps clock_floor_ps from_macro
#     to_macro through_macros startpoint endpoint end_x end_y (one line)
#
#   placed_ps, floor_ps   the worst crossing path into the end, as placed
#                   and in the second reading; "-" when the reading has
#                   no crossing path over data_min_ps into it
#   clock_*_ps      the end's capture clock delay in that reading: in
#                   both for every end the first reading has, from the
#                   end's worst path where the second reading has no
#                   crossing path into it (the capture clock delay does
#                   not depend on the path); "-" as placed for an end
#                   only the second reading has
#   from, to, through, startpoint   the first reading's path, the
#                   second's when only it has the end
#   endpoint, end_x end_y   the end: its pin's name and its cell's place,
#                   um; several registers can share a report name
source $::env(SCRIPTS_DIR)/load.tcl
set control [env_var_or_empty FLOOR_CONTROL]
if { $control ne "" && $control ne "1" } {
  utl::error FLW 131 "crossing_floor: FLOOR_CONTROL is 1 (the control) or empty, not $control"
}
set ::env(RESULTS_DIR) [file dirname $::env(SET_ODB)]
load_design [file tail $::env(SET_ODB)]
set_propagated_clock [all_clocks]
# the clock network's nets, found before any wire changes
set clock_nets [sta::find_all_clk_nets]
log_cmd estimate_parasitics -placement
if { [env_var_exists_and_non_empty CONE_MACROS] } {
  set parent [env_var_or_empty PARENT_INST]
  if { $parent eq "" } {
    set parent u_parent
  }
  set needs [lassign [sta::crossing_cones $::env(CONE_MACROS) $parent 1 1] seeds kept before]
  puts "crossing_cones: $seeds crossing nets, $kept of $before instances kept,\
    [lindex $needs end] of them side-only starts, false paths"
}

set budget $::env(BUDGET_PS)
set period [get_property [lindex [all_clocks] 0] period]
set data_min $budget
if { [env_var_exists_and_non_empty CROSSING_DATA_MIN_PS] } {
  set data_min [expr { min($budget, $::env(CROSSING_DATA_MIN_PS)) }]
}

# crossing_paths.tcl's macro of a pin: its instance name's first level
proc macro_of { pin } {
  set name [get_full_name $pin]
  set slash [string first / $name]
  while { $slash > 0 && [string index $name [expr { $slash - 1 }]] eq "\\" } {
    set slash [string first / $name [expr { $slash + 1 }]]
  }
  if { $slash < 0 } { return "" }
  return [string range $name 0 [expr { $slash - 1 }]]
}

# crossing_paths.tcl's place of a pin: its cell's lower left, um
proc place_of { pin } {
  if { [catch { set it [sta::sta_to_db_pin $pin] }] || $it eq "NULL" || $it eq "" } {
    return "- -"
  }
  set b [[$it getInst] getBBox]
  return "[expr { [$b xMin] / 1000.0 }] [expr { [$b yMin] / 1000.0 }]"
}

# One reading: each crossing end over data_min with its worst crossing
# path, keyed by the end's name and place: {need clock from to through
# start pin}, ps, pin the end's.
proc floor_reading { period data_min } {
  set ends [dict create]
  foreach path [find_timing_paths -path_delay max -group_path_count 1000000 \
                  -endpoint_path_count 1 -slack_max [expr { $period - $data_min }]] {
    set start [get_property $path startpoint]
    set end [get_property $path endpoint]
    if { [$start is_top_level_port] || [$end is_top_level_port] } {
      continue
    }
    set from [macro_of $start]
    set to [macro_of $end]
    set through {}
    foreach point [get_property $path points] {
      set m [macro_of [get_property $point pin]]
      if { $m ne "" && $m ne $from && $m ne $to && $m ni $through } {
        lappend through $m
      }
    }
    if { $from eq $to && $through eq {} } {
      continue
    }
    set need [expr { $period - [get_property $path slack] }]
    set key [list [get_full_name $end] [place_of $end]]
    if { [dict exists $ends $key] && [lindex [dict get $ends $key] 0] >= $need } {
      continue
    }
    set through_text [expr { [llength $through] ? [join [lsort $through] ,] : "-" }]
    dict set ends $key [list $need [sta::time_sta_ui [$path target_clk_delay]] \
      $from $to $through_text [get_full_name $start] $end]
  }
  return $ends
}

proc floor_worst { ends } {
  set worst ""
  dict for {key e} $ends {
    if { $worst eq "" || [lindex $e 0] > $worst } {
      set worst [lindex $e 0]
    }
  }
  return [expr { $worst eq "" ? "none" : [format "%.1f ps" $worst] }]
}

set t0 [clock seconds]
set placed [floor_reading $period $data_min]
puts "crossing_floor: as placed, [dict size $placed] crossing ends over\
  $data_min ps, worst [floor_worst $placed], [expr { [clock seconds] - $t0 }] s"

if { $control eq "" } {
  set mode floor
  set_wire_rc -signal -resistance 1e-9 -capacitance 1e-9
} else {
  set mode control
}
log_cmd estimate_parasitics -placement
# the platform's RC back, as load_design set it, and the clock network
# estimated again with it: its leaf nets went to zero with the signal
# wires
if { [env_var_exists_and_non_empty LAYER_PARASITICS_FILE] } {
  source $::env(LAYER_PARASITICS_FILE)
} else {
  source $::env(PLATFORM_DIR)/setRC.tcl
}
foreach net $clock_nets {
  est::estimate_parasitic_net [sta::db_net_to_sta $net]
}
puts "crossing_floor: [llength $clock_nets] clock nets estimated as placed"
set t0 [clock seconds]
set again [floor_reading $period $data_min]
puts "crossing_floor: $mode, [dict size $again] crossing ends over\
  $data_min ps, worst [floor_worst $again], [expr { [clock seconds] - $t0 }] s"

# the second reading's capture clock delay of each end the first reading
# has and the second does not, from the end's worst path: one search for
# them all
set unread {}
dict for { key e } $placed {
  if { ![dict exists $again $key] } {
    lappend unread [lindex $e 6]
  }
}
set clock_again [dict create]
if { $unread ne {} } {
  foreach path [find_timing_paths -path_delay max -to $unread \
                  -group_path_count 1000000 -endpoint_path_count 1] {
    set end [get_property $path endpoint]
    dict set clock_again [list [get_full_name $end] [place_of $end]] \
      [sta::time_sta_ui [$path target_clk_delay]]
  }
}
puts "crossing_floor: [llength $unread] ends as placed with no crossing path\
  over $data_min ps in the second reading, [dict size $clock_again] of them\
  given their capture clock delay by their worst path"

# a reading's field of an end, ps, or "-" when the reading has no path
proc floor_ps { e i } {
  if { $e eq "" } {
    return "-"
  }
  return [format %.1f [lindex $e $i]]
}

set rows {}
set clock_changed 0
foreach key [lsort -unique [concat [dict keys $placed] [dict keys $again]]] {
  set p ""
  set a ""
  if { [dict exists $placed $key] } {
    set p [dict get $placed $key]
  }
  if { [dict exists $again $key] } {
    set a [dict get $again $key]
  }
  if { $p ne "" } {
    lassign $p need clock from to through start
    set order $need
  } else {
    lassign $a need clock from to through start
    set order -1
  }
  set clock_a [floor_ps $a 1]
  if { $a eq "" && [dict exists $clock_again $key] } {
    set clock_a [format %.1f [dict get $clock_again $key]]
  }
  if { $p ne "" && $clock_a ne "-" && [floor_ps $p 1] ne $clock_a } {
    incr clock_changed
  }
  lassign $key end place
  lappend rows [list $order [join [list [floor_ps $p 0] [floor_ps $a 0] \
    [floor_ps $p 1] $clock_a $from $to $through $start $end $place] "\t"]]
}
set f [open $::env(CROSSING_TXT) w]
puts $f "# crossing_floor mode=$mode period_ps=$period data_min_ps=$data_min"
puts $f "# placed_ps\tfloor_ps\tclock_placed_ps\tclock_floor_ps\tfrom_macro\tto_macro\tthrough_macros\tstartpoint\tendpoint\tend_x end_y"
foreach row [lsort -real -decreasing -index 0 $rows] {
  puts $f [lindex $row 1]
}
close $f
puts "crossing_floor: [llength $rows] crossing ends in $::env(CROSSING_TXT),\
  the capture clock delay differs between the readings at $clock_changed"
