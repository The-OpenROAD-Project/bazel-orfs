# A macro pin plan: a placed parent tells each hardened macro where its pins
# belong, on as many of its sides as its logic needs. For every signal pin
# of a macro instance,
# the centre of what the pin's net reaches in the parent (the other pins
# and ports on the net, the block's own pin left out) is taken into the
# block's frame and projected onto the nearest point of the block's
# outline: that side, and a stretch of it around that point, is the pin's
# region. Pins that land on the same side are written as one constraint
# per side, from the first to the last projection, widened to room for
# them all; the pin placer orders them inside it.
#
# A side that faces nothing but the die's edge gets no pins: no partner
# projects onto it.
#
# PIN_PLAN_STAGE is the parent's stage to read (3_place, 4_cts, 5_1_grt).
# PINS_OUT is a list of <macro module> <path> <width um> <height um>: one
# pin script per entry, for the macro's next build (IO_CONSTRAINTS). A
# width and height of 0 write it in the frame of the master the parent
# placed; others scale every place and stretch to a die of that size, for
# a block whose parent sees a mocked outline of the same shape. A block
# with several instances is written from the first by name, and says so.
# Macros PINS_OUT does not name, a generated SRAM's say, keep their pins.
#
# PIN_PLAN_PLACEMENT, when set, gets every macro's place from this
# placement, so the next build keeps the places the pins were planned for.
#
# PIN_PLAN_REPORT, when set, gets a table of every macro's signal pins as
# they are: how many on each side, and how many of those face away from
# their logic (the side their partners' centre projects onto is another).
# The same measure before and after a plan says what it did.
#
# From bazel-orfs #1294's pin loop (pins_from_parent.tcl), there one side
# per hardened block of a planned parent.
source $::env(SCRIPTS_DIR)/load.tcl
set stage $::env(PIN_PLAN_STAGE)
load_design $stage.odb $stage.sdc
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
# room per pin along a side: eight M3 tracks, twice asap7's planner
# pitch, since the pin placer does not use every slot on every layer, and
# down to four (the planner's pitch) where a side is crowded; a stretch at
# least min_um long; and corner_um kept clear at each end of a side, where
# the pin placer avoids the corners. A stretch of exactly the pitch at a
# side's end once stopped the pin placer on a bare "vector".
set room_um 0.288
set tight_um 0.144
set min_um 2.0
set corner_um 1.0

# One set_io_pin_constraint per side: pins is {side {{name pos} ...}},
# lens {side length}, all in um along the side; each stretch from the
# first to the last position, widened to room for its pins and kept
# clear of the side's corners.
proc write_regions { f what sides lens } {
  global room_um tight_um min_um corner_um
  foreach side {left right bottom top} {
    set pins [dict get $sides $side]
    if { [llength $pins] == 0 } { continue }
    set len [dict get $lens $side]
    set ps [lmap p $pins { lindex $p 1 }]
    set lo [tcl::mathfunc::min {*}$ps]
    set hi [tcl::mathfunc::max {*}$ps]
    set free [expr { $len - 2 * $corner_um }]
    set need [expr { max(min([llength $pins] * $room_um, $free), [llength $pins] * $tight_um, $min_um) }]
    if { $need > $free } {
      error "pin_plan.tcl: $what needs $need um of its $side side for [llength $pins] pins, has $free between its corners"
    }
    if { $hi - $lo < $need } {
      set mid [expr { ($lo + $hi) / 2 }]
      set lo [expr { $mid - $need / 2 }]
      set hi [expr { $mid + $need / 2 }]
    }
    # inside the side and clear of its corners, the shift keeping the
    # stretch's length
    if { $lo < $corner_um } { set hi [expr { $hi + $corner_um - $lo }]; set lo $corner_um }
    if { $hi > $len - $corner_um } {
      set lo [expr { $lo - ($hi - ($len - $corner_um)) }]
      set hi [expr { $len - $corner_um }]
    }
    # projections reaching both corners span more than the room between
    # them, and the shifts above push the stretch past the side's start
    set lo [expr { max($lo, $corner_um) }]
    puts $f "set_io_pin_constraint -region $side:[format %.3f $lo]-[format %.3f $hi] -pin_names {[lmap p $pins { lindex $p 0 }]}"
    puts "pin_plan.tcl: $what [llength $pins] pins on $side [format %.3f $lo]-[format %.3f $hi] um"
  }
}

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
    default { error "pin_plan.tcl: [$inst getName] is [$inst getOrient], not R0, MY, MX or R180" }
  }
}

# The centre of what a macro pin's net reaches in the parent, the pin itself
# left out: the other pins and the ports on the net. Empty with none.
proc partner_centre { iterm } {
  set net [$iterm getNet]
  if { $net eq "NULL" } { return {} }
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
  if { [llength $xs] == 0 } { return {} }
  return [list [expr { [tcl::mathop::+ {*}$xs] / [llength $xs] }] \
    [expr { [tcl::mathop::+ {*}$ys] / [llength $ys] }]]
}

# The side of a w x h box a point (bx by, in the box's frame) belongs to,
# and its place along that side: the smallest signed distance to each
# edge's line, which outside the box is the side the point is farthest out
# past and inside it the nearest edge; the place, the point clamped.
proc box_side { w h bx by } {
  set d [dict create left $bx right [expr { $w - $bx }] bottom $by top [expr { $h - $by }]]
  set side [lindex [lsort -stride 2 -index 1 -real $d] 0]
  set px [expr { min(max($bx, 0), $w) }]
  set py [expr { min(max($by, 0), $h) }]
  return [list $side [expr { $side in {left right} ? $py : $px }]]
}

# Every macro's signal pins as they are, in the parent's frame: how many on
# each side and how many of those face away from their logic.
if { [info exists ::env(PIN_PLAN_REPORT)] && $::env(PIN_PLAN_REPORT) ne "" } {
  set f [open $::env(PIN_PLAN_REPORT) w]
  puts $f "# pin_plan.tcl: [$block getName] at $stage, every macro's signal pins by the side they are on (parent frame), and of them, those facing away from their logic"
  puts $f [format "%-40s %-24s %6s %6s %6s %6s %6s %6s" instance master pins top bottom left right away]
  set total 0
  set total_away 0
  foreach inst [lsort -command { apply {{a b} { string compare [$a getName] [$b getName] }} } [$block getInsts]] {
    if { ![[$inst getMaster] isBlock] } { continue }
    set box [$inst getBBox]
    set w [$box getDX]
    set h [$box getDY]
    set on [dict create top 0 bottom 0 left 0 right 0]
    set away 0
    set n 0
    foreach iterm [$inst getITerms] {
      if { [$iterm getSigType] ne "SIGNAL" } { continue }
      set c [partner_centre $iterm]
      if { $c eq "" } { continue }
      set pb [$iterm getBBox]
      lassign [box_side $w $h [expr { ([$pb xMin] + [$pb xMax]) / 2.0 - [$box xMin] }] \
        [expr { ([$pb yMin] + [$pb yMax]) / 2.0 - [$box yMin] }]] is
      lassign [box_side $w $h [expr { [lindex $c 0] - [$box xMin] }] \
        [expr { [lindex $c 1] - [$box yMin] }]] wants
      dict incr on $is
      if { $is ne $wants } { incr away }
      incr n
    }
    puts $f [format "%-40s %-24s %6d %6d %6d %6d %6d %6d" [$inst getName] [[$inst getMaster] getName] \
      $n [dict get $on top] [dict get $on bottom] [dict get $on left] [dict get $on right] $away]
    incr total $n
    incr total_away $away
  }
  puts $f "total $total pins, $total_away facing away from their logic"
  close $f
}

# Every macro where this placement put it, for the next build's
# MACRO_PLACEMENT_TCL: the pins are planned for these places, so the next
# build keeps them.
if { [info exists ::env(PIN_PLAN_PLACEMENT)] && $::env(PIN_PLAN_PLACEMENT) ne "" } {
  set f [open $::env(PIN_PLAN_PLACEMENT) w]
  puts $f "# Written by pin_plan.tcl: [$block getName]'s macros where its $stage placement put them."
  foreach inst [lsort -command { apply {{a b} { string compare [$a getName] [$b getName] }} } [$block getInsts]] {
    if { ![[$inst getMaster] isBlock] } { continue }
    set loc [$inst getLocation]
    puts $f [format "place_macro -macro_name {%s} -location {%s %s} -orientation %s -exact" \
      [$inst getName] [expr { double([lindex $loc 0]) / $dbu }] \
      [expr { double([lindex $loc 1]) / $dbu }] [$inst getOrient]]
    puts $f "\[\[ord::get_db_block\] findInst {[$inst getName]}\] setPlacementStatus FIRM"
  }
  close $f
}

set out [dict create]
foreach {module path tw th} $::env(PINS_OUT) { dict lappend out $module [list $path $tw $th] }
set done [dict create]
set insts [lsort -command { apply {{a b} { string compare [$a getName] [$b getName] }} } [$block getInsts]]
foreach inst $insts {
  set m [$inst getMaster]
  if { ![$m isBlock] } { continue }
  set module [$m getName]
  if { ![dict exists $out $module] } {
    puts "pin_plan.tcl: $module ([$inst getName]) not planned: PINS_OUT does not name it"
    continue
  }
  if { [dict exists $done $module] } {
    puts "pin_plan.tcl: $module written from [dict get $done $module], [$inst getName] not used"
    continue
  }
  dict set done $module [$inst getName]
  set w [$m getWidth]
  set h [$m getHeight]
  set sides [dict create left {} right {} bottom {} top {}]
  foreach iterm [$inst getITerms] {
    if { [$iterm getSigType] ne "SIGNAL" } { continue }
    set c [partner_centre $iterm]
    if { $c eq "" } { continue }
    lassign [to_block_frame $inst {*}$c] bx by
    lassign [box_side $w $h $bx $by] side pos
    dict lappend sides $side [list [[$iterm getMTerm] getName] [expr { $pos / double($dbu) }]]
  }
  foreach target [dict get $out $module] {
    lassign $target path tw th
    set mw [expr { $w / double($dbu) }]
    set mh [expr { $h / double($dbu) }]
    set sx [expr { $tw > 0 ? $tw / $mw : 1.0 }]
    set sy [expr { $th > 0 ? $th / $mh : 1.0 }]
    set f [open $path w]
    puts $f "# Written by pin_plan.tcl from [$block getName]'s placement, instance [$inst getName], scaled [format %.4f $sx] x [format %.4f $sy]."
    set scaled [dict create]
    foreach side {left right bottom top} {
      set scale [expr { $side in {left right} ? $sy : $sx }]
      dict set scaled $side [lmap p [dict get $sides $side] { list [lindex $p 0] [expr { [lindex $p 1] * $scale }] }]
    }
    write_regions $f "$path: $module" $scaled [dict create left [expr { $mh * $sy }] right [expr { $mh * $sy }] bottom [expr { $mw * $sx }] top [expr { $mw * $sx }]]
    close $f
  }
}
foreach module [dict keys $out] {
  if { ![dict exists $done $module] } {
    error "pin_plan.tcl: PINS_OUT names $module, which [$block getName] does not instantiate"
  }
}

# The parent's own ports where this placement left them, for a parent
# whose ports are free (PARENT_PINS_OUT): the next round's macro placer
# then sees them where they ended rather than at random.
if { [info exists ::env(PARENT_PINS_OUT)] && $::env(PARENT_PINS_OUT) ne "" } {
  set die [$block getDieArea]
  set sides [dict create left {} right {} bottom {} top {}]
  foreach bterm [$block getBTerms] {
    if { [$bterm getSigType] ne "SIGNAL" } { continue }
    set b [$bterm getBBox]
    set cx [expr { (([$b xMin] + [$b xMax]) / 2.0 - [$die xMin]) / $dbu }]
    set cy [expr { (([$b yMin] + [$b yMax]) / 2.0 - [$die yMin]) / $dbu }]
    set w [expr { [$die dx] / double($dbu) }]
    set h [expr { [$die dy] / double($dbu) }]
    set d [dict create left $cx right [expr { $w - $cx }] bottom $cy top [expr { $h - $cy }]]
    set side [lindex [lsort -stride 2 -index 1 -real $d] 0]
    dict lappend sides $side [list [$bterm getName] [expr { $side in {left right} ? $cy : $cx }]]
  }
  set f [open $::env(PARENT_PINS_OUT) w]
  puts $f "# Written by pin_plan.tcl: [$block getName]'s ports where its placement left them."
  write_regions $f "[$block getName] ports" $sides [dict create left $h right $h bottom $w top $w]
  close $f
}
