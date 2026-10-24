# A parent hardened as a macro whose die is the whole design's, with a
# notch for the tiles (tools/carve/wrap_parent.py): the box NOTCH_X0
# NOTCH_Y0 NOTCH_X1 NOTCH_Y1 holds them, no cell is placed and no wire
# routed there. The tiles are u_b<row>_<col> in a grid in
# the notch, row 0 at its top (place_notch.tcl). The parent's own ports
# go on its bottom edge; each port for a tile pin, <instance>__<pin>,
# goes exactly where that pin will be, on the same layer, so the two
# abut pin on pin.
set block [ord::get_db_block]
set tech [ord::get_db_tech]
set dbu [$tech getDbUnitsPerMicron]
set die [$block getDieArea]
foreach k {X0 Y0 X1 Y1} {
  set n$k [expr { int(round($::env(NOTCH_$k) * $dbu)) }]
}
odb::dbBlockage_create $block $nX0 $nY0 $nX1 $nY1
foreach layer [$tech getLayers] {
  if { [$layer getType] eq "ROUTING" } {
    odb::dbObstruction_create $block $layer $nX0 $nY0 $nX1 $nY1
  }
}
# no row runs through the notch or within NOTCH_HALO of it (0.54 um,
# as MACRO_ROWS_HALO_Y keeps an ordinary parent's rows off its macros:
# room for the wires to the tiles' pins): cut_rows cuts around macros,
# not around blockages, so a row that does is split at the notch's edges
set halo [expr { int(round([expr { [info exists ::env(NOTCH_HALO)] ? $::env(NOTCH_HALO) : 0.54 }] * $dbu)) }]
foreach row [$block getRows] {
  set b [$row getBBox]
  if { [$b yMax] <= $nY0 - $halo || [$b yMin] >= $nY1 + $halo } { continue }
  if { [$b xMax] <= $nX0 - $halo || [$b xMin] >= $nX1 + $halo } { continue }
  set site [$row getSite]
  set sw [$site getWidth]
  lassign [$row getOrigin] ox oy
  set name [$row getName]
  set orient [$row getOrient]
  set end [$b xMax]
  odb::dbRow_destroy $row
  set n [expr { ($nX0 - $halo - $ox) / $sw }]
  if { $n > 0 } {
    odb::dbRow_create $block ${name}_w $site $ox $oy $orient HORIZONTAL $n $sw
  }
  set x1 [expr { $ox + (($nX1 + $halo - $ox + $sw - 1) / $sw) * $sw }]
  set n [expr { ($end - $x1) / $sw }]
  if { $n > 0 } {
    odb::dbRow_create $block ${name}_e $site $x1 $oy $orient HORIZONTAL $n $sw
  }
}
# Each tile pin as a box in tile coordinates (dbu) and its layer: from
# the tiles' pin plan (PIN_PLAN, TILE_W, TILE_H; tools/carve/pin_plan.py),
# so the parent waits for no tile, or from the tile's LEF (TILE_MASTER).
set boxes [dict create]
if { [info exists ::env(PIN_PLAN)] && $::env(PIN_PLAN) ne "" } {
  set tw [expr { int(round($::env(TILE_W) * $dbu)) }]
  set th [expr { int(round($::env(TILE_H) * $dbu)) }]
  set f [open $::env(PIN_PLAN)]
  while { [gets $f line] >= 0 } {
    if { [llength $line] != 7 } { continue }
    lassign $line pin side layer x0 y0 x1 y1
    dict set boxes $pin [list $layer {*}[lmap v [list $x0 $y0 $x1 $y1] { expr { int(round($v * $dbu)) } }]]
  }
  close $f
} else {
  set master [[ord::get_db] findMaster $::env(TILE_MASTER)]
  if { $master eq "NULL" } {
    error "io_notch.tcl: no master $::env(TILE_MASTER); is its LEF in ADDITIONAL_LEFS?"
  }
  set tw [$master getWidth]
  set th [$master getHeight]
  foreach mterm [$master getMTerms] {
    set box [lindex [[lindex [$mterm getMPins] 0] getGeometry] 0]
    if { $box eq "" } { continue }
    dict set boxes [$mterm getName] [list [[$box getTechLayer] getName] \
      [$box xMin] [$box yMin] [$box xMax] [$box yMax]]
  }
}
set own {}
set placed 0
foreach bt [$block getBTerms] {
  set name [$bt getName]
  if { ![regexp {^u_b(\d+)_(\d+)__(.+)$} $name -> r c pin] } {
    lappend own $name
    continue
  }
  if { ![dict exists $boxes $pin] } { error "io_notch.tcl: $name: the tile has no pin $pin" }
  lassign [dict get $boxes $pin] layer bx0 by0 bx1 by1
  # the tile's pin mirrored across the edge it is on: the two touch
  # there, and the parent's lies outside the notch, where its router
  # can reach it
  set cx [expr { ($bx0 + $bx1) / 2 }]
  set cy [expr { ($by0 + $by1) / 2 }]
  if { $by0 == 0 } {
    set cy [expr { -$cy }]
  } elseif { $by1 == $th } {
    set cy [expr { 2 * $th - $cy }]
  } elseif { $bx0 == 0 } {
    set cx [expr { -$cx }]
  } elseif { $bx1 == $tw } {
    set cx [expr { 2 * $tw - $cx }]
  } else {
    error "io_notch.tcl: $name: the tile's pin $pin is on no edge"
  }
  set x [expr { $nX0 + $c * $tw + $cx }]
  set y [expr { $nY1 - ($r + 1) * $th + $cy }]
  place_pin -pin_name $name -layer $layer \
    -location [list [expr { $x / double($dbu) }] [expr { $y / double($dbu) }]] \
    -pin_size [list [expr { ($bx1 - $bx0) / double($dbu) }] [expr { ($by1 - $by0) / double($dbu) }]]
  incr placed
}
# PINS_WEST, a pattern: own ports whose nets go round the notch through
# the west arm (to the top arm, say), at the bottom edge's west end. A
# port under its column would leave the global router a box that runs
# straight through the notch, where nothing can go, and the way round
# outside it.
set west {}
if { [info exists ::env(PINS_WEST)] && $::env(PINS_WEST) ne "" } {
  set west [lsearch -all -inline -regexp $own $::env(PINS_WEST)]
  set own [lsearch -all -inline -not -regexp $own $::env(PINS_WEST)]
  set_io_pin_constraint -region bottom:0-[expr { 2 * $::env(NOTCH_X0) }] -pin_names $west
}
set_io_pin_constraint -region bottom:* -pin_names $own
# A path from port to port is a wire through the parent. Repair would
# buffer it along a straight line, through the notch where no wire can
# go, and leave the global router boxes that miss the way round: it
# becomes one net, the buffer synthesis put between the ports removed,
# and is not touched again.
set through 0
foreach inst [$block getInsts] {
  set master [$inst getMaster]
  if { ![string match "BUF*" [$master getName]] } { continue }
  set in ""
  set out ""
  foreach it [$inst getITerms] {
    if { [$it getNet] eq "NULL" || [[$it getNet] getSigType] ne "SIGNAL" } { continue }
    if { [$it isInputSignal] } { set in [$it getNet] }
    if { [$it isOutputSignal] } { set out [$it getNet] }
  }
  if { $in eq "" || $out eq "" } { continue }
  if { [llength [$in getITerms]] != 1 || [llength [$in getBTerms]] != 1 } { continue }
  if { [llength [$out getITerms]] != 1 || [llength [$out getBTerms]] != 1 } { continue }
  set bt [lindex [$out getBTerms] 0]
  odb::dbInst_destroy $inst
  $bt connect $in
  odb::dbNet_destroy $out
  $in setDoNotTouch 1
  incr through
}
puts "io_notch.tcl: $placed tile pins in the notch, [llength $own] pins on the bottom edge, [llength $west] at its west end, $through feed-throughs kept whole"
