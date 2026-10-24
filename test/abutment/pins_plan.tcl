# A tile's pins where its plan says (tools/carve/pin_plan.py, PIN_PLAN):
# one rectangle per pin bit, on the tracks the parent and the tile's
# neighbours share, decided before anything is built.
set n 0
set f [open $::env(PIN_PLAN)]
while { [gets $f line] >= 0 } {
  if { [llength $line] != 7 } { continue }
  lassign $line pin side layer x0 y0 x1 y1
  place_pin -pin_name $pin -layer $layer \
    -location [list [expr { ($x0 + $x1) / 2.0 }] [expr { ($y0 + $y1) / 2.0 }]] \
    -pin_size [list [expr { $x1 - $x0 }] [expr { $y1 - $y0 }]]
  incr n
}
close $f
puts "pins_plan.tcl: $n pins"
