# The lateral case: the parent's logic must sit beside the block, not
# across from its pin side, so every wire leaves the pin side and turns
# along the channel. A placement blockage over the whole column above the
# block (channel and all) leaves the cells the strip to the right of it;
# see arms.bzl for the die that gives that strip its area.
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set core [$block getCoreArea]
set macro ""
foreach i [$block getInsts] { if { [[$i getMaster] isBlock] } { set macro $i } }
set bb [$macro getBBox]
set x0 [$core xMin]
set x1 [$bb xMax]
set y0 [$bb yMax]
set y1 [$core yMax]
odb::dbBlockage_create $block NULL $x0 $y0 $x1 $y1
puts "lateral_blockage.tcl: cells kept out of ([expr {$x0/double($dbu)}], [expr {$y0/double($dbu)}]) - ([expr {$x1/double($dbu)}], [expr {$y1/double($dbu)}]) um; the strip to the right is theirs"
