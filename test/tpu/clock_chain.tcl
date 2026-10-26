# Useful skew at home, for tpu's dissolved tiles (PRE_CTS_TCL): each
# tile kept the clock tree it was built with (dissolve.tcl), and here the
# tiles' clock entries leave tpu's clock net for a chain of buffers that
# runs east along the array, one tap per column, CHAIN_STEP_PS later per
# column: the skew the clock had running through the tiles (bazel-orfs
# #1396), data flowing east captured that much later, without a clock
# tree that knows about useful skew. Column 0 itself is put
# CHAIN_COL0_PS behind the parent's registers once CTS has built their
# tree.
#
# The chain's head is the one pin of the array on tpu's clock net, a sink
# to CTS like any other. Everything
# after the head, the chain and each tile's own tree, is skipped by CTS
# and dont_touch for repair. Each column's step is tuned here, a buffer
# at a time, on placement parasitics with the clock propagated, to the
# buffer count closest to CHAIN_STEP_PS.
set block [ord::get_db_block]
set db [ord::get_db]
set dbu [$block getDbUnitsPerMicron]
set clk_net [[$block findBTerm clk] getNet]
set buf [$db findMaster $::env(CHAIN_BUFFER)]
if { $buf eq "NULL" } {
  utl::error FLW 720 "clock_chain.tcl: no buffer $::env(CHAIN_BUFFER)"
}
set step [expr { double($::env(CHAIN_STEP_PS)) }]
set x0 [expr { int(round($::env(ARRAY_X0) * $dbu)) }]
set y0 [expr { int(round($::env(ARRAY_Y0) * $dbu)) }]
set tile_w [expr { int(round($::env(TILE_W) * $dbu)) }]
set tile_h [expr { int(round($::env(TILE_H) * $dbu)) }]

# the tiles' clock entries on tpu's clock net, by column
set entries [dict create]
set rows 0
foreach it [$clk_net getITerms] {
  if { ![$it isInputSignal] } { continue }
  if { ![regexp {^u_b(\d+)_(\d+)\.} [[$it getInst] getName] -> r c] } { continue }
  dict lappend entries $c $it
  set rows [expr { max($rows, $r + 1) }]
}
set cols [lsort -integer [dict keys $entries]]
if { [llength $cols] == 0 } {
  utl::error FLW 721 "clock_chain.tcl: no tile's clock entry on [$clk_net getName]"
}
set mid_y [expr { $y0 + $rows * $tile_h / 2 }]

# the hook is sourced in a procedure: the procedures here are given
# what they use
proc chain_buffer { block buf x y } {
  set n 0
  while { [$block findInst "clkchain_$n"] ne "NULL" } { incr n }
  set b [odb::dbInst_create $block $buf "clkchain_$n"]
  $b setLocation $x $y
  $b setPlacementStatus PLACED
  return $b
}
proc chain_net { block name } {
  set n [odb::dbNet_create $block $name]
  $n setSigType CLOCK
  return $n
}
proc pin { inst name } { return [$inst findITerm $name] }

# the head, west of column 0, mid-height
set head [chain_buffer $block $buf [expr { $x0 - [$buf getWidth] }] $mid_y]
[pin $head A] connect $clk_net
set col_net [dict create]
set col_drv [dict create]
set prev ""
foreach c $cols {
  set n [chain_net $block "clkchain_col$c"]
  if { $prev eq "" } {
    [pin $head Y] connect $n
    dict set col_drv $c $head
  } else {
    set b [chain_buffer $block $buf [expr { $x0 + $c * $tile_w }] $mid_y]
    [pin $b A] connect [dict get $col_net $prev]
    [pin $b Y] connect $n
    dict set col_drv $c $b
  }
  foreach it [dict get $entries $c] { $it connect $n }
  dict set col_net $c $n
  set prev $c
}

# arrival at a column's net, the clock propagated through the chain
set_propagated_clock [all_clocks]
proc col_arrival { col_drv c } {
  set p [get_pins [[dict get $col_drv $c] getName]/Y]
  # asap7's time unit is the picosecond
  return [expr { double([get_property $p arrival_max_rise]) }]
}
proc measure {} {
  estimate_parasitics -placement
}

# each column's step from the column before it: one buffer more before
# its tap until the step passes CHAIN_STEP_PS, then the count closest to
# it
set report {}
set prev ""
foreach c $cols {
  if { $prev eq "" } {
    # column 0 is the head alone until CTS has built the parent's tree
    set prev $c
    continue
  }
  set target $step
  measure
  set d [expr { [col_arrival $col_drv $c] - [col_arrival $col_drv $prev] }]
  set k 1
  while { $d < $target } {
    if { $k >= 32 } {
      utl::error FLW 722 "clock_chain.tcl: column $c's step is $d ps after $k buffers"
    }
    # one more: the column's driver feeds a new buffer that feeds the tap
    set drv [dict get $col_drv $c]
    set mid [chain_net $block "clkchain_col${c}_$k"]
    set b [chain_buffer $block $buf [expr { [lindex [$drv getLocation] 0] + [$buf getWidth] }] $mid_y]
    [pin $drv Y] connect $mid
    [pin $b A] connect $mid
    [pin $b Y] connect [dict get $col_net $c]
    dict set col_drv $c $b
    incr k
    set last $d
    measure
    set d [expr { [col_arrival $col_drv $c] - [col_arrival $col_drv $prev] }]
  }
  if { $k > 1 && $target - $last < $d - $target } {
    # one buffer fewer is closer: the last one goes
    set b [dict get $col_drv $c]
    set in [[pin $b A] getNet]
    set drv [[$in getFirstOutput] getInst]
    [pin $b A] disconnect
    [pin $b Y] disconnect
    odb::dbInst_destroy $b
    [pin $drv Y] connect [dict get $col_net $c]
    odb::dbNet_destroy $in
    dict set col_drv $c $drv
    incr k -1
    measure
    set d [expr { [col_arrival $col_drv $c] - [col_arrival $col_drv $prev] }]
  }
  lappend report [format "col %d: %d buffers, +%.1f ps" $c $k $d]
  set prev $c
}
unset_propagated_clock [all_clocks]

# Column 0 behind the parent's tree, once CTS has built it and before
# repair times anything: CTS hangs the head on a shallow branch of the
# tree, nowhere near the parent's registers' latency, and the parent's
# registers launch into column 0 (the skew registers, a_in into each
# row's first processing element). Buffers go between the head and
# column 0's tap until column 0's registers take the clock
# CHAIN_COL0_PS after the parent's, on average; every column moves with
# it. The hook is sourced in a procedure, and clock_tree_synthesis is
# called after it returns: the wrapper is global.
proc chain_mean_arrival { pattern } {
  set sum 0.0
  set n 0
  foreach pin [all_registers -clock_pins] {
    if { [regexp $pattern [get_full_name $pin]] } {
      set sum [expr { $sum + [get_property $pin arrival_max_rise] }]
      incr n
    }
  }
  if { $n == 0 } {
    utl::error FLW 724 "clock_chain.tcl: no register matches $pattern"
  }
  return [expr { $sum / $n }]
}
proc chain_align_col0 { target buf } {
  set block [ord::get_db_block]
  set head [$block findInst clkchain_0]
  set tap [$block findNet clkchain_col0]
  set_propagated_clock [all_clocks]
  set k 0
  while { 1 } {
    estimate_parasitics -placement
    set d [expr {
      [chain_mean_arrival {^u_b\d+_0\.}] - [chain_mean_arrival {^u_rest\.}]
    }]
    if { $d >= $target } { break }
    if { $k >= 32 } {
      utl::error FLW 725 "clock_chain.tcl: column 0 is $d ps after the parent after $k buffers"
    }
    # one more between the tap's driver and the tap
    set drv [[$tap getFirstOutput] getInst]
    set mid [odb::dbNet_create $block "clkchain_col0_$k"]
    $mid setSigType CLOCK
    set n 0
    while { [$block findInst "clkchain_$n"] ne "NULL" } { incr n }
    set b [odb::dbInst_create $block $buf "clkchain_$n"]
    lassign [$drv getLocation] x y
    $b setLocation [expr { $x + [$buf getWidth] }] $y
    $b setPlacementStatus PLACED
    # odb refuses to rewire a dont_touch net or instance (ODB-0373)
    $tap setDoNotTouch 0
    $drv setDoNotTouch 0
    [$drv findITerm Y] connect $mid
    [$b findITerm A] connect $mid
    [$b findITerm Y] connect $tap
    foreach o [list $tap $mid $b] { $o setDoNotTouch 1 }
    # the head's input is on the tree CTS built: it stays touchable
    if { $drv ne $head } { $drv setDoNotTouch 1 }
    incr k
  }
  utl::info FLW 726 [format "clock_chain.tcl: column 0 %.1f ps after the\
    parent's registers, %d buffers added after CTS" $d $k]
}
rename clock_tree_synthesis chain_cts
proc clock_tree_synthesis { args } {
  chain_cts {*}$args
  chain_align_col0 [expr { double($::env(CHAIN_COL0_PS)) }] \
    [[ord::get_db] findMaster $::env(CHAIN_BUFFER)]
}

# everything after the head: CTS skips it, repair leaves it alone
set skipped 0
set todo [list [[pin $head Y] getNet]]
set seen [dict create]
while { [llength $todo] > 0 } {
  set net [lindex $todo 0]
  set todo [lrange $todo 1 end]
  if { [dict exists $seen [$net getId]] } { continue }
  dict set seen [$net getId] 1
  $net setDoNotTouch 1
  cts::set_skip_clock_nets $net
  incr skipped
  foreach it [$net getITerms] {
    if { ![$it isInputSignal] } { continue }
    # through the tree's buffers and inverters to the registers
    set inst [$it getInst]
    if { [[$inst getMaster] isSequential] } { continue }
    foreach o [$inst getITerms] {
      if { [$o isOutputSignal] && [$o getNet] ne "NULL" } { lappend todo [$o getNet] }
    }
  }
}
foreach i [$block getInsts] {
  if { [string match clkchain_* [$i getName]] && $i ne $head } { $i setDoNotTouch 1 }
}
set n_buf 0
foreach i [$block getInsts] {
  if { [string match clkchain_* [$i getName]] } { incr n_buf }
}
utl::info FLW 723 "clock_chain.tcl: $n_buf buffers, [llength $cols] columns,\
  $skipped clock nets skipped by CTS; [join $report {; }]"
