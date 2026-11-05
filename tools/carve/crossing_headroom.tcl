# How much of one crossing set's period the Top could still win, and in
# which kind of move: tools/odb_debug/headroom.tcl's measurements on the
# set's crossing paths only. The set is loaded as crossing_time.tcl loads
# it (its cones, its false starts, its parasitics read from SET_SPEF: the
# set carries no route guides to estimate from). The zero-wire what-if
# estimates from placement with every layer's RC at zero, and reads the
# SPEF back after. Every what-if is undone and the period measured again.
#
# The scope is the set's crossing paths over BUDGET_PS, found as
# crossing_paths.tcl finds them (start and end in different macros, or
# through a third): hr_r2r is narrowed to their end pins, the pin objects
# the selection found. Its period must be the selection's worst crossing,
# what crossing_time.tcl reports; it stops with an error when it is not.
#
#   SET_ODB, SET_SDC, CONE_MACROS, PARENT_INST   as crossing_time.tcl
#   HR_TCL       tools/odb_debug/headroom.tcl
#   BUDGET_PS    the target: the mass over it is what a move has to shift
#   CROSSING_TXT one JSON object, written again after every measurement,
#                so a set stopped part way says what it measured
#   HR_ENDS      the worst crossing endpoints VT and skew work on (0: all)
#   HR_ORDER     the measurements, in order (wire vt skew cycles)
#   HR_SKIP      measurements to skip, of: wire vt skew cycles
#   HR_LEAKAGE   1: VT reports the leakage before, with and after its swap.
#                Off by default: OpenSTA's power propagates activity through
#                every instance of the set on one thread, three times per
#                VT measurement, over an hour each on an XSTile set
source $::env(SCRIPTS_DIR)/load.tcl
set ::env(RESULTS_DIR) [file dirname $::env(SET_ODB)]
load_design [file tail $::env(SET_ODB)] [file tail $::env(SET_SDC)]
source $::env(HR_TCL)
set_propagated_clock [all_clocks]
set ::hr_parasitics [list read_spef $::env(SET_SPEF)]
read_spef $::env(SET_SPEF)
# zero wire: placement estimates with no RC; back: the rc and the SPEF
set mode placement
set rc_file $::env(PLATFORM_DIR)/setRC.tcl
proc hr_wires_back { rc_file mode } {
  source $rc_file
  hr_update_parasitics
}
if { [env_var_or_empty HR_LEAKAGE] ne "1" } {
  proc hr_leakage {} {
    return ""
  }
}

if { [env_var_exists_and_non_empty CONE_MACROS] } {
  set parent [env_var_or_empty PARENT_INST]
  if { $parent eq "" } {
    set parent u_parent
  }
  sta::crossing_cones $::env(CONE_MACROS) $parent 1 1
}

set budget $::env(BUDGET_PS)
set ::hr_target $budget
set ends [expr { [env_var_exists_and_non_empty HR_ENDS] ? $::env(HR_ENDS) : 0 }]
set skip [env_var_or_empty HR_SKIP]
set order [expr { [env_var_exists_and_non_empty HR_ORDER] ? $::env(HR_ORDER) : {wire vt skew cycles} }]

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

# the crossing paths over the budget, as crossing_paths.tcl selects them
set period [get_property [lindex [all_clocks] 0] period]
set starts [dict create]
set finishes [dict create]
set crossings 0
# The end pins themselves. Looked up again by their full names with
# get_pins, 9,899 of an XSTile set's 14,511 went missing, its worst among
# them, and the period read 114 ps low with no warning.
set ::hr_scope_to {}
set worst_slack ""
set worst_end ""
foreach path [find_timing_paths -path_delay max -group_path_count 1000000 \
                -endpoint_path_count 1 -slack_max [expr { $period - $budget }]] {
  set start [get_property $path startpoint]
  set end [get_property $path endpoint]
  if { [$start is_top_level_port] || [$end is_top_level_port] } { continue }
  set from [macro_of $start]
  set to [macro_of $end]
  set crossing [expr { $from ne $to }]
  if { !$crossing } {
    foreach point [get_property $path points] {
      set m [macro_of [get_property $point pin]]
      if { $m ne "" && $m ne $from } {
        set crossing 1
        break
      }
    }
  }
  if { !$crossing } { continue }
  incr crossings
  set slack [get_property $path slack]
  if { $worst_slack eq "" || $slack < $worst_slack } {
    set worst_slack $slack
    set worst_end [get_full_name $end]
  }
  dict set starts [get_full_name $start] 1
  if { ![dict exists $finishes [get_full_name $end]] } {
    lappend ::hr_scope_to $end
  }
  dict set finishes [get_full_name $end] 1
}

proc json_value { v } {
  if { [string is double -strict $v] } { return $v }
  if { [llength $v] > 1 } {
    return "\[[join [lmap x $v { json_value $x }] ,]\]"
  }
  return "\"[string map {\\ \\\\ \" \\\"} $v]\""
}
proc json_dict { d } {
  set items {}
  dict for {k v} $d { lappend items "\"$k\": [json_value $v]" }
  return "{[join $items {, }]}"
}
proc write_result { result } {
  set out "{"
  set first 1
  dict for {k v} $result {
    if { !$first } { append out ", " }
    set first 0
    if { $k in {period wire vt skew cycles} } {
      append out "\"$k\": [json_dict $v]"
    } else {
      append out "\"$k\": [json_value $v]"
    }
  }
  append out "}"
  set f [open $::env(CROSSING_TXT) w]
  puts $f $out
  close $f
  puts $out
  flush stdout
}

set result [dict create set_odb [file tail $::env(SET_ODB)] budget $budget \
  crossing_endpoints [dict size $finishes] crossing_starts [dict size $starts]]
if { $crossings == 0 } {
  dict set result note "no crossing path over the budget"
} else {
  # the selection's own worst crossing, what crossing_time.tcl reports
  dict set result crossing_period [expr { $period - $worst_slack }]
  dict set result crossing_worst_end $worst_end
  # -to only: a -from makes OpenSTA search every arrival again, filtered,
  # on one thread, for each of the many periods the headroom tools ask
  # for. The worst path to a crossing endpoint is the crossing path or a
  # worse one, so the period can only read high.
  proc hr_r2r {} {
    return [list -to $::hr_scope_to]
  }
  set t0 [clock seconds]
  set pd [hr_period]
  dict set result period $pd
  if { abs([dict get $pd period] - ($period - $worst_slack)) > 0.01 } {
    write_result $result
    error "crossing_headroom: the scope's period [dict get $pd period] ps is not\
      the worst crossing [expr { $period - $worst_slack }] ps ($worst_end):\
      the scope lost endpoints"
  }
  write_result $result
  foreach m $order {
    if { $m in $skip } { continue }
    switch -- $m {
      wire { dict set result wire [hr_floor_wire $rc_file $mode] }
      vt { dict set result vt [hr_vt $ends] }
      skew { dict set result skew [hr_skew $ends 1] }
      cycles { dict set result cycles [hr_floor_cycles $ends] }
      default { error "crossing_headroom: no measurement $m, of: wire vt skew cycles" }
    }
    dict set result seconds [expr { [clock seconds] - $t0 }]
    write_result $result
  }
}
write_result $result
