# mock_area = "pins" on lb_32x128 (die 7.4 x 4.7 um, 32 pins, M4/M5,
# MOCK_AREA_PIN_MARGIN 8): the mocked die is the pin-fitted square, capped
# at the real die's height, and every signal pin sits on the bottom or the
# left edge (mock_pins.tcl), so the mock has an orientation.
read_db $::env(RESULTS_DIR)/3_place.odb
set block [ord::get_db_block]
set die [$block getDieArea]
set w [ord::dbu_to_microns [$die dx]]
set h [ord::dbu_to_microns [$die dy]]
puts "mocked die: $w x $h um"
if { !($w > 0.5 * 7.4 && $w < 7.4) } {
  puts "expected the pin-fitted side to shrink the 7.4 um width, got $w"
  exit 1
}
if { abs($h - 4.7) > 1e-6 } {
  puts "expected the height capped at the real die's 4.7 um, got $h"
  exit 1
}
set bad {}
set n 0
foreach bterm [$block getBTerms] {
  if { [$bterm getSigType] ne "SIGNAL" } { continue }
  incr n
  set bbox [$bterm getBBox]
  if { [$bbox yMin] != [$die yMin] && [$bbox xMin] != [$die xMin] } {
    lappend bad [$bterm getName]
  }
}
if { $n == 0 } {
  puts "no signal pins found"
  exit 1
}
if { [llength $bad] } {
  puts "pins off the bottom and left edges: $bad"
  exit 1
}
puts "all $n signal pins on the bottom and left edges"
exec touch $::env(WORK_HOME)/pins_mock_ok.txt
