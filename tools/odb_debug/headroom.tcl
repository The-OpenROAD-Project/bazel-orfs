# Repair headroom: how much of a stage's reg2reg period is left on the table,
# and in which kind of move. The .claude/skills/repair-headroom skill says
# when to ask and how to read the answers.
#
# Every proc measures; none changes the design for good. A what-if (a clock
# latency per flop, a threshold-voltage swap, wires at zero) is undone
# before the proc returns, and the period is measured again to prove it.
# Only OpenSTA commands are used, except hr_floor_wire's re-estimation, so
# the same procs time a stitched view of a parent and its blocks in a bare
# OpenSTA session as they time a stage in the odb-debug daemon.
#
# Scope: the cones of the `ends` worst reg2reg endpoints; 0, the default,
# is every endpoint. Skew needs the flops around the violations free to
# move: riscv32i's 1,017 violating endpoints scoped to the worst 1,000 left
# its skew at 613.8 ps instead of 562.2. Scope a very large design only to
# make it answer at all, and say so with the number. Each proc returns a
# Tcl dict.

# Register to register: every flop's clock pin to every flop's data pin.
# The SDC's IO constraints are not part of the question.
proc hr_r2r {} {
  return [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
}

proc hr_clock_period {} {
  return [get_property [lindex [all_clocks] 0] period]
}

# The reg2reg period (clock period minus the worst reg2reg slack), its
# violating endpoints and their total negative slack. The worst slack is
# taken over every endpoint's own worst path: the single worst-path search
# was seen to differ by a few ps between two calls on an unchanged design.
proc hr_period {} {
  set worst ""
  set viol 0
  set tns 0.0
  set ends [find_timing_paths {*}[hr_r2r] -endpoint_path_count 1 \
    -group_path_count [sta::endpoint_count] -unique_paths_to_endpoint]
  foreach pe $ends {
    set s [get_property $pe slack]
    if { $worst eq "" || $s < $worst } { set worst $s }
    if { $s < 0 } {
      incr viol
      set tns [expr { $tns + $s }]
    }
  }
  if { $worst eq "" } {
    error "no reg2reg paths: is the clock defined and propagated to registers?"
  }
  return [dict create period [expr { [hr_clock_period] - $worst }] \
    clock_period [hr_clock_period] endpoints [llength $ends] \
    violating $viol tns $tns]
}

# The `count` worst reg2reg path ends; 0 is all of them.
proc hr_worst_ends { count } {
  if { $count <= 0 } { set count [sta::endpoint_count] }
  return [find_timing_paths {*}[hr_r2r] -sort_by_slack -endpoint_path_count 1 \
    -group_path_count $count -unique_paths_to_endpoint]
}

# A register cell's pins: its clock pin, its other inputs, its outputs.
proc hr_flop_pins { cell } {
  set ck [get_pins -quiet -of_objects $cell -filter "is_register_clock == 1"]
  set d [get_pins -quiet -of_objects $cell -filter "direction == input && is_register_clock == 0"]
  set q [get_pins -quiet -of_objects $cell -filter "direction == output"]
  return [list $ck $d $q]
}

# The flops at either end of the `ends` worst reg2reg paths.
proc hr_worst_flops { ends } {
  set seen [dict create]
  set flops {}
  foreach pe [hr_worst_ends $ends] {
    foreach pin [list [get_property $pe startpoint] [get_property $pe endpoint]] {
      set c [get_cells -of_objects $pin]
      set n [get_full_name $c]
      if { ![dict exists $seen $n] } {
        dict set seen $n 1
        lappend flops $c
      }
    }
  }
  return $flops
}

proc hr_min_slack { pins prop } {
  set m ""
  foreach p $pins {
    set s [get_property $p $prop]
    if { $s ne "" && ($m eq "" || $s < $m) } { set m $s }
  }
  return $m
}

# The one-flop-loop floor: the worst path from a flop back to itself, over
# the flops of the `ends` worst paths. Neither clock skew nor retiming can
# make a loop through one register shorter than its own delay, so the
# period cannot go below this whatever they do; on the designs measured so
# far, useful skew landed within 1 % of it.
proc hr_floor_cycles { {ends 0} } {
  set p [hr_clock_period]
  set worst ""
  set at ""
  set loops 0
  foreach c [hr_worst_flops $ends] {
    lassign [hr_flop_pins $c] ck d q
    if { [llength $ck] != 1 || ![llength $d] } { continue }
    set pe [lindex [find_timing_paths -from $ck -to $d -group_path_count 1] 0]
    if { $pe eq "" } { continue }
    incr loops
    set per [expr { $p - [get_property $pe slack] }]
    if { $worst eq "" || $per > $worst } {
      set worst $per
      set at [get_full_name $c]
    }
  }
  return [dict create floor $worst flop $at loops $loops]
}

# Useful skew, in timing only: each flop of the `ends` worst paths gets its
# clock arrival shifted (an ideal latency on its clock pin, set to its own
# arrival plus a delta), balanced by damped Jacobi slack balancing: a flop
# moves half way towards the point where its worst path in and its worst
# path out have the same slack. With hold, every round ends by pulling back
# each flop whose own move broke hold, by what it broke. The latencies are
# removed before returning. The answer is what a clock tree that delivered
# those arrivals would give, not a tree anyone has built.
proc hr_skew { {ends 0} {hold 1} {iters 60} {blocks {}} } {
  set p [hr_clock_period]
  set flops {}
  foreach c [hr_worst_flops $ends] {
    lassign [hr_flop_pins $c] ck d q
    if { [llength $ck] != 1 || ![llength $d] || ![llength $q] } { continue }
    set amax [get_property $ck arrival_max_rise]
    set amin [get_property $ck arrival_min_rise]
    if { $amax eq "" || $amin eq "" } { continue }
    lappend flops [list $ck $d $q $amin $amax]
  }
  set n [llength $flops]
  set delta [lrepeat $n 0.0]
  set start [dict get [hr_period] period]
  set best $start
  set stall 0
  set rounds 0
  for { set it 1 } { $it <= $iters && $n } { incr it } {
    incr rounds
    set moves {}
    for { set i 0 } { $i < $n } { incr i } {
      lassign [lindex $flops $i] ck d q amin amax
      set sin [hr_min_slack $d slack_max]
      set sout [hr_min_slack $q slack_max]
      if { $sin eq "" || $sout eq "" } { continue }
      # a later capture clock helps the path in and hurts the path out
      set step [expr { 0.25 * ($sout - $sin) }]
      if { $hold } {
        if { $step > 0 } {
          set h [hr_min_slack $d slack_min]
          if { $h ne "" } { set step [expr { min($step, max(0.0, $h)) }] }
        } else {
          set h [hr_min_slack $q slack_min]
          if { $h ne "" } { set step [expr { max($step, -max(0.0, $h)) }] }
        }
      }
      if { abs($step) > 1e-4 * $p } { lappend moves $i $step }
    }
    foreach { i step } $moves {
      lset delta $i [expr { [lindex $delta $i] + $step }]
      hr_set_latency [lindex $flops $i] [lindex $delta $i]
    }
    if { $hold } { hr_skew_hold_back $flops delta }
    set w [dict get [hr_period] period]
    if { $w < $best - 1e-3 * $p } {
      set best $w
      set stall 0
    } else {
      incr stall
    }
    if { $w < $best } { set best $w }
    if { $stall >= 5 } { break }
  }
  set holdslack ""
  set hp [lindex [find_timing_paths {*}[hr_r2r] -path_delay min -sort_by_slack \
    -group_path_count 1] 0]
  if { $hp ne "" } { set holdslack [get_property $hp slack] }
  # where the arrivals moved: in the parent's clock tree, or inside a
  # block, whose own CTS would have to deliver them
  set dmin 0.0
  set dmax 0.0
  set moved_parent 0
  set moved_block 0
  for { set i 0 } { $i < $n } { incr i } {
    set v [lindex $delta $i]
    set dmin [expr { min($dmin, $v) }]
    set dmax [expr { max($dmax, $v) }]
    if { abs($v) <= 1e-4 * $p } { continue }
    if { [hr_in_blocks [get_full_name [lindex $flops $i 0]] $blocks] } {
      incr moved_block
    } else {
      incr moved_parent
    }
  }
  foreach f $flops {
    lassign $f ck
    unset_clock_latency $ck
  }
  set after [dict get [hr_period] period]
  return [dict create start $start skew $best flops $n rounds $rounds \
    moved_parent $moved_parent moved_block $moved_block \
    delta_min $dmin delta_max $dmax hold_slack $holdslack restored $after]
}

# Whether an instance or pin path lies inside one of the block instance
# paths in `blocks`.
proc hr_in_blocks { name blocks } {
  foreach b $blocks {
    if { [string first "$b/" $name] == 0 } { return 1 }
  }
  return 0
}

proc hr_set_latency { flop delta } {
  lassign $flop ck d q amin amax
  set_clock_latency -max [expr { $amax + $delta }] $ck
  set_clock_latency -min [expr { $amin + $delta }] $ck
}

# Hold after simultaneous moves: a flop whose own move broke hold is pulled
# back by what it broke, until no move breaks it (or five passes).
proc hr_skew_hold_back { flops delta_var } {
  upvar $delta_var delta
  for { set pass 0 } { $pass < 5 } { incr pass } {
    set fixes 0
    for { set i 0 } { $i < [llength $flops] } { incr i } {
      set dv [lindex $delta $i]
      if { $dv == 0 } { continue }
      lassign [lindex $flops $i] ck d q
      set back 0
      if { $dv > 0 } {
        set h [hr_min_slack $d slack_min]
        if { $h ne "" && $h < 0 } { set back [expr { max($h, -$dv) }] }
      } else {
        set h [hr_min_slack $q slack_min]
        if { $h ne "" && $h < 0 } { set back [expr { min(-$h, -$dv) }] }
      }
      if { $back != 0 } {
        lset delta $i [expr { $dv + $back }]
        hr_set_latency [lindex $flops $i] [lindex $delta $i]
        incr fixes
      }
    }
    if { !$fixes } { break }
  }
}

# A cell's twin at another threshold voltage, by name. asap7 names its VTs
# by suffix: _ASAP7_75t_R (RVT), _L (LVT), _SL (SLVT), fastest last.
proc hr_vt_order {} { return {R L SL} }
proc hr_vt_of { ref } {
  if { [regexp {^(.*_ASAP7_75t_)(R|L|SL)$} $ref -> stem vt] } { return [list $stem $vt] }
  return {}
}

# CTS's cells, and the registers and clock gates themselves, keep their
# VT: a swap there would move a clock arrival and act as skew.
proc hr_vt_keep { cell ref } {
  set leaf [lindex [split [get_full_name $cell] /] end]
  return [expr { [regexp {^(clkbuf|clkload|delaybuf|clone_clk)} $leaf]
    || [regexp {^(ICG|DFF|DHL|DLL|SDF|ASYNC)} $ref] }]
}

# The design's leakage power in watts (OpenSTA's power with its default
# activities), or "" when it cannot be computed. Leakage does not depend
# on activity, so the defaults do not matter for it.
proc hr_leakage {} {
  if { [catch { lindex [sta::design_power [sta::cmd_scene]] 2 } leak] } {
    return ""
  }
  return $leak
}

# Threshold-voltage headroom: every data cell in the fanin cones of the
# `ends` worst reg2reg endpoints moved to the fastest VT that is loaded, the
# period measured, every cell put back. `blocks` are instance paths whose
# cells are counted apart (a stitched view: those belong to the blocks' own
# repair, not the parent's); with `parent_only` they are not swapped.
# What it costs is the leakage before, with the swap, and after the undo.
proc hr_vt { {ends 0} {blocks {}} {parent_only 0} } {
  set start [dict get [hr_period] period]
  set leak_start [hr_leakage]
  set order [hr_vt_order]
  set eps {}
  foreach pe [hr_worst_ends $ends] { lappend eps [get_property $pe endpoint] }
  set swapped {}
  set n_parent 0
  set n_block 0
  set already_fastest 0
  set have_vts [dict create]
  foreach c [get_fanin -to $eps -flat -only_cells] {
    set ref [get_property $c ref_name]
    set sv [hr_vt_of $ref]
    if { ![llength $sv] } { continue }
    lassign $sv stem vt
    dict set have_vts $vt 1
    if { [hr_vt_keep $c $ref] } { continue }
    set in_block [hr_in_blocks [get_full_name $c] $blocks]
    if { $in_block && $parent_only } { continue }
    set to ""
    foreach v [lreverse $order] {
      if { $v eq $vt } { break }
      set lc [get_lib_cells -quiet */$stem$v]
      if { [llength $lc] } {
        set to [lindex $lc 0]
        break
      }
    }
    if { $to eq "" } {
      incr already_fastest
      continue
    }
    lappend swapped [list $c [get_lib_cells */$ref]]
    replace_cell $c $to
    if { $in_block } { incr n_block } else { incr n_parent }
  }
  hr_update_parasitics
  set after [dict get [hr_period] period]
  set leak_vt [hr_leakage]
  foreach s $swapped {
    lassign $s c lc
    replace_cell $c [lindex $lc 0]
  }
  hr_update_parasitics
  set restored [dict get [hr_period] period]
  return [dict create start $start vt $after \
    leakage_start $leak_start leakage_vt $leak_vt leakage_restored [hr_leakage] \
    swapped_parent $n_parent \
    swapped_block $n_block already_fastest $already_fastest \
    vts_in_cones [lsort [dict keys $have_vts]] restored $restored]
}

# After a cell swap: OpenSTA deletes the reduced parasitics of every net
# that drives the swapped cell (they depend on its pin capacitance;
# ConcreteParasitics::loadPinCapacitanceChanged), and a net without
# parasitics times as a wire of zero length, which flatters every swap.
# ::hr_parasitics is the command that puts them back the way the session
# got them: the daemon re-estimates (estimate_parasitics -global_routing or
# -placement), the stitched view re-reads its SPEF. Empty: no parasitics
# to restore (a session timed without wires).
set ::hr_parasitics ""
proc hr_update_parasitics {} {
  if { $::hr_parasitics ne "" } {
    uplevel #0 $::hr_parasitics
  }
}

# The zero-wire floor, in OpenROAD: every routing layer's and the default
# wire's resistance and capacitance near zero, parasitics estimated the
# way the stage had them, the period measured, the stage's own RC put back
# and estimated again. Clock wires go to zero too, as in the flat view's
# STA_WIRES=0, so the floor carries the clock's change with it.
proc hr_floor_wire { rc_file mode } {
  set start [dict get [hr_period] period]
  set tech [ord::get_db_tech]
  foreach layer [$tech getLayers] {
    if { [$layer getType] ne "ROUTING" } { continue }
    set_layer_rc -layer [$layer getName] -resistance 1e-9 -capacitance 1e-9
  }
  set_wire_rc -signal -resistance 1e-9 -capacitance 1e-9
  set_wire_rc -clock -resistance 1e-9 -capacitance 1e-9
  estimate_parasitics -$mode
  set floor [dict get [hr_period] period]
  source $rc_file
  estimate_parasitics -$mode
  set restored [dict get [hr_period] period]
  return [dict create start $start floor $floor restored $restored]
}
