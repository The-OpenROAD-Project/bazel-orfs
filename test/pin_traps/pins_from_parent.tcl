# One round of the pin loop: a placed parent (3_place.odb) tells each
# block where its pins belong. For every signal pin of a block instance,
# the centre of what the pin's net reaches in the parent (the other pins
# and ports on the net, the block's own pin left out) is taken into the
# block's frame and projected onto the nearest point of the block's
# outline: that side, and a stretch of it around that point, is the pin's
# region. Pins that land on the same side are written as one constraint
# per side, from the first to the last projection, widened to room for
# them all; the pin placer orders them inside it.
#
# PINS_OUT is a list of <block module> <path>: one pin script per block,
# for the block's next build (IO_CONSTRAINTS). A block with several
# instances is written from the first by name, and says so.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
# room per pin along a side: four M3 tracks, asap7's planner pitch
set room_um 0.144

proc to_block_frame { inst x y } {
  # a point of the parent in the frame of the block's master, for the
  # orientations a parent places a block in
  set box [$inst getBBox]
  set m [$inst getMaster]
  set w [$m getWidth]
  set h [$m getHeight]
  set dx [expr { $x - [$box xMin] }]
  set dy [expr { $y - [$box yMin] }]
  switch [$inst getOrient] {
    R0 { return [list $dx $dy] }
    MY { return [list [expr { $w - $dx }] $dy] }
    MX { return [list $dx [expr { $h - $dy }]] }
    R180 { return [list [expr { $w - $dx }] [expr { $h - $dy }]] }
    default { error "pins_from_parent.tcl: [$inst getName] is [$inst getOrient], not R0, MY, MX or R180" }
  }
}

set out [dict create]
foreach {module path} $::env(PINS_OUT) { dict set out $module $path }
set done [dict create]
set insts [lsort -command { apply {{a b} { string compare [$a getName] [$b getName] }} } [$block getInsts]]
foreach inst $insts {
  set m [$inst getMaster]
  if { ![$m isBlock] } { continue }
  set module [$m getName]
  if { ![dict exists $out $module] } {
    error "pins_from_parent.tcl: no PINS_OUT path for block $module ([$inst getName])"
  }
  if { [dict exists $done $module] } {
    puts "pins_from_parent.tcl: $module written from [dict get $done $module], [$inst getName] not used"
    continue
  }
  dict set done $module [$inst getName]
  set w [$m getWidth]
  set h [$m getHeight]
  set sides [dict create left {} right {} bottom {} top {}]
  foreach iterm [$inst getITerms] {
    if { [$iterm getSigType] ne "SIGNAL" } { continue }
    set net [$iterm getNet]
    if { $net eq "NULL" } { continue }
    set xs {}
    set ys {}
    foreach other [$net getITerms] {
      if { $other eq $iterm } { continue }
      set b [$other getBBox]
      lappend xs [expr { ([$b xMin] + [$b xMax]) / 2.0 }]
      lappend ys [expr { ([$b yMin] + [$b yMax]) / 2.0 }]
    }
    foreach bterm [$net getBTerms] {
      set b [$bterm getBBox]
      lappend xs [expr { ([$b xMin] + [$b xMax]) / 2.0 }]
      lappend ys [expr { ([$b yMin] + [$b yMax]) / 2.0 }]
    }
    if { [llength $xs] == 0 } { continue }
    set cx [expr { [tcl::mathop::+ {*}$xs] / [llength $xs] }]
    set cy [expr { [tcl::mathop::+ {*}$ys] / [llength $ys] }]
    lassign [to_block_frame $inst $cx $cy] bx by
    # the side: the smallest signed distance to each edge's line, which
    # outside the box is the side the point is farthest out past and
    # inside it the nearest edge; the place on it, the point clamped
    set d [dict create left $bx right [expr { $w - $bx }] bottom $by top [expr { $h - $by }]]
    set side [lindex [lsort -stride 2 -index 1 -real $d] 0]
    set px [expr { min(max($bx, 0), $w) }]
    set py [expr { min(max($by, 0), $h) }]
    set pos [expr { $side in {left right} ? $py : $px }]
    dict lappend sides $side [list [[$iterm getMTerm] getName] [expr { $pos / double($dbu) }]]
  }
  set f [open [dict get $out $module] w]
  puts $f "# Written by pins_from_parent.tcl from [$block getName]'s placement, instance [$inst getName]."
  foreach side {left right bottom top} {
    set pins [dict get $sides $side]
    if { [llength $pins] == 0 } { continue }
    set len [expr { ($side in {left right} ? $h : $w) / double($dbu) }]
    set ps [lmap p $pins { lindex $p 1 }]
    set lo [tcl::mathfunc::min {*}$ps]
    set hi [tcl::mathfunc::max {*}$ps]
    set need [expr { [llength $pins] * $room_um }]
    if { $need > $len } {
      error "pins_from_parent.tcl: $module needs $need um of its $side side for [llength $pins] pins, has $len"
    }
    if { $hi - $lo < $need } {
      set mid [expr { ($lo + $hi) / 2 }]
      set lo [expr { $mid - $need / 2 }]
      set hi [expr { $mid + $need / 2 }]
    }
    # inside the side, the shift keeping the stretch's length
    if { $lo < 0 } { set hi [expr { $hi - $lo }]; set lo 0 }
    if { $hi > $len } { set lo [expr { $lo - ($hi - $len) }]; set hi $len }
    puts $f "set_io_pin_constraint -region $side:[format %.3f $lo]-[format %.3f $hi] -pin_names {[lmap p $pins { lindex $p 0 }]}"
    puts "pins_from_parent.tcl: $module [llength $pins] pins on $side [format %.3f $lo]-[format %.3f $hi] um"
  }
  close $f
}
foreach module [dict keys $out] {
  if { ![dict exists $done $module] } {
    error "pins_from_parent.tcl: PINS_OUT names $module, which [$block getName] does not instantiate"
  }
}
