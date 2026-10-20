# Writes a MACRO_PLACEMENT_TCL that puts back what a flow's floorplan
# decided about its macros: every macro where the build placed it, with
# its placement status, and every placement blockage, a macro's halo
# (a blockage tied to the macro) included. Run by export_design.py
# --snapshot-macro-placement, with openroad:
#
#   SNAPSHOT_ODB   the flow's 2_floorplan.odb
#   SNAPSHOT_OUT   the script to write
#   SNAPSHOT_FROM  what to name as the source in its header
#
# A macro left unplaced stops it here: there is nothing to snapshot.
# Prints the number of macros; with none, it writes nothing.

set db [odb::dbDatabase_create]
odb::read_db $db $::env(SNAPSHOT_ODB)
set block [[$db getChip] getBlock]
set dbu [$block getDbUnitsPerMicron]

set macros {}
foreach inst [$block getInsts] {
  if { ![$inst isBlock] } {
    continue
  }
  set status [$inst getPlacementStatus]
  if { ![$inst isPlaced] } {
    error "snapshot_macros.tcl: macro [$inst getName] is $status in\
      $::env(SNAPSHOT_ODB): nothing to snapshot"
  }
  set loc [$inst getLocation]
  lappend macros [format "snapshot_macro {%s} %s %s %s %s" [$inst getName] \
    [expr { double([lindex $loc 0]) / $dbu }] \
    [expr { double([lindex $loc 1]) / $dbu }] \
    [$inst getOrient] $status]
}
puts "snapshot_macros.tcl: macros [llength $macros]"
if { [llength $macros] == 0 } {
  exit
}

set blockages {}
foreach b [$block getBlockages] {
  set i [$b getInstance]
  set r [$b getBBox]
  lappend blockages [list [expr { $i == "NULL" ? "-" : "{[$i getName]}" }] \
    [$r xMin] [$r yMin] [$r xMax] [$r yMax] [$b isSoft] [$b getMaxDensity]]
}

set lines [list \
  "# Macro placement snapshot of $::env(SNAPSHOT_FROM)'s floorplan." \
  "# Written by `bazelisk run //:export -- --snapshot-macro-placement`" \
  "# (bazel-orfs tools/ramp/snapshot_macros.tcl): every macro where the" \
  "# build put it, and the placement blockages in database units, a" \
  "# macro's halo tied to its macro. ORFS sources it as" \
  "# MACRO_PLACEMENT_TCL; it decides nothing." \
  "proc snapshot_inst \{ name \} \{" \
  "  set inst \[\[ord::get_db_block\] findInst \$name\]" \
  "  if \{ \$inst == \"NULL\" \} \{" \
  "    error \"macro placement snapshot: no instance \$name in this netlist\"" \
  "  \}" \
  "  return \$inst" \
  "\}" \
  "proc snapshot_macro \{ name x y orient status \} \{" \
  "  set inst \[snapshot_inst \$name\]" \
  "  place_macro -macro_name \$name -location \[list \$x \$y\] -orientation \$orient -exact" \
  "  \$inst setPlacementStatus \$status" \
  "\}"]
set lines [concat $lines $macros]
if { [llength $blockages] > 0 } {
  lappend lines \
    "set block \[ord::get_db_block\]" \
    "foreach \{inst x1 y1 x2 y2 soft max_density\} \{"
  foreach b $blockages {
    lappend lines "  [join $b]"
  }
  lappend lines \
    "\} \{" \
    "  if \{ \$inst eq \"-\" \} \{" \
    "    set b \[odb::dbBlockage_create \$block \$x1 \$y1 \$x2 \$y2\]" \
    "  \} else \{" \
    "    set b \[odb::dbBlockage_create \$block \$x1 \$y1 \$x2 \$y2 \[snapshot_inst \$inst\]\]" \
    "  \}" \
    "  if \{ \$soft \} \{" \
    "    \$b setSoft" \
    "  \}" \
    "  \$b setMaxDensity \$max_density" \
    "\}"
}
set f [open $::env(SNAPSHOT_OUT) w]
puts $f [join $lines "\n"]
close $f
puts "snapshot_macros.tcl: blockages [llength $blockages] into $::env(SNAPSHOT_OUT)"
