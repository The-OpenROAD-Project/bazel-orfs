# The toy's four blocks where test/planned_parent's plan puts them, R0,
# FIRM, and the plan's soft blockage over each row of blocks
# (test/planned_parent/plan/place_macros.tcl says why). The plan's
# register files are not macros here: the toy synthesises them as flops.
set block [ord::get_db_block]
foreach {master x y} {
  BlockB 41.040 41.040
  BlockD 164.160 41.040
  BlockA 41.040 246.240
  BlockC 164.160 246.240
} {
  set insts {}
  foreach inst [$block getInsts] {
    if { [[$inst getMaster] getName] eq $master } { lappend insts $inst }
  }
  if { [llength $insts] != 1 } {
    utl::error FLW 1 "power_shards: $master has [llength $insts] instances, the plan places one"
  }
  place_macro -macro_name [[lindex $insts 0] getName] -location [list $x $y] -orientation R0 -exact
  [lindex $insts 0] setPlacementStatus FIRM
}
set dbu [[ord::get_db_tech] getDbUnitsPerMicron]
set core [$block getCoreArea]
foreach {lo hi} {
  41.040 123.120
  246.240 328.320
} {
  set bl [odb::dbBlockage_create $block [$core xMin] [expr { int($lo * $dbu) }] [$core xMax] [expr { int($hi * $dbu) }]]
  $bl setSoft
}
