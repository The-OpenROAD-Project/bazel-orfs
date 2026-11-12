# What the Top's second pass unfirms (unfirm.tcl), on the Top's floorplan
# (parent_macro.bzl, <pm>_unfirm): the cells of the crossing paths into
# the ends of TOP_UNFIRM, at TOP_UNFIRM_DEEP and TOP_UNFIRM_SIDE as the
# place step takes them, made movable by the rules unfirm::check stops
# on. Nothing is placed and nothing written but the counts.
#
# Each control below makes a stop of unfirm.tcl fire, for its reason, its
# message read back; a control that does not stop, or stops for another
# reason, stops the check (FLW 136). FLW 130, 132, 133, 134 and 135 have
# controls; FLW 22, the stranded-cells stop (ORFS's id, global_place.tcl's
# message), has none, nor has FLW 133's stop on sta's clock nets:
#   1. a selected cell fixed again: unfirm::check names it (FLW 132)
#   2. one register deeper holds the paths' cells and adds registers, back
#      and fwd each stay within both; a depth that is not a count and a
#      side that is none of the three are refused (FLW 133)
#   3. the nets that lost their route are exactly the nets of a selected
#      cell that had one, by name; one net left out of either side is
#      named (FLW 132)
#   4. unfirm::did_place on logs without the routability-driven pass,
#      without the timing-driven pass, and with both but no cell moved
#      (FLW 134)
#   5. an end pin that is not in the design, and an ends file with no end
#      (FLW 130)
#   6. the nets without a route after the unfirm, less those without one
#      before it, are exactly the nets it dropped the route of that global
#      route must route, by name; unfirm::unrouted stops on them (FLW 135)
#
#   TOP_UNFIRM, UNFIRM_TCL, TOP_UNFIRM_DEEP, TOP_UNFIRM_SIDE,
#   TOP_CLOCK_PERIOD   as top_level.tcl
#   UNFIRM_TXT   the counts and the controls, "key value" lines
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb
source $::env(UNFIRM_TCL)

set block [ord::get_db_block]
set records {}
proc record { key value } {
  lappend ::records "$key $value"
}

proc require { control ok what } {
  if { !$ok } {
    utl::error FLW 136 "unfirm_check: control $control: $what"
  }
}

# script, run in the caller, must stop with the message id, its message
# holding each of words and none of absent
proc must_raise { control id words script { absent {} } } {
  utl::redirectStringBegin
  set rc [catch { uplevel 1 $script } msg]
  set out [utl::redirectStringEnd]
  set line ""
  foreach l [split $out "\n"] {
    if { [string first "$id\]" $l] >= 0 } {
      set line [string trim $l]
    }
  }
  set ok [expr { $rc == 1 && [string first $id $msg] >= 0 && $line ne "" }]
  foreach w $words {
    if { [string first $w $line] < 0 } {
      set ok 0
    }
  }
  foreach w $absent {
    if { [string first $w $line] >= 0 } {
      set ok 0
    }
  }
  if { !$ok } {
    set got [expr { $rc ? "$msg: [string trim $out]" : "it passed" }]
    utl::error FLW 136 "unfirm_check: control $control did not stop with $id\
      for its reason ([join $words {, }]): $got"
  }
  puts "unfirm_check: control $control stopped as it must: $line"
  record control_$control $id
}

# 1 when every item of small is in large
proc within { small large } {
  foreach x $large {
    set in($x) 1
  }
  foreach x $small {
    if { ![info exists in($x)] } {
      return 0
    }
  }
  return 1
}

set deep [unfirm::env_or TOP_UNFIRM_DEEP 0]
set side [unfirm::env_or TOP_UNFIRM_SIDE both]
set groups [unfirm::read_ends $::env(TOP_UNFIRM)]
set ends {}
dict for { group its } $groups {
  lappend ends {*}$its
}
record ends [llength $ends]
record groups [dict size $groups]

# 2. the selection by depth and side, nothing unfirmed yet
unfirm::clocks
foreach { d s } { 0 both 1 both 1 back 1 fwd } {
  set c [unfirm::selection $ends $d $s]
  set sel($d,$s) [array names ::unfirm::mov]
  set regs($d,$s) [dict get $c unfirmed_registers]
  record cells_${d}_$s [llength $sel($d,$s)]
  record registers_${d}_$s $regs($d,$s)
}
require 2 [within $sel(0,both) $sel(1,both)] \
  "one register deeper does not hold every cell of the paths"
require 2 [expr { $regs(1,both) > $regs(0,both) }] \
  "one register deeper adds no register: $regs(0,both) and $regs(1,both)"
require 2 [within $sel(1,back) $sel(1,both)] "back is not within both"
require 2 [within $sel(1,fwd) $sel(1,both)] "fwd is not within both"
must_raise 2_side FLW-0133 { TOP_UNFIRM_SIDE sideways } {
  unfirm::selection $ends 1 sideways
}
must_raise 2_deep FLW-0133 { "TOP_UNFIRM_DEEP is a count of registers" "not -1" } {
  unfirm::selection $ends -1 both
}
set rows { 0 both }
if { $deep != 0 } {
  lappend rows $deep $side
}
foreach line [unfirm::census $groups $rows] {
  record census $line
}

# the nets with a route before the unfirm, and those global route must
# route that have none
lassign [unfirm::unrouted_nets] unrouted_before
foreach net [$block getNets] {
  if { [$net getSigType] in { POWER GROUND } } {
    continue
  }
  if { [llength [$net getGuides]] > 0 || [$net getWire] ne "NULL" } {
    set had($net) 1
  }
}

set counts [unfirm::apply $groups $deep $side]
dict for { key value } $counts {
  record $key $value
}
record left_firm [expr { [dict get $counts cells] - [dict get $counts unfirmed] }]

# 1. the rules held in apply; one selected cell fixed again breaks one
set names {}
foreach inst [array names ::unfirm::mov] {
  lappend names [$inst getName]
}
set name [lindex [lsort $names] 0]
set inst [$block findInst $name]
$inst setPlacementStatus FIRM
must_raise 1_rules FLW-0132 [list $name "is selected and fixed"] {
  unfirm::check ::unfirm::mov $::unfirm::guided
}
$inst setPlacementStatus PLACED
unfirm::check ::unfirm::mov $::unfirm::guided

# 3. the routes dropped: the nets that lost theirs against the nets of a
# selected cell that had one, the clock network's left out as the unfirm
# leaves it; FLW 132 on a difference
proc routes_match { lost touched } {
  foreach n $touched {
    set t($n) 1
  }
  foreach n $lost {
    set l($n) 1
  }
  set extra {}
  foreach n $lost {
    if { ![info exists t($n)] } {
      lappend extra $n
    }
  }
  set kept {}
  foreach n $touched {
    if { ![info exists l($n)] } {
      lappend kept $n
    }
  }
  if { [llength $extra] } {
    unfirm::fail "[llength $extra] nets lost their route and are on no selected cell,\
      the first [lindex [lsort $extra] 0]"
  }
  if { [llength $kept] } {
    unfirm::fail "[llength $kept] nets of a selected cell kept their route,\
      the first [lindex [lsort $kept] 0]"
  }
}
set lost {}
foreach net [array names had] {
  if { [llength [$net getGuides]] == 0 && [$net getWire] eq "NULL" } {
    lappend lost [$net getName]
  }
}
set touched {}
foreach inst [array names ::unfirm::mov] {
  foreach it [$inst getITerms] {
    set net [$it getNet]
    if { $net eq "NULL" || [info exists ::unfirm::clknet($net)] } {
      continue
    }
    if { [info exists had($net)] && ![info exists on_selected($net)] } {
      set on_selected($net) 1
      lappend touched [$net getName]
    }
  }
}
routes_match $lost $touched
require 3 [expr { [llength $lost] > 0 }] "no net lost its route"
record lost_route_nets [llength $lost]
set first [lindex [lsort $touched] 0]
must_raise 3_extra FLW-0132 [list "lost their route and are on no selected cell" $first] {
  routes_match $lost [lrange [lsort $touched] 1 end]
}
must_raise 3_kept FLW-0132 [list "kept their route" $first] {
  routes_match [lsearch -all -inline -not -exact $lost $first] $touched
}

# 6. no route after the unfirm: what it dropped and global route must route,
# with what had none before; unfirm::unrouted, which the final pass runs
# after global route, stops on them
lassign [unfirm::unrouted_nets] unrouted_after
set dropped {}
foreach net [array names had] {
  if {
    [llength [$net getGuides]] == 0 && [$net getWire] eq "NULL"
    && [unfirm::needs_route $net]
  } {
    lappend dropped [$net getName]
  }
}
foreach n $unrouted_before {
  set was_unrouted($n) 1
}
set new_unrouted {}
foreach n $unrouted_after {
  if { ![info exists was_unrouted($n)] } {
    lappend new_unrouted $n
  }
}
require 6 [expr { [llength $dropped] > 0 }] "the unfirm dropped no route global route must restore"
require 6 [within $unrouted_before $unrouted_after] \
  "a net without a route before the unfirm has one after it"
require 6 [expr { [lsort $new_unrouted] eq [lsort $dropped] }] \
  "[llength $new_unrouted] nets lost their route in the unfirm as unfirm::unrouted_nets\
  counts them, [llength $dropped] of the nets it dropped the route of need one"
record unrouted_before [llength $unrouted_before]
record unrouted_after_unfirm [llength $unrouted_after]
must_raise 6_unrouted FLW-0135 \
  [list "[llength $unrouted_after] nets of two or more pins have no route"] {
  unfirm::unrouted
}

# 4. the drivers rule on logs as global placement prints them
set passes [list \
  "\[INFO GPL-0040\] Routability pass 1: weighted congestion 0.9500 (target 1.0100),\
    0 of 195 actionable tiles overflowed (0.0%)." \
  "\[INFO GPL-0100\] Timing-driven iteration 1/2, virtual: true." \
  "\[INFO GPL-1001\] Global placement finished at iteration 412"]
set both_log [join $passes "\n"]
set read [unfirm::did_place $both_log 1 1]
require 4 [expr { [dict get $read routability_passes] == 1 && [dict get $read timing_passes] == 1
  && [dict get $read nesterov_iterations] == 412 && [dict get $read last_congestion] == 0.95 }] \
  "did_place read $read from a log of both passes"
set no_routability [join [lsearch -all -inline -not -glob $passes {*GPL-004*}] "\n"]
must_raise 4_routability FLW-0134 { "no routability-driven pass" } {
  unfirm::did_place $no_routability 1 1
} { "no timing-driven" "changed place" }
set no_timing [join [lsearch -all -inline -not -glob $passes {*GPL-0100*}] "\n"]
must_raise 4_timing FLW-0134 { "no timing-driven pass" } {
  unfirm::did_place $no_timing 1 1
} { "no routability-driven" "changed place" }
must_raise 4_moved FLW-0134 { "none of the 1 unfirmed cells changed place" } {
  unfirm::did_place $both_log 0 1
} { "no routability-driven" "no timing-driven" }

# 5. the ends file
set path $::env(OBJECTS_DIR)/unfirm_check_ends.tsv
set f [open $path w]
puts $f "check\tu_unfirm_check_none/r/D\t0.0 0.0"
close $f
must_raise 5_missing FLW-0130 { "1 end pins are not in the design" u_unfirm_check_none/r/D } {
  unfirm::read_ends $path
}
close [open $path w]
must_raise 5_empty FLW-0130 { "no end to unfirm" } {
  unfirm::read_ends $path
}
file delete $path

set f [open $::env(UNFIRM_TXT) w]
puts $f [join $records "\n"]
close $f
