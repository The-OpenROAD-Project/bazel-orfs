# A top level that is macros only: the parent macro PARENT_INST at the
# die's origin, the tiles u_b<row>_<col> in a grid in its notch, row 0
# at the notch's top, NOTCH_X0 and NOTCH_Y1 (io_notch.tcl). place_macro
# refuses macros whose bounding boxes overlap (MPL-0041), and the
# parent's box holds its notch: the macros are placed through the
# database directly, fixed, and the router sees their real shapes.
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
proc at { inst x y } {
  $inst setOrigin $x $y
  $inst setOrient R0
  $inst setPlacementStatus FIRM
}
at [$block findInst $::env(PARENT_INST)] 0 0
set x0 [expr { int(round($::env(NOTCH_X0) * $dbu)) }]
set y1 [expr { int(round($::env(NOTCH_Y1) * $dbu)) }]
set n 0
foreach i [$block getInsts] {
  if { ![regexp {^u_b(\d+)_(\d+)$} [$i getName] -> r c] } { continue }
  set m [$i getMaster]
  at $i [expr { $x0 + $c * [$m getWidth] }] [expr { $y1 - ($r + 1) * [$m getHeight] }]
  incr n
}
puts "place_notch.tcl: $n tiles in the notch"
