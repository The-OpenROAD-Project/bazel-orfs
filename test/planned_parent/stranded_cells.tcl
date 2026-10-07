# The parent's legalization hook on the miniature, as JSON: a few placed
# cells moved to the middle of the biggest hard block, where there is no
# row, then the hook's own step and the detailed placement it wraps
# (legalize_out_of_blocks.tcl). The miniature's blocks are 31 um deep;
# the legaliser's fallback finds such cells a row by itself, and failed
# only on XSTile's few hundred um deep (DPL-0036), so this checks what the
# hook does, not that the miniature fails without it. Declared beside the
# flow it probes.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 3_place.odb 3_place.sdc
set block [ord::get_db_block]
set big ""
set area 0
foreach inst [$block getInsts] {
  if { ![[$inst getMaster] isBlock] } { continue }
  set b [$inst getBBox]
  set a [expr { double([$b getDX]) * [$b getDY] }]
  if { $a > $area } { set area $a; set big $inst }
}
set b [$big getBBox]
set cx [expr { ([$b xMin] + [$b xMax]) / 2 }]
set cy [expr { ([$b yMin] + [$b yMax]) / 2 }]
set stranded {}
foreach inst [$block getInsts] {
  if { [$inst getPlacementStatus] ne "PLACED" || [[$inst getMaster] getType] ne "CORE" } { continue }
  $inst setLocation $cx $cy
  lappend stranded $inst
  if { [llength $stranded] == 4 } { break }
}
proc inside { stranded box } {
  set n 0
  foreach inst $stranded {
    set l [$inst getLocation]
    incr n [expr { [lindex $l 0] >= [$box xMin] && [lindex $l 0] < [$box xMax]
      && [lindex $l 1] >= [$box yMin] && [lindex $l 1] < [$box yMax] }]
  }
  return $n
}
set before [inside $stranded $b]
source $::env(LEGALIZE_HOOK)
set wrapped [expr { [info procs detailed_placement_helper_inner] ne "" }]
cells_out_of_blocks
set after_hook [inside $stranded $b]
set moved [expr { $before - $after_hook }]
foreach inst $stranded { $inst setLocation $cx $cy }
set legal [expr { ![catch { detailed_placement_helper } msg] && ![catch { check_placement -verbose } msg] }]
set f [open $::env(OUTPUT_JSON) w]
puts $f [format {{"block": "%s", "stranded": %d, "inside_before": %d, "wrapped": %s,
 "moved": %d, "inside_after_hook": %d, "inside_after_legalization": %d, "legal": %s, "error": "%s"}} \
  [$big getName] [llength $stranded] $before [expr { $wrapped ? "true" : "false" }] \
  $moved $after_hook [inside $stranded $b] [expr { $legal ? "true" : "false" }] \
  [expr { $legal ? "" : [string map {\" '} [lindex [split $msg \n] 0]] }]]
close $f
