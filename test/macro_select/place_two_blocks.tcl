# The channel case: two blocks on the core's bottom edge, R0, pin sides up,
# BLOCK_GAP_UM apart; the parent's logic above them. Origins on the
# 0.144 x 2.16 um lattice that keeps asap7 M2-M5 pins on the parent's tracks.
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set core [$block getCoreArea]
set gap [expr { $::env(BLOCK_GAP_UM) * $dbu }]
set macros {}
foreach i [$block getInsts] { if { [[$i getMaster] isBlock] } { lappend macros $i } }
set macros [lsort -command { apply {{a b} { string compare [$a getName] [$b getName] }} } $macros]
set lx [expr { int(ceil([$core xMin] / (0.144 * $dbu))) * int(0.144 * $dbu) }]
set y [expr { int(ceil([$core yMin] / (2.16 * $dbu))) * int(2.16 * $dbu) }]
set x $lx
foreach inst $macros {
  place_macro -macro_name [$inst getName] -location [list [expr { $x / double($dbu) }] [expr { $y / double($dbu) }]] -orientation R0 -exact
  puts "place_two_blocks.tcl: [$inst getName] at [expr { $x / double($dbu) }] [expr { $y / double($dbu) }] um"
  set x [expr { int(ceil(($x + [[$inst getMaster] getWidth] + $gap) / (0.144 * $dbu))) * int(0.144 * $dbu) }]
}
