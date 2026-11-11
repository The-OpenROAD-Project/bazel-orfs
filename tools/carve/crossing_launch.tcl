# How much earlier the flops that launch a crossing set's crossings over
# BUDGET_PS could be clocked, and what that would take: plain timing, the
# set loaded as crossing_time.tcl loads it, nothing moved.
#
# For each launching flop: the worst crossing it launches; the worst setup
# slack at its own D pins (an earlier clock captures earlier too); the
# worst hold slack of the paths it launches (they arrive earlier); the
# room, the smaller of the two and never below zero; and the bound, its
# worst crossing less the room. A hold-limited room grows towards the setup
# limit if the short paths are padded, so with HOLD_TO each launcher's
# fanout endpoints are counted by the hold slack of its worst path to each,
# under 100, 300 and HOLD_TO ps, with the delay that raises them all to
# HOLD_TO. On an XSTile crossing set, three flops launched all 14,511
# failing crossings; the worst was hold-limited to 80 ps with 612 ps of
# setup room, and 231 of its 30,303 fanout endpoints were under 600 ps.
#
#   SET_ODB, SET_SPEF, CONE_MACROS, PARENT_INST   as crossing_time.tcl
#   BUDGET_PS    the crossings that count: those over it
#   HOLD_TO      count the fanout up to this hold slack, ps (0: no count)
#   CROSSING_TXT one JSON object: the set, then one entry per launcher
source $::env(SCRIPTS_DIR)/load.tcl
set ::env(RESULTS_DIR) [file dirname $::env(SET_ODB)]
load_design [file tail $::env(SET_ODB)]
set_propagated_clock [all_clocks]
read_spef $::env(SET_SPEF)
if { [env_var_exists_and_non_empty CONE_MACROS] } {
  set parent [env_var_or_empty PARENT_INST]
  if { $parent eq "" } {
    set parent u_parent
  }
  sta::crossing_cones $::env(CONE_MACROS) $parent 1 1
}
set budget $::env(BUDGET_PS)
set hold_to [expr { [env_var_exists_and_non_empty HOLD_TO] ? $::env(HOLD_TO) : 0 }]

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

proc min_slack { pins prop } {
  set m ""
  foreach p $pins {
    set s [get_property $p $prop]
    if { $s ne "" && ($m eq "" || $s < $m) } { set m $s }
  }
  return $m
}

# the crossing paths over the budget, as crossing_paths.tcl selects them,
# and each launching flop's worst
set period [get_property [lindex [all_clocks] 0] period]
set launchers {}
set worst [dict create]
set crossings 0
foreach path [find_timing_paths -path_delay max -group_path_count 1000000 \
                -endpoint_path_count 1 -slack_max [expr { $period - $budget }]] {
  set start [get_property $path startpoint]
  set end [get_property $path endpoint]
  if { [$start is_top_level_port] || [$end is_top_level_port] } { continue }
  set from [macro_of $start]
  set crossing [expr { $from ne [macro_of $end] }]
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
  set n [get_full_name $start]
  if { ![dict exists $worst $n] } {
    lappend launchers $start
    dict set worst $n $slack
  } elseif { $slack < [dict get $worst $n] } {
    dict set worst $n $slack
  }
}

# JSON: a number, null for an unconstrained pin's INF or none, or a string
proc jnum { v } {
  if { $v eq "" || ![string is double -strict $v] || !(abs($v) < 1e300) } {
    return null
  }
  return $v
}
proc jstr { v } {
  return "\"[string map {\\ \\\\ \" \\\"} $v]\""
}

set entries {}
foreach sp $launchers {
  set c [get_cells -of_objects $sp]
  set ck [get_pins -quiet -of_objects $c -filter "is_register_clock == 1"]
  set d [get_pins -quiet -of_objects $c -filter "direction == input && is_register_clock == 0"]
  set q [get_pins -quiet -of_objects $c -filter "direction == output"]
  set crossing_ps [expr { $period - [dict get $worst [get_full_name $sp]] }]
  set setup_d [min_slack $d slack_max]
  set hold_q [min_slack $q slack_min]
  set room ""
  set bound ""
  if { $setup_d ne "" && $hold_q ne "" } {
    set room [expr { max(0.0, min($setup_d, $hold_q)) }]
    set bound [expr { $crossing_ps - $room }]
  }
  set e [list "\"flop\": [jstr [get_full_name $c]]" \
    "\"crossing_ps\": [jnum $crossing_ps]" "\"setup_d\": [jnum $setup_d]" \
    "\"hold_fanout\": [jnum $hold_q]" "\"room\": [jnum $room]" \
    "\"bound\": [jnum $bound]"]
  if { $hold_to > 0 && [llength $ck] == 1 } {
    set n 0
    set under {0 0 0}
    set pad 0.0
    foreach pe [find_timing_paths -from $ck -path_delay min \
                  -endpoint_path_count 1 -unique_paths_to_endpoint \
                  -group_path_count [sta::endpoint_count]] {
      set h [get_property $pe slack]
      incr n
      set i 0
      foreach lim [list 100 300 $hold_to] {
        if { $h < $lim } { lset under $i [expr { [lindex $under $i] + 1 }] }
        incr i
      }
      if { $h < $hold_to } { set pad [expr { $pad + $hold_to - $h }] }
    }
    lappend e "\"fanout\": $n" "\"hold_under_100\": [lindex $under 0]" \
      "\"hold_under_300\": [lindex $under 1]" \
      "\"hold_under_to\": [lindex $under 2]" "\"pad_ps\": [jnum $pad]"
  }
  lappend entries "{[join $e {, }]}"
}
set out "{\"set_odb\": [jstr [file tail $::env(SET_ODB)]], \"budget\": $budget,\
  \"hold_to\": $hold_to, \"crossings\": $crossings,\
  \"launchers\": \[[join $entries {, }]\]}"
set f [open $::env(CROSSING_TXT) w]
puts $f $out
close $f
puts $out
