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

set fixed 0
foreach inst [$block getInsts] {
  if { [$inst isPlaced] } {
    $inst setPlacementStatus LOCKED
    incr fixed
  }
}
puts "top_dissolve: $fixed instances fixed where their macros placed them"

# The rows the parent's cells sit on, over its core: the floorplan's,
# over the die, held a macro the size of the die.
foreach row [$block getRows] {
  odb::dbRow_destroy $row
}
make_rows -core_area $::env(PARENT_CORE_AREA) -site $::env(PLACE_SITE)
# A macro off the top level's rows or sites, or overlapping another,
# stops here, not at the legaliser.
check_placement -verbose
