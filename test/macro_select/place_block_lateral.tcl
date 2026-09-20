# The lateral case: the block at the bottom-left, its pin side up, and a
# placement blockage above it so the parent's logic sits to its right.
set block [ord::get_db_block]
set inst [lindex [$block getInsts] 0]
foreach i [$block getInsts] { if { [[$i getMaster] isBlock] } { set inst $i } }
set m [$inst getMaster]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set core [$block getCoreArea]
# centred along x, on the core's bottom edge, origin on the 0.144 x 2.16 um
# lattice that keeps asap7 M2-M5 pins on the parent's tracks
set x [expr { int(ceil([$core xMin] / (0.144 * $dbu))) * int(0.144 * $dbu) }]
set y [expr { int(ceil([$core yMin] / (2.16 * $dbu))) * int(2.16 * $dbu) }]
place_macro -macro_name [$inst getName] -location [list [expr { $x / double($dbu) }] [expr { $y / double($dbu) }]] -orientation R0 -exact
puts "place_block_lateral.tcl: [$inst getName] at [expr { $x / double($dbu) }] [expr { $y / double($dbu) }] um"

# The lateral case: the parent's logic must sit beside the block, not
# across from its pin side, so every wire leaves the pin side and turns
# along the channel. A placement blockage over the whole column above the
# block (channel and all) leaves the cells the strip to the right of it;
# see arms.bzl for the die that gives that strip its area.
set macro ""
foreach i [$block getInsts] { if { [[$i getMaster] isBlock] } { set macro $i } }
set bb [$macro getBBox]
set x0 [$core xMin]
set x1 [$bb xMax]
set y0 [$bb yMax]
set y1 [$core yMax]
odb::dbBlockage_create $block $x0 $y0 $x1 $y1
puts "place_block_lateral.tcl: cells kept out of ([expr {$x0/double($dbu)}], [expr {$y0/double($dbu)}]) - ([expr {$x1/double($dbu)}], [expr {$y1/double($dbu)}]) um; the strip to the right is theirs"
