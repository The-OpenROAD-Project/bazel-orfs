# The tiles u_b<row>_<col> abutted in a grid, row 0 at the top, the
# grid's bottom-left corner at ARRAY_X0 ARRAY_Y0 um: placed through the
# database, FIRM, as place_notch.tcl does. The corner is on the parent's
# site grid and an even number of rows up, so the tiles' rows continue
# the parent's when they dissolve (dissolve.tcl).
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set x0 [expr { int(round($::env(ARRAY_X0) * $dbu)) }]
set y0 [expr { int(round($::env(ARRAY_Y0) * $dbu)) }]
set tiles {}
set rows 0
foreach i [$block getInsts] {
  if { ![regexp {^u_b(\d+)_(\d+)$} [$i getName] -> r c] } { continue }
  lappend tiles [list $i $r $c]
  set rows [expr { max($rows, $r + 1) }]
}
foreach t $tiles {
  lassign $t i r c
  set m [$i getMaster]
  $i setOrigin [expr { $x0 + $c * [$m getWidth] }] [expr { $y0 + ($rows - 1 - $r) * [$m getHeight] }]
  $i setOrient R0
  $i setPlacementStatus FIRM
}
puts "place_grid.tcl: [llength $tiles] tiles, $rows rows"
