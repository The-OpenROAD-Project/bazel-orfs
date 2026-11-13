# The top level of a parent macro (parent_macro.bzl), flat: the parent
# macro PARENT_INST at the die's origin and each block where the parent's
# hole for it is (HOLES, as parent_holes.tcl reads it), each block's pins
# checked against the plan's (PLAN_PINS) the parent built its holes from,
# then every one of them dissolved into the cells, nets and route guides
# of its own global route (DISSOLVE_MASTERS, the parent's master first,
# and DISSOLVE_ODBS, their 5_1_grt.odb in the same order), its clock
# tree left behind for the top level's CTS to build
# one tree over every register. The cells stay where their macro placed
# them, fixed: the top level places only its clock tree.
#
# Then the macros nested in them that the flow lists (DISSOLVE_NESTED_MASTERS,
# DISSOLVE_NESTED_ODBS, parent_macro.bzl's dissolve_nested; XSTile's
# register files), each dissolved into its own flow's cells, LOCKED where
# that flow placed them, onto the top level's rows (dissolve_nested.tcl,
# DISSOLVE_NESTED_TCL): its registers on the top level's clock net
# (DISSOLVE_NESTED_CLOCKS, its clock pins) for the one tree.
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]

proc only_inst { block master } {
  set found {}
  foreach inst [$block getInsts] {
    if { [[$inst getMaster] getName] eq $master } { lappend found $inst }
  }
  if { [llength $found] != 1 } {
    utl::error FLW 21 "top_dissolve: $master has [llength $found] instances, one hole"
  }
  return [lindex $found 0]
}

set parent [$block findInst $::env(PARENT_INST)]
if { $parent eq "NULL" } { utl::error FLW 20 "top_dissolve: no instance $::env(PARENT_INST)" }
$parent setOrigin 0 0
$parent setOrient R0
$parent setPlacementStatus FIRM
set ::plan_pins_only 1
foreach f $::env(PLAN_PINS) {
  source $f
}
unset ::plan_pins_only
foreach {master x y w h} $::env(HOLES) {
  set inst [only_inst $block $master]
  set m [$inst getMaster]
  set moved {}
  foreach {pin layer qx qy qw qh} $::plan_pins($master) {
    set mterm [$m findMTerm $pin]
    if { $mterm eq "NULL" } {
      lappend moved "$pin (none)"
      continue
    }
    set box [lindex [[lindex [$mterm getMPins] 0] getGeometry] 0]
    set cx [expr { ([$box xMin] + [$box xMax]) / 2 }]
    set cy [expr { ([$box yMin] + [$box yMax]) / 2 }]
    if { abs($cx - round($qx * $dbu)) > 1 || abs($cy - round($qy * $dbu)) > 1
         || [[$box getTechLayer] getName] ne $layer } {
      lappend moved "$pin ([expr { $cx / double($dbu) }] [expr { $cy / double($dbu) }] [[$box getTechLayer] getName])"
    }
  }
  if { [llength $moved] > 0 } {
    utl::error FLW 22 "top_dissolve: $master's pins are not where the plan put them, [llength $moved] of them: [lrange $moved 0 4]; it was built from another plan"
  }
  $inst setOrigin [expr { int(round($x * $dbu)) }] [expr { int(round($y * $dbu)) }]
  $inst setOrient R0
  $inst setPlacementStatus FIRM
}

# Every buffer of the libraries: dissolve strips only the ones a macro's
# CTS or clock repair put on its clock nets.
set buffers {}
foreach cell [get_lib_cells *] {
  if { [get_property $cell is_buffer] } {
    lappend buffers [get_property $cell name]
  }
}
if { [llength $::env(DISSOLVE_MASTERS)] != [llength $::env(DISSOLVE_ODBS)] } {
  utl::error FLW 23 "top_dissolve: [llength $::env(DISSOLVE_MASTERS)] masters, [llength $::env(DISSOLVE_ODBS)] odbs"
}
foreach master $::env(DISSOLVE_MASTERS) odb_file $::env(DISSOLVE_ODBS) {
  # each flow's results are under its own design's name
  if { ![string match "*/$master/*" $odb_file] } {
    utl::error FLW 24 "top_dissolve: $odb_file is not $master's"
  }
  set inst [only_inst $block $master]
  set name [$inst getName]
  dissolve_macro -inst $name -db $odb_file -strip_clock_buffers $buffers
  puts "top_dissolve: $name dissolved from $odb_file"
}

# The rows the parent's cells sit on, over its core: the floorplan's,
# over the die, held a macro the size of the die. Made before the nested
# macros are dissolved: their cells go onto these rows.
foreach row [$block getRows] {
  odb::dbRow_destroy $row
}
make_rows -core_area $::env(PARENT_CORE_AREA) -site $::env(PLACE_SITE)

set nested {}
if { [env_var_exists_and_non_empty DISSOLVE_NESTED_MASTERS] } {
  source $::env(DISSOLVE_NESTED_TCL)
  set nested [dissolve_nested::run $block $::env(DISSOLVE_NESTED_MASTERS) \
    $::env(DISSOLVE_NESTED_ODBS) $::env(DISSOLVE_NESTED_CLOCKS) $buffers]
}

# The supply pins of what the dissolves brought in. floorplan.tcl made the
# platform's global connections before any of these instances existed and
# left the rules in the database for a later step that creates instances:
# this one. pdn.tcl applies them again, but after PDN_TCL, and PDN_TCL
# builds a grid over each macro from the supply nets its pins are on: a
# macro on none gets no grid (PDN-0231) and the step goes on without it;
# only when no macro has one does the connect to that grid stop the step
# (PDN-0217). global_connect skips a dont_touch instance (ODB-0383), and a
# dissolved cell is dont_touch when its cell in the block was, so the flag
# is lifted for the connections and put back, as pdn.tcl does.
proc open_supply_pins { inst } {
  set open {}
  foreach iterm [$inst getITerms] {
    set mterm [$iterm getMTerm]
    set type [$mterm getSigType]
    if { ($type eq "POWER" || $type eq "GROUND") && [$iterm getNet] eq "NULL" } {
      lappend open [$mterm getName]
    }
  }
  return $open
}
set lifted {}
set macros {}
foreach inst [$block getInsts] {
  if { [$inst isBlock] } {
    lappend macros $inst
  }
  if { [$inst isDoNotTouch] && [llength [open_supply_pins $inst]] > 0 } {
    lappend lifted $inst
  }
}
foreach inst $lifted {
  $inst setDoNotTouch 0
}
set connected [global_connect]
foreach inst $lifted {
  $inst setDoNotTouch 1
}
# A macro with a supply pin on no net stops here: the PDN would warn, leave
# it without a grid and go on, unless every macro were unpowered.
set unpowered {}
foreach inst $macros {
  set open [open_supply_pins $inst]
  if { [llength $open] > 0 } {
    lappend unpowered "[$inst getName] ($open)"
  }
}
if { [llength $unpowered] > 0 } {
  utl::error FLW 31 "top_dissolve: [llength $unpowered] of [llength $macros] macros have a supply pin on no net after the global connections ($connected pins connected): [lrange $unpowered 0 4]; no rule names the pin, or the database holds no rules (ODB-0378)"
}
puts "top_dissolve: [llength $macros] macros on their supply nets, $connected pins connected, dont_touch lifted from [llength $lifted] instances for the global connections"
# the nested macros' cells on theirs, for the power grid pdn.tcl lays along
# their rows after this step
if { [llength $nested] > 0 } {
  dissolve_nested::check_supply $nested
}

set fixed 0
foreach inst [$block getInsts] {
  if { [$inst isPlaced] } {
    $inst setPlacementStatus LOCKED
    incr fixed
  }
}
puts "top_dissolve: $fixed instances fixed where their macros placed them"

# A macro off the top level's rows or sites, or overlapping another,
# stops here, not at the legaliser.
check_placement -verbose
