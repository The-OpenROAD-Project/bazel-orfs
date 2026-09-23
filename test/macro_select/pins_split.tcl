# The channel block's pins: inputs on the left half of the top side, outputs
# on the right half. Placed R0 twice, the left instance's outputs and the
# right instance's inputs meet at the gap between them, the way the planner
# gives partners facing edge segments; the other half faces the parent.
set block [ord::get_db_block]
set die [$block getDieArea]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set mid [expr { ([$die xMin] + [$die xMax]) / 2.0 / $dbu }]
set right [expr { [$die xMax] / double($dbu) }]
set ins {}
set outs {}
foreach bterm [$block getBTerms] {
  if { [$bterm getSigType] ne "SIGNAL" && [$bterm getSigType] ne "CLOCK" } { continue }
  if { [$bterm getIoType] eq "OUTPUT" } { lappend outs [$bterm getName] } else { lappend ins [$bterm getName] }
}
set_io_pin_constraint -region top:0-$mid -pin_names $ins
set_io_pin_constraint -region top:$mid-$right -pin_names $outs
puts "pins_split.tcl: [llength $ins] inputs on top:0-$mid, [llength $outs] outputs on top:$mid-$right"
