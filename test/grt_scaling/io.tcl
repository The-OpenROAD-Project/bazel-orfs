# Pin each wirebound group to one edge of the die, round robin, so the
# groups spread to the perimeter and the inter-group nets span the die
# whatever its size. Read by ORFS's place_pins through IO_CONSTRAINTS.
#
# The anchor ports are flat and group-major (bit g*WIDTH+b is group g's
# bit b); WIDTH is dout's width and the group count follows from aout's,
# both read off the netlist, so this file needs no knob and cannot
# disagree with the define the arm was synthesised with.
set width 0
set anchor_bits 0
foreach bterm [[ord::get_db_block] getBTerms] {
  set n [$bterm getName]
  if { [regexp {^dout\[} $n] } { incr width }
  if { [regexp {^aout\[} $n] } { incr anchor_bits }
}
if { $width == 0 || $anchor_bits == 0 } {
  utl::error FLW 1 "no aout ports: synthesise with -D WIREBOUND_IO_ANCHORS"
}
set groups [expr { $anchor_bits / $width }]

set edges {left bottom right top}
set names [dict create]
foreach bterm [[ord::get_db_block] getBTerms] {
  set n [$bterm getName]
  if { [regexp {^a(in|out)\[(\d+)\]} $n -> dir bit] } {
    set g [expr { $bit / $width }]
    dict lappend names $g $n
  }
}
for {set g 0} {$g < $groups} {incr g} {
  set edge [lindex $edges [expr { $g % 4 }]]
  set_io_pin_constraint -region $edge:* -pin_names [dict get $names $g]
}
puts "io.tcl: $groups groups of $width bits pinned round robin to [join $edges {, }]"
