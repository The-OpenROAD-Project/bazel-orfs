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

# A target period, in the liberty's time unit; 0 is none. A design whose
# SDC asks far less than anyone hopes to reach (XiangShan's tile: 473 ps
# against a 2,000 ps goal) violates at nearly every endpoint, so the
# violating count and TNS say nothing; the endpoints at or over the target
# and their excess over it are the mass a move has to shift.
set ::hr_target 0

# The reg2reg period (clock period minus the worst reg2reg slack), its
# violating endpoints and their total negative slack, and with a target
# the endpoints at or over it and their total excess. The worst slack is
# taken over every endpoint's own worst path: the single worst-path search
# was seen to differ by a few ps between two calls on an unchanged design.
proc hr_period {} {
  set worst ""
  set viol 0
  set tns 0.0
  set over 0
  set excess 0.0
  set p [hr_clock_period]
  set ends [find_timing_paths {*}[hr_r2r] -endpoint_path_count 1 \
    -group_path_count [sta::endpoint_count] -unique_paths_to_endpoint]
  foreach pe $ends {
    set s [get_property $pe slack]
    if { $worst eq "" || $s < $worst } { set worst $s }
    if { $s < 0 } {
      incr viol
      set tns [expr { $tns + $s }]
    }
    if { $::hr_target > 0 && $p - $s >= $::hr_target } {
      incr over
      set excess [expr { $excess + $p - $s - $::hr_target }]
    }
  }
  if { $worst eq "" } {
    error "no reg2reg paths: is the clock defined and propagated to registers?"
  }
  set d [dict create period [expr { $p - $worst }] \
    clock_period $p endpoints [llength $ends] violating $viol tns $tns]
  if { $::hr_target > 0 } {
    dict set d target $::hr_target
    dict set d over_target $over
    dict set d excess_target $excess
  }
  return $d
}

# The mass over the target of a period dict, as keys to merge into a
# measurement's answer; nothing without a target.
proc hr_mass { d } {
  if { $::hr_target <= 0 } { return {} }
  return [dict create over_target [dict get $d over_target] \
    excess_target [dict get $d excess_target]]
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

# The one-flop-loop floor: the worst path from a flop back to itself. Neither
# clock skew nor retiming can make a loop through one register shorter than
# its own delay, so the period cannot go below this whatever they do; on the
# designs measured so far, useful skew landed within 1 % of it.
#
# Exact, and cheap by a bound: a flop's loop is one of the paths into its own
# data pin, so the flop's endpoint period is at least its loop. The endpoints
# are visited worst first, a loop search each (find_timing_paths -from its
# clock pin -to its data pin, about 0.25 s on a 450k-instance block), and the
# visit stops at the first endpoint whose period is below the worst loop
# found: no flop after it can have a worse one. `visited` and `stop` say how
# far it went.
#
# With ends > 0 only the flops of the `ends` worst endpoints are searched,
# without the bound: the result is then a lower bound of the floor, conclusive
# only above a target (`scope` says so). XiangShan's FltRegionModule gave 213
# ps scoped to 1,000 endpoints and 762.2 ps exact.
#
# `binds` says whether the floor sets the period now (`period`, the worst
# endpoint's), and `buffers` / `through` how many buffers the worst loop has
# and the worst path through any of them. A buffer whose worst path is worse
# than the loop is a trade repair made for that path, not a mistake: moving
# the loop's sink ahead of it slows that path (.claude/skills/repair-headroom).
proc hr_floor_cycles { {ends 0} } {
  set p [hr_clock_period]
  set worst ""
  set at ""
  set loops 0
  set visited 0
  set stop "every endpoint visited"
  # each endpoint's period and flop as values first: the next
  # find_timing_paths frees the path ends this one returned
  set order {}
  foreach pe [hr_worst_ends $ends] {
    lappend order [expr { $p - [get_property $pe slack] }] \
      [get_full_name [get_cells -of_objects [get_property $pe endpoint]]]
  }
  set seen [dict create]
  foreach { period n } $order {
    if { $ends <= 0 && $worst ne "" && $period < $worst } {
      set stop [format "endpoint period %.1f below the worst loop" $period]
      break
    }
    incr visited
    if { [dict exists $seen $n] } { continue }
    dict set seen $n 1
    set c [get_cells $n]
    lassign [hr_flop_pins $c] ck d q
    if { [llength $ck] != 1 || ![llength $d] } { continue }
    set loop [lindex [find_timing_paths -from $ck -to $d -group_path_count 1] 0]
    if { $loop eq "" } { continue }
    incr loops
    set per [expr { $p - [get_property $loop slack] }]
    if { $worst eq "" || $per > $worst } {
      set worst $per
      set at $n
    }
  }
  if { $ends > 0 } {
    set scope "lower bound: the flops of the $ends worst endpoints only"
  } else {
    set scope exact
  }
  set period [expr { [llength $order] ? [lindex $order 0] : "" }]
  set binds [expr { $worst ne "" && $period ne "" && $worst >= $period - 0.05 }]
  lassign [hr_loop_buffers $at $p] buffers through
  return [dict create floor $worst flop $at loops $loops visited $visited \
    stop $stop scope $scope period $period binds $binds buffers $buffers \
    through $through]
}

# The buffers on flop n's own loop and the worst period through any of them,
# "" without a buffer.
proc hr_loop_buffers { n p } {
  if { $n eq "" } { return [list 0 ""] }
  lassign [hr_flop_pins [get_cells $n]] ck d q
  set loop [lindex [find_timing_paths -from $ck -to $d -group_path_count 1] 0]
  set names {}
  foreach pt [lrange [get_property $loop points] 1 end] {
    set pin [get_property $pt pin]
    if { [get_property $pin direction] ne "output" } { continue }
    if { [get_property [get_property [get_cells -of_objects $pin] liberty_cell] is_buffer] } {
      lappend names [get_full_name $pin]
    }
  }
  # slack queries after the walk: each searches, and frees the loop's points
  set through ""
  foreach name $names {
    set per [expr { $p - [get_property [get_pins $name] slack_max] }]
    if { $through eq "" || $per > $through } { set through $per }
  }
  return [list [llength $names] $through]
}

# Useful skew, in timing only: each flop of the `ends` worst paths gets its
# clock arrival shifted (an ideal latency on its clock pin, set to its own
# arrival plus a delta), balanced by damped Jacobi slack balancing: a flop
# moves half way towards the point where its worst path in and its worst
# path out have the same slack. With hold, every round ends by pulling back
# each flop whose own move broke hold, by what it broke. The latencies are
# removed before returning. The answer is what a clock tree that delivered
# those arrivals would give, not a tree anyone has built.
# The worst register-to-register hold slack, or "" without one.
proc hr_hold_slack {} {
  set hp [lindex [find_timing_paths {*}[hr_r2r] -path_delay min -sort_by_slack \
    -group_path_count 1] 0]
  if { $hp eq "" } { return "" }
  return [get_property $hp slack]
}

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
  # the hold the design starts with: skew promises not to make it worse,
  # not to repair a violation the design already has
  set holdstart [hr_hold_slack]
  set n [llength $flops]
  set delta [lrepeat $n 0.0]
  set pd [hr_period]
  set start [dict get $pd period]
  # Each round is judged by the paths through the flops it moves, the only
  # paths a move changes: the worst slack at their data and output pins.
  # The full measurement (every endpoint's worst path, hr_period) is taken
  # once, at the best round: on XiangShan's tile, 761,301 endpoints, it is
  # the cost of the whole design, and every round used to pay it.
  set best [hr_scope_period $flops]
  set best_delta $delta
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
    set w [hr_scope_period $flops]
    if { $w < $best - 1e-3 * $p } {
      set stall 0
    } else {
      incr stall
    }
    if { $w < $best } {
      set best $w
      set best_delta $delta
    }
    if { $stall >= 5 } { break }
  }
  # back to the best round, measured in full
  for { set i 0 } { $i < $n } { incr i } {
    if { [lindex $delta $i] != [lindex $best_delta $i] } {
      hr_set_latency [lindex $flops $i] [lindex $best_delta $i]
    }
  }
  set delta $best_delta
  set best_pd [hr_period]
  set best [dict get $best_pd period]
  if { $best > $start } {
    # moving nothing is a skew too: the rounds' best was worse in full,
    # so every flop goes back to its own arrival
    for { set i 0 } { $i < $n } { incr i } {
      if { [lindex $delta $i] != 0 } { hr_set_latency [lindex $flops $i] 0.0 }
    }
    set best $start
    set best_pd $pd
    set delta [lrepeat $n 0.0]
  }
  set holdslack [hr_hold_slack]
  # where the arrivals moved: in the parent's clock tree, or inside a
  # block, whose own CTS would have to deliver them
  set dmin 0.0
  set dmax 0.0
  set moved_parent 0
  set moved_block 0
  set by_inst [dict create]
  for { set i 0 } { $i < $n } { incr i } {
    set v [lindex $delta $i]
    set dmin [expr { min($dmin, $v) }]
    set dmax [expr { max($dmax, $v) }]
    if { abs($v) <= 1e-4 * $p } { continue }
    set pin [get_full_name [lindex $flops $i 0]]
    if { [hr_in_blocks $pin $blocks] } {
      incr moved_block
    } else {
      incr moved_parent
    }
    # the instance the flop sits in: its name up to the last two levels
    # (the flop, its pin)
    set inst [join [lrange [split $pin /] 0 end-2] /]
    if { $inst eq "" } { set inst "(top)" }
    dict update by_inst $inst m {
      if { ![info exists m] } { set m {0 0.0} }
      lassign $m c a
      set m [list [incr c] [expr { $a + abs($v) }]]
    }
  }
  # where the moves sit, most moved first: each "instance flops ps", the
  # flops moved and the sum of their moves
  set top_moved {}
  foreach {inst m} [lsort -stride 2 -index {1 1} -real -decreasing $by_inst] {
    if { [llength $top_moved] >= 20 } { break }
    lassign $m c a
    lappend top_moved [format "%s %d %.0f" $inst $c $a]
  }
  foreach f $flops {
    lassign $f ck
    unset_clock_latency $ck
  }
  set after [dict get [hr_period] period]
  return [dict merge [dict create start $start skew $best flops $n rounds $rounds \
    moved_parent $moved_parent moved_block $moved_block \
    delta_min $dmin delta_max $dmax hold_slack $holdslack hold_start $holdstart \
    restored $after \
    top_moved $top_moved] [hr_mass $best_pd]]
}

# The retiming floor: useful skew without hold. Moving a register through
# its logic (retiming) shifts the same path delays a clock arrival does,
# in steps of whole gates, and creates no hold problem it cannot fix by
# padding; so it cannot pass the balance skew reaches with hold ignored,
# which is set by the loops through the registers (their delay per
# register). The gap to the period is the most any retiming could win;
# none, and retiming has nothing to work with. top_moved names the
# instances whose flops would have to move: a retiming tool works inside
# a module (yosys's abc -dff on SYNTH_RETIME_MODULES), never across a
# hardened block or a memory. The damped balancing may stop short of the
# exact floor: the answer is an upper bound on it, below the one-flop loop
# only by error.
proc hr_floor_retime { {ends 0} {iters 60} {blocks {}} } {
  set d [hr_skew $ends 0 $iters $blocks]
  dict set d floor [dict get $d skew]
  dict unset d skew
  dict unset d hold_slack
  dict unset d hold_start
  return $d
}

# The period as the paths through `flops` see it: the clock period minus
# the worst setup slack at their data and output pins.
proc hr_scope_period { flops } {
  set worst ""
  foreach f $flops {
    lassign $f ck d q
    foreach s [list [hr_min_slack $d slack_max] [hr_min_slack $q slack_max]] {
      if { $s ne "" && ($worst eq "" || $s < $worst) } { set worst $s }
    }
  }
  if { $worst eq "" } { return [hr_clock_period] }
  return [expr { [hr_clock_period] - $worst }]
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
  set after_pd [hr_period]
  set after [dict get $after_pd period]
  set leak_vt [hr_leakage]
  foreach s $swapped {
    lassign $s c lc
    replace_cell $c [lindex $lc 0]
  }
  hr_update_parasitics
  set restored [dict get [hr_period] period]
  return [dict merge [dict create start $start vt $after \
    leakage_start $leak_start leakage_vt $leak_vt leakage_restored [hr_leakage] \
    swapped_parent $n_parent \
    swapped_block $n_block already_fastest $already_fastest \
    vts_in_cones [lsort [dict keys $have_vts]] restored $restored] [hr_mass $after_pd]]
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

# The zero-wire bound, in OpenROAD: every routing layer's and the default
# wire's resistance and capacitance near zero, parasitics estimated the
# way the stage had them, the period measured, the stage's own RC put back
# and estimated again. Clock wires go to zero too, as in the flat view's
# STA_WIRES=0, so the bound carries the clock's change with it. It times
# the clock arrivals as they are, so it is no floor: useful skew passes it
# (hr_floor_wire_skew), the one-flop loop at zero wire bounds both.
proc hr_floor_wire { rc_file mode } {
  set start [dict get [hr_period] period]
  hr_wires_zero $mode
  set floor [dict get [hr_period] period]
  hr_wires_back $rc_file $mode
  set restored [dict get [hr_period] period]
  return [dict create start $start floor $floor restored $restored]
}

# Every routing layer's and every wire's R and C near zero, the clock's
# too, and the parasitics estimated again: each path's logic alone.
proc hr_wires_zero { mode } {
  set tech [ord::get_db_tech]
  foreach layer [$tech getLayers] {
    if { [$layer getType] ne "ROUTING" } { continue }
    set_layer_rc -layer [$layer getName] -resistance 1e-9 -capacitance 1e-9
  }
  set_wire_rc -signal -resistance 1e-9 -capacitance 1e-9
  set_wire_rc -clock -resistance 1e-9 -capacitance 1e-9
  estimate_parasitics -$mode
}

# The stage's own RC back, and the parasitics estimated with it.
proc hr_wires_back { rc_file mode } {
  source $rc_file
  estimate_parasitics -$mode
}

# Zero wire, then useful skew on it, hold kept: what wire and skew together
# could give, the logic alone clocked at its best. The one-flop loop at
# zero wire (hr_floor_cycles_nowire) bounds it; nothing else wire or skew
# can do passes it.
proc hr_floor_wire_skew { rc_file mode {ends 0} } {
  set start [dict get [hr_period] period]
  hr_wires_zero $mode
  set floor_wire [dict get [hr_period] period]
  set s [hr_skew $ends 1]
  hr_wires_back $rc_file $mode
  set restored [dict get [hr_period] period]
  return [dict merge $s [dict create start $start floor_wire $floor_wire \
    floor [dict get $s skew] restored $restored]]
}

# The one-flop-loop floor at zero wire: each loop's logic alone. No skew,
# retiming or wire (placement, buffering, reseating) passes it; only the
# loop's own cells (sizing, VT) or its logic can.
proc hr_floor_cycles_nowire { rc_file mode {ends 0} } {
  set start [dict get [hr_period] period]
  hr_wires_zero $mode
  set c [hr_floor_cycles $ends]
  hr_wires_back $rc_file $mode
  set restored [dict get [hr_period] period]
  return [dict merge $c [dict create start $start restored $restored]]
}
