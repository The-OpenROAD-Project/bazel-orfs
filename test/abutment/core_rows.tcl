# A top level of macros with a strip of rows of its own: the core
# becomes the rows' bounding box. The floorplan's core is the die, as
# every macro must fit in it (IFP-0002) and global placement takes every
# macro's height against it (GPL-0119); tapcell's cut_rows has since
# removed the rows under the macros. Detailed placement counts the
# macros inside the core as used, the parent's box over its tiles twice
# (DPL-0038), so from detailed placement on, the clock tree's buffers
# included, the core holds none of them. Sourced before detailed
# placement, after global placement has run.
set block [ord::get_db_block]
set rows [$block getRows]
if { [llength $rows] == 0 } { error "core_rows.tcl: no rows left" }
set b [[lindex $rows 0] getBBox]
lassign [list [$b xMin] [$b yMin] [$b xMax] [$b yMax]] x0 y0 x1 y1
foreach row $rows {
  set b [$row getBBox]
  set x0 [expr { min($x0, [$b xMin]) }]
  set y0 [expr { min($y0, [$b yMin]) }]
  set x1 [expr { max($x1, [$b xMax]) }]
  set y1 [expr { max($y1, [$b yMax]) }]
}
$block setCoreArea [odb::new_Rect $x0 $y0 $x1 $y1]
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
puts [format "core_rows.tcl: the core is %d rows, %.3f %.3f %.3f %.3f um" [llength $rows] \
  [expr { $x0 / double($dbu) }] [expr { $y0 / double($dbu) }] \
  [expr { $x1 / double($dbu) }] [expr { $y1 / double($dbu) }]]
