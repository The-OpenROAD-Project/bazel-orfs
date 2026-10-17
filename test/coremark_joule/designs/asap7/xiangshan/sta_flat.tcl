# The whole design timed flat: the parent's netlist with every block's real
# cells and wires (sta_part.tcl's pieces) in place of the block's abstract,
# so a path starts and ends at a real flop wherever it is. Run by OpenSTA:
#   STA_PARENT=XSTile STA_PARTS="XSTile Frontend ..." STA_DIR=<dir with each
#   part's .v, .spef, .sdc, _libs.tar> STA_OUT=<report> sta -exit sta_flat.tcl
# Every reg2reg endpoint is classified by where its worst path starts and
# ends: in the parent, or inside a block.
set dir $::env(STA_DIR)
set parent $::env(STA_PARENT)
set parts $::env(STA_PARTS)
set blocks [lsearch -all -inline -not -exact $parts $parent]

# every part's liberty once, except a block's own abstract: its cells are
# the block's netlist now
set libdir [file join $dir libs]
file mkdir $libdir
foreach part $parts { exec tar -xf [file join $dir ${part}_libs.tar] -C $libdir }
foreach lib [lsort [glob -directory $libdir *]] {
  set base [file tail $lib]
  if { [lsearch -exact [lmap b $blocks { string cat $b _typ.lib }] $base] >= 0 } { continue }
  read_liberty $lib
}
foreach part $parts { read_verilog [file join $dir $part.v] }
link_design $parent
read_sdc [file join $dir $parent.sdc]
# reduced as read: a full RC network per net of the whole design does not
# fit; the reduced model is what estimate_parasitics gives the flow's timing
# STA_WIRES=0 times the same netlist without wires: each path's logic alone
set wires [expr { ![info exists ::env(STA_WIRES)] || $::env(STA_WIRES) }]
if { $wires } { read_spef -reduce [file join $dir $parent.spef] }
set where {}
foreach b $blocks {
  set insts [get_cells -hierarchical -filter "ref_name == $b"]
  if { [llength $insts] != 1 } { error "sta_flat: $b has [llength $insts] instances in $parent, want 1" }
  set path [get_full_name [lindex $insts 0]]
  lappend where $path $b
  if { $wires } { read_spef -reduce -path $path [file join $dir $b.spef] }
}
set_propagated_clock [all_clocks]

# where a pin is: the block whose instance contains it, or the parent
proc part_of { pin } {
  global where parent
  set name [get_full_name $pin]
  foreach { path b } $where {
    if { [string first "$path/" $name] == 0 } { return $b }
  }
  return $parent
}

set p [get_property [lindex [all_clocks] 0] period]
# register to register over the whole linked design: the parent's SDC lists
# the parent's own registers in its reg2reg group (write_sdc expands
# all_registers when the parent is written), so a flop inside a block is no
# group's start or end; these are every flop's clock and data pins
set r2r [list -from [all_registers -clock_pins] -to [all_registers -data_pins]]
set out {}
# the worst path as values: the next find_timing_paths frees its path ends
set w [lindex [find_timing_paths {*}$r2r -sort_by_slack -group_path_count 1] 0]
set worst_slack [get_property $w slack]
lappend out [format "reg2reg %8.0f ps  %s -> %s" $worst_slack \
  [get_full_name [get_property $w startpoint]] [get_full_name [get_property $w endpoint]]]
unset w
set kpi [format "reg2reg min period %.0f ps" [expr { $p - $worst_slack }]]
# the KPI first, so a histogram that does not finish still leaves it
set f [open $::env(STA_OUT) w]
puts $f [join [concat $out [list $kpi]] "\n"]
close $f

# every reg2reg endpoint's period (a block's own endpoints are those its
# interface logic model keeps: the flops at its boundary), by the class of its worst path, 10 ps bins
set bin 10
set ends [find_timing_paths {*}$r2r -endpoint_path_count 1 \
  -group_path_count [sta::endpoint_count]]
array set hist {}
array set worst {}
foreach t $ends {
  set s [part_of [get_property $t startpoint]]
  set e [part_of [get_property $t endpoint]]
  set c [expr { $s eq $e ? ($s eq $parent ? "parent" : $s) : "$s->$e" }]
  set slack [get_property $t slack]
  set b [expr { int(floor(($p - $slack) / $bin)) }]
  if { [info exists hist($c,$b)] } { incr hist($c,$b) } else { set hist($c,$b) 1 }
  if { ![info exists worst($c)] || $slack < [lindex $worst($c) 0] } {
    set worst($c) [list $slack [get_full_name [get_property $t startpoint]] [get_full_name [get_property $t endpoint]]]
  }
}
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
lappend out $kpi
set f [open $::env(STA_OUT) w]
puts $f [join $out "\n"]
close $f
# each class's worst path, cell by cell
if { [info exists ::env(STA_PATHS)] } {
  set f [open $::env(STA_PATHS) w]
  close $f
  foreach c [lsort [array names worst]] {
    lassign $worst($c) slack from to
    set f [open $::env(STA_PATHS) a]
    puts $f "### class $c worst [format %.0f [expr { $p - $slack }]] ps"
    close $f
    report_checks -from [get_pins $from] -to [get_pins $to] -format full_clock_expanded \
      -fields {fanout cap slew} -digits 0 >> $::env(STA_PATHS)
  }
}
