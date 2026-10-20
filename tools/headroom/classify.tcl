# Classes of a stitched design's reg2reg endpoints, by where each one's
# worst path runs: it starts in the parent or in a block, ends in one, and
# may pass through a block on the way. Sourced by headroom_flat.tcl
# (orfs_headroom's <name>_classes) and by XiangShan's sta_flat.tcl.
#
# A class is
#   parent         from the parent to the parent, through no block
#   B              inside block B
#   S->E           from S to E, through no third part
#   S->via:B->E    through block B (several joined with +) on the way from S
#                  to E, B being neither: in at one of B's ports and out at
#                  another with no flop of B between, the arc a hardened
#                  block lends the parent's path. A path through a block it
#                  neither starts nor ends in is surgery's in2out case.
#
# `where` is a flat list of block instance paths and their block names.

# The part a pin is in: the block whose instance contains it, or the parent.
proc hr_part_of { name where parent } {
  foreach { path b } $where {
    if { [string first "$path/" $name] == 0 } { return $b }
  }
  return $parent
}

# The parts a path end's worst path runs through, in order, each once per
# stretch.
proc hr_path_parts { path_end where parent } {
  set parts {}
  foreach point [get_property $path_end points] {
    set p [hr_part_of [get_full_name [get_property $point pin]] $where $parent]
    if { [lindex $parts end] ne $p } { lappend parts $p }
  }
  return $parts
}

# The class of a path through `parts`, in order.
proc hr_class { parts parent } {
  set s [lindex $parts 0]
  set e [lindex $parts end]
  set via {}
  foreach p [lrange $parts 1 end-1] {
    if { $p ne $parent && $p ne $s && $p ne $e && [lsearch -exact $via $p] < 0 } {
      lappend via $p
    }
  }
  if { [llength $via] } { return "$s->via:[join $via +]->$e" }
  if { $s ne $e } { return "$s->$e" }
  return [expr { $s eq $parent ? "parent" : $s }]
}

# Every reg2reg endpoint's worst path, classified: for each class its worst
# path and its endpoints' periods (the clock period minus the slack) in
# `bin` ps bins, as lines:
#   class <c> worst <ps> ps  <from> -> <to>
#   class <c> endpoints bin <bin> ps from <ps>: <counts>
# With worst_var, the caller's array of that name gets each class's worst
# path as {slack from to}.
proc hr_classes { where parent {bin 10} {worst_var ""} } {
  set p [get_property [lindex [all_clocks] 0] period]
  set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
  set ends [find_timing_paths {*}$r2r -endpoint_path_count 1 \
    -group_path_count [sta::endpoint_count]]
  array set hist {}
  array set worst {}
  foreach t $ends {
    set c [hr_class [hr_path_parts $t $where $parent] $parent]
    set slack [get_property $t slack]
    set b [expr { int(floor(($p - $slack) / $bin)) }]
    if { [info exists hist($c,$b)] } { incr hist($c,$b) } else { set hist($c,$b) 1 }
    if { ![info exists worst($c)] || $slack < [lindex $worst($c) 0] } {
      set worst($c) [list $slack [get_full_name [get_property $t startpoint]] \
        [get_full_name [get_property $t endpoint]]]
    }
  }
  set out {}
  foreach c [lsort [array names worst]] {
    set bins {}
    foreach k [array names hist "$c,*"] { lappend bins [lindex [split $k ,] end] }
    set bins [lsort -integer $bins]
    set counts {}
    for { set b [lindex $bins 0] } { $b <= [lindex $bins end] } { incr b } {
      lappend counts [expr { [info exists hist($c,$b)] ? $hist($c,$b) : 0 }]
    }
    lassign $worst($c) slack from to
    lappend out [format "class %s worst %.0f ps  %s -> %s" $c [expr { $p - $slack }] $from $to]
    lappend out [format "class %s endpoints bin %d ps from %d ps: %s" $c $bin \
      [expr { [lindex $bins 0] * $bin }] [join $counts " "]]
  }
  if { $worst_var ne "" } {
    upvar 1 $worst_var w
    array set w [array get worst]
  }
  return $out
}
