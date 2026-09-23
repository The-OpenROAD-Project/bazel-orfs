# The DIE_AREA and CORE_AREA of a mocked abstract: the real floorplan's,
# scaled. MOCK_AREA is either a factor (0.5 halves both sides) or "pins",
# which fits the die to the block's pins: the smallest square whose
# MOCK_AREA_PIN_EDGES edges (2 by default, see mock_pins.tcl) hold every
# BTerm at place_pins' spacing on the pin layers the flow allows, times
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

proc mock_area_gcd { a b } {
  while { $b } { set t [expr { $a % $b }]; set a $b; set b $t }
  return $a
}

# (period, sorted residues) of a layer's tracks along an axis, from the
# block's track patterns: a layer's grid may be several interleaved
# patterns (asap7's M2 y tracks are seven of period 0.27 um), so it
# repeats with their common period and has a track at each residue.
# Empty when the layer has no tracks.
proc mock_area_track_residues { block layer axis } {
  set tg [$block findTrackGrid $layer]
  if { $tg eq "NULL" } { return {} }
  if { $axis eq "V" } { set n [$tg getNumGridPatternsX] } else { set n [$tg getNumGridPatternsY] }
  set pats {}
  set period 0
  for { set i 0 } { $i < $n } { incr i } {
    if { $axis eq "V" } { set p [$tg getGridPatternX $i] } else { set p [$tg getGridPatternY $i] }
    lassign $p origin count step
    if { $step <= 0 } { continue }
    lappend pats [list $origin $step]
    set period [expr { $period ? $period * $step / [mock_area_gcd $period $step] : $step }]
  }
  if { !$period } { return {} }
  set res [dict create]
  foreach p $pats {
    lassign $p origin step
    for { set k 0 } { $k < $period / $step } { incr k } {
      dict set res [expr { ($origin + $k * $step) % $period }] 1
    }
  }
  return [list $period [lsort -integer [dict keys $res]]]
}

# Whether a mirror of a block this long maps every layer's track set onto
# itself, so pins on those tracks stay on tracks under the flip.
proc mock_area_mirror_legal { size residues_list } {
  foreach pr $residues_list {
    lassign $pr period res
    set mirrored [dict create]
    foreach r $res { dict set mirrored [expr { (($size - $r) % $period + $period) % $period }] 1 }
    if { [lsort -integer [dict keys $mirrored]] ne $res } { return 0 }
  }
  return 1
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
      foreach name $::env($var) {
        set layer [[$db getTech] findLayer $name]
        if { $layer ne "NULL" && [$layer getPitch] > $pitch } { set pitch [$layer getPitch] }
      }
    }
  }
  if { $pitch == 0 } { error "MOCK_AREA=pins needs IO_PLACER_H/IO_PLACER_V naming routing layers with a pitch" }
  # The pins go on MOCK_AREA_PIN_EDGES adjacent edges (mock_pins.tcl; 2 by
  # default, so the mock has an orientation), stacked on as many layers as
  # the flow gives place_pins for that edge direction.
  set edges [expr { [info exists ::env(MOCK_AREA_PIN_EDGES)] ? int($::env(MOCK_AREA_PIN_EDGES)) : 2 }]
  set layers [expr { min([llength $::env(IO_PLACER_H)], [llength $::env(IO_PLACER_V)]) }]
  set pins [llength [$block getBTerms]]
  set margin [expr { [info exists ::env(MOCK_AREA_PIN_MARGIN)] ? double($::env(MOCK_AREA_PIN_MARGIN)) : 1.5 }]
  set perimeter [expr { $pins * $tracks * $pitch / double($layers) }]
  set side [expr { $margin * $perimeter / double($edges) }]
  set longest [expr { double(max([$die_bbox dx], [$die_bbox dy])) }]
  # A parent may flip the mock. A flip about the y axis moves a pin from
  # x to side - x, which is on a track only for some sides: those whose
  # mirror maps every vertical pin layer's track set onto itself (M3 at
  # pitch 0.036 from 0.009 needs side == 0.018 mod 0.036). So the side is
  # rounded up to the first size legal for a flip about the x axis (the
  # horizontal pin layers), and for both axes when such a size exists;
  # asap7's M3 and M5 on one edge have none, and then only MX is legal
  # and the parent's placer knows to keep MY off.
  if { $side < $longest } {
    set hres {}
    set vres {}
    set periods {}
    foreach {var axis lst} {IO_PLACER_H H hres IO_PLACER_V V vres} {
      foreach name $::env($var) {
        set layer [[$db getTech] findLayer $name]
        if { $layer eq "NULL" } { continue }
        set r [mock_area_track_residues $block $layer $axis]
        if { [llength $r] } { lappend $lst $r; lappend periods [lindex $r 0] }
      }
    }
    set grid [[$db getTech] getManufacturingGrid]
    if { $grid <= 0 } { set grid 1 }
    set span 1
    foreach p $periods { set span [expr { $span * $p / [mock_area_gcd $span $p] }] }
    set s0 [expr { int(ceil($side / $grid)) * $grid }]
    set best_h -1
    set best_hv -1
    for { set s $s0 } { $s < $s0 + $span && $best_hv < 0 } { incr s $grid } {
      if { [mock_area_mirror_legal $s $hres] } {
        if { $best_h < 0 } { set best_h $s }
        if { [mock_area_mirror_legal $s $vres] } { set best_hv $s }
      }
    }
    if { $best_hv >= 0 } {
      set side $best_hv
      set flips "MX and MY"
    } elseif { $best_h >= 0 } {
      set side $best_h
      set flips "MX only"
    } else {
      set side $s0
      set flips "none"
    }
    puts "MOCK_AREA=pins: flips that keep the pins on tracks at this side: $flips"
  }
  set factor [expr { min(1.0, $side / $longest) }]
  # A square of that side, never larger than the real die on either axis:
  # scaling the real outline by the factor would give a non-square block
  # a short edge holding fewer pins than the side was fitted for.
  set die_w [expr { int(round(min($side, double([$die_bbox xMax])))) }]
  set die_h [expr { int(round(min($side, double([$die_bbox yMax])))) }]
  puts "MOCK_AREA=pins: $pins pins on $edges edge(s), $layers layer(s), [expr { $tracks * $pitch / $dbu_per_uu }] um per pin, margin $margin: side [expr { $side / $dbu_per_uu }] um of [expr { $longest / $dbu_per_uu }] um, factor $factor"
  # What the parent will have to route: every pin is a wire that leaves
  # through the channel along its side and travels along it on the layers
  # that run that way. Pins on a side divided by those layers' track density
  # is the channel width the side needs, before the parent's own wires. The
  # mock does not know its parent's channels, so this is a number, not a
  # verdict for the parent's floorplan to check against the channels it
  # draws.
  foreach {edge var count} [list bottom IO_PLACER_H [expr { $edges == 1 ? $pins : $edges == 2 ? ($pins + 1) / 2 : ($pins + 3) / 4 }] \
                                left IO_PLACER_V [expr { $edges == 1 ? 0 : $edges == 2 ? $pins / 2 : ($pins + 3) / 4 }]] {
    set density 0.0
    foreach name $::env($var) {
      set layer [[$db getTech] findLayer $name]
      if { $layer ne "NULL" && [$layer getPitch] > 0 } { set density [expr { $density + $dbu_per_uu / double([$layer getPitch]) }] }
    }
    if { $count > 0 && $density > 0 } {
      puts [format "MOCK_AREA=pins: escape: %d pins on the %s side need %.1f um of channel along it (%s: %.1f tracks/um)" $count $edge [expr { $count / $density }] $::env($var) $density]
    }
  }
} else {
  set factor [expr { double($::env(MOCK_AREA)) }]
  set die_w [expr { int(round($factor * [$die_bbox xMax])) }]
  set die_h [expr { int(round($factor * [$die_bbox yMax])) }]
}
# Whole dbu, so the die the flow builds is exactly the side chosen above.
# The die-to-core margins are absolute and are kept, so a die scaled below
# them would give a negative core; the core keeps at least one row. A
# power grid that needs more than that fails at the mocked floorplan
# (PDN-0185): the block is too small for the mock to shrink, so raise
# MOCK_AREA_PIN_MARGIN or keep its real outline.
set rows [$block getRows]
set min_core [expr { [llength $rows] ? [[[lindex $rows 0] getSite] getHeight] : 0 }]
foreach {var lo hi} [list die_w [expr { [$core_bbox xMin] - [$die_bbox xMin] }] [expr { [$die_bbox xMax] - [$core_bbox xMax] }] \
                          die_h [expr { [$core_bbox yMin] - [$die_bbox yMin] }] [expr { [$die_bbox yMax] - [$core_bbox yMax] }]] {
  set floor [expr { min($lo + $hi + $min_core, $var eq "die_w" ? [$die_bbox xMax] : [$die_bbox yMax]) }]
  if { [set $var] < $floor } {
    puts "MOCK_AREA: $var [expr { [set $var] / $dbu_per_uu }] um is inside the die-to-core margins, raised to [expr { $floor / $dbu_per_uu }] um"
    set $var $floor
  }
}

set die_area "0 0 [expr $die_w / $dbu_per_uu] [expr $die_h / $dbu_per_uu]"
set core_area "[expr ([$core_bbox xMin] - [$die_bbox xMin]) / $dbu_per_uu] \
 [expr ([$core_bbox yMin] - [$die_bbox yMin]) / $dbu_per_uu] \
 [expr ($die_w - ([$die_bbox xMax] - [$core_bbox xMax])) / $dbu_per_uu ] \
 [expr ($die_h - ([$die_bbox yMax] - [$core_bbox yMax])) / $dbu_per_uu]"

set f [open $::env(OUTPUT) w]
puts $f "\{\"DIE_AREA\": \"$die_area\", \"CORE_AREA\": \"$core_area\", \"CORE_UTILIZATION\": \"\"\}"
close $f
