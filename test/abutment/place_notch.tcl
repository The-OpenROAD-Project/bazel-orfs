# A top level that is macros only: the parent macro PARENT_INST at the
# die's origin, the tiles u_b<row>_<col> in a grid in its notch, row 0
# at the notch's top, NOTCH_X0 and NOTCH_Y1 (io_notch.tcl). place_macro
# refuses macros whose bounding boxes overlap (MPL-0041), and the
# parent's box holds its notch: the macros are placed through the
# database directly, fixed, and the router sees their real shapes.
# PARENT_Y, when set, lifts them all that far off the die's bottom edge,
# over a strip of the top level's own rows (core_rows.tcl), and the
# routing tracks with them, so the macros' pins stay on the top level's
# grid; the top level's own cells, if any, are placed in a region that is
# the strip.
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
proc at { inst x y } {
  $inst setOrigin $x $y
  $inst setOrient R0
  $inst setPlacementStatus FIRM
}
set py [expr { [info exists ::env(PARENT_Y)] ? int(round($::env(PARENT_Y) * $dbu)) : 0 }]
at [$block findInst $::env(PARENT_INST)] 0 $py
set x0 [expr { int(round($::env(NOTCH_X0) * $dbu)) }]
set y1 [expr { $py + int(round($::env(NOTCH_Y1) * $dbu)) }]
set n 0
foreach i [$block getInsts] {
  # under the wrapper's instance, if any (u_tpu.u_b0_0)
  if { ![regexp {(?:^|\.)u_b(\d+)_(\d+)$} [$i getName] -> r c] } { continue }
  set m [$i getMaster]
  at $i [expr { $x0 + $c * [$m getWidth] }] [expr { $y1 - ($r + 1) * [$m getHeight] }]
  incr n
}
puts "place_notch.tcl: $n tiles in the notch"
if { $py > 0 } {
  # the platform's tracks remade, each layer's y offset now (offset +
  # PARENT_Y) modulo its pitch: still from the die's bottom edge, in nm
  # so the modulo is exact. The platform sets MAKE_TRACKS outright, so a
  # design cannot give the floorplan its own.
  foreach grid [$block getTrackGrids] {
    odb::dbTrackGrid_destroy $grid
  }
  rename make_tracks make_tracks_platform
  proc make_tracks { layer args } {
    set i [lsearch -exact $args -y_offset]
    set p [lsearch -exact $args -y_pitch]
    if { $i >= 0 && $p >= 0 } {
      set off [expr { round([lindex $args [expr { $i + 1 }]] * 1000) }]
      set pitch [expr { round([lindex $args [expr { $p + 1 }]] * 1000) }]
      set lifted [expr { ($off + round($::env(PARENT_Y) * 1000)) % $pitch }]
      if { $lifted == 0 } { set lifted $pitch }
      lset args [expr { $i + 1 }] [expr { $lifted / 1000.0 }]
    }
    make_tracks_platform $layer {*}$args
  }
  source $::env(MAKE_TRACKS)
  rename make_tracks {}
  rename make_tracks_platform make_tracks
  puts "place_notch.tcl: macros and tracks lifted $::env(PARENT_Y) um"
}
if { $py > 0 } {
  # Global placement counts the area of every fixed instance in the
  # region it places, the parent's box over its tiles twice, more than
  # the die: placing the top level's cells there diverges (GPL-0305).
  # The strip holds no macro.
  set die [$block getDieArea]
  set region [odb::dbRegion_create $block strip]
  odb::dbBox_create $region [$die xMin] [$die yMin] [$die xMax] [expr { [$die yMin] + $py }]
  set group [odb::dbGroup_create $region strip]
  set cells 0
  foreach inst [$block getInsts] {
    if { [[$inst getMaster] isBlock] || [$inst isFixed] } { continue }
    $group addInst $inst
    incr cells
  }
  puts "place_notch.tcl: $cells cells of the top level's own placed in the strip"
}
