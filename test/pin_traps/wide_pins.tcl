# Every signal pin of the block at an exact place on its top edge, on M3,
# one every four tracks from the left, each WIDE_PIN_UM wide and 0.36 um
# tall: the planner's exact pins, drawn as wide as the trap asks (pin
# trap 8). M3's tracks on asap7 are at 0.009 + k * 0.036 um.
set block [ord::get_db_block]
set die [$block getDieArea]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set top [expr { [$die yMax] / double($dbu) }]
set names {}
foreach bterm [$block getBTerms] {
  if { [$bterm getSigType] eq "SIGNAL" } { lappend names [$bterm getName] }
}
set k 56
foreach name [lsort -dictionary $names] {
  set x [expr { 0.009 + $k * 0.036 }]
  place_pin -pin_name $name -layer M3 -location [list $x [expr { $top - 0.18 }]] \
    -pin_size [list $::env(WIDE_PIN_UM) 0.36] -force_to_die_boundary
  incr k 4
}
puts "wide_pins.tcl: [llength $names] pins on M3, $::env(WIDE_PIN_UM) um wide"
