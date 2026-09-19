# IO constraints for a mocked abstract sized to its pins (MOCK_AREA=pins):
# every pin goes to MOCK_AREA_PIN_EDGES adjacent edges of the die, so the
# mock has an orientation a parent's macro placer can use. A block whose
# pins fill its perimeter evenly carries no orientation at all; one whose
# pins sit on the bottom and left edges changes its wirelength under an
# x-flip and a y-flip, which is what lets a placer choose them.
#
#   1  all pins on the bottom edge
#   2  alternate bottom and left (the default in mock_area.tcl)
#   4  no constraint: place_pins spreads them as it does for the real block
#
# Sourced by the mocked variant's floorplan through IO_CONSTRAINTS, so the
# block's own constraints file is not read for the mock.
set edges [expr { [info exists ::env(MOCK_AREA_PIN_EDGES)] ? int($::env(MOCK_AREA_PIN_EDGES)) : 2 }]
if { $edges != 4 } {
  set bottom {}
  set left {}
  set i 0
  foreach bterm [[ord::get_db_block] getBTerms] {
    if { [$bterm getSigType] ne "SIGNAL" && [$bterm getSigType] ne "CLOCK" } { continue }
    if { $edges == 1 || $i % 2 == 0 } { lappend bottom [$bterm getName] } else { lappend left [$bterm getName] }
    incr i
  }
  if { [llength $bottom] } { set_io_pin_constraint -region bottom:* -pin_names $bottom }
  if { [llength $left] } { set_io_pin_constraint -region left:* -pin_names $left }
  puts "mock_pins.tcl: [llength $bottom] pins on the bottom edge, [llength $left] on the left"
}
