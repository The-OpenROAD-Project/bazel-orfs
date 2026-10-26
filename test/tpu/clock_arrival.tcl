# The clock's arrival at every register, stitched across tpu's macros
# (orfs_headroom's reports): per macro instance, the earliest, mean and
# latest arrival at its registers' clock pins, in ps. The clock runs
# east through each row of tiles, so a tile's registers see it later
# than its west neighbour's: the skew data flowing east gets for free.
# A register of the top level itself: in the rig (tpu_meso.sv), the
# FIFOs' side facing the pins or the side facing tpu's logic; else the
# parent's.
proc rig_side { name parent } {
  if { [regexp {^(rst_q|u_in\.(mem|widx)|u_out\.(ridx|deq_))} $name] } { return "rig:pins" }
  if { [regexp {^(u_in\.(ridx|deq_)|u_out\.(mem|widx))} $name] } { return "rig:logic" }
  return $parent
}

proc hr_report { where parent } {
  set at {}
  foreach pin [all_registers -clock_pins] {
    set name [get_full_name $pin]
    set inst [lindex [split $name /] 0]
    # a dissolved tile's registers are u_b<r>_<c>.<cell> (dissolve.tcl)
    regexp {^(u_b\d+_\d+)\.} $name -> inst
    if { ![dict exists $where $inst] && ![regexp {^u_b\d+_\d+$} $inst] } {
      set inst [rig_side $name $parent]
    }
    dict lappend at $inst [get_property $pin arrival_max_rise]
  }
  set lines {}
  dict for {inst ts} $at {
    set ts [lmap t $ts { expr { double($t) } }]
    set sum 0.0
    foreach t $ts { set sum [expr { $sum + $t }] }
    lappend lines [format "%s %.1f %.1f %.1f %d" $inst \
      [tcl::mathfunc::min {*}$ts] [expr { $sum / [llength $ts] }] \
      [tcl::mathfunc::max {*}$ts] [llength $ts]]
  }
  return [lsort $lines]
}
