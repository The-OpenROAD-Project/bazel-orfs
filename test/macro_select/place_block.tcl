# The parent's one macro at the bottom of the die, R0, its pin side up,
# CHANNEL_UM below the logic region: the geometry the planner draws.
set block [ord::get_db_block]
set inst [lindex [$block getInsts] 0]
foreach i [$block getInsts] { if { [[$i getMaster] isBlock] } { set inst $i } }
set m [$inst getMaster]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set core [$block getCoreArea]
# centred along x, on the core's bottom edge, origin on the 0.144 x 2.16 um
# lattice that keeps asap7 M2-M5 pins on the parent's tracks
set x [expr { int(([$core xMin] + [$core xMax] - [$m getWidth]) / 2.0 / (0.144 * $dbu)) * int(0.144 * $dbu) }]
set y [expr { int(ceil([$core yMin] / (2.16 * $dbu))) * int(2.16 * $dbu) }]
place_macro -macro_name [$inst getName] -location [list [expr { $x / double($dbu) }] [expr { $y / double($dbu) }]] -orientation R0 -exact
puts "place_block.tcl: [$inst getName] at [expr { $x / double($dbu) }] [expr { $y / double($dbu) }] um"
