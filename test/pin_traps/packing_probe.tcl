# The macro placer on one floorplan with each core shape in SHAPES, a list
# of <name> <width um> <height um>: the rows are remade for a core of that
# size at the die's lower left corner (core margin 2.16 um), every block
# unplaced, and rtl_macro_placer run as the flow runs it. A shape it
# refuses is a result here, not a failed build: the stage it would stop
# is the floorplan, which a test cannot take as an input. Per shape: did
# the placer return, its first error line, and how many blocks it left
# inside the core. The floorplan's tap cells are removed first.
source $::env(SCRIPTS_DIR)/load.tcl
load_design 2_floorplan.odb 2_floorplan.sdc
set block [ord::get_db_block]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set site [[lindex [$block getRows] 0] getSite]
# the floorplan stage's tap cells sit on the old rows, fixed, and the
# macro placer refuses fixed cells in its area (MPL-0050): out with them
foreach inst [$block getInsts] {
  if { ![[$inst getMaster] isBlock] && [$inst isFixed] } { odb::dbInst_destroy $inst }
}
set results {}
foreach {shape w h} $::env(SHAPES) {
  make_rows -core_area [list 2.16 2.16 [expr { 2.16 + $w }] [expr { 2.16 + $h }]] -site [$site getName]
  set macros {}
  foreach inst [$block getInsts] {
    if { [[$inst getMaster] isBlock] } {
      $inst setPlacementStatus NONE
      lappend macros $inst
    }
  }
  set ok [expr { ![catch {
    rtl_macro_placer -min_channel_size $::env(PACKING_CHANNEL_UM) -target_util $::env(PLACE_DENSITY)
  } err] }]
  set inside 0
  set core [$block getCoreArea]
  foreach inst $macros {
    set b [$inst getBBox]
    if { [$inst isPlaced] && [$b xMin] >= [$core xMin] && [$b yMin] >= [$core yMin] \
      && [$b xMax] <= [$core xMax] && [$b yMax] <= [$core yMax] } {
      incr inside
    }
  }
  set msg [expr { $ok ? "" : [lindex [split $err "\n"] 0] }]
  regsub -all {"} $msg {'} msg
  lappend results "    \"$shape\": {\"width_um\": $w, \"height_um\": $h, \"placed\": $ok, \"inside\": $inside, \"macros\": [llength $macros], \"error\": \"$msg\"}"
}
set fp [open $::env(OUTPUT_JSON) w]
puts $fp "{\n  \"shapes\": {\n[join $results ",\n"]\n  }\n}"
close $fp
