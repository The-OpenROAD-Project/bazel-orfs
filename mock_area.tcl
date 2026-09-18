# The DIE_AREA and CORE_AREA of a mocked abstract: the real floorplan's,
# scaled. MOCK_AREA is either a factor (0.5 halves both sides) or "pins",
# which fits the die to the block's pins: the smallest square whose four
# edges hold every BTerm at place_pins' spacing, times
# MOCK_AREA_PIN_MARGIN (default 1.5, so the parent's wires to a macro do
# not all converge on pins at the legal minimum pitch), and never larger
# than the real die. A block whose size is set by its pins keeps its size;
# one sized by its cells shrinks to what the parent has to route to.
read_db $::env(RESULTS_DIR)/2_floorplan.odb
set db [::ord::get_db]
set dbu_per_uu [expr double([[$db getTech] getDbUnitsPerMicron])]
set block [[$db getChip] getBlock]
set die_bbox [$block getDieArea]
set core_bbox [$block getCoreArea]

proc area_um {bbox} {
  global dbu_per_uu
  return "[expr [$bbox xMin] / $dbu_per_uu] [expr [$bbox yMin] / $dbu_per_uu] [expr [$bbox xMax] / $dbu_per_uu] [expr [$bbox yMax] / $dbu_per_uu]"
}

puts "DIE_AREA: [area_um $die_bbox]"
puts "CORE_AREA: [area_um $core_bbox]"

if { $::env(MOCK_AREA) eq "pins" } {
  # Spacing along an edge: place_pins' minimum distance in tracks (its
  # default is 2; PLACE_PINS_ARGS may say otherwise) times the coarser of
  # the two pin layers' pitches, so both edge directions are covered.
  set tracks 2
  if { [info exists ::env(PLACE_PINS_ARGS)] } {
    set args $::env(PLACE_PINS_ARGS)
    set i [lsearch -exact $args -min_distance]
    if { $i >= 0 && [lsearch -exact $args -min_distance_in_tracks] >= 0 } {
      set tracks [lindex $args [expr { $i + 1 }]]
    }
  }
  set pitch 0
  foreach var {IO_PLACER_H IO_PLACER_V} {
    if { [info exists ::env($var)] } {
      set layer [[$db getTech] findLayer $::env($var)]
      if { $layer ne "NULL" && [$layer getPitch] > $pitch } { set pitch [$layer getPitch] }
    }
  }
  if { $pitch == 0 } { error "MOCK_AREA=pins needs IO_PLACER_H/IO_PLACER_V naming routing layers with a pitch" }
  set pins [llength [$block getBTerms]]
  set margin [expr { [info exists ::env(MOCK_AREA_PIN_MARGIN)] ? double($::env(MOCK_AREA_PIN_MARGIN)) : 1.5 }]
  set perimeter [expr { $pins * $tracks * $pitch }]
  set side [expr { $margin * $perimeter / 4.0 }]
  set longest [expr { double(max([$die_bbox dx], [$die_bbox dy])) }]
  set factor [expr { min(1.0, $side / $longest) }]
  puts "MOCK_AREA=pins: $pins pins, [expr { $tracks * $pitch / $dbu_per_uu }] um per pin, margin $margin: side [expr { $side / $dbu_per_uu }] um of [expr { $longest / $dbu_per_uu }] um, factor $factor"
} else {
  set factor [expr { double($::env(MOCK_AREA)) }]
}
set scale [expr { $factor / $dbu_per_uu }]

set die_area "0 0 [expr $scale*[$die_bbox xMax]] [expr $scale*[$die_bbox yMax]]"
set core_area "[expr ([$core_bbox xMin] - [$die_bbox xMin]) / $dbu_per_uu] \
 [expr ([$core_bbox yMin] - [$die_bbox yMin]) / $dbu_per_uu] \
 [expr $scale*[$die_bbox xMax] - ([$die_bbox xMax] - [$core_bbox xMax]) / $dbu_per_uu ] \
 [expr $scale*[$die_bbox yMax] - ([$die_bbox yMax] - [$core_bbox yMax]) / $dbu_per_uu]"

set f [open $::env(OUTPUT) w]
puts $f "\{\"DIE_AREA\": \"$die_area\", \"CORE_AREA\": \"$core_area\", \"CORE_UTILIZATION\": \"\"\}"
close $f
